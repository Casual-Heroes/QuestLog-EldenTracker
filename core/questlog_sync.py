"""
QuestLog session sync — 2s heartbeat + local timing mirror.

App is the authoritative clock. Every heartbeat pushes session_sec,
streak_sec, longest_sec, and survival_sec so the web display matches
exactly. No divergence possible.

Status poll every ~6s detects web-side changes (reset, death undo)
and fires on_server_sync so the main thread can mirror them.
"""

import time
import threading
import requests
from core.crash_logger import get_logger

log = get_logger("questlog.sync")

BASE_URL = "https://questlog.casual-heroes.com"


class QuestLogSync:
    def __init__(self, session_token, api_key=None, on_server_sync=None):
        self.token           = session_token
        self.api_key         = api_key
        self.running         = False
        self._on_server_sync = on_server_sync  # callback(dict) — runs on bg thread
        self._http           = requests.Session()
        self._lock           = threading.Lock()

        self._session_sec        = 0.0
        self._last_tick          = None   # set in start() before thread launches
        self._last_death_ts      = None
        self._longest_life       = 0.0
        self._local_deaths       = 0
        self._life_start_ts      = None   # when current life began (after last death / start)
        self._total_survival_sec = 0.0    # cumulative alive time across all lives this session
        self._current_boss       = ""     # boss currently being fought (for death attribution)

    def _url(self, path):
        return f"{BASE_URL}/api/soulslike/session/{self.token}/{path}"

    def _headers(self):
        return {"X-Listener-Key": self.api_key} if self.api_key else {}

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self):
        now = time.time()
        with self._lock:
            self._last_tick     = now
            self._last_death_ts = now
            self._life_start_ts = now
        self.running = True
        log.info("QuestLogSync starting — token=%s", self.token[:12] if self.token else "none")
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self.running = False

    # ── Main loop ─────────────────────────────────────────────────────────────

    def _loop(self):
        log.info("Heartbeat loop started — token=%s", self.token[:12] if self.token else "none")
        _status_counter = 0
        while self.running:
            try:
                now = time.time()
                with self._lock:
                    delta = now - self._last_tick
                    self._last_tick = now
                    self._session_sec += delta

                self._heartbeat(game_running=True)

                # Status poll every 3rd tick (~6s) — detect web-side resets/undos
                _status_counter += 1
                if _status_counter >= 3:
                    _status_counter = 0
                    self._poll_status()

            except Exception as e:
                log.warning("Heartbeat error: %s", e)
            time.sleep(2)
        log.info("Heartbeat loop stopped — token=%s", self.token[:12] if self.token else "none")

    def _poll_status(self):
        try:
            sr = self._http.get(self._url("status/"), headers=self._headers(), timeout=5)
            if sr.status_code != 200:
                return
            data = sr.json()
            server_deaths = data.get("deaths", 0)
            with self._lock:
                local = self._local_deaths
            if server_deaths != local:
                log.info("Deaths drift: server=%d local=%d — syncing", server_deaths, local)
                with self._lock:
                    self._local_deaths = server_deaths
                    if server_deaths == 0:
                        self._reset_timers(time.time())
                if self._on_server_sync:
                    self._on_server_sync({
                        "deaths":    server_deaths,
                        "rage_pct":  data.get("rage_pct", 0),
                        "rage_name": data.get("rage_name", "Maiden's Grace"),
                        "reset":     server_deaths == 0,
                    })
        except Exception as e:
            log.debug("Status poll failed: %s", e)

    def _reset_timers(self, now):
        """Zero all timing state. Must be called with lock held."""
        self._session_sec        = 0.0
        self._last_death_ts      = now
        self._longest_life       = 0.0
        self._last_tick          = now
        self._life_start_ts      = now
        self._total_survival_sec = 0.0
        self._local_deaths       = 0

    # ── Heartbeat / push ──────────────────────────────────────────────────────

    def _heartbeat(self, game_running=True):
        try:
            with self._lock:
                session_sec      = int(self._session_sec)
                longest_life     = int(self._longest_life)
                life_start       = self._life_start_ts
                total_surv       = self._total_survival_sec
            now = time.time()
            streak_sec   = int(now - life_start) if life_start else 0
            survival_sec = int(total_surv + (now - life_start if life_start else 0))
            self._http.post(
                self._url("heartbeat/"),
                json={
                    "game_running": game_running,
                    "session_sec":  session_sec,
                    "streak_sec":   streak_sec,
                    "longest_sec":  longest_life,
                    "survival_sec": survival_sec,
                },
                headers=self._headers(),
                timeout=5,
            )
            log.debug("Heartbeat OK session=%d streak=%d longest=%d survival=%d",
                      session_sec, streak_sec, longest_life, survival_sec)
        except Exception as e:
            log.warning("Heartbeat failed: %s", e)

    def _push_timers(self, streak_override=None, survival_override=None):
        """Immediately push timer state — used after death/reset so web updates at once."""
        try:
            with self._lock:
                session_sec  = int(self._session_sec)
                longest_life = int(self._longest_life)
                total_surv   = self._total_survival_sec
                life_start   = self._life_start_ts
            now = time.time()
            streak_sec   = streak_override if streak_override is not None else (
                int(now - life_start) if life_start else 0
            )
            survival_sec = survival_override if survival_override is not None else (
                int(total_surv + (now - life_start if life_start else 0))
            )
            self._http.post(
                self._url("heartbeat/"),
                json={
                    "game_running": True,
                    "session_sec":  session_sec,
                    "streak_sec":   streak_sec,
                    "longest_sec":  longest_life,
                    "survival_sec": survival_sec,
                },
                headers=self._headers(),
                timeout=5,
            )
        except Exception:
            pass

    # ── Timing accessors (called every second from UI tick) ───────────────────

    def session_time_sec(self):
        with self._lock:
            return int(self._session_sec)

    def current_streak_sec(self):
        with self._lock:
            if self._life_start_ts is None:
                return 0
            return int(time.time() - self._life_start_ts)

    def longest_life_sec(self):
        with self._lock:
            return int(self._longest_life)

    # ── Event hooks ───────────────────────────────────────────────────────────

    def on_death(self, boss=""):
        now = time.time()
        with self._lock:
            if self._life_start_ts:
                life_dur = now - self._life_start_ts
                self._total_survival_sec += life_dur
                if life_dur > self._longest_life:
                    self._longest_life = life_dur
            self._life_start_ts = now
            self._last_death_ts = now
            self._local_deaths += 1
        threading.Thread(target=self._post_death_immediate, args=(boss,), daemon=True).start()

    def on_subtract(self):
        with self._lock:
            if self._local_deaths > 0:
                self._local_deaths -= 1
        threading.Thread(target=self._post, args=("subtract-death/", {}), daemon=True).start()

    def on_reset(self):
        now = time.time()
        with self._lock:
            self._reset_timers(now)
        threading.Thread(target=self._do_reset, daemon=True).start()

    def _do_reset(self):
        try:
            self._http.post(self._url("reset-deaths/"), json={},
                            headers=self._headers(), timeout=5)
            log.info("reset-deaths posted")
        except Exception as e:
            log.warning("reset-deaths failed: %s", e)
        self._push_timers(streak_override=0, survival_override=0)

    # ── Boss focus / mark / unmark ────────────────────────────────────────────

    def set_focus(self, boss_name):
        with self._lock:
            self._current_boss = boss_name
        try:
            r = self._http.post(self._url("set-focus/"),
                                json={"boss_name": boss_name},
                                headers=self._headers(), timeout=5)
            log.info("set_focus %r → status=%d body=%r", boss_name, r.status_code, r.text[:200])
        except Exception as e:
            log.warning("set_focus failed: %s", e, exc_info=True)

    def clear_focus(self):
        with self._lock:
            self._current_boss = ""
        try:
            r = self._http.post(self._url("set-focus/"),
                                json={"boss_name": ""},
                                headers=self._headers(), timeout=5)
            log.info("clear_focus → status=%d body=%r", r.status_code, r.text[:200])
        except Exception as e:
            log.warning("clear_focus failed: %s", e)

    def mark_boss(self, boss_key):
        """Returns response dict with rage_pct/rage_name if successful, else None."""
        with self._lock:
            self._current_boss = ""
        try:
            r = self._http.post(
                self._url("boss/mark/"),
                json={"boss_key": boss_key},
                headers=self._headers(),
                timeout=5,
            )
            log.debug("mark_boss key=%r status=%d body=%r", boss_key, r.status_code, r.text[:300])
            if not r.content:
                return None
            data = r.json()
            if data.get("ok"):
                return data
            log.warning("mark_boss server rejected: status=%d body=%s", r.status_code, r.text[:300])
        except Exception as e:
            log.warning("mark_boss failed: %s", e)
        return None

    def unmark_boss(self, boss_key):
        threading.Thread(
            target=self._post, args=("boss/unmark/", {"boss_key": boss_key}), daemon=True
        ).start()

    def get_current_boss(self):
        with self._lock:
            return self._current_boss

    # ── Build CRUD ────────────────────────────────────────────────────────────

    def get_builds(self, game='elden_ring'):
        try:
            r = self._http.get(
                f"{BASE_URL}/api/soulslike/desktop/builds/",
                headers=self._headers(),
                params={'game': game},
                timeout=10,
            )
            return r.json().get('builds', []) if r.ok else []
        except Exception as e:
            log.warning("get_builds failed: %s", e)
            return []

    def save_build(self, build_data: dict, game='elden_ring'):
        try:
            r = self._http.post(
                f"{BASE_URL}/api/soulslike/desktop/builds/",
                headers=self._headers(),
                params={'game': game},
                json=build_data,
                timeout=10,
            )
            return r.json() if r.ok else None
        except Exception as e:
            log.warning("save_build failed: %s", e)
            return None

    def delete_build(self, build_id: int, game='elden_ring'):
        try:
            r = self._http.delete(
                f"{BASE_URL}/api/soulslike/desktop/builds/{build_id}/",
                headers=self._headers(),
                params={'game': game},
                timeout=10,
            )
            return r.json().get('ok', False) if r.ok else False
        except Exception as e:
            log.warning("delete_build failed: %s", e)
            return False

    # ── Aliases (same interface as QuestLogClient) ────────────────────────────

    def post_death(self, boss=""):
        self.on_death(boss)

    def post_subtract(self):
        self.on_subtract()

    def post_reset(self):
        self.on_reset()

    def post_boss_reset(self):
        threading.Thread(target=self._post, args=("reset-deaths/", {}), daemon=True).start()

    def end_run(self):
        try:
            self._heartbeat(game_running=False)
        except Exception:
            pass
        threading.Thread(target=self._post, args=("end/", {}), daemon=True).start()
        self.stop()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _post(self, path, payload):
        try:
            self._http.post(self._url(path), json=payload,
                            headers=self._headers(), timeout=5)
        except Exception as e:
            log.warning("POST %s failed: %s", path, e)

    def _post_death_immediate(self, boss=""):
        """POST death then immediately push timers with streak=0."""
        try:
            self._http.post(self._url("death/"),
                            json={"boss": boss, "source": "app"},
                            headers=self._headers(), timeout=5)
        except Exception as e:
            log.warning("Death post failed: %s", e)
        self._push_timers(streak_override=0)
