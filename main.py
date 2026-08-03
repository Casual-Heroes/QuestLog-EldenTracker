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
from core.run import load_run_meta, get_run_dir, save_active_slug, update_run_meta
from core.session import Session
from core.deaths import DeathTracker
from core.detection import Detector
from core.bosses import BossTracker
from core.state_writer import write_state
from core.save_parser import SaveParseError
from core.catalog_sync import startup_sync
from games.registry import get_game
from gui.run_selector import RunSelectorWidget
from gui.boss_tracker import BossTrackerWindow

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
    updated = pyqtSignal(float, str, int)  # rage_pct, rage_name, hollow_streak

class _DeathHotkeyBridge(QObject):
    """
    F8/F9/F10 fire on the `keyboard` library's own listener thread, not
    Qt's main thread. on_death/on_subtract/on_reset touch QWidgets
    (self._tracker.death_log_tab, etc.) directly, so calling them straight
    from the hotkey callback hits the same "QObject::setParent: Cannot set
    parent, new parent is in a different thread" warning/crash risk that
    _FocusHotkeyBridge was added for -- route through signals so the real
    work runs on the main thread no matter which thread the hotkey fired on.
    """
    death_requested    = pyqtSignal()
    subtract_requested = pyqtSignal()
    reset_requested    = pyqtSignal()

class _FocusHotkeyBridge(QObject):
    """
    Boss hotkeys fire on the `keyboard` library's own listener thread, not Qt's
    main thread. open_focus_picker() creates/execs a QDialog and
    unfocus_current_boss()/defeat_focused_boss() touch existing widgets --
    all need to run on the main thread. Route through signals queued by Qt
    instead of calling the tracker directly from the hotkey callback.
    """
    focus_requested   = pyqtSignal()
    unfocus_requested = pyqtSignal()
    defeat_requested  = pyqtSignal()

class _RunPollReady(QObject):
    updated = pyqtSignal(list, list)  # active_runs, run_history

class _LeaderboardSubmitReady(QObject):
    """
    QuestLogClient.submit_to_leaderboard()'s on_done/on_error callbacks run
    on a background thread (see _fire() in core/api_client.py) -- route
    through signals so updating mortality_tab's Submit button state and
    showing a result dialog both happen on the main thread.
    """
    succeeded = pyqtSignal()
    failed    = pyqtSignal(str)   # error message


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


def _start_catalog_sync():
    try:
        result = startup_sync(logger=log)
        log.info(
            "Catalog sync: updated=%d unchanged=%d offline=%s update_required=%s",
            len(result.updated),
            len(result.unchanged),
            result.offline,
            result.app_update_required,
        )
        for warning in result.warnings:
            log.warning("Catalog sync: %s", warning)
    except Exception:
        log.exception("Catalog sync failed unexpectedly; continuing with bundled/cache data")


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
        self._save_watcher = None  # core.save_watcher.SaveWatcher, live save-file item tracking
        self._save_watcher_slot = 0  # character slot index to poll
        self._save_named_prev  = None  # previous poll's owned-item name set (for diffing)
        self._save_qty_prev    = None  # previous poll's stackable-item quantity dict (for diffing)
        self._save_auto_collect_submitted = set()  # item keys already submitted from save reconciliation this run
        self._reward_bosses_synced = set()  # boss keys already server-marked from save-owned rewards
        self._active_game_id = None  # game_id of the currently active run, for SaveWatcher setup
        self._active_mode_id = None  # normalized mode_id ("vanilla"/"reforged") of the active run
        self._active_slug    = None  # slug of the currently active run, for update_run_meta calls
        self._active_questlog_token = ""  # this run's server token, survives past _ql_sync's lifecycle
        self._run_ended     = False  # explicit End Run has been clicked (or restored from meta.json)
        self._run_submitted = False  # this run has been submitted to the leaderboard (one-shot)
        self._subtract_in_flight = False  # guards on_subtract() against double-fire (F10 + UI button racing)
        self._run_started_at   = None  # unix timestamp from server run's started_at field
        self._prev_session_deaths = 0  # for new-session detection
        self._timer        = QTimer()
        self._timer.timeout.connect(self._tick)

        # Bridge for server-side sync (web reset, death undo, etc.) → main thread
        self._sync_bridge = _ServerSyncReady()
        self._sync_bridge.synced.connect(self._apply_server_sync)

        # Bridge for rage updates after boss kill → main thread
        self._rage_bridge = _RageReady()
        self._rage_bridge.updated.connect(self._apply_rage_update)

        # Bridge for boss hotkeys (fire on keyboard lib's thread) → main thread
        self._focus_hotkey_bridge = _FocusHotkeyBridge()
        self._focus_hotkey_bridge.focus_requested.connect(self._open_focus_picker)
        self._focus_hotkey_bridge.unfocus_requested.connect(self._unfocus_current_boss)
        self._focus_hotkey_bridge.defeat_requested.connect(self._defeat_focused_boss)

        # Bridge for F8/F9/F10 hotkeys (fire on keyboard lib's thread) → main thread
        self._death_hotkey_bridge = _DeathHotkeyBridge()

        # Bridge for run poller updates → main thread
        self._run_poll_bridge = _RunPollReady()
        self._run_poll_bridge.updated.connect(self._selector_win._widget.set_server_runs)

        # Bridge for submit_to_leaderboard's response (fires on a bg thread) → main thread
        self._leaderboard_submit_bridge = _LeaderboardSubmitReady()
        self._leaderboard_submit_bridge.succeeded.connect(self._on_leaderboard_submit_succeeded)
        self._leaderboard_submit_bridge.failed.connect(self._on_leaderboard_submit_failed)

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

        self._active_game_id = game_id
        self._active_mode_id = mode_id
        self._active_slug    = slug
        self._run_ended     = bool(meta.get("ended", False))
        self._run_submitted = bool(meta.get("submitted", False))

        save_active_slug(slug)
        self._run_dir      = run_dir
        self._rage_label   = game_meta.get("rage_label", "Rage Index")
        self._run_started_at = meta.get("started_at")
        if not self._run_started_at:
            # Older/local-only runs never had started_at written at all
            # (create_run only sets it when explicitly passed in, e.g. from
            # a server-connected run) -- backfill it now so Run Duration
            # shows something instead of "--" forever, and persist it so
            # this only happens once per run.
            import time as _time
            self._run_started_at = int(_time.time())
            try:
                update_run_meta(slug, {"started_at": self._run_started_at})
            except Exception:
                log.exception("Failed to backfill started_at for run '%s'", slug)

        self._session = Session(process_name=game_meta["process"], run_dir=run_dir)
        self._deaths  = DeathTracker(self._session)
        self._bosses  = BossTracker(game_id=game_id, mode_id=mode_id, run_dir=run_dir)

        # ── Start QuestLog sync only if this run has a matching server token ────
        if self._ql_sync:
            self._ql_sync.stop()
        self._ql_sync  = None
        self._local_run = None
        run_token = meta.get("questlog_token", "")
        # Kept around after this run ends (unlike self._ql_sync, which stays
        # alive but is a different lifecycle concern) so Submit to
        # Leaderboard can still build its URL later -- see submit handler.
        self._active_questlog_token = run_token if run_token != "__local__" else ""
        if run_token and run_token != "__local__" and self._api and self._api._api_key:
            from core.questlog_sync import QuestLogSync
            self._ql_sync = QuestLogSync(
                run_token, self._api._api_key,
                on_server_sync=lambda d: self._sync_bridge.synced.emit(d),
                game_id=meta.get("game_id"),
                initial_deaths=self._session.total_deaths,
                initial_session_deaths=self._session.session_deaths,
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

        # ── Live save-file item tracking ─────────────────────────────────────
        # Vanilla/Reforged Elden Ring only (see core.save_watcher docstring
        # for why Convergence isn't wired up yet). Works the same whether
        # this run is cloud-synced or local -- both self._ql_sync and
        # self._local_run expose the same collect_item(name)/uncollect_item(name)
        # API the manual click path already uses, so the poller in _tick()
        # doesn't need to know or care which backend is active.
        self._save_watcher    = None
        self._save_named_prev = None
        self._save_qty_prev   = None
        self._save_auto_collect_submitted = set()
        if game_id == "elden_ring" and mode_id in ("vanilla", "reforged"):
            from gui.boss_tracker import _load_settings, _save_settings
            settings = _load_settings()
            tracker_settings = dict(settings)
            for key in ("save_file_path", "save_slot", "save_character_name"):
                if key in meta:
                    tracker_settings[key] = meta[key]
            save_path = tracker_settings.get("save_file_path", "")
            if not save_path:
                from core.save_paths import find_save_file_for_mode
                candidate = find_save_file_for_mode(mode_id)
                if candidate:
                    save_path = candidate["path"]
                    tracker_settings["save_file_path"] = save_path
                    settings["save_file_path"] = save_path
                    _save_settings(settings)
                    log.info("Auto-detected %s save file: %s", mode_id, save_path)
            if save_path and os.path.isfile(save_path):
                from core.save_watcher import SaveWatcher
                try:
                    self._save_watcher = SaveWatcher(save_path, mode=mode_id)
                    self._save_watcher_slot = self._resolve_save_slot(tracker_settings)
                    log.info("Live save tracking enabled: %s (mode=%s slot_index=%d game_slot=%d)",
                             save_path, mode_id, self._save_watcher_slot, self._save_watcher_slot + 1)
                except Exception:
                    log.exception("Failed to start SaveWatcher for %r", save_path)
                    self._save_watcher = None

        # ── Event callbacks ───────────────────────────────────────────────────
        def on_death():
            if self._run_ended:
                log.info("DEATH ignored -- run has ended")
                return
            boss = self._ql_sync.get_current_boss() if self._ql_sync else ""
            boss_key = self._ql_sync.get_current_boss_key() if self._ql_sync else ""
            if self._ql_sync:
                def _on_death_resp(resp):
                    if self._tracker:
                        life_sec = resp.get("life_duration", 0)
                        session_deaths = int(resp.get("session_deaths", self._session.session_deaths) or 0)
                        total_deaths = int(
                            resp.get("total_deaths", resp.get("deaths", self._session.total_deaths)) or 0
                        )
                        self._tracker.death_log_tab.append_death(
                            resp.get("boss") or boss,
                            life_sec,
                            session_deaths,
                            total_deaths,
                        )
                log.info("DEATH requested boss=%r boss_key=%r", boss, boss_key)
                self._ql_sync.on_death(boss, boss_key=boss_key, on_death_response=_on_death_resp)
            elif self._local_run:
                self._deaths.record_death()
                s, d = self._session, self._deaths
                pct, state, _ = d.rage_state()
                log.info("DEATH  session=%d  total=%d  rage=%d%%  %s  boss=%r  boss_key=%r",
                         s.session_deaths, s.total_deaths, pct, state, boss, boss_key)
                import time as _time
                now = _time.time()
                life_sec = int(now - self._local_life_start) if self._local_life_start else 0
                self._local_life_start = now   # reset life clock for next life
                self._local_run.append_death(boss, life_sec, s.session_deaths, s.total_deaths)
                if self._tracker:
                    self._tracker.death_log_tab.append_death(
                        boss, life_sec, s.session_deaths, s.total_deaths)

        def on_subtract():
            if self._run_ended:
                log.info("SUBTRACT DEATH ignored -- run has ended")
                return
            # Guard against double-fire: F10 hotkey and the UI Subtract
            # button both route here now, and could otherwise both land
            # within the same instant (e.g. hotkey + accidental click).
            # Web hit this exact bug -- see ER_SAVE_PARSING_RESEARCH.md's
            # app-sync doc, section 2 -- and fixed it with an in-flight
            # guard rather than blocking either input source outright.
            if self._subtract_in_flight:
                log.info("SUBTRACT DEATH ignored -- already in flight")
                return
            self._subtract_in_flight = True
            try:
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(750, lambda: setattr(self, "_subtract_in_flight", False))
            except Exception:
                self._subtract_in_flight = False

            if self._ql_sync:
                log.info("SUBTRACT DEATH requested")
                self._ql_sync.on_subtract()
            elif self._local_run:
                self._deaths.subtract_death()
                log.info("SUBTRACT DEATH  session=%d  total=%d",
                         self._session.session_deaths, self._session.total_deaths)
                self._local_run.undo_last_death()
                if self._tracker:
                    # Reload from disk so UI matches persisted state
                    recent = self._local_run.get_recent_deaths()
                    s2 = self._session
                    self._tracker.death_log_tab.load_from_status(
                        recent, s2.session_deaths, s2.total_deaths)

        def on_reset():
            if self._run_ended:
                log.info("RESET ALL DEATHS ignored -- run has ended")
                return
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
            if not self._ql_sync:
                self._deaths.record_kill(tier=tier or ENEMY)

        def on_focus_hotkey():
            # Fires on the `keyboard` lib's own thread -- emit a signal so
            # the actual dialog/widget work happens on the main Qt thread
            # (see _FocusHotkeyBridge docstring).
            self._focus_hotkey_bridge.focus_requested.emit()

        def on_unfocus_hotkey():
            self._focus_hotkey_bridge.unfocus_requested.emit()

        def on_defeat_hotkey():
            self._focus_hotkey_bridge.defeat_requested.emit()

        # F8/F9/F10 fire on the `keyboard` lib's own thread too (see
        # _DeathHotkeyBridge docstring) -- these are what get passed to
        # Detector, while on_death/on_subtract/on_reset themselves stay
        # connected directly to the UI buttons' Qt signals (already on the
        # main thread there, no bridge needed for that path).
        def on_death_hotkey():
            self._death_hotkey_bridge.death_requested.emit()

        def on_subtract_hotkey():
            self._death_hotkey_bridge.subtract_requested.emit()

        def on_reset_hotkey():
            self._death_hotkey_bridge.reset_requested.emit()

        self._death_hotkey_bridge.death_requested.connect(on_death)
        self._death_hotkey_bridge.subtract_requested.connect(on_subtract)
        self._death_hotkey_bridge.reset_requested.connect(on_reset)

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
                        int(result.get("hollow_streak", 0) or 0),
                    )
            threading.Thread(target=_mark, daemon=True).start()

        # ── Pull saved hotkeys from settings ──────────────────────────────────
        from gui.boss_tracker import _load_settings
        saved = _load_settings()
        hotkeys = {
            "death":    saved.get("hotkey_death",    "f9"),
            "subtract": saved.get("hotkey_subtract", "f10"),
            "reset":    saved.get("hotkey_reset",    "f8"),
            "focus":    saved.get("hotkey_focus",    "f4"),
            "unfocus":  saved.get("hotkey_unfocus",  "f5"),
            "defeat":   saved.get("hotkey_defeat",   "f11"),
        }

        self._detector = Detector(
            self._deaths,
            on_death=on_death_hotkey,
            on_subtract=on_subtract_hotkey,
            on_reset=on_reset_hotkey,
            on_focus=on_focus_hotkey,
            on_unfocus=on_unfocus_hotkey,
            on_defeat=on_defeat_hotkey,
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

        # Restore ended/submitted state from meta.json -- re-opening a
        # previously-ended run should show it that way immediately, not
        # just live-update in the session that originally ended it.
        self._tracker.mortality_tab.set_can_submit(bool(self._active_questlog_token))
        self._tracker.mortality_tab.set_submitted(self._run_submitted)
        self._tracker.mortality_tab.set_ended(self._run_ended)

        self._tracker.switch_run.connect(self._go_to_selector)
        # Route the UI's Add/Subtract/Reset buttons through the SAME handlers
        # the F8/F9/F10 hotkeys use, rather than BossTrackerWindow's own
        # separate (and narrower -- _api-only, no _local_run/boss_key
        # support) _on_add_death/_on_subtract_death/_on_reset_deaths. Two
        # independent paths to the same server action is exactly what let
        # Subtract double-fire (F10 + button both able to fire with no
        # shared guard) -- unifying to one path fixes that for all three
        # actions, not just subtract.
        self._tracker.mortality_tab.sig_add_death.connect(on_death)
        self._tracker.mortality_tab.sig_subtract_death.connect(on_subtract)
        self._tracker.mortality_tab.sig_reset_deaths.connect(on_reset)
        self._tracker.mortality_tab.sig_set_total_deaths.connect(self._set_total_deaths)
        self._tracker.mortality_tab.sig_set_session_deaths.connect(self._set_session_deaths)
        # Focus/Unfocus buttons -- same handlers as the focus/unfocus hotkeys, so
        # clicking and hotkey-pressing are just two triggers for one path.
        self._tracker.mortality_tab.sig_focus_boss.connect(on_focus_hotkey)
        self._tracker.mortality_tab.sig_unfocus_boss.connect(on_unfocus_hotkey)
        self._tracker.mortality_tab.sig_end_run.connect(self._on_end_run_clicked)
        self._tracker.mortality_tab.sig_submit_leaderboard.connect(self._on_submit_leaderboard_clicked)
        self._tracker.settings_tab.hotkeys_changed.connect(self._detector.update_hotkeys)
        self._tracker.settings_tab.save_path_changed.connect(self._on_save_path_changed)
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
        self._run_started_at   = None
        self._save_watcher     = None
        self._save_named_prev  = None
        self._save_qty_prev    = None
        self._save_auto_collect_submitted = set()
        self._reward_bosses_synced = set()
        self._active_game_id   = None
        self._active_mode_id   = None
        self._active_slug      = None
        self._active_questlog_token = ""
        self._run_ended        = False
        self._run_submitted    = False
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
                boss_list = self._bosses.export()
                if self._ql_sync:
                    # Merge in per-boss death counts from the server's status
                    # poll (self._bosses.export() is the LOCAL boss tracker --
                    # defeated/tier/group only, no death counts; those live
                    # server-side, keyed by boss_key).
                    death_by_key = {b["key"]: int(b.get("deaths", 0) or 0) for b in self._ql_sync.get_bosses()}
                    death_aliases = {
                        "Alabaster Lord (East of the Church of the Plague)": (
                            "Alabaster Lord (Caelid)",
                        ),
                    }
                    for b in boss_list:
                        deaths = death_by_key.get(b["key"], int(b.get("deaths", 0) or 0))
                        for alias in death_aliases.get(b["key"], ()):
                            deaths = max(deaths, death_by_key.get(alias, 0), int(b.get("deaths", 0) or 0))
                        b["deaths"] = deaths
                self._tracker.refresh(
                    boss_list,
                    session=self._session,
                    deaths=self._deaths,
                    ql_sync=self._ql_sync,
                    local_run=self._local_run,
                    started_at=self._run_started_at,
                )
            self._poll_save_watcher()
        except Exception:
            log.exception("Error in tick loop")

    def _resolve_save_slot(self, settings):
        """
        Pick which character slot SaveWatcher should poll. Explicit
        save_slot wins; save_character_name is a friendlier fallback. If
        neither is configured, preserve the old default of slot 0 and log
        populated slots so misconfiguration is visible.
        """
        slot = settings.get("save_slot")
        if isinstance(slot, int) and 0 <= slot < 10:
            return slot
        try:
            slot = int(slot)
            if 0 <= slot < 10:
                return slot
        except (TypeError, ValueError):
            pass

        wanted_name = (settings.get("save_character_name") or "").strip().lower()
        slots = []
        if self._save_watcher:
            try:
                slots = self._save_watcher.list_slots()
            except Exception:
                log.exception("Could not list save slots")
        if slots:
            log.info(
                "Detected save slots: %s",
                ", ".join(f"{s['index']}={s['name']!r}" for s in slots),
            )
        if wanted_name:
            for s in slots:
                if s["name"].strip().lower() == wanted_name:
                    return s["index"]
            log.warning("Configured save_character_name=%r was not found; using slot 0", wanted_name)
        return 0

    def _poll_save_watcher(self):
        """
        Reads the live save file (if configured) and auto-collects any
        item the save shows as owned, matching it against the current
        run's seeded item list. Calls the exact same
        collect_item(name) the manual click path already uses (see
        gui/boss_tracker.py ItemsTab._on_row_click) -- this only adds a new
        caller, never a new "how an item gets marked collected" code path.

        This is reconciliation, not just live diffing: items already in
        inventory before the tracker starts should be checked off too. It
        never calls uncollect_item, unlike the manual click path which can
        toggle either way.
        """
        watcher = self._save_watcher
        if watcher is None:
            return
        backend = self._ql_sync or self._local_run
        if backend is None:
            return

        items, _collected, _total = backend.get_items()
        if not items:
            log.debug("Live save tracking waiting for run item checklist")
            return

        try:
            named_snapshot, qty_snapshot = watcher.poll(self._save_watcher_slot)
        except (SaveParseError, FileNotFoundError, PermissionError, OSError) as e:
            log.warning("Save file poll failed (will retry next tick): %s", e)
            return

        if self._save_named_prev is None:
            # First successful poll this run -- establish the baseline
            # without treating everything already-owned as "newly" owned
            # (that would fire collect_item for the player's entire
            # existing inventory on run start, which is correct behavior
            # actually -- items already owned SHOULD get auto-checked off
            # immediately rather than waiting for a future pickup -- so
            # this baseline poll intentionally still runs the match/collect
            # logic below, it just has nothing "previous" to diff against).
            self._save_named_prev = set()
            self._save_qty_prev   = {}

        newly_named = named_snapshot - self._save_named_prev

        def _bare_item_name(entry):
            return entry.rsplit(" (", 1)[0] if isinstance(entry, str) and entry.endswith(")") else entry

        def _item_key(name):
            return str(name or "").strip().casefold()

        owned_by_lower = {
            _item_key(_bare_item_name(entry)): _bare_item_name(entry)
            for entry in named_snapshot
        }
        for name, qty in qty_snapshot.items():
            if qty > 0:
                owned_by_lower[_item_key(name)] = name

        uncollected_by_lower = {
            _item_key(it["name"]): it["name"] for it in items if not it["collected"]
        }

        for item_key, match in list(uncollected_by_lower.items()):
            if item_key in self._save_auto_collect_submitted:
                continue
            if item_key in owned_by_lower:
                log.info("Live save tracking: auto-collecting %r (already owned in save)", match)
                self._save_auto_collect_submitted.add(item_key)
                backend.collect_item(match)
                self._auto_mark_reward_boss(match)
                uncollected_by_lower.pop(item_key, None)

        for entry in newly_named:
            # Keep a specific diff log for new pickups, even though the
            # reconciliation pass above is authoritative for collection.
            name = _bare_item_name(entry)
            if _item_key(name) in owned_by_lower:
                log.debug("Live save tracking: newly detected owned item %r", name)

        # Quantity increases (stackable goods/key items) -- included for
        # parity with tools/live_save_diff.py's approach even though no
        # current build item type is quantity-tracked (see
        # core/save_watcher.py docstring); matched the same way, by bare
        # name against the run's uncollected items, in case a future build
        # item type needs this.
        for name, qty in qty_snapshot.items():
            prev_qty = self._save_qty_prev.get(name, 0)
            if qty > prev_qty:
                match = uncollected_by_lower.get(_item_key(name))
                if match:
                    log.info("Live save tracking: auto-collecting %r (qty %d -> %d)", match, prev_qty, qty)
                    self._save_auto_collect_submitted.add(_item_key(name))
                    backend.collect_item(match)
                    self._auto_mark_reward_boss(match)
                    uncollected_by_lower.pop(_item_key(name), None)

        self._save_named_prev = named_snapshot
        self._save_qty_prev   = qty_snapshot

    def _auto_mark_reward_boss(self, item_name):
        reward_bosses = {
            ("reforged", "Singularity"): "Alabaster Lord (East of the Church of the Plague)",
        }
        boss_key = reward_bosses.get((self._active_mode_id, item_name))
        if not boss_key or not self._bosses:
            return
        boss = self._bosses.bosses.get(boss_key)
        if not boss:
            log.warning("Live save tracking: reward %r maps to missing boss %r", item_name, boss_key)
            return
        needs_server_mark = self._ql_sync and boss_key not in self._reward_bosses_synced
        if not boss.get("defeated"):
            log.info("Live save tracking: auto-marking boss %r from reward %r", boss_key, item_name)
            self._bosses.mark_defeated(boss_key)
        elif needs_server_mark:
            log.info("Live save tracking: boss %r already marked locally for reward %r", boss_key, item_name)
        if needs_server_mark:
            self._reward_bosses_synced.add(boss_key)
            def _mark():
                result = self._ql_sync.mark_boss(boss_key)
                if result:
                    self._rage_bridge.updated.emit(
                        float(result.get("rage_pct", 0)),
                        result.get("rage_name", "Maiden's Grace"),
                        int(result.get("hollow_streak", 0) or 0),
                    )
            threading.Thread(target=_mark, daemon=True).start()

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
        self._selector_win._widget.build_planner_tab.set_api(self._api)
        self._selector_win._widget.set_logged_in(username)
        self._selector_win._widget.set_server_runs(active_runs, run_history)

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
        self._selector_win._widget.build_planner_tab.set_api(self._api)
        if self._tracker:
            self._tracker._api = self._api
            self._tracker.build_planner_tab.set_api(self._api)
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
        from gui.boss_tracker import _load_settings

        _MODE_MAP = {"err": "reforged", "vanilla": "vanilla", "reforged": "reforged"}

        token      = server_run.get("token", "")
        game       = server_run.get("game", "elden_ring")
        mode       = _MODE_MAP.get(server_run.get("game_mode", "vanilla"), "vanilla")
        name       = server_run.get("build_name") or server_run.get("name") or f"{game.replace('_', ' ').title()} — QuestLog"
        started_at = server_run.get("started_at")
        settings   = _load_settings()
        save_meta  = {}
        for key in ("save_file_path", "save_slot", "save_character_name"):
            if key in settings and settings.get(key) not in ("", None):
                save_meta[key] = settings[key]

        # Find existing local stub that was created for this exact server token,
        # or always create a fresh one — never reuse a different run's data.
        slug = None
        for meta in list_runs():
            if meta.get("questlog_token") == token:
                slug = meta["slug"]
                log.info("Reusing local stub '%s' for server run %s", slug, token[:8])
                break

        if slug is None:
            slug = create_run(
                name,
                game,
                mode,
                questlog_token=token,
                started_at=started_at,
                save_file_path=save_meta.get("save_file_path"),
                save_slot=save_meta.get("save_slot"),
                save_character_name=save_meta.get("save_character_name"),
            )
            log.info("Created local stub run '%s' for server run %s", slug, token[:8])
        else:
            updates = dict(save_meta)
            if started_at:
                # Update started_at on existing stub in case it wasn't stored yet.
                updates["started_at"] = started_at
            if updates:
                update_run_meta(slug, updates)

        # Set API client using our stored api_key + the server run's token
        if self._api:
            api_key = self._api._api_key
        else:
            log.warning("CONNECT clicked but not logged in — skipping cloud sync")
            api_key = ""

        if api_key and token:
            self._api = QuestLogClient(api_key, token)
            self._selector_win._widget.build_planner_tab.set_api(self._api)
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
        self._selector_win._widget.build_planner_tab.set_api(self._api)
        self._selector_win._widget.set_logged_in(username)
        # Fetch runs immediately in background — no manual refresh needed
        self._refresh_server_runs(api_key)

    def _refresh_server_runs(self, api_key=None, username=None):
        """Fetch profile from server and update the selector's server runs section."""
        import requests
        from core.api_client import APP_VERSION, BASE_URL, REQUEST_TIMEOUT
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

        def _fetch():
            try:
                r = requests.get(
                    f"{BASE_URL}/api/soulslike/desktop/profile/",
                    headers={
                        "X-Listener-Key": api_key,
                        "X-App-Version":  APP_VERSION,
                        "User-Agent":     f"QuestLog-EldenTracker/{APP_VERSION}",
                    },
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
        # If already logged in this session, reflect that immediately
        if self._api and saved.get("username"):
            tab._set_logged_in(saved["username"])
        layout.addWidget(tab)
        dlg.exec()

    def _on_save_path_changed(self, path):
        """
        Settings' Browse/Auto-detect just persisted a new save_file_path --
        rebuild self._save_watcher immediately (if a run is active) rather
        than waiting for a restart, matching the existing hotkey-remap live-
        apply UX (settings_tab.hotkeys_changed -> self._detector.update_hotkeys).
        """
        self._save_watcher     = None
        self._save_named_prev  = None
        self._save_qty_prev    = None
        self._save_auto_collect_submitted = set()
        self._reward_bosses_synced = set()
        if not path or not os.path.isfile(path):
            return
        if self._active_game_id != "elden_ring" or self._active_mode_id not in ("vanilla", "reforged"):
            return
        from core.save_watcher import SaveWatcher
        from gui.boss_tracker import _load_settings
        try:
            self._save_watcher = SaveWatcher(path, mode=self._active_mode_id)
            self._save_watcher_slot = self._resolve_save_slot(_load_settings())
            log.info("Live save tracking path updated: %s (mode=%s slot_index=%d game_slot=%d)",
                     path, self._active_mode_id, self._save_watcher_slot, self._save_watcher_slot + 1)
        except Exception:
            log.exception("Failed to start SaveWatcher for %r", path)
            self._save_watcher = None

    def _on_end_run_clicked(self):
        """
        Explicit "End Run" -- ends the run server-side (if cloud-synced)
        and persists ended=True locally, but deliberately does NOT tear the
        app down the way _stop_active() does (no window close, no
        self._timer/self._detector stop, self._ql_sync's poll loop keeps
        running). Distinct from switch_run/closing the window, which
        already end the run implicitly via _stop_active() -- this is a
        separate, explicit action the user chose to take while staying on
        this run's window.
        """
        if self._run_ended:
            return
        from PyQt6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self._tracker, "End this run?",
            "End this run? You can still submit it to the leaderboard "
            "afterward, but you won't be able to log more deaths against it.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if self._ql_sync:
            try:
                self._ql_sync.notify_run_ended()
            except Exception:
                log.exception("notify_run_ended failed")

        self._run_ended = True
        if self._active_slug:
            try:
                update_run_meta(self._active_slug, {"ended": True})
            except Exception:
                log.exception("Failed to persist ended=True for run '%s'", self._active_slug)

        if self._tracker:
            self._tracker.mortality_tab.set_ended(True)
        log.info("Run explicitly ended: %s", self._active_slug)

    def _on_submit_leaderboard_clicked(self):
        """
        "Submit to Leaderboard" -- one-shot, only reachable once the run
        has ended and a server-tracked session (questlog_token) exists.
        Goes through self._api (QuestLogClient), not self._ql_sync, since
        self._ql_sync's own lifecycle is unrelated to whether this run can
        still be submitted (it keeps running after End Run, and submission
        must also work if the app was restarted after ending a run, when no
        QuestLogSync exists for it at all).
        """
        if not self._run_ended or self._run_submitted:
            return
        if not self._active_questlog_token or not self._api:
            return

        from PyQt6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self._tracker, "Submit to Leaderboard?",
            "This is final — once submitted, this run can't be resubmitted "
            "or removed.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if self._tracker:
            self._tracker.mortality_tab.submit_leaderboard_btn.setEnabled(False)

        bridge = self._leaderboard_submit_bridge
        self._api.submit_to_leaderboard(
            self._active_questlog_token,
            on_done=lambda data: bridge.succeeded.emit(),
            on_error=lambda msg: bridge.failed.emit(msg),
        )

    def _on_leaderboard_submit_succeeded(self):
        self._run_submitted = True
        if self._active_slug:
            try:
                update_run_meta(self._active_slug, {"submitted": True})
            except Exception:
                log.exception("Failed to persist submitted=True for run '%s'", self._active_slug)
        if self._tracker:
            self._tracker.mortality_tab.set_submitted(True)
        log.info("Run submitted to leaderboard: %s", self._active_slug)

    def _on_leaderboard_submit_failed(self, message):
        # "This run has already been submitted" is treated the same as
        # success per the API contract -- the local record just fell out of
        # sync with the server, not a real failure.
        if "already been submitted" in message.lower():
            self._on_leaderboard_submit_succeeded()
            return
        log.warning("Leaderboard submission failed: %s", message)
        if self._tracker:
            self._tracker.mortality_tab.submit_leaderboard_btn.setEnabled(True)
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self._tracker, "Submission Failed", message)

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

    def _set_total_deaths(self, value):
        if not self._session:
            return
        value = max(0, int(value))
        self._session.total_deaths = value
        session_changed = False
        if self._session.session_deaths > value:
            self._session.session_deaths = value
            session_changed = True
        self._session.save()
        if self._ql_sync:
            self._ql_sync.set_death_counts(
                total_deaths=self._session.total_deaths,
                session_deaths=self._session.session_deaths if session_changed else None,
            )
        if self._tracker:
            self._tracker.death_log_tab.update_counts(
                self._session.session_deaths,
                self._session.total_deaths,
            )
            self._tracker.refresh(
                self._bosses.export(),
                self._session,
                self._deaths,
                ql_sync=self._ql_sync,
                local_run=self._local_run,
                started_at=self._run_started_at,
            )
        log.info("Total deaths manually set to %d", self._session.total_deaths)

    def _set_session_deaths(self, value):
        if not self._session:
            return
        value = max(0, int(value))
        self._session.session_deaths = value
        total_changed = False
        if self._session.total_deaths < value:
            self._session.total_deaths = value
            total_changed = True
        self._session.save()
        if self._ql_sync:
            self._ql_sync.set_death_counts(
                total_deaths=self._session.total_deaths if total_changed else None,
                session_deaths=self._session.session_deaths,
            )
        if self._tracker:
            self._tracker.death_log_tab.update_counts(
                self._session.session_deaths,
                self._session.total_deaths,
            )
            self._tracker.refresh(
                self._bosses.export(),
                self._session,
                self._deaths,
                ql_sync=self._ql_sync,
                local_run=self._local_run,
                started_at=self._run_started_at,
            )
        log.info("Session deaths manually set to %d", self._session.session_deaths)

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

            # Mirror server counters directly. Replaying the diff through
            # record_death()/subtract_death() makes a stale poll look like a
            # real click, which can undo a just-logged death and corrupt Fury.
            server_total   = data.get("total_deaths", data.get("deaths", self._session.total_deaths))
            sess_deaths    = data.get("session_deaths", server_session_deaths)
            if sess_deaths >= 0:
                self._session.session_deaths = sess_deaths
            if server_total >= 0:
                self._session.total_deaths = server_total
                self._session.save()
            if "rage_pct" in data:
                self._apply_rage_update(
                    float(data.get("rage_pct", 0)),
                    data.get("rage_name", "Maiden's Grace"),
                    int(data.get("hollow_streak", 0) or 0),
                )
            log.info("Death count synced from web: session=%d total=%d",
                     self._session.session_deaths, self._session.total_deaths)

    def _apply_rage_update(self, rage_pct, rage_name, hollow_streak=None):
        """Main-thread handler: apply rage values returned by server after boss kill."""
        if self._deaths:
            self._deaths._rage_pct = float(rage_pct)
            self._deaths._consecutive = int(rage_pct / 25)
            if hollow_streak is not None:
                self._deaths._hollow_streak = int(hollow_streak)

    def _open_focus_picker(self):
        """Main-thread handler for the focus hotkey (see _FocusHotkeyBridge)."""
        if self._tracker:
            self._tracker.open_focus_picker()

    def _unfocus_current_boss(self):
        """Main-thread handler for the unfocus hotkey (see _FocusHotkeyBridge)."""
        if self._tracker:
            self._tracker.unfocus_current_boss()

    def _defeat_focused_boss(self):
        """Main-thread handler for the defeat-focused-boss hotkey."""
        if self._run_ended:
            log.info("DEFEAT FOCUSED BOSS ignored -- run has ended")
            return
        if self._tracker and self._tracker.defeat_focused_boss():
            log.info("DEFEAT FOCUSED BOSS hotkey applied")
        else:
            log.info("DEFEAT FOCUSED BOSS ignored -- no boss focused")

    def _do_logout(self):
        from gui.boss_tracker import _load_settings, _save_settings
        s = _load_settings()
        s["api_key"] = ""
        s["session_token"] = ""
        s["username"] = ""
        _save_settings(s)
        self._api = None
        if self._tracker:
            self._tracker._api = None
        self._selector_win._widget.set_logged_out()
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
    threading.Thread(target=_start_catalog_sync, name="questlog-catalog-sync", daemon=True).start()

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
