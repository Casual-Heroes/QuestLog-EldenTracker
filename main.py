import sys
import os
import threading
import http.server
os.environ["QT_LOGGING_RULES"] = "qt.qpa.fonts.warning=false"

if sys.platform == "win32":
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("casualheroes.eldentracker")

import core.crash_logger as crash_logger
crash_logger.setup()
log = crash_logger.get_logger("questlog.main")

from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6.QtCore import QTimer, QObject, pyqtSignal
from PyQt6.QtGui import QIcon

from core.paths import assets as _assets_path, overlay as _overlay_path
_ICO_CH = _assets_path("CH.ico")
from core.run import load_run_meta, get_run_dir, save_active_slug
from core.session import Session
from core.deaths import DeathTracker
from core.detection import Detector
from core.bosses import BossTracker
from core.state_writer import write_state
from games.registry import get_game
from gui.run_selector import RunSelectorWidget
from gui.boss_tracker import BossTrackerWindow
from gui.build_planner import BuildPlannerWidget
from gui.tournaments import TournamentWidget

TICK_MS      = 1000
OVERLAY_PORT = 8765


class _ServerRunsReady(QObject):
    ready = pyqtSignal(list, list)  # active_runs, run_history

class _LoginReady(QObject):
    success = pyqtSignal(str, str, dict)  # api_key, username, profile
    error   = pyqtSignal(str)

class _ServerSyncReady(QObject):
    synced = pyqtSignal(dict)  # deaths, rage_pct, rage_name, reset

class _RageReady(QObject):
    updated = pyqtSignal(float, str)  # rage_pct, rage_name

class _CloudBuildsReady(QObject):
    ready = pyqtSignal(list)  # list of build dicts from profile API

class _BuildPollReady(QObject):
    updated = pyqtSignal(list)  # flat sorted build list from poller

class _RunPollReady(QObject):
    updated = pyqtSignal(list, list)  # active_runs, run_history


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


def _clamped_geo_from(geo, dst_win):
    """Return a QRect based on geo, clamped to dst_win's minimum size."""
    from PyQt6.QtCore import QRect
    minw = dst_win.minimumWidth()
    minh = dst_win.minimumHeight()
    return QRect(geo.x(), geo.y(), max(geo.width(), minw), max(geo.height(), minh))


class SelectorWindow(QMainWindow):
    def __init__(self, app_controller):
        super().__init__()
        self._app = app_controller
        self.setWindowTitle("EldenTracker — Powered by QuestLog")
        self.setWindowIcon(QIcon(_ICO_CH))
        self.setMinimumSize(1280, 720)
        self.setStyleSheet("QMainWindow { background: #09090f; }")
        from PyQt6.QtGui import QPalette, QColor
        _mw_pal = self.palette()
        _mw_pal.setColor(QPalette.ColorRole.Window, QColor("#09090f"))
        self.setPalette(_mw_pal)

        from PyQt6.QtWidgets import QTabWidget
        from PyQt6.QtGui import QFont

        tabs = QTabWidget()
        tabs.setStyleSheet("""
            QTabWidget { background: #09090f; }
            QTabWidget::pane { border: none; background: #09090f; }
            QTabBar { background: #0f1018; border-bottom: 1px solid #1e1f2e; }
            QTabBar::tab {
                background: transparent; color: #6b7280;
                border: none; border-bottom: 2px solid transparent;
                padding: 10px 28px; font-size: 11px; font-weight: 600;
                letter-spacing: 1.5px;
            }
            QTabBar::tab:selected { color: #c9a84c; border-bottom: 2px solid #c9a84c; }
            QTabBar::tab:hover:!selected { color: #f1f0f5; }
        """)
        tabs.setFont(QFont("Segoe UI", 10))
        from PyQt6.QtGui import QPalette, QColor
        _pal = tabs.palette()
        _pal.setColor(QPalette.ColorRole.Window, QColor("#09090f"))
        _pal.setColor(QPalette.ColorRole.Base, QColor("#09090f"))
        tabs.setPalette(_pal)
        tabs.setAutoFillBackground(True)

        # Runs tab
        self._widget = RunSelectorWidget()
        self._widget.run_selected.connect(self._app._launch_run)
        self._widget.run_deleted.connect(self._app._on_run_deleted)
        tabs.addTab(self._widget, "RUNS")

        # Builds tab
        self._build_planner = BuildPlannerWidget()
        self._build_planner.start_run_requested.connect(self._app._start_run_from_build)
        tabs.addTab(self._build_planner, "BUILDS")

        # Compete tab
        self._tournament_widget = TournamentWidget()
        tabs.addTab(self._tournament_widget, "COMPETE")

        self.setCentralWidget(tabs)
        self._tabs = tabs

    def closeEvent(self, event):
        self._app._shutdown()
        event.accept()


class App:
    def __init__(self):
        self._selector_win = SelectorWindow(self)
        self._selector_win._widget.login_requested.connect(self._do_login)
        self._selector_win._widget.server_run_connect.connect(self._on_server_run_connect)
        self._selector_win._widget.refresh_requested.connect(self._refresh_server_runs)
        self._selector_win._widget.settings_requested.connect(self._open_settings)
        self._build_planner = self._selector_win._build_planner
        self._build_planner.cloud_build_changed.connect(self._on_cloud_build_changed)
        self._tracker      = None
        self._tracker_was_maximized = False   # captured at show time, not close time
        self._tracker_geo  = None             # captured at show time for restore
        self._detector     = None
        self._session      = None
        self._deaths       = None
        self._bosses       = None
        self._run_dir      = None
        self._rage_label   = "Rage Index"
        self._api          = None   # QuestLogClient when logged in
        self._ql_sync      = None   # QuestLogSync when a run is connected
        self._local_run    = None   # LocalRunData for non-synced runs
        self._local_life_start = None  # timestamp of current life start (local runs)
        self._prev_session_deaths = 0  # for new-session detection
        self._build_poller = None   # BuildSyncPoller — only when logged in
        self._timer        = QTimer()
        self._timer.timeout.connect(self._tick)

        # Bridge for server-side sync (web reset, death undo, etc.) → main thread
        self._sync_bridge = _ServerSyncReady()
        self._sync_bridge.synced.connect(self._apply_server_sync)

        # Bridge for rage updates after boss kill → main thread
        self._rage_bridge = _RageReady()
        self._rage_bridge.updated.connect(self._apply_rage_update)

        # Bridge for cloud builds → build planner main thread
        self._cloud_builds_bridge = _CloudBuildsReady()
        self._cloud_builds_bridge.ready.connect(self._build_planner.receive_cloud_builds)

        # Bridge for build poller updates → main thread
        self._build_poll_bridge = _BuildPollReady()
        self._build_poll_bridge.updated.connect(self._build_planner.receive_cloud_builds)

        # Bridge for run poller updates → main thread
        self._run_poll_bridge = _RunPollReady()
        self._run_poll_bridge.updated.connect(self._selector_win._widget.set_server_runs)

    def start(self):
        self._selector_win.show()
        self._restore_login()

    # ── Run lifecycle ─────────────────────────────────────────────────────────

    def _launch_run(self, slug):
        log.info("Launching run: %s", slug)
        self._stop_active()

        try:
            _MODE_MAP = {"err": "reforged", "vanilla": "vanilla", "reforged": "reforged"}
            meta      = load_run_meta(slug)
            game_id   = meta["game_id"]
            mode_id   = _MODE_MAP.get(meta["mode_id"], meta["mode_id"])
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

        # ── Start QuestLog sync only if this run has a matching server token ────
        if self._ql_sync:
            self._ql_sync.stop()
        self._ql_sync  = None
        self._local_run = None
        run_token = meta.get("questlog_token", "")
        if run_token and run_token != "__local__" and self._api and self._api._api_key:
            from core.questlog_sync import QuestLogSync
            self._ql_sync = QuestLogSync(
                run_token, self._api._api_key,
                on_server_sync=lambda d: self._sync_bridge.synced.emit(d),
                game_id=meta.get("game_id"),
            )
            self._ql_sync.start()
            log.info("QuestLog sync started token=%s", run_token[:12])
        else:
            # Local run — set up local items + death log
            import time as _time
            from core.local_run_data import LocalRunData
            self._local_run = LocalRunData(run_dir)
            self._local_life_start = _time.time()
            build_path = meta.get("build_path", "")
            if build_path and not self._local_run._items:
                from core.run import _safe_build_path
                safe_bp = _safe_build_path(build_path)
                if safe_bp:
                    import json as _json
                    try:
                        with open(safe_bp) as _f:
                            _build = _json.load(_f)
                        self._local_run.seed_from_build(_build)
                    except Exception:
                        log.warning("Could not load build for item seeding: %r", build_path)
                else:
                    log.warning("build_path outside allowed dir — skipping seed: %r", build_path)

        # ── Event callbacks ───────────────────────────────────────────────────
        def on_death():
            self._deaths.record_death()
            s, d = self._session, self._deaths
            pct, state, _ = d.rage_state()
            boss = self._ql_sync.get_current_boss() if self._ql_sync else ""
            log.info("DEATH  session=%d  total=%d  rage=%d%%  %s  boss=%r",
                     s.session_deaths, s.total_deaths, pct, state, boss)
            if self._ql_sync:
                ses_d = s.session_deaths
                tot_d = s.total_deaths
                def _on_death_resp(resp):
                    if self._tracker:
                        life_sec = resp.get("life_duration", 0)
                        self._tracker.death_log_tab.append_death(boss, life_sec, ses_d, tot_d)
                self._ql_sync.on_death(boss, on_death_response=_on_death_resp)
            elif self._local_run:
                import time as _time
                now = _time.time()
                life_sec = int(now - self._local_life_start) if self._local_life_start else 0
                self._local_life_start = now   # reset life clock for next life
                self._local_run.append_death(boss, life_sec, s.session_deaths, s.total_deaths)
                if self._tracker:
                    self._tracker.death_log_tab.append_death(
                        boss, life_sec, s.session_deaths, s.total_deaths)

        def on_subtract():
            self._deaths.subtract_death()
            log.info("SUBTRACT DEATH  session=%d  total=%d",
                     self._session.session_deaths, self._session.total_deaths)
            if self._ql_sync:
                self._ql_sync.on_subtract()
            elif self._local_run:
                self._local_run.undo_last_death()
                if self._tracker:
                    # Reload from disk so UI matches persisted state
                    recent = self._local_run.get_recent_deaths()
                    s2 = self._session
                    self._tracker.death_log_tab.load_from_status(
                        recent, s2.session_deaths, s2.total_deaths)

        def on_reset():
            self._session.reset_total_deaths()
            self._deaths.reset()
            log.info("RESET ALL DEATHS")
            if self._ql_sync:
                self._ql_sync.on_reset()
            elif self._local_run:
                import time as _time
                self._local_run._deaths = []
                self._local_run._save_deaths()
                self._local_life_start = _time.time()
                if self._tracker:
                    self._tracker.death_log_tab.load_from_status([], 0, 0)

        def on_kill(tier=None):
            from games.registry import ENEMY
            self._deaths.record_kill(tier=tier or ENEMY)

        def on_boss_mark(boss_key):
            if not self._ql_sync:
                return
            rage_bridge = self._rage_bridge
            ql = self._ql_sync
            def _mark():
                result = ql.mark_boss(boss_key)
                if result:
                    rage_bridge.updated.emit(
                        float(result.get("rage_pct", 0)),
                        result.get("rage_name", "Maiden's Grace"),
                    )
            threading.Thread(target=_mark, daemon=True).start()

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

        log.info("=== Elden Ring Tracker — %s  [%s / %s] ===", meta["name"], game_id, mode_id)

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
            api=self._ql_sync or self._api,
            on_boss_mark=on_boss_mark if self._ql_sync else None,
            ql_sync=self._ql_sync,
        )
        if self._local_run:
            self._tracker.items_tab.set_local_run(self._local_run)
            self._tracker.death_log_tab.set_active(True)
            # Pre-populate items if any exist
            items, collected, total = self._local_run.get_items()
            if items:
                self._tracker.items_tab.refresh(items, collected, total)

        self._tracker.switch_run.connect(self._go_to_selector)
        self._tracker.settings_tab.hotkeys_changed.connect(self._detector.update_hotkeys)
        self._tracker.settings_tab.login_requested.connect(self._do_login)
        self._tracker.settings_tab.logout_requested.connect(self._do_logout)
        self._tracker.settings_tab.login_succeeded.connect(self._on_login_succeeded)
        self._tracker.settings_tab.reset_stats.connect(self._on_reset_stats)
        # Hide selector first to avoid ghost flash, then show tracker in its place
        sel_was_max = self._selector_win.isMaximized()
        sel_geo     = self._selector_win.geometry()
        self._selector_win.hide()
        if sel_was_max:
            self._tracker_was_maximized = True
            self._tracker_geo = sel_geo   # keep screen position even when maximized
            self._tracker.showMaximized()
        else:
            self._tracker_was_maximized = False
            self._tracker_geo = sel_geo
            self._tracker.setGeometry(sel_geo)
            self._tracker.show()

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
            was_maximized = self._tracker_was_maximized
            saved_geo     = self._tracker_geo
            self._tracker_was_maximized = False
            self._tracker_geo = None
            if tracker:
                tracker.hide()
                tracker.deleteLater()
            if was_maximized:
                if saved_geo:
                    self._selector_win.setGeometry(
                        saved_geo.x(), saved_geo.y(),
                        max(saved_geo.width(), self._selector_win.minimumWidth()),
                        max(saved_geo.height(), self._selector_win.minimumHeight()),
                    )
                self._selector_win.showMaximized()
            else:
                if saved_geo:
                    self._selector_win.setGeometry(_clamped_geo_from(saved_geo, self._selector_win))
                self._selector_win.show()
            self._selector_win._widget._populate_runs()


    def _go_to_selector(self):
        self._stop_active()
        tracker = self._tracker
        self._tracker = None
        was_maximized = self._tracker_was_maximized
        saved_geo     = self._tracker_geo
        self._tracker_was_maximized = False
        self._tracker_geo = None
        if tracker:
            tracker.hide()
            tracker.deleteLater()
        if was_maximized:
            # Restore to the correct screen before maximizing — hidden windows lose
            # screen context and showMaximized() alone defaults to primary monitor.
            # Setting geometry to saved_geo first puts the window on the right screen
            # with a valid restore size, then showMaximized() maximizes it there.
            if saved_geo:
                self._selector_win.setGeometry(
                    saved_geo.x(), saved_geo.y(),
                    max(saved_geo.width(), self._selector_win.minimumWidth()),
                    max(saved_geo.height(), self._selector_win.minimumHeight()),
                )
            self._selector_win.showMaximized()
        else:
            if saved_geo:
                self._selector_win.setGeometry(_clamped_geo_from(saved_geo, self._selector_win))
            self._selector_win.show()
        self._selector_win._widget._populate_runs()

    def _stop_active(self):
        self._timer.stop()
        if self._ql_sync:
            try:
                self._ql_sync.end_run()
            except Exception:
                pass
            self._ql_sync = None
        self._local_run        = None
        self._local_life_start = None
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

    # ── Start run from build ─────────────────────────────────────────────────

    def _start_run_from_build(self, build: dict):
        """Called when user clicks START RUN in the build planner."""
        from core.run import create_run
        game = build.get("game", "elden_ring")
        name = build.get("name", "Unnamed Build").strip() or "Unnamed Build"
        if game == "err":
            game_id, mode_id = "elden_ring", "reforged"
        else:
            game_id, mode_id = "elden_ring", "vanilla"

        # Create the local run stub immediately — never block the UI thread.
        # If the user is logged in, create_session fires on a background thread
        # and patches the token into the run meta when it comes back.
        slug = create_run(name, game_id, mode_id)
        self._selector_win._widget._populate_runs()
        self._selector_win._tabs.setCurrentIndex(0)
        self._launch_run(slug)
        log.info("Started run '%s' from build '%s'", slug, name)

        if self._api and getattr(self._api, "_api_key", None):
            from core.local_run_data import items_from_build
            from core.run import get_run_dir
            import json as _json

            api       = self._api
            items     = items_from_build(build)
            run_meta_path = os.path.join(get_run_dir(slug), "meta.json")

            def _create_ql():
                try:
                    resp = api.create_session(
                        game=game, game_mode=mode_id,
                        build_name=name, items=items,
                    )
                    token = resp.get("token") if resp.get("ok") else None
                    if not token:
                        log.warning("create_session returned no token: %s", resp)
                        return
                    # Patch token into the run meta file on disk
                    try:
                        with open(run_meta_path) as f:
                            meta = _json.load(f)
                        meta["questlog_token"] = token
                        with open(run_meta_path, "w") as f:
                            _json.dump(meta, f, indent=2)
                        log.info("QL token patched into run '%s' token=%s", slug, token[:12])
                    except Exception as e:
                        log.warning("Could not patch QL token into meta: %s", e)
                except Exception as exc:
                    log.warning("create_session failed: %s", exc)

            threading.Thread(target=_create_ql, daemon=True).start()

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
                    ql_sync=self._ql_sync,
                    local_run=self._local_run,
                )
        except Exception:
            log.exception("Error in tick loop")

    # ── Login / logout ────────────────────────────────────────────────────────

    def _do_login(self):
        from core.api_client import QuestLogClient
        log.info("Login requested — opening browser")

        self._selector_win._widget.login_btn.setEnabled(False)
        self._selector_win._widget.login_btn.setText("Waiting for login...")

        # Must be created on main thread before the worker starts
        notifier = _LoginReady()
        notifier.success.connect(self._on_login_result)
        notifier.error.connect(self._on_login_error)

        def _worker():
            QuestLogClient.login(
                on_success=lambda key, user, prof: notifier.success.emit(key, user, prof),
                on_error=lambda msg: notifier.error.emit(msg),
            )

        threading.Thread(target=_worker, daemon=True).start()

    def _on_login_result(self, api_key, username, profile):
        """Runs on main thread via signal."""
        from core.api_client import QuestLogClient
        from gui.boss_tracker import _load_settings, _save_settings
        active_runs = profile.get("active_runs", [])
        run_history = profile.get("run_history", [])

        # Save credentials so session persists across restarts
        s = _load_settings()
        s["api_key"]  = api_key
        s["username"] = username
        _save_settings(s)

        self._api = QuestLogClient(api_key, s.get("session_token", ""))
        self._selector_win._widget.set_logged_in(username)
        self._selector_win._widget.set_server_runs(active_runs, run_history)
        self._build_planner.set_api_key(api_key)
        self._selector_win._tournament_widget.set_api_key(api_key)
        self._start_build_poller(api_key)

        if self._tracker:
            self._tracker.settings_tab.login_succeeded.emit(api_key, username, active_runs)
        else:
            self._on_login_succeeded(api_key, username, active_runs)

        log.info("Login OK — %r, active=%d history=%d", username, len(active_runs), len(run_history))

    def _on_login_error(self, msg):
        """Runs on main thread via signal."""
        self._selector_win._widget.set_logged_out()
        if self._tracker:
            self._tracker.settings_tab.login_failed.emit(msg)
        log.warning("Login failed: %s", msg)

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
            for tab in self._tracker._boss_tabs.values():
                tab._api = self._api
        self._selector_win._widget.set_logged_in(username)
        if token:
            from gui.boss_tracker import _load_settings, _save_settings
            s = _load_settings()
            s["session_token"] = token
            _save_settings(s)
        log.info("Logged in as %r (token=%s) — cloud sync active", username, token[:8] if token else "none")

    def _on_server_run_connect(self, server_run):
        """
        User clicked CONNECT on a QuestLog server run.
        Sets the API client to use that run's token, then launches a matching
        local run (creating a minimal stub if none exists locally).
        """
        from core.api_client import QuestLogClient
        from core.run import list_runs, create_run

        _MODE_MAP = {"err": "reforged", "vanilla": "vanilla", "reforged": "reforged"}

        token   = server_run.get("token", "")
        game    = server_run.get("game", "elden_ring")
        mode    = _MODE_MAP.get(server_run.get("game_mode", "vanilla"), "vanilla")
        name    = server_run.get("build_name") or server_run.get("name") or f"{game.replace('_', ' ').title()} — QuestLog"

        # Find existing local stub that was created for this exact server token,
        # or always create a fresh one — never reuse a different run's data.
        slug = None
        for meta in list_runs():
            if meta.get("questlog_token") == token:
                slug = meta["slug"]
                log.info("Reusing local stub '%s' for server run %s", slug, token[:8])
                break

        if slug is None:
            slug = create_run(name, game, mode, questlog_token=token)
            log.info("Created local stub run '%s' for server run %s", slug, token[:8])

        # Set API client using our stored api_key + the server run's token
        if self._api:
            api_key = self._api._api_key
        else:
            log.warning("CONNECT clicked but not logged in — skipping cloud sync")
            api_key = ""

        if api_key and token:
            self._api = QuestLogClient(api_key, token)
            # Persist token so next launch auto-reconnects
            from gui.boss_tracker import _load_settings, _save_settings
            s = _load_settings()
            s["session_token"] = token
            _save_settings(s)
            log.info("Connected to server run token=%s", token[:8])

        self._launch_run(slug)

    def _restore_login(self):
        """On startup: restore api_key + session_token from settings, auto-fetch runs."""
        from gui.boss_tracker import _load_settings
        from core.api_client import QuestLogClient
        saved    = _load_settings()
        api_key  = saved.get("api_key", "")
        username = saved.get("username", "")
        token    = saved.get("session_token", "")
        if not api_key or not username:
            return
        log.info("Auto-restoring session for %r (token=%s)", username, token[:8] if token else "none")
        self._api = QuestLogClient(api_key, token)
        self._selector_win._widget.set_logged_in(username)
        self._build_planner.set_api_key(api_key)
        self._selector_win._tournament_widget.set_api_key(api_key)
        self._start_build_poller(api_key)
        # Fetch runs immediately in background — no manual refresh needed
        self._refresh_server_runs(api_key)

    def _refresh_server_runs(self, api_key=None, username=None):
        """Fetch profile from server and update the selector's server runs section."""
        import requests
        from core.api_client import BASE_URL, REQUEST_TIMEOUT
        if api_key is None:
            if self._api:
                api_key = self._api._api_key
            else:
                from gui.boss_tracker import _load_settings
                api_key = _load_settings().get("api_key", "")
        if not api_key:
            return

        self._selector_win._widget.set_server_runs_loading()

        notifier = _ServerRunsReady()
        notifier.ready.connect(self._selector_win._widget.set_server_runs)

        cloud_builds_bridge = self._cloud_builds_bridge

        def _fetch():
            try:
                r = requests.get(
                    f"{BASE_URL}/api/soulslike/desktop/profile/",
                    headers={"X-Listener-Key": api_key},
                    timeout=REQUEST_TIMEOUT,
                )
                log.info("Profile API status=%d", r.status_code)
                profile = r.json() if r.ok else {}
            except Exception as e:
                log.warning("Refresh server runs failed: %s", e)
                profile = {}
            active_runs = profile.get("active_runs", [])
            run_history = profile.get("run_history", [])
            log.info("Server runs — active=%d history=%d", len(active_runs), len(run_history))
            notifier.ready.emit(active_runs, run_history)
            # Push builds to build planner
            builds = profile.get("builds", [])
            if builds:
                log.info("Cloud builds received: %d", len(builds))
                cloud_builds_bridge.ready.emit(builds)

        threading.Thread(target=_fetch, daemon=True).start()

    def _open_settings(self):
        if self._tracker:
            self._tracker.show()
            self._tracker.raise_()
            return
        # No active run — show standalone settings dialog
        from PyQt6.QtWidgets import QDialog, QVBoxLayout
        from gui.boss_tracker import SettingsTab, _load_settings, _save_settings, QSS
        dlg = QDialog(self._selector_win)
        dlg.setWindowTitle("Settings")
        dlg.setMinimumSize(480, 560)
        dlg.setStyleSheet(QSS)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(0, 0, 0, 0)
        saved = _load_settings()
        tab = SettingsTab(saved)
        tab.hotkeys_changed.connect(lambda hk: _save_settings({**_load_settings(), **hk}))
        tab.login_requested.connect(self._do_login)
        tab.logout_requested.connect(self._do_logout)
        layout.addWidget(tab)
        dlg.exec()

    def _on_reset_stats(self):
        """Reset all deaths + timers in app and on QuestLog."""
        if self._session:
            self._session.reset_total_deaths()
            self._session.reset_session_time()   # waits for EXE if game not running
        if self._deaths:
            self._deaths.reset()
        if self._ql_sync:
            self._ql_sync.on_reset()   # clears local timers + POSTs reset-deaths + heartbeat(zeros)
        # Update UI immediately — don't wait for next tick
        self._sync_bridge.synced.emit({
            "deaths":    0,
            "rage_pct":  0,
            "rage_name": "Maiden's Grace",
            "reset":     True,
        })
        log.info("Stats reset via settings")

    def _apply_server_sync(self, data):
        """Main-thread handler: mirror web-side state changes (reset, undo) into local trackers."""
        if not (self._session and self._deaths):
            return
        if data.get("reset"):
            self._session.reset_total_deaths()
            self._deaths.reset()
            self._prev_session_deaths = 0
            log.info("Reset synced from web")
        else:
            server_session_deaths = data.get("session_deaths", -1)

            # New sitting detected — server reset session after grace period
            if server_session_deaths == 0 and self._prev_session_deaths > 0:
                self._session.reset_session_time()
                self._session.session_deaths = 0
                self._deaths.on_new_session_detected()
                log.info("New session detected via server sync — timer and session deaths reset")

            if server_session_deaths >= 0:
                self._prev_session_deaths = server_session_deaths

            # Sync session deaths from server's session_deaths field
            # Use total deaths (deaths) only to update the total counter
            server_total   = data.get("deaths", 0)
            sess_deaths    = data.get("session_deaths", server_session_deaths)
            if sess_deaths >= 0:
                sess_diff = sess_deaths - self._session.session_deaths
                if sess_diff > 0:
                    for _ in range(sess_diff):
                        self._deaths.record_death()
                elif sess_diff < 0:
                    for _ in range(abs(sess_diff)):
                        self._deaths.subtract_death()
            # Sync total deaths directly without going through record_death loop
            if server_total >= 0:
                self._session.total_deaths = server_total
                self._session.save()
            log.info("Death count synced from web: session=%d total=%d",
                     self._session.session_deaths, self._session.total_deaths)

    def _apply_rage_update(self, rage_pct, rage_name):
        """Main-thread handler: apply rage values returned by server after boss kill."""
        if self._deaths:
            self._deaths._rage_pct = float(rage_pct)
            self._deaths._consecutive = int(rage_pct / 25)

    def _start_build_poller(self, api_key: str):
        if self._build_poller:
            self._build_poller.stop()
        from core.build_sync_poller import BuildSyncPoller
        build_bridge = self._build_poll_bridge
        run_bridge   = self._run_poll_bridge

        def _on_builds(builds, added, removed, updated):
            build_bridge.updated.emit(builds)

        def _on_runs(active_runs, run_history):
            run_bridge.updated.emit(active_runs, run_history)

        def _active_token():
            return self._ql_sync.token if self._ql_sync else None

        self._build_poller = BuildSyncPoller(
            api_key,
            on_builds_updated=_on_builds,
            on_runs_updated=_on_runs,
            active_token_fn=_active_token,
        )
        self._build_poller.start()

    def _on_cloud_build_changed(self):
        if self._build_poller:
            self._build_poller.force_refresh()

    def _do_logout(self):
        self._api = None
        if self._tracker:
            self._tracker._api = None
        if self._build_poller:
            self._build_poller.stop()
            self._build_poller = None
        log.info("Logged out — running offline")

    # ── Shutdown ──────────────────────────────────────────────────────────────

    def _shutdown(self):
        log.info("Shutting down.")
        self._stop_active()
        if self._build_poller:
            self._build_poller.stop()
            self._build_poller = None
        tracker = self._tracker
        self._tracker = None
        if tracker:
            tracker.close()
        QApplication.quit()


def _ensure_single_instance():
    """Return a mutex handle that keeps this process as the sole instance.
    Exits immediately if another instance is already running."""
    if sys.platform != "win32":
        return None
    import ctypes
    mutex = ctypes.windll.kernel32.CreateMutexW(None, True, "CasualHeroes_EldenTracker_Mutex")
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        # Bring existing window to front if possible, then exit
        import ctypes.wintypes
        hwnd = ctypes.windll.user32.FindWindowW(None, "EldenTracker — Powered by QuestLog")
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 9)   # SW_RESTORE
            ctypes.windll.user32.SetForegroundWindow(hwnd)
        sys.exit(0)
    return mutex   # keep reference alive for process lifetime


def main():
    _mutex = _ensure_single_instance()

    threading.Thread(target=_start_overlay_server, daemon=True).start()

    try:
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)
        app.setWindowIcon(QIcon(_ICO_CH))
        controller = App()
        controller.start()
        sys.exit(app.exec())
    except Exception:
        log.exception("Fatal error in main()")
        raise


if __name__ == "__main__":
    main()
