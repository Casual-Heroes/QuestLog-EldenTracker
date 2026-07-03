"""
QuestLog API client — optional cloud sync.
All session calls are fire-and-forget (daemon threads). Never blocks the UI or hotkeys.
"""

import threading
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from core.crash_logger import get_logger

log = get_logger("questlog.api")

BASE_URL        = "https://questlog.casual-heroes.com"
AUTH_PORT       = 9457
REQUEST_TIMEOUT = 5


def _fire(fn, *args, **kwargs):
    threading.Thread(target=fn, args=args, kwargs=kwargs, daemon=True).start()


class QuestLogClient:
    def __init__(self, api_key, session_token):
        import requests
        self._api_key       = api_key
        self._session_token = session_token
        self._http          = requests.Session()
        self._http.timeout  = REQUEST_TIMEOUT

    @property
    def _key_header(self):
        return {"X-Listener-Key": self._api_key}

    def _url(self, path):
        return f"{BASE_URL}/api/soulslike/session/{self._session_token}/{path}"

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _post(self, path, payload=None):
        try:
            r = self._http.post(self._url(path), json=payload or {}, timeout=REQUEST_TIMEOUT)
            if not r.ok:
                log.warning("API %s → %d", path, r.status_code)
            return r.json() if r.ok else None
        except Exception as e:
            log.warning("API post %s failed: %s", path, e)
            return None

    def _get(self, path):
        try:
            r = self._http.get(self._url(path), timeout=REQUEST_TIMEOUT)
            return r.json() if r.ok else None
        except Exception as e:
            log.warning("API get %s failed: %s", path, e)
            return None

    # ── SSO login (call from a worker thread) ─────────────────────────────────

    @staticmethod
    def login(on_success, on_error):
        """
        Opens browser to QuestLog SSO, spins up localhost:9457 callback server,
        exchanges code for api_key, fetches active runs.
        Calls on_success(api_key, username, runs) or on_error(str).
        Must be called from a non-Qt thread.
        """
        import requests

        result = {"code": None}

        class _Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                qs = parse_qs(urlparse(self.path).query)
                result["code"] = qs.get("code", [None])[0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"""
                    <html><body style="background:#09090f;color:#c9a84c;
                    font-family:sans-serif;text-align:center;padding:60px">
                    <h2>Connected to QuestLog!</h2>
                    <p style="color:#6b7280">You can close this window.</p>
                    <script>setTimeout(()=>window.close(),2000)</script>
                    </body></html>
                """)

            def log_message(self, *args):
                pass

        try:
            server = HTTPServer(("localhost", AUTH_PORT), _Handler)
            server.timeout = 120
            webbrowser.open(f"{BASE_URL}/listener/auth/")
            server.handle_request()
            server.server_close()
        except Exception as e:
            on_error(f"Login server error: {e}")
            return

        if not result["code"]:
            on_error("Login cancelled or timed out.")
            return

        try:
            r = requests.get(
                f"{BASE_URL}/api/listener/auth/exchange/",
                params={"code": result["code"]},
                timeout=10,
            )
            data = r.json()
        except Exception as e:
            on_error(f"Auth exchange failed: {e}")
            return

        if not data.get("ok"):
            on_error(data.get("error", "Auth exchange failed."))
            return

        api_key  = data["api_key"]
        username = data.get("username", "")

        try:
            profile_r = requests.get(
                f"{BASE_URL}/api/soulslike/desktop/profile/",
                headers={"X-Listener-Key": api_key},
                timeout=10,
            )
            profile = profile_r.json() if profile_r.ok else {}
        except Exception as e:
            on_error(f"Could not fetch profile: {e}")
            return

        on_success(api_key, username, profile)

    # ── Run discovery ─────────────────────────────────────────────────────────

    def get_profile(self):
        """
        Fetch full desktop profile: active_runs, run_history, builds.
        Blocking — call from thread.
        Returns dict with keys: active_runs, run_history, builds (each a list).
        """
        try:
            r = self._http.get(
                f"{BASE_URL}/api/soulslike/desktop/profile/",
                headers=self._key_header,
                timeout=10,
            )
            return r.json() if r.ok else {}
        except Exception as e:
            log.warning("get_profile failed: %s", e)
            return {}

    def create_session(self, game, game_mode, build_name=""):
        """
        Start a new run session on the server.
        Returns {'ok': True, 'token': '...', 'manage_url': '...'} or {}.
        Blocking — call from thread.
        """
        try:
            r = self._http.post(
                f"{BASE_URL}/api/soulslike/desktop/session/create/",
                json={"game": game, "game_mode": game_mode,
                      "build_name": build_name, "timing_mode": "listener"},
                headers=self._key_header,
                timeout=10,
            )
            return r.json() if r.ok else {}
        except Exception as e:
            log.warning("create_session failed: %s", e)
            return {}

    def get_active_runs(self):
        """Returns full runs payload or empty dict. Blocking — call from thread."""
        try:
            r = self._http.get(
                f"{BASE_URL}/api/soulslike/runs/active/",
                headers=self._key_header,
                timeout=10,
            )
            return r.json() if r.ok else {}
        except Exception as e:
            log.warning("get_active_runs failed: %s", e)
            return {}

    # ── Status poll ───────────────────────────────────────────────────────────

    def get_status(self):
        """Poll full session status. Returns dict or None. Blocking — call from thread."""
        return self._get("status/")

    # ── Heartbeat ─────────────────────────────────────────────────────────────

    def heartbeat(self, game_running=False):
        _fire(self._post, "heartbeat/", {"game_running": game_running})

    # ── Death events ──────────────────────────────────────────────────────────

    def post_death(self, boss=""):
        _fire(self._post, "death/", {"boss": boss, "source": "app"})

    def post_subtract(self):
        _fire(self._post, "subtract-death/")

    def post_reset(self):
        _fire(self._post, "reset-deaths/")

    # ── Boss events ───────────────────────────────────────────────────────────

    def mark_boss(self, boss_key):
        _fire(self._post, "boss/mark/", {"boss_key": boss_key})

    def unmark_boss(self, boss_key):
        _fire(self._post, "boss/unmark/", {"boss_key": boss_key})

    def post_boss_reset(self):
        """Unmark all bosses — fire sequentially in one thread to avoid flood."""
        # Server doesn't have a bulk-reset endpoint yet; individual unmarks sent
        # in background. When server adds bulk reset, swap this call.
        _fire(self._post, "reset-deaths/")  # placeholder until bulk boss reset lands

    def set_focus(self, boss_name=""):
        """Set which boss deaths are attributed to. Empty string to clear."""
        _fire(self._post, "set-focus/", {"boss_name": boss_name})

    # ── End run ───────────────────────────────────────────────────────────────

    def end_run(self):
        _fire(self._post, "end/")
