import sys
import os
import threading
import http.server
os.environ["QT_LOGGING_RULES"] = "qt.qpa.fonts.warning=false"

if sys.platform == "win32":
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("casualheroes.questlog.mortalitytracker")

import core.crash_logger as crash_logger
crash_logger.setup()
log = crash_logger.get_logger("questlog.main")

from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QIcon

from core.paths import assets as _assets_path, overlay as _overlay_path
from core.run import load_run_meta, get_run_dir, save_active_slug
from core.session import Session
from core.deaths import DeathTracker
from core.detection import Detector
from core.bosses import BossTracker
from core.state_writer import write_state
from games.registry import get_game
from gui.run_selector import RunSelectorWidget
from gui.boss_tracker import BossTrackerWindow

TICK_MS      = 1000
OVERLAY_PORT = 8765


def _start_overlay_server():
    overlay_dir = _overlay_path()

    class _Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=overlay_dir, **kwargs)
        def log_message(self, *args):
            pass

    try:
        httpd = http.server.HTTPServer(("localhost", OVERLAY_PORT), _Handler)
        log.info("Overlay server: http://localhost:%d/index.html", OVERLAY_PORT)
        httpd.serve_forever()
    except OSError:
        log.warning("Overlay port %d already in use — skipping.", OVERLAY_PORT)


class SelectorWindow(QMainWindow):
    def __init__(self, app_controller):
        super().__init__()
        self._app = app_controller
        self.setWindowTitle("QuestLog Mortality Tracker")
        self.setMinimumSize(600, 720)
        self._widget = RunSelectorWidget()
        self._widget.run_selected.connect(self._app._launch_run)
        self._widget.run_deleted.connect(self._app._on_run_deleted)
        self.setCentralWidget(self._widget)

    def closeEvent(self, event):
        self._app._shutdown()
        event.accept()


class App:
    def __init__(self):
        self._selector_win = SelectorWindow(self)
        self._tracker      = None
        self._detector     = None
        self._session      = None
        self._deaths       = None
        self._bosses       = None
        self._run_dir      = None
        self._rage_label   = "Rage Index"
        self._api          = None   # QuestLogClient when logged in
        self._timer        = QTimer()
        self._timer.timeout.connect(self._tick)

    def start(self):
        self._selector_win.show()

    # ── Run lifecycle ─────────────────────────────────────────────────────────

    def _launch_run(self, slug):
        log.info("Launching run: %s", slug)
        self._stop_active()

        try:
            meta      = load_run_meta(slug)
            game_id   = meta["game_id"]
            mode_id   = meta["mode_id"]
            run_dir   = get_run_dir(slug)
            game_meta = get_game(game_id)
        except Exception:
            log.exception("Failed to load run metadata for '%s'", slug)
            return

        save_active_slug(slug)
        self._run_dir    = run_dir
        self._rage_label = game_meta.get("rage_label", "Rage Index")

        self._session = Session(process_name=game_meta["process"], run_dir=run_dir)
        self._deaths  = DeathTracker(self._session)
        self._bosses  = BossTracker(game_id=game_id, mode_id=mode_id, run_dir=run_dir)

        # ── Event callbacks ───────────────────────────────────────────────────
        def on_death():
            self._deaths.record_death()
            s, d = self._session, self._deaths
            pct, state, _ = d.rage_state()
            log.info("DEATH  session=%d  total=%d  rage=%d%%  %s",
                     s.session_deaths, s.total_deaths, pct, state)
            if self._api:
                self._api.post_death()

        def on_subtract():
            self._deaths.subtract_death()
            log.info("SUBTRACT DEATH  session=%d  total=%d",
                     self._session.session_deaths, self._session.total_deaths)
            if self._api:
                self._api.post_subtract()

        def on_reset():
            self._session.reset_total_deaths()
            self._deaths.reset()
            log.info("RESET ALL DEATHS")
            if self._api:
                self._api.post_reset()

        def on_kill(tier=None):
            from games.registry import ENEMY
            self._deaths.record_kill(tier=tier or ENEMY)

        # ── Pull saved hotkeys from settings ──────────────────────────────────
        from gui.boss_tracker import _load_settings
        saved = _load_settings()
        hotkeys = {
            "death":    saved.get("hotkey_death",    "f9"),
            "subtract": saved.get("hotkey_subtract", "f10"),
            "reset":    saved.get("hotkey_reset",    "f8"),
        }

        self._detector = Detector(
            self._deaths,
            on_death=on_death,
            on_subtract=on_subtract,
            on_reset=on_reset,
            hotkeys=hotkeys,
        )
        self._detector.start()

        log.info("=== Mortality Tracker — %s  [%s / %s] ===", meta["name"], game_id, mode_id)

        # ── Tracker window ────────────────────────────────────────────────────
        tracker = self._tracker
        self._tracker = None
        if tracker:
            tracker.close()
            tracker.deleteLater()

        self._tracker = BossTrackerWindow(
            self._bosses,
            run_meta=meta,
            session=self._session,
            deaths=self._deaths,
            on_kill=on_kill,
            rage_label=self._rage_label,
            api=self._api,
        )
        self._tracker.switch_run.connect(self._go_to_selector)
        self._tracker.settings_tab.hotkeys_changed.connect(self._detector.update_hotkeys)
        self._tracker.settings_tab.login_requested.connect(self._do_login)
        self._tracker.settings_tab.logout_requested.connect(self._do_logout)
        self._tracker.settings_tab.login_succeeded.connect(self._on_login_succeeded)
        self._tracker.show()
        self._selector_win.hide()

        self._timer.start(TICK_MS)

    def _on_run_deleted(self, slug):
        if self._run_dir and slug in self._run_dir.replace("\\", "/"):
            self._stop_active()
            self._run_dir    = None
            self._rage_label = "Rage Index"
            self._session    = None
            self._deaths     = None
            self._bosses     = None
            tracker = self._tracker
            self._tracker = None
            if tracker:
                tracker.close()
                tracker.deleteLater()
            self._selector_win._widget._populate_runs()
            self._selector_win.show()

    def _go_to_selector(self):
        self._stop_active()
        tracker = self._tracker
        self._tracker = None
        if tracker:
            tracker.close()
            tracker.deleteLater()
        self._selector_win._widget._populate_runs()
        self._selector_win.show()

    def _stop_active(self):
        self._timer.stop()
        if self._detector:
            self._detector.stop()
            self._detector = None
        if self._session:
            try:
                self._session.save()
            except Exception:
                log.exception("Failed to save session")
        if self._bosses:
            try:
                self._bosses.save()
            except Exception:
                log.exception("Failed to save bosses")

    # ── Tick ─────────────────────────────────────────────────────────────────

    def _tick(self):
        if not (self._session and self._deaths and self._bosses):
            return
        try:
            self._session.poll()
            self._deaths.update_rage_decay()
            write_state(self._session, self._deaths, self._bosses,
                        run_dir=self._run_dir, rage_label=self._rage_label)
            if self._tracker:
                self._tracker.refresh(
                    self._bosses.export(),
                    session=self._session,
                    deaths=self._deaths,
                )
        except Exception:
            log.exception("Error in tick loop")

    # ── Login / logout ────────────────────────────────────────────────────────

    def _do_login(self):
        from core.api_client import QuestLogClient
        log.info("Login requested — opening browser")

        def on_success(api_key, username, runs):
            if self._tracker:
                self._tracker.settings_tab.login_succeeded.emit(api_key, username, runs)

        def on_error(msg):
            if self._tracker:
                self._tracker.settings_tab.login_failed.emit(msg)

        threading.Thread(
            target=QuestLogClient.login,
            args=(on_success, on_error),
            daemon=True,
        ).start()

    def _on_login_succeeded(self, api_key, username, runs):
        from core.api_client import QuestLogClient

        # Match the active run to the currently open local run by game/mode
        token = ""
        if runs and self._session:
            meta = load_run_meta(self._run_dir.split("\\")[-1]) if self._run_dir else {}
            game_id = meta.get("game_id", "")
            mode_id = meta.get("mode_id", "")
            for r in runs:
                rg = r.get("game", "")
                rm = r.get("game_mode", "")
                # match elden_ring + vanilla/err
                if game_id in rg or rg in game_id:
                    token = r["token"]
                    # Sync defeated bosses from server state
                    if self._bosses and r.get("defeated_bosses"):
                        for key in r["defeated_bosses"]:
                            self._bosses.mark_defeated(key)
                    break
            if not token and runs:
                token = runs[0]["token"]

        self._api = QuestLogClient(api_key, token)
        if self._tracker:
            self._tracker._api = self._api
            # Propagate api into all open boss tabs
            for tab in self._tracker._boss_tabs.values():
                tab._api = self._api
        log.info("Logged in as %s (token=%s) — cloud sync active", username, token[:8] if token else "none")

    def _do_logout(self):
        self._api = None
        if self._tracker:
            self._tracker._api = None
        log.info("Logged out — running offline")

    # ── Shutdown ──────────────────────────────────────────────────────────────

    def _shutdown(self):
        log.info("Shutting down.")
        self._stop_active()
        tracker = self._tracker
        self._tracker = None
        if tracker:
            tracker.close()
        QApplication.quit()


def main():
    threading.Thread(target=_start_overlay_server, daemon=True).start()

    try:
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)
        app.setWindowIcon(QIcon(_assets_path("QL1.ico")))
        controller = App()
        controller.start()
        sys.exit(app.exec())
    except Exception:
        log.exception("Fatal error in main()")
        raise


if __name__ == "__main__":
    main()
