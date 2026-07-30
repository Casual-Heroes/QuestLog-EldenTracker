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
from core.catalog_sync import CatalogStore

log = get_logger("questlog.sync")

BASE_URL = "https://questlog.casual-heroes.com"
APP_VERSION = "1.1.0"

# ── Game process registry ─────────────────────────────────────────────────────
# Add new games here. Key = game_id used by the API, value = set of exe names
# (all lowercase). Multiple exes per game handles vanilla + mod launchers.
GAME_PROCESSES = {
    "elden_ring": {"eldenring.exe"},
    "err":        {"eldenring.exe", "regulation-reforged.exe"},
    "remnant2":   {"remnant2.exe"},
}

# Flat set of all known exes for quick membership check
_ALL_GAME_EXES = {exe for exes in GAME_PROCESSES.values() for exe in exes}

_BOSS_KEY_ALIASES = {
    "Alabaster Lord (Caelid)": "Alabaster Lord (East of the Church of the Plague)",
}


def _normalize_boss_key(boss_key):
    return _BOSS_KEY_ALIASES.get(boss_key, boss_key)


def _is_game_running(game_id: str = None) -> bool:
    """
    Return True if a game process is running.
    If game_id is given, only checks that game's exes.
    Otherwise checks all known game exes.
    """
    try:
        import psutil
        exes = GAME_PROCESSES.get(game_id, _ALL_GAME_EXES) if game_id else _ALL_GAME_EXES
        return any(p.name().lower() in exes for p in psutil.process_iter(["name"]))
    except Exception:
        return False


class QuestLogSync:
    def __init__(
        self,
        session_token,
        api_key=None,
        on_server_sync=None,
        game_id=None,
        initial_deaths=None,
        initial_session_deaths=None,
    ):
        self.token           = session_token
        self.api_key         = api_key
        self._game_id        = game_id   # used to scope process detection
        self._stop_event     = threading.Event()
        self._on_server_sync = on_server_sync  # callback(dict) — runs on bg thread
        self._http           = requests.Session()
        self._http.headers.update({
            "User-Agent":    f"QuestLog-EldenTracker/{APP_VERSION}",
            "X-App-Version": APP_VERSION,
        })
        self._http.verify    = True
        self._catalog        = CatalogStore(logger=log)
        self._lock           = threading.Lock()

        self._session_sec        = 0.0
        self._last_tick          = None   # set in start() before thread launches
        self._last_death_ts      = None
        self._longest_life       = 0.0
        self._local_deaths       = int(initial_deaths or 0)
        self._local_deaths_known = initial_deaths is not None
        self._life_start_ts      = None   # when current life began (after last death / start)
        self._total_survival_sec = 0.0    # cumulative alive time across all lives this session
        self._current_boss       = ""     # boss name currently being fought (for death attribution)
        self._current_boss_key   = ""     # boss_key for the above -- disambiguates same-named bosses (e.g. "Erdtree Avatar" appears in 6 locations); always send alongside boss_name, never boss_name alone
        self._cached_items         = []     # last items list from status poll
        self._cached_deaths        = []     # last recent_deaths list from status poll
        self._items_total          = 0
        self._items_collected      = 0
        self._true_death_rate      = None   # server-computed deaths/boss (None until first boss killed)
        self._cached_bosses         = []    # last bosses[] array from status poll (each has key/name/defeated/deaths)
        self._pending_boss_death_floors = {}  # boss_key -> minimum count after a local death until status catches up
        self._boss_deaths_total     = 0     # died while a boss was focused
        self._non_boss_deaths_total = 0     # died with nothing focused (exploring, fall damage, etc)
        self._lifetime_playtime_sec = 0     # true lifetime played time -- never reset by Full Reset/Stop Session
        self._lifetime_playtime_fmt = ""    # server-formatted HH:MM:SS or "Xd HH:MM"
        self._session_deaths_per_hour = None  # None until listener_session_sec >= 600 (server-side gate)
        self._run_deaths_per_hour     = None  # None until lifetime_playtime_sec >= 600 (server-side gate)
        self._rage_pct                = 0.0
        self._rage_name               = "Maiden's Grace"
        self._hollow_streak           = 0
        self._local_session_deaths = (
            int(initial_session_deaths)
            if initial_session_deaths is not None
            else -1
        )    # tracks server session_deaths for new-session detection
        self._local_mutation_ts   = 0.0    # guards against stale status polls right after app actions
        self._local_mutation_kind = ""
        self._pending_death_sync  = False  # death endpoint failed or has not been confirmed by status yet
        self._death_in_flight     = False  # F9/button must POST once and wait for the authoritative response
        self._subtract_in_flight  = False  # F10/button must POST once and wait for the authoritative response
        self._last_death_request  = 0.0    # shared cooldown across F9/button/automatic detection
        self._game_active          = False  # True only when game EXE is detected running
        self._paused_streak_sec    = 0      # streak seconds banked when game stopped
        self._paused_survival_sec  = 0.0   # survival seconds banked when game stopped

    def _url(self, path):
        return f"{BASE_URL}/api/soulslike/session/{self.token}/{path}"

    def _headers(self):
        h = {"X-App-Version": APP_VERSION}
        if self.api_key:
            h["X-Listener-Key"] = self.api_key
        return h

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    @property
    def running(self):
        return not self._stop_event.is_set()

    def start(self):
        now = time.time()
        with self._lock:
            self._last_tick     = now
            self._last_death_ts = now
            self._life_start_ts = now
        self._stop_event.clear()
        log.info("QuestLogSync starting — token=%s", self.token[:12] if self.token else "none")
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._stop_event.set()

    # ── Main loop ─────────────────────────────────────────────────────────────

    def _loop(self):
        log.info("Heartbeat loop started — token=%s", self.token[:12] if self.token else "none")
        _status_counter = 0
        while not self._stop_event.is_set():
            try:
                now = time.time()
                game_running = _is_game_running(self._game_id)
                with self._lock:
                    delta = now - self._last_tick
                    self._last_tick = now
                    if game_running:
                        self._session_sec += delta
                        if not self._game_active:
                            # Game just started — resume life clock from now
                            self._life_start_ts = now
                        self._game_active = True
                    else:
                        if self._game_active:
                            # Game just stopped — bank streak + survival, freeze clocks
                            if self._life_start_ts:
                                self._paused_streak_sec   = int(now - self._life_start_ts)
                                self._paused_survival_sec = self._total_survival_sec + (now - self._life_start_ts)
                            self._life_start_ts = None
                            self._game_active   = False

                self._heartbeat(game_running=game_running)

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
            if sr.status_code == 403:
                log.warning("Session 403 — token expired or session ended on server. Stopping sync.")
                self._stop_event.set()
                return
            if sr.status_code != 200:
                log.warning("Status poll non-200: status=%d body=%r", sr.status_code, sr.text[:300])
                return
            data = sr.json()

            # Cache items + deaths for UI accessors
            with self._lock:
                incoming_bosses = []
                for raw_boss in data.get("bosses", []):
                    boss = dict(raw_boss)
                    boss_key = _normalize_boss_key(boss.get("key", ""))
                    if boss_key:
                        boss["key"] = boss_key
                    floor = self._pending_boss_death_floors.get(boss_key)
                    if floor is not None:
                        server_count = int(boss.get("deaths", 0) or 0)
                        if server_count >= floor:
                            self._pending_boss_death_floors.pop(boss_key, None)
                        else:
                            boss["deaths"] = floor
                    incoming_bosses.append(boss)

                seen_boss_keys = {b.get("key") for b in incoming_bosses}
                for boss_key, floor in self._pending_boss_death_floors.items():
                    if boss_key and boss_key not in seen_boss_keys:
                        incoming_bosses.append({
                            "key": boss_key,
                            "name": self._current_boss or boss_key,
                            "defeated": False,
                            "deaths": floor,
                        })

                self._cached_items    = data.get("items", [])
                self._cached_deaths   = data.get("recent_deaths", [])
                self._items_total     = data.get("total", 0)
                self._items_collected = data.get("collected", 0)
                self._true_death_rate = data.get("true_death_rate")
                self._cached_bosses         = incoming_bosses   # each: {name, key, defeated, deaths, ...}
                server_boss_deaths_total = int(data.get("boss_deaths_total", 0) or 0)
                if self._pending_boss_death_floors:
                    server_boss_deaths_total = max(server_boss_deaths_total, self._boss_deaths_total)
                self._boss_deaths_total     = server_boss_deaths_total
                self._non_boss_deaths_total = data.get("non_boss_deaths_total", 0)
                self._lifetime_playtime_sec = data.get("lifetime_playtime_sec", 0)
                self._lifetime_playtime_fmt = data.get("lifetime_playtime_fmt", "")
                # Both null (not 0) from the server until their respective
                # played-time clock passes 600s -- preserved as None here,
                # NOT defaulted to 0, so the UI can tell "no data yet" apart
                # from "genuinely zero deaths so far."
                self._session_deaths_per_hour = data.get("session_deaths_per_hour")
                self._run_deaths_per_hour     = data.get("run_deaths_per_hour")
                self._rage_pct                = float(data.get("rage_pct", 0) or 0)
                self._rage_name               = data.get("rage_name", "Maiden's Grace") or "Maiden's Grace"
                self._hollow_streak           = int(
                    data.get("hollow_streak")
                    or data.get("hollow_count")
                    or data.get("gone_hollow_count")
                    or data.get("hollow_deaths")
                    or data.get("hollow")
                    or 0
                )

            server_deaths         = data.get("deaths", 0)
            server_session_deaths = data.get("session_deaths", -1)
            with self._lock:
                local         = self._local_deaths
                local_session = self._local_session_deaths
                local_known   = self._local_deaths_known
                mutation_ts   = self._local_mutation_ts
                mutation_kind = self._local_mutation_kind
                pending_death_sync = self._pending_death_sync
            mutation_age = time.time() - mutation_ts if mutation_ts else None

            if not local_known:
                with self._lock:
                    self._local_deaths         = server_deaths
                    self._local_deaths_known   = True
                    self._local_session_deaths = server_session_deaths if server_session_deaths >= 0 else 0
                log.info("Death sync baseline initialized: total=%d session=%d",
                         server_deaths, server_session_deaths)
                return

            # Death/subtract POSTs are asynchronous. A status poll can arrive
            # before the server has applied the local action; do not mirror
            # that stale count back into the app and undo the click.
            if mutation_age is not None and (mutation_age < 8 or pending_death_sync):
                total_lagged_death = mutation_kind == "death" and server_deaths < local
                total_lagged_subtract = mutation_kind in ("subtract", "reset") and server_deaths > local
                total_lagged_set = mutation_kind == "set" and server_deaths != local
                session_lagged_death = (
                    mutation_kind == "death"
                    and server_session_deaths >= 0
                    and local_session >= 0
                    and server_session_deaths < local_session
                )
                session_lagged_subtract = (
                    mutation_kind in ("subtract", "reset")
                    and server_session_deaths >= 0
                    and local_session >= 0
                    and server_session_deaths > local_session
                )
                session_lagged_set = (
                    mutation_kind == "set"
                    and server_session_deaths >= 0
                    and local_session >= 0
                    and server_session_deaths != local_session
                )
                if mutation_kind == "death" and server_deaths >= local:
                    with self._lock:
                        self._pending_death_sync = False
                if (
                    total_lagged_death
                    or total_lagged_subtract
                    or total_lagged_set
                    or session_lagged_death
                    or session_lagged_subtract
                    or session_lagged_set
                ):
                    log.info("Ignoring stale death status after local action: server=%d/%d local=%d/%d age=%.1fs",
                             server_deaths, server_session_deaths, local, local_session, mutation_age)
                    return

            new_session = server_session_deaths == 0 and local_session > 0
            if server_deaths != local or new_session:
                log.info("Deaths drift or new session: server=%d local=%d server_sess=%d local_sess=%d",
                         server_deaths, local, server_session_deaths, local_session)
                with self._lock:
                    self._local_deaths         = server_deaths
                    self._local_deaths_known   = True
                    self._local_session_deaths = server_session_deaths if server_session_deaths >= 0 else 0
                    now = time.time()
                    if server_deaths == 0:
                        # Full reset from server -- zero everything
                        self._reset_timers(now)
                    elif new_session:
                        # Grace expired -- reset session stats only, keep longest_life
                        self._reset_session_timers(now)
                if self._on_server_sync:
                    self._on_server_sync({
                        "deaths":         server_deaths,
                        "rage_pct":       data.get("rage_pct", 0),
                        "rage_name":      data.get("rage_name", "Maiden's Grace"),
                        "hollow_streak":   (
                            data.get("hollow_streak")
                            or data.get("hollow_count")
                            or data.get("gone_hollow_count")
                            or data.get("hollow_deaths")
                            or data.get("hollow")
                            or 0
                        ),
                        "reset":          server_deaths == 0,
                        "session_deaths": server_session_deaths,
                    })
        except Exception as e:
            log.debug("Status poll failed: %s", e)

    def _reset_session_timers(self, now):
        """Reset session-scoped stats only. Keeps run-scoped longest_life. Lock must be held."""
        self._session_sec          = 0.0
        self._last_death_ts        = now
        self._last_tick            = now
        self._life_start_ts        = now if self._game_active else None
        self._total_survival_sec   = 0.0
        self._local_session_deaths = 0
        self._paused_streak_sec    = 0
        self._paused_survival_sec  = 0.0

    def _reset_timers(self, now):
        """Full reset -- zeros everything including run-scoped longest_life. Lock must be held."""
        self._reset_session_timers(now)
        self._longest_life         = 0.0
        self._local_deaths         = 0
        self._local_deaths_known   = True
        self._pending_death_sync   = False
        self._pending_boss_death_floors.clear()
        self._local_mutation_ts    = now
        self._local_mutation_kind  = "reset"

    # ── Heartbeat / push ──────────────────────────────────────────────────────

    def _heartbeat(self, game_running=True):
        try:
            payload = self._timer_payload(game_running=game_running)
            r = self._http.post(
                self._url("heartbeat/"),
                json=payload,
                headers=self._headers(),
                timeout=5,
            )
            if not r.ok:
                self._http.post(
                    self._url("heartbeat/"),
                    json=self._legacy_timer_payload(payload),
                    headers=self._headers(),
                    timeout=5,
                )
            elif r.content:
                self._apply_death_count_status(r.json())
            log.debug("Heartbeat OK session=%d streak=%d longest=%d survival=%d",
                      payload["session_sec"], payload["streak_sec"],
                      payload["longest_sec"], payload["survival_sec"])
        except Exception as e:
            log.warning("Heartbeat failed: %s", e)

    def _push_timers(self, streak_override=None, survival_override=None):
        """Immediately push timer state — used after death/reset so web updates at once."""
        try:
            payload = self._timer_payload(
                game_running=True,
                streak_override=streak_override,
                survival_override=survival_override,
            )
            r = self._http.post(
                self._url("heartbeat/"),
                json=payload,
                headers=self._headers(),
                timeout=5,
            )
            if not r.ok:
                log.warning("Timer push rejected: status=%d body=%r; retrying legacy payload",
                            r.status_code, r.text[:300])
                self._http.post(
                    self._url("heartbeat/"),
                    json=self._legacy_timer_payload(payload),
                    headers=self._headers(),
                    timeout=5,
                )
            elif r.content:
                self._apply_death_count_status(r.json())
            log.info("Timer push OK session=%d streak=%d deaths=%d session_deaths=%d boss_key=%r",
                     payload["session_sec"], payload["streak_sec"],
                     payload["deaths"], payload["session_deaths"],
                     payload.get("boss_key", ""))
        except Exception as e:
            log.warning("Timer push failed: %s", e)

    # ── Timing accessors (called every second from UI tick) ───────────────────

    def _timer_payload(self, game_running=True, streak_override=None, survival_override=None):
        with self._lock:
            session_sec    = int(self._session_sec)
            longest_life   = int(self._longest_life)
            total_surv     = self._total_survival_sec
            life_start     = self._life_start_ts
            deaths         = int(self._local_deaths)
            session_deaths = max(0, int(self._local_session_deaths))
            boss           = self._current_boss
            boss_key       = self._current_boss_key
        now = time.time()
        raw_streak = int(now - life_start) if life_start else 0
        raw_survival = int(total_surv + (now - life_start if life_start else 0))
        return {
            "game_running": game_running,
            "session_sec": session_sec,
            "streak_sec": (
                int(streak_override)
                if streak_override is not None
                else min(raw_streak, self._MAX_LIFE_SEC)
            ),
            "longest_sec": longest_life,
            "survival_sec": (
                int(survival_override)
                if survival_override is not None
                else min(raw_survival, self._MAX_LIFE_SEC)
            ),
            "deaths": deaths,
            "session_deaths": session_deaths,
            "boss": boss,
            "boss_key": boss_key,
        }

    def _legacy_timer_payload(self, payload):
        return {
            "game_running": payload["game_running"],
            "session_sec": payload["session_sec"],
            "streak_sec": payload["streak_sec"],
            "longest_sec": payload["longest_sec"],
            "survival_sec": payload["survival_sec"],
        }

    def session_time_sec(self):
        with self._lock:
            return int(self._session_sec)

    def current_streak_sec(self):
        with self._lock:
            if not self._game_active or self._life_start_ts is None:
                return self._paused_streak_sec
            return int(time.time() - self._life_start_ts)

    def longest_life_sec(self):
        with self._lock:
            return int(self._longest_life)

    def current_survival_sec(self):
        with self._lock:
            if not self._game_active or self._life_start_ts is None:
                return int(self._paused_survival_sec)
            return int(self._total_survival_sec + (time.time() - self._life_start_ts))

    def get_true_death_rate(self):
        with self._lock:
            return self._true_death_rate

    def get_items(self):
        with self._lock:
            return list(self._cached_items), self._items_collected, self._items_total

    def get_recent_deaths(self):
        with self._lock:
            return list(self._cached_deaths)

    def get_bosses(self):
        """Last bosses[] array from the status poll -- each entry has key/name/defeated/deaths."""
        with self._lock:
            return list(self._cached_bosses)

    def get_death_split(self):
        """Returns (boss_deaths_total, non_boss_deaths_total)."""
        with self._lock:
            return self._boss_deaths_total, self._non_boss_deaths_total

    def get_lifetime_playtime(self):
        """Returns (seconds, formatted_str) -- true lifetime played time, never reset."""
        with self._lock:
            return self._lifetime_playtime_sec, self._lifetime_playtime_fmt

    def get_deaths_per_hour(self):
        """Returns (session_deaths_per_hour, run_deaths_per_hour) -- either can be
        None if the respective played-time clock is under the server's 600s
        minimum-sample threshold. None means "not enough data yet," not zero."""
        with self._lock:
            return self._session_deaths_per_hour, self._run_deaths_per_hour

    def get_rage_state(self):
        with self._lock:
            return self._rage_pct, self._rage_name, self._hollow_streak

    def collect_item(self, item_name, on_done=None):
        def _do():
            try:
                r = self._http.post(
                    self._url("collect/"),
                    json={"item_name": item_name, "method": "app"},
                    headers=self._headers(), timeout=5,
                )
                if r.ok and on_done:
                    on_done(r.json())
            except Exception as e:
                log.warning("collect_item failed: %s", e)
        threading.Thread(target=_do, daemon=True).start()

    def uncollect_item(self, item_name, on_done=None):
        def _do():
            try:
                r = self._http.post(
                    self._url("uncollect/"),
                    json={"item_name": item_name},
                    headers=self._headers(), timeout=5,
                )
                if r.ok and on_done:
                    on_done(r.json())
            except Exception as e:
                log.warning("uncollect_item failed: %s", e)
        threading.Thread(target=_do, daemon=True).start()

    # ── Event hooks ───────────────────────────────────────────────────────────

    _MAX_LIFE_SEC = 43200  # 12h sanity cap — guards against stale timestamps

    def on_death(self, boss="", boss_key=None, on_death_response=None):
        if boss_key is None:
            boss_key = boss
        boss_key = _normalize_boss_key(boss_key)
        now = time.time()
        with self._lock:
            if self._death_in_flight:
                log.info("Death ignored -- request already in flight")
                return
            if now - self._last_death_request < 8.0:
                log.info("Death ignored -- request cooldown active")
                return
            self._death_in_flight = True
            self._last_death_request = now
            if boss or boss_key:
                self._current_boss = boss
                self._current_boss_key = boss_key
            self._local_mutation_ts = now
            self._local_mutation_kind = "death"
            self._pending_death_sync = True
        threading.Thread(
            target=self._post_death_immediate, args=(boss, boss_key, on_death_response), daemon=True
        ).start()

    def on_subtract(self):
        with self._lock:
            if self._subtract_in_flight:
                log.info("Subtract ignored -- request already in flight")
                return
            self._subtract_in_flight = True
            self._local_mutation_ts = time.time()
            self._local_mutation_kind = "subtract"
            self._pending_death_sync = False
        threading.Thread(target=self._post_subtract_immediate, daemon=True).start()

    def set_death_counts(self, total_deaths=None, session_deaths=None):
        total_value = max(0, int(total_deaths)) if total_deaths is not None else None
        session_value = max(0, int(session_deaths)) if session_deaths is not None else None
        with self._lock:
            if total_value is not None:
                self._local_deaths = total_value
                self._local_deaths_known = True
            if session_value is not None:
                self._local_session_deaths = session_value
            self._local_mutation_ts = time.time()
            self._local_mutation_kind = "set"
            self._pending_death_sync = False
        threading.Thread(
            target=self._post_death_count_corrections,
            args=(total_value, session_value),
            daemon=True,
        ).start()

    def _death_count_status(self, data):
        if isinstance(data, dict) and isinstance(data.get("status"), dict):
            return data["status"]
        return data if isinstance(data, dict) else {}

    def _apply_death_count_status(self, data):
        status = self._death_count_status(data)
        if not status:
            return {}
        with self._lock:
            total_deaths = status.get("total_deaths", status.get("deaths"))
            if total_deaths is not None:
                self._local_deaths = max(0, int(total_deaths or 0))
                self._local_deaths_known = True
            if "session_deaths" in status:
                self._local_session_deaths = max(0, int(status.get("session_deaths") or 0))
            if "boss_deaths_total" in status:
                self._boss_deaths_total = max(0, int(status.get("boss_deaths_total") or 0))
            if "non_boss_deaths_total" in status:
                self._non_boss_deaths_total = max(0, int(status.get("non_boss_deaths_total") or 0))
            current_boss_key = _normalize_boss_key(
                status.get("current_boss_key")
                or status.get("boss_key")
                or self._current_boss_key
            )
            if status.get("current_boss"):
                self._current_boss = status.get("current_boss") or ""
            elif status.get("boss"):
                self._current_boss = status.get("boss") or ""
            if current_boss_key:
                self._current_boss_key = current_boss_key
            if current_boss_key and "current_boss_deaths" in status:
                boss_deaths = max(0, int(status.get("current_boss_deaths") or 0))
                self._pending_boss_death_floors.pop(current_boss_key, None)
                for cached_boss in self._cached_bosses:
                    if _normalize_boss_key(cached_boss.get("key")) == current_boss_key:
                        cached_boss["key"] = current_boss_key
                        cached_boss["deaths"] = boss_deaths
                        break
                else:
                    self._cached_bosses.append({
                        "key": current_boss_key,
                        "name": self._current_boss or current_boss_key,
                        "defeated": False,
                        "deaths": boss_deaths,
                    })
            self._session_deaths_per_hour = status.get(
                "session_deaths_per_hour",
                self._session_deaths_per_hour,
            )
            self._run_deaths_per_hour = status.get(
                "run_deaths_per_hour",
                self._run_deaths_per_hour,
            )
            if "rage_pct" in status:
                self._rage_pct = float(status.get("rage_pct", 0) or 0)
            if "rage_name" in status:
                self._rage_name = status.get("rage_name") or "Maiden's Grace"
            if "hollow_streak" in status:
                self._hollow_streak = int(status.get("hollow_streak") or 0)
            if "longest_life" in status:
                self._longest_life = max(self._longest_life, float(status.get("longest_life") or 0))
            if "total_survival" in status:
                self._total_survival_sec = float(status.get("total_survival") or 0)
            if "current_life_sec" in status:
                current_life_sec = max(0, int(status.get("current_life_sec") or 0))
                self._life_start_ts = time.time() - current_life_sec if self._game_active else None
            self._pending_death_sync = False
        return status

    def _post_death_count_corrections(self, total_deaths=None, session_deaths=None):
        """Apply manual death corrections through explicit server endpoints.

        Server contract: when both need correction, set Total first, then This
        Session. These endpoints are corrections, not death events, so they do
        not alter boss attribution, Fury, or the current streak.
        """
        latest_status = None
        try:
            if total_deaths is not None:
                r = self._http.post(
                    self._url("set-total-deaths/"),
                    json={"total_deaths": total_deaths},
                    headers=self._headers(),
                    timeout=5,
                )
                if r.ok:
                    latest_status = self._apply_death_count_status(r.json()) or latest_status
                    log.info("set-total-deaths OK total=%d", total_deaths)
                else:
                    log.warning("set-total-deaths rejected: status=%d body=%r",
                                r.status_code, r.text[:300])

            if session_deaths is not None:
                r = self._http.post(
                    self._url("set-session-deaths/"),
                    json={"session_deaths": session_deaths},
                    headers=self._headers(),
                    timeout=5,
                )
                if r.ok:
                    latest_status = self._apply_death_count_status(r.json()) or latest_status
                    log.info("set-session-deaths OK session=%d", session_deaths)
                else:
                    log.warning("set-session-deaths rejected: status=%d body=%r",
                                r.status_code, r.text[:300])

            if latest_status and self._on_server_sync:
                self._on_server_sync(latest_status)
        except Exception as e:
            log.warning("Death count correction failed: %s", e)

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

    def _post_subtract_immediate(self):
        try:
            r = self._http.post(
                self._url("subtract-death/"),
                json={},
                headers=self._headers(),
                timeout=5,
            )
            if r.ok and r.content:
                status = self._apply_death_count_status(r.json())
                log.info(
                    "subtract-death OK total=%r session=%r boss_deaths=%r non_boss=%r",
                    status.get("total_deaths", status.get("deaths")),
                    status.get("session_deaths"),
                    status.get("boss_deaths_total"),
                    status.get("non_boss_deaths_total"),
                )
                if self._on_server_sync:
                    self._on_server_sync(status)
            else:
                log.warning(
                    "subtract-death rejected: status=%d body=%r",
                    r.status_code,
                    r.text[:300],
                )
                self._poll_status()
        except Exception as e:
            log.warning("subtract-death failed: %s", e)
            self._poll_status()
        finally:
            with self._lock:
                self._subtract_in_flight = False

    # ── Boss focus / mark / unmark ────────────────────────────────────────────

    def set_focus(self, boss_name, boss_key=None):
        """
        boss_key disambiguates bosses that share a boss_name across different
        locations (e.g. "Erdtree Avatar" fought in 6 different areas) -- always
        pass it. Falls back to boss_name if boss_key isn't given (legacy
        callers), but that reintroduces the collision risk the server-side
        boss_key field exists to fix.
        """
        if boss_key is None:
            boss_key = boss_name
        boss_key = _normalize_boss_key(boss_key)
        with self._lock:
            self._current_boss     = boss_name
            self._current_boss_key = boss_key
        try:
            r = self._http.post(self._url("set-focus/"),
                                json={"boss_name": boss_name, "boss_key": boss_key},
                                headers=self._headers(), timeout=5)
            if not r.ok:
                log.warning("set_focus %r (key=%r) → status=%d", boss_name, boss_key, r.status_code)
        except Exception as e:
            log.warning("set_focus failed: %s", e, exc_info=True)

    def clear_focus(self):
        with self._lock:
            self._current_boss     = ""
            self._current_boss_key = ""
        try:
            r = self._http.post(self._url("set-focus/"),
                                json={"boss_name": "", "boss_key": ""},
                                headers=self._headers(), timeout=5)
            log.info("clear_focus → status=%d body=%r", r.status_code, r.text[:200])
        except Exception as e:
            log.warning("clear_focus failed: %s", e)

    def mark_boss(self, boss_key):
        """Returns response dict with rage_pct/rage_name if successful, else None."""
        boss_key = _normalize_boss_key(boss_key)
        with self._lock:
            self._current_boss     = ""
            self._current_boss_key = ""
        try:
            r = self._http.post(
                self._url("boss/mark/"),
                json={"boss_key": boss_key},
                headers=self._headers(),
                timeout=5,
            )
            if not r.ok:
                log.warning("mark_boss %r → status=%d", boss_key, r.status_code)
            if not r.content:
                return None
            data = r.json()
            if data.get("ok"):
                with self._lock:
                    if "rage_pct" in data:
                        self._rage_pct = float(data.get("rage_pct", 0) or 0)
                    if "rage_name" in data:
                        self._rage_name = data.get("rage_name") or self._rage_name
                    for hollow_key in (
                        "hollow_streak",
                        "hollow_count",
                        "gone_hollow_count",
                        "hollow_deaths",
                        "hollow",
                    ):
                        if hollow_key in data:
                            self._hollow_streak = int(data.get(hollow_key) or 0)
                            break
                return data
            log.warning("mark_boss server rejected: status=%d body=%s", r.status_code, r.text[:300])
        except Exception as e:
            log.warning("mark_boss failed: %s", e)
        return None

    def unmark_boss(self, boss_key):
        boss_key = _normalize_boss_key(boss_key)
        threading.Thread(
            target=self._post, args=("boss/unmark/", {"boss_key": boss_key}), daemon=True
        ).start()

    def clear_boss_deaths(self, boss_key, on_done=None):
        """
        Clears death ATTRIBUTION for one boss (mis-click/testing correction)
        -- does NOT touch Total Deaths, since the deaths still happened,
        only the boss tag on those specific death_events rows was wrong.
        """
        boss_key = _normalize_boss_key(boss_key)
        def _do():
            try:
                r = self._http.post(
                    self._url("boss/clear-deaths/"),
                    json={"boss_key": boss_key},
                    headers=self._headers(), timeout=5,
                )
                if not r.ok:
                    log.warning("clear_boss_deaths %r → status=%d", boss_key, r.status_code)
                if on_done:
                    on_done(r.json() if r.ok and r.content else None)
            except Exception as e:
                log.warning("clear_boss_deaths failed: %s", e)
                if on_done:
                    on_done(None)
        threading.Thread(target=_do, daemon=True).start()

    def get_current_boss(self):
        with self._lock:
            return self._current_boss

    def get_current_boss_key(self):
        with self._lock:
            return self._current_boss_key

    # ── Build Planner reference data (no auth required -- public endpoints) ────
    # Mirrors QuestLogClient's copies of the same methods -- the Build tab
    # inside an active tracker window is handed a QuestLogSync (not a
    # QuestLogClient), and needs the same reference-data fetches to render
    # anything beyond the raw build detail (classes for the class picker,
    # stat-caps for bar coloring, ar-data/ar-variants for Attack Rating,
    # weapons/aow/affinities for equipment editing).

    def _get_public(self, path, game=None, extra_params=None, timeout=10):
        try:
            params = dict(extra_params or {})
            if game:
                params['game'] = game
            r = self._http.get(f"{BASE_URL}/api/soulslike/{path}/", params=params, timeout=timeout)
            if r.ok:
                data = r.json()
                self._catalog.store_public_response(path, data, game=game, extra_params=extra_params)
                return data
            cached = self._catalog.load_public_fallback(path, game=game, extra_params=extra_params)
            if cached is not None:
                log.warning("%s fetch returned HTTP %d; using cached catalog data", path, r.status_code)
                return cached
            return None
        except Exception as e:
            cached = self._catalog.load_public_fallback(path, game=game, extra_params=extra_params)
            if cached is not None:
                log.warning("%s fetch failed; using cached catalog data: %s", path, e)
                return cached
            log.warning("%s fetch failed: %s", path, e)
            return None

    def get_classes(self, game='elden_ring'):
        data = self._get_public('classes', game=game)
        return data.get('classes', []) if data else []

    def get_stat_caps(self, game='elden_ring'):
        data = self._get_public('stat-caps', game=game)
        return data.get('caps', []) if data else []

    def get_derived_curves(self, game='elden_ring'):
        data = self._get_public('derived-curves', game=game)
        return data.get('curves', {}) if data else {}

    def get_ar_data(self, game='elden_ring'):
        return self._get_public('ar-data', game=game) or {}

    def get_ar_variants(self, weapon_name, game='elden_ring'):
        import urllib.parse
        path = f"weapons/{urllib.parse.quote(weapon_name, safe='')}/ar-variants"
        data = self._get_public(path, game=game)
        if not data:
            data = self._catalog.load_ar_variants_fallback(weapon_name, game)
        elif data.get('variants') is not None:
            self._catalog.store_ar_variants(weapon_name, data, game)
        return data.get('variants', []) if data else []

    def get_weapons(self, game='elden_ring', weapon_type=None, q=None, limit=1000):
        extra = {'limit': limit}
        if weapon_type:
            extra['type'] = weapon_type
        if q:
            extra['q'] = q
        return self._get_public('weapons', game=game, extra_params=extra) or {'weapons': [], 'weapon_types': []}

    def get_aow(self, game='elden_ring', q=None, limit=1000):
        extra = {'limit': limit}
        if q:
            extra['q'] = q
        data = self._get_public('aow', game=game, extra_params=extra)
        return data.get('aow', []) if data else []

    def get_armor(self, q=None, limit=1000):
        extra = {'limit': limit}
        if q:
            extra['q'] = q
        data = self._get_public('armor', game='elden_ring', extra_params=extra)
        return data.get('armor', []) if data else []

    def get_talismans(self, game='elden_ring', q=None, limit=1000):
        extra = {'limit': limit}
        if q:
            extra['q'] = q
        data = self._get_public('talismans', game=game, extra_params=extra)
        return data.get('talismans', []) if data else []

    def get_spirit_ashes(self, game='elden_ring'):
        data = self._get_public('spirit-ashes', game=game)
        return data.get('ashes', []) if data else []

    def get_crystal_tears(self, game='elden_ring'):
        if game == 'err':
            data = self._get_public('err/crystal-tears')
        else:
            data = self._get_public('crystal-tears', game=game)
        return data.get('tears', []) if data else []

    def get_enkindling(self):
        return self._get_public('err/enkindling') or {}

    def get_enkindling_eligible(self, aow_name):
        data = self._get_public('err/enkindling/eligible', extra_params={'aow': aow_name})
        return data.get('affixes', []) if data else []

    def get_err_aow_skills(self, q=None, limit=1000):
        extra = {'limit': limit}
        if q:
            extra['q'] = q
        data = self._get_public('err/aow-skills', extra_params=extra)
        return data.get('skills', []) if data else []

    def get_affinities_err(self):
        data = self._get_public('err/affinities')
        return data.get('affinities', []) if data else []

    def get_curios(self):
        return self._get_public('err/curios') or {}

    def get_fortunes(self):
        data = self._get_public('err/fortunes')
        return data.get('fortunes', []) if data else []

    def get_runeforging(self):
        return self._get_public('err/runeforging') or {}

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

    def get_build_detail(self, build_id, game='elden_ring'):
        """
        Full build detail (stats, class, every equipped slot) for one build --
        same response shape as the web's /builds/<share_token>/ endpoint
        (see CHARACTER_BUILDER_APP_HANDOFF.md section 3), but reached via the
        desktop endpoint (X-Listener-Key auth) instead of session-cookie auth.
        Returns None on any failure -- caller shows a load-error state rather
        than a half-populated build.
        """
        try:
            r = self._http.get(
                f"{BASE_URL}/api/soulslike/desktop/builds/{build_id}/",
                headers=self._headers(),
                params={'game': game},
                timeout=10,
            )
            if not r.ok:
                log.warning("get_build_detail(%s, game=%s) non-200: status=%d body=%r",
                            build_id, game, r.status_code, r.text[:300])
                return self._get_shared_build_detail(build_id, game)
            return r.json()
        except Exception as e:
            log.warning("get_build_detail(%s, game=%s) failed: %s", build_id, game, e)
            return self._get_shared_build_detail(build_id, game)

    def _get_shared_build_detail(self, build_key, game='elden_ring'):
        """Fallback for build rows keyed by share_token instead of desktop id."""
        try:
            r = self._http.get(
                f"{BASE_URL}/api/soulslike/builds/{build_key}/",
                params={'game': game},
                timeout=10,
            )
            if not r.ok:
                log.warning("get_shared_build_detail(%s, game=%s) non-200: status=%d body=%r",
                            build_key, game, r.status_code, r.text[:300])
                return None
            return r.json()
        except Exception as e:
            log.warning("get_shared_build_detail(%s, game=%s) failed: %s", build_key, game, e)
            return None

    def save_build(self, build_data: dict, game='elden_ring'):
        try:
            r = self._http.post(
                f"{BASE_URL}/api/soulslike/desktop/builds/",
                headers=self._headers(),
                params={'game': game},
                json=build_data,
                timeout=30,
            )
            if not r.ok:
                log.warning("save_build(game=%s) non-200: status=%d body=%r",
                            game, r.status_code, r.text[:500])
                try:
                    return r.json()
                except Exception:
                    return {"error": f"HTTP {r.status_code}"}
            data = r.json()
            log.info(
                "save_build(game=%s) ok id=%r build_id=%r share_token=%r",
                game,
                data.get("id"),
                data.get("build_id"),
                data.get("share_token"),
            )
            return data
        except Exception as e:
            log.warning("save_build failed: %s", e)
            return {"error": str(e)}

    def delete_build(self, build_id: int, game='elden_ring'):
        try:
            r = self._http.post(
                f"{BASE_URL}/api/soulslike/desktop/builds/{build_id}/delete/",
                headers=self._headers(),
                params={'game': game},
                timeout=10,
            )
            return r.json().get('ok', False) if r.ok else False
        except Exception as e:
            log.warning("delete_build failed: %s", e)
            return False

    # ── Aliases (same interface as QuestLogClient) ────────────────────────────

    def post_death(self, boss="", boss_key=None):
        self.on_death(boss, boss_key=boss_key)

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

    def notify_run_ended(self):
        """
        Posts to /end/ WITHOUT calling self.stop() -- for the explicit
        "End Run" button, which ends the run server-side but keeps this
        QuestLogSync instance's heartbeat/status-poll loop alive so the
        app keeps ticking/syncing after the click (unlike end_run(), used
        by _stop_active() where this instance is discarded right after
        anyway). Calling end_run() here instead would silently kill the
        poll loop while self._ql_sync stayed non-None, leaving the UI
        looking alive but never receiving another status update.
        """
        threading.Thread(target=self._post, args=("end/", {}), daemon=True).start()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _post(self, path, payload):
        try:
            self._http.post(self._url(path), json=payload,
                            headers=self._headers(), timeout=5)
        except Exception as e:
            log.warning("POST %s failed: %s", path, e)

    def _post_death_immediate(self, boss="", boss_key=None, on_death_response=None):
        """POST death then immediately push timers with streak=0."""
        if boss_key is None:
            boss_key = boss
        boss_key = _normalize_boss_key(boss_key)
        r = None
        try:
            if boss or boss_key:
                focus_resp = self._http.post(
                    self._url("set-focus/"),
                    json={"boss_name": boss, "boss_key": boss_key},
                    headers=self._headers(), timeout=5,
                )
                if not focus_resp.ok:
                    log.warning("Pre-death focus rejected: status=%d body=%r boss=%r boss_key=%r",
                                focus_resp.status_code, focus_resp.text[:300], boss, boss_key)
            post_boss = boss_key or boss
            payload = self._timer_payload(game_running=True, streak_override=0)
            payload.update({"boss": post_boss, "boss_key": boss_key, "source": "listener"})
            r = self._http.post(self._url("death/"),
                                json=payload,
                                headers=self._headers(), timeout=5)
            if not r.ok:
                log.warning("Death post rejected: status=%d body=%r boss=%r boss_key=%r",
                            r.status_code, r.text[:300], boss, boss_key)
                fallback = {"boss": post_boss, "boss_key": boss_key, "source": "listener"}
                r = self._http.post(self._url("death/"),
                                    json=fallback,
                                    headers=self._headers(), timeout=5)
                if not r.ok:
                    log.warning("Death post fallback rejected: status=%d body=%r boss=%r boss_key=%r",
                                r.status_code, r.text[:300], boss, boss_key)
            if r.ok:
                response_data = r.json()
                status = self._apply_death_count_status(response_data)
                log.info(
                    "Death post OK boss=%r boss_key=%r total=%r session=%r boss_deaths=%r non_boss=%r duplicate=%r",
                    boss,
                    boss_key,
                    status.get("total_deaths", status.get("deaths")),
                    status.get("session_deaths"),
                    status.get("boss_deaths_total"),
                    status.get("non_boss_deaths_total"),
                    status.get("duplicate"),
                )
                if self._on_server_sync:
                    self._on_server_sync(status)
            if r.ok and on_death_response:
                try:
                    on_death_response(response_data)
                except Exception:
                    pass
            if not r.ok:
                self._poll_status()
        except Exception as e:
            log.warning("Death post failed: %s", e)
            self._poll_status()
        if r is not None and r.ok:
            self._push_timers(streak_override=0)
        with self._lock:
            self._death_in_flight = False
