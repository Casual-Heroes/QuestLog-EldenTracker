import sys
import os
os.environ["QT_LOGGING_RULES"] = "qt.qpa.fonts.warning=false"

# Tell Windows this is its own app (not python.exe) so the taskbar shows our icon
if sys.platform == "win32":
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("casualheroes.questlog.mortalitytracker")

import core.crash_logger as crash_logger
crash_logger.setup()
log = crash_logger.get_logger("questlog.main")

from PyQt6.QtWidgets import QApplication, QMainWindow, QStackedWidget, QWidget
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QIcon

from core.run import load_run_meta, get_run_dir, save_active_slug, load_active_slug
from core.session import Session
from core.deaths import DeathTracker
from core.detection import Detector
from core.bosses import BossTracker
from core.state_writer import write_state
from games.registry import get_game
from gui.run_selector import RunSelectorWidget
from gui.boss_tracker import BossTrackerWindow

TICK_MS = 1000


class App(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("QuestLog Mortality Tracker")
        self.setMinimumSize(600, 720)

        self._stack    = QStackedWidget()
        self.setCentralWidget(self._stack)

        self._selector  = RunSelectorWidget()
        self._tracker   = None   # BossTrackerWindow — built when run is selected
        self._detector  = None
        self._session   = None
        self._deaths    = None
        self._bosses    = None
        self._run_dir    = None
        self._rage_label = "Rage Index"
        self._timer      = QTimer()
        self._timer.timeout.connect(self._tick)

        self._selector.run_selected.connect(self._launch_run)
        self._selector.run_deleted.connect(self._on_run_deleted)
        self._stack.addWidget(self._selector)
        self._stack.setCurrentWidget(self._selector)

        # Resume last active run automatically if it exists
        last = load_active_slug()
        if last:
            try:
                load_run_meta(last)   # verify it still exists
                self._launch_run(last)
                return
            except Exception:
                log.warning("Could not resume last run '%s' — starting fresh.", last)

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
        self._run_dir   = run_dir
        self._rage_label = game_meta.get("rage_label", "Rage Index")

        self._session = Session(process_name=game_meta["process"], run_dir=run_dir)
        self._deaths  = DeathTracker(self._session)
        self._bosses  = BossTracker(game_id=game_id, mode_id=mode_id, run_dir=run_dir)

        def on_death():
            self._deaths.record_death()
            s, d = self._session, self._deaths
            pct, state, _ = d.rage_state()
            log.info("DEATH  session=%d  total=%d  rage=%d%%  %s",
                     s.session_deaths, s.total_deaths, pct, state)

        def on_kill(tier=None):
            from games.registry import ENEMY
            self._deaths.record_kill(tier=tier or ENEMY)

        def on_reset():
            self._session.reset_total_deaths()
            self._deaths.reset()

        self._detector = Detector(
            self._deaths,
            on_death=on_death,
            on_kill=on_kill,
            on_grace=None,
            on_reset=on_reset,
        )
        self._detector.start()

        log.info("=== Mortality Tracker — %s  [%s / %s] ===", meta["name"], game_id, mode_id)
        log.info("Hotkeys: F9=Death  F10=Kill  F8=Hold 3s to reset")

        tracker_win = BossTrackerWindow(
            self._bosses,
            run_meta=meta,
            session=self._session,
            deaths=self._deaths,
            on_kill=on_kill,
            rage_label=self._rage_label,
        )
        tracker_win.switch_run.connect(self._go_to_selector)

        if self._tracker:
            self._stack.removeWidget(self._tracker)
            self._tracker.deleteLater()

        self._tracker = tracker_win
        self._stack.addWidget(self._tracker)
        self._stack.setCurrentWidget(self._tracker)
        self.setWindowTitle(f"QuestLog Mortality Tracker — {meta['name']}")

        self._timer.start(TICK_MS)

    def _on_run_deleted(self, slug):
        # If the deleted run is the active one, stop it cleanly before rmtree runs
        if self._run_dir and slug in self._run_dir.replace("\\", "/"):
            self._stop_active()
            # Null everything out so the tick loop can't write to the deleted path
            self._run_dir    = None
            self._rage_label = "Rage Index"
            self._session    = None
            self._deaths     = None
            self._bosses     = None
            if self._tracker:
                self._stack.removeWidget(self._tracker)
                self._tracker.deleteLater()
                self._tracker = None
            self._stack.setCurrentWidget(self._selector)
            self.setWindowTitle("QuestLog Mortality Tracker")

    def _go_to_selector(self):
        self._stop_active()
        self._selector._populate_runs()
        self._stack.setCurrentWidget(self._selector)
        self.setWindowTitle("QuestLog Mortality Tracker")

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

    def closeEvent(self, event):
        log.info("Shutting down.")
        self._stop_active()
        event.accept()


def main():
    try:
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(True)
        _icon_path = os.path.join(os.path.dirname(__file__), "assets", "QL1.ico")
        app.setWindowIcon(QIcon(_icon_path))
        win = App()
        win.show()
        sys.exit(app.exec())
    except Exception:
        log.exception("Fatal error in main()")
        raise


if __name__ == "__main__":
    main()
