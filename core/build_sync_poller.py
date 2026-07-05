"""
Polls the QL API every 5 minutes when a user is logged in.

Checks two things per cycle:
  - Builds (elden_ring + err) via /api/soulslike/desktop/builds/
  - Active runs via /api/soulslike/desktop/profile/

Callbacks fire on the bg thread — callers must marshal to Qt main thread via signals.
"""

import threading
import time

import requests

from core.crash_logger import get_logger

log = get_logger("questlog.build_poller")

BASE_URL      = "https://questlog.casual-heroes.com"
POLL_INTERVAL = 300   # 5 minutes
GAMES         = ("elden_ring", "err")


class BuildSyncPoller:
    def __init__(self, api_key: str, on_builds_updated, on_runs_updated=None,
                 active_token_fn=None):
        """
        api_key           — QL listener key
        on_builds_updated — callback(builds, added, removed, updated)
        on_runs_updated   — callback(active_runs, run_history) or None
        active_token_fn   — zero-arg callable returning the token of the run the
                            app is currently heartbeating, so we never overwrite it
        """
        self._api_key         = api_key
        self._on_builds       = on_builds_updated
        self._on_runs         = on_runs_updated
        self._active_token_fn = active_token_fn or (lambda: None)
        self._known_builds    = {}   # {(game, id): build_dict}
        self._known_run_tokens = set()  # tokens seen from last run poll
        self._running         = False
        self._thread          = None
        self._http            = requests.Session()
        self._http.verify     = True
        self._http.headers.update({
            "User-Agent":    "QuestLog-EldenTracker/1.0.2b",
            "X-App-Version": "1.0.2",
        })

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        log.info("QLPoller started")

    def stop(self):
        self._running = False
        log.info("QLPoller stopped")

    def force_refresh(self):
        """Call immediately after a local create/delete so UI doesn't wait 5 min."""
        threading.Thread(target=self._fetch_and_diff, daemon=True).start()

    # ── Loop ──────────────────────────────────────────────────────────────────

    def _loop(self):
        self._fetch_and_diff()
        while self._running:
            time.sleep(POLL_INTERVAL)
            if self._running:
                self._fetch_and_diff()

    def _fetch_and_diff(self):
        self._diff_builds()
        self._diff_runs()

    # ── Builds ────────────────────────────────────────────────────────────────

    def _diff_builds(self):
        new_map = {}
        for game in GAMES:
            for b in self._fetch_builds(game):
                new_map[(game, b["id"])] = {**b, "game": game}

        added   = [k for k in new_map if k not in self._known_builds]
        removed = [k for k in self._known_builds if k not in new_map]
        changed = [
            k for k in new_map
            if k in self._known_builds
            and new_map[k].get("updated_at") != self._known_builds[k].get("updated_at")
        ]

        if added or removed or changed:
            self._known_builds = new_map
            all_builds = sorted(new_map.values(),
                                key=lambda b: b.get("updated_at", 0), reverse=True)
            log.info("Build diff — +%d -%d ~%d", len(added), len(removed), len(changed))
            try:
                self._on_builds(all_builds, added=added, removed=removed, updated=changed)
            except Exception as e:
                log.warning("on_builds_updated error: %s", e)

    def _fetch_builds(self, game: str) -> list:
        try:
            r = self._http.get(
                f"{BASE_URL}/api/soulslike/desktop/builds/",
                headers={"X-Listener-Key": self._api_key},
                params={"game": game},
                timeout=10,
            )
            if r.status_code == 401:
                log.warning("Build poll 401 — stopping poller")
                self.stop()
                return []
            r.raise_for_status()
            builds = r.json().get("builds", [])
            if builds:
                log.info("_fetch_builds sample keys game=%s: %s", game, list(builds[0].keys()))
            return builds
        except requests.Timeout:
            log.debug("Build poll timeout game=%s", game)
            return []
        except requests.ConnectionError:
            log.debug("Build poll offline game=%s", game)
            return []
        except Exception as e:
            log.warning("Build poll error game=%s: %s", game, e)
            return []

    # ── Runs ──────────────────────────────────────────────────────────────────

    def _diff_runs(self):
        if not self._on_runs:
            return
        active_runs, run_history = self._fetch_runs()
        if active_runs is None:
            return  # network error — skip

        server_tokens = {r.get("token") for r in active_runs if r.get("token")}
        active_token  = self._active_token_fn()

        added   = server_tokens - self._known_run_tokens
        removed = self._known_run_tokens - server_tokens

        # Never report a removal for the run the app is currently tracking
        if active_token:
            removed.discard(active_token)

        if added or removed:
            self._known_run_tokens = server_tokens
            log.info("Run diff — +%d -%d", len(added), len(removed))
            try:
                self._on_runs(active_runs, run_history)
            except Exception as e:
                log.warning("on_runs_updated error: %s", e)

    def _fetch_runs(self):
        """Returns (active_runs, run_history) or (None, None) on error."""
        try:
            r = self._http.get(
                f"{BASE_URL}/api/soulslike/desktop/profile/",
                headers={"X-Listener-Key": self._api_key},
                timeout=10,
            )
            if r.status_code == 401:
                log.warning("Run poll 401 — stopping poller")
                self.stop()
                return None, None
            r.raise_for_status()
            data = r.json()
            return data.get("active_runs", []), data.get("run_history", [])
        except requests.Timeout:
            log.debug("Run poll timeout")
            return None, None
        except requests.ConnectionError:
            log.debug("Run poll offline")
            return None, None
        except Exception as e:
            log.warning("Run poll error: %s", e)
            return None, None
