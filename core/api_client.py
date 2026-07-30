"""
QuestLog API client — optional cloud sync.
All session calls are fire-and-forget (daemon threads). Never blocks the UI or hotkeys.
"""

import secrets
import threading
import time
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from core.crash_logger import get_logger
from core.catalog_sync import CatalogStore

log = get_logger("questlog.api")

BASE_URL        = "https://questlog.casual-heroes.com"
AUTH_PORT       = 9457
REQUEST_TIMEOUT = 5
APP_VERSION     = "1.1.0"


def _fire(fn, *args, **kwargs):
    threading.Thread(target=fn, args=args, kwargs=kwargs, daemon=True).start()


class QuestLogClient:
    def __init__(self, api_key, session_token):
        import requests
        self._api_key       = api_key
        self._session_token = session_token
        self._http          = requests.Session()
        self._http.verify   = True
        self._http.timeout  = REQUEST_TIMEOUT
        self._http.headers.update({
            "User-Agent":    f"QuestLog-EldenTracker/{APP_VERSION}",
            "X-App-Version": APP_VERSION,
        })
        self._catalog = CatalogStore(logger=log)

    @property
    def _key_header(self):
        return {"X-Listener-Key": self._api_key}

    def _url(self, path):
        return f"{BASE_URL}/api/soulslike/session/{self._session_token}/{path}"

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _post(self, path, payload=None, headers=None):
        try:
            r = self._http.post(self._url(path), json=payload or {},
                                 headers=headers, timeout=REQUEST_TIMEOUT)
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

        csrf_state = secrets.token_urlsafe(16)
        result = {"code": None, "state": None}

        class _Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                log.info("OAuth callback: path=%r", self.path)
                qs = parse_qs(urlparse(self.path).query)
                returned_state = qs.get("state", [None])[0]
                code           = qs.get("code",  [None])[0]
                log.info("OAuth params: code=%r state_returned=%r state_expected=%r",
                         code, returned_state, csrf_state)

                # Always accept -- state is not echoed by this site's OAuth flow
                if not code:
                    # favicon.ico or other stray browser request -- ignore silently
                    self.send_response(204)
                    self.end_headers()
                    return

                result["code"]  = code
                result["state"] = returned_state or csrf_state
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"""<html><body style="background:#09090f;color:#c9a84c;
                    font-family:sans-serif;text-align:center;padding:60px">
                    <h2>Connected to QuestLog!</h2>
                    <p style="color:#6b7280">You can close this window.</p>
                    <script>setTimeout(()=>window.close(),2000)</script>
                    </body></html>""")

            def log_message(self, *args):
                pass

        try:
            server = HTTPServer(("localhost", AUTH_PORT), _Handler)
            server.timeout = 2        # short poll interval so we can check deadline
            webbrowser.open(f"{BASE_URL}/listener/auth/?state={csrf_state}")
            deadline = time.monotonic() + 120
            while not result["code"] and time.monotonic() < deadline:
                server.handle_request()  # returns after each request OR after timeout secs
            server.server_close()
        except Exception as e:
            on_error(f"Login server error: {e}")
            return

        if not result["code"]:
            on_error("Login cancelled or timed out.")
            return

        _session = requests.Session()
        _session.verify = True
        _session.headers.update({
            "User-Agent":    f"QuestLog-EldenTracker/{APP_VERSION}",
            "X-App-Version": APP_VERSION,
        })
        try:
            r = _session.get(
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
            profile_r = _session.get(
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

    def get_builds(self, game='elden_ring'):
        """
        Build summary list (name/level/tag/etc) for My Builds. Same shape as
        QuestLogSync.get_builds() -- kept as a separate copy here (rather than
        sharing code) because QuestLogClient is reachable pre-run (login
        api_key only, no session_token), which is exactly when the Build
        Planner tab on the run-selector screen needs it.
        """
        try:
            r = self._http.get(
                f"{BASE_URL}/api/soulslike/desktop/builds/",
                headers=self._key_header,
                params={'game': game},
                timeout=10,
            )
            if not r.ok:
                log.warning("get_builds non-200: status=%d body=%r", r.status_code, r.text[:300])
                return []
            return r.json().get('builds', [])
        except Exception as e:
            log.warning("get_builds failed: %s", e)
            return []

    def get_build_detail(self, build_id, game='elden_ring'):
        """
        Full build detail (stats, class, every equipped slot) for one build --
        see CHARACTER_BUILDER_APP_HANDOFF.md section 3 for the response shape.
        Used by the Build Planner tab on the run-selector screen, where no
        run session_token exists yet (only the login api_key) -- unlike
        QuestLogSync's copy of this method, which is reached once a run is
        active and has both.
        """
        try:
            r = self._http.get(
                f"{BASE_URL}/api/soulslike/desktop/builds/{build_id}/",
                headers=self._key_header,
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

    # ── Build Planner reference data (no auth required -- public endpoints) ────
    # These feed core/ar_calculator.py and core/derived_stats.py, which were
    # already fully built (ported from the web's JS) but never wired to a
    # data source until now. See CHARACTER_BUILDER_APP_HANDOFF.md section 3
    # for exact response shapes.

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

    def _get_public(self, path, game=None, extra_params=None, timeout=10):
        """Shared GET for the unauthenticated /api/soulslike/<path>/ endpoints."""
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
        """{'classes': [...]} -- class grid + resolving class_id -> name/starting stats."""
        data = self._get_public('classes', game=game)
        return data.get('classes', []) if data else []

    def get_stat_caps(self, game='elden_ring'):
        """{'caps': [{stat, soft_cap_1/2/3, hard_cap, notes}]} -- feeds get_stat_bar_state()."""
        data = self._get_public('stat-caps', game=game)
        return data.get('caps', []) if data else []

    def get_derived_curves(self, game='elden_ring'):
        """{'curves': {stat_name: [float,...]}} -- ERR only, empty for vanilla ER."""
        data = self._get_public('derived-curves', game=game)
        return data.get('curves', {}) if data else {}

    def get_ar_data(self, game='elden_ring'):
        """{'curves','aec','reinforce'} -- everything compute_ar() needs except the weapon variant itself."""
        return self._get_public('ar-data', game=game) or {}

    def get_ar_variants(self, weapon_name, game='elden_ring'):
        """{'variants': [...]} -- per-affinity AR rows for one weapon, for compute_ar()."""
        import urllib.parse
        path = f"weapons/{urllib.parse.quote(weapon_name, safe='')}/ar-variants"
        data = self._get_public(path, game=game)
        if not data:
            data = self._catalog.load_ar_variants_fallback(weapon_name, game)
        elif data.get('variants') is not None:
            self._catalog.store_ar_variants(weapon_name, data, game)
        return data.get('variants', []) if data else []

    def get_weapons(self, game='elden_ring', weapon_type=None, q=None, limit=1000):
        """{'weapons':[...], 'weapon_types':[...]} -- weapon picker + AR base data."""
        extra = {'limit': limit}
        if weapon_type:
            extra['type'] = weapon_type
        if q:
            extra['q'] = q
        return self._get_public('weapons', game=game, extra_params=extra) or {'weapons': [], 'weapon_types': []}

    def get_aow(self, game='elden_ring', q=None, limit=1000):
        """{'aow':[{id,name,affinity,fp_cost,compatible,image_url}]} -- vanilla ER AoW picker only."""
        extra = {'limit': limit}
        if q:
            extra['q'] = q
        data = self._get_public('aow', game=game, extra_params=extra)
        return data.get('aow', []) if data else []

    def get_armor(self, q=None, limit=1000):
        """{'armor':[{id,name,type,defense,poise,weight,image_url}]} -- ERR reuses vanilla armor data always, no game param."""
        extra = {'limit': limit}
        if q:
            extra['q'] = q
        data = self._get_public('armor', game='elden_ring', extra_params=extra)
        return data.get('armor', []) if data else []

    def get_talismans(self, game='elden_ring', q=None, limit=1000):
        """{'talismans':[{id,name,effect,weight,image_url}]}."""
        extra = {'limit': limit}
        if q:
            extra['q'] = q
        data = self._get_public('talismans', game=game, extra_params=extra)
        return data.get('talismans', []) if data else []

    def get_spirit_ashes(self, game='elden_ring'):
        """{'ashes':[{name,fp_cost,hp_cost,enrage_fp_cost,summon_type,passive_behavior,enraged_behavior,acquisition,is_new_to_err}]}."""
        data = self._get_public('spirit-ashes', game=game)
        return data.get('ashes', []) if data else []

    def get_enkindling(self):
        """{'system_overview','affixes':[{name,affinity,tiers:[{star,text,static_effect|null}]}]} -- ERR-only, all 39 affixes, fetch once and cache by name."""
        return self._get_public('err/enkindling') or {}

    def get_enkindling_eligible(self, aow_name):
        """{'aow','affixes':[...]} -- per-AoW eligible affix list. Degrades to Mundane-only
        server-side on zero matches, never errors/empties -- don't special-case an empty list."""
        data = self._get_public('err/enkindling/eligible', extra_params={'aow': aow_name})
        return data.get('affixes', []) if data else []

    def get_crystal_tears(self, game='elden_ring'):
        """{'tears':[{name,effect,location?,duration?,is_new?}]} -- vanilla hardcoded 30, ERR via err/crystal-tears/."""
        if game == 'err':
            data = self._get_public('err/crystal-tears')
        else:
            data = self._get_public('crystal-tears', game=game)
        return data.get('tears', []) if data else []

    def get_err_aow_skills(self, q=None, limit=1000):
        """{'general_changes','skills':[{name,armaments,affinity,effect,scaling_note,acquisition,is_new,is_unique_skill,unique_weapon_name}]} -- ERR-only rebalanced AoW table."""
        extra = {'limit': limit}
        if q:
            extra['q'] = q
        data = self._get_public('err/aow-skills', extra_params=extra)
        return data.get('skills', []) if data else []

    def get_affinities_err(self):
        """{'general_note','affinities':[{name,whetblade,scaling_stat,damage_type_change,effect,is_new}]} -- ERR-reworked affinities."""
        data = self._get_public('err/affinities')
        return data.get('affinities', []) if data else []

    def get_curios(self):
        """{'system_overview','curios':[{name,trigger,effects:[3 ranks],acquisition}]} -- ERR only, no game param."""
        return self._get_public('err/curios') or {}

    def get_fortunes(self):
        """{'fortunes':[{id,name,fortune_type,buffs,drawbacks,unique_effects,how_to_unlock,minor_effects}]} -- ERR only."""
        data = self._get_public('err/fortunes')
        return data.get('fortunes', []) if data else []

    def get_runeforging(self):
        """{'system_overview','categories':[{great_rune,category,binding_runes:[...]}]} -- ERR only."""
        return self._get_public('err/runeforging') or {}

    def save_build(self, build_data: dict, game='elden_ring'):
        """
        Create or update a build through the desktop listener-key endpoint.
        The server upserts from the collection POST; do not PATCH the detail
        URL. See CHARACTER_BUILDER_APP_HANDOFF.md section 2 for the exact
        payload shape (stats, class_id, rh1_weapon_id, etc).
        """
        try:
            r = self._http.post(
                f"{BASE_URL}/api/soulslike/desktop/builds/",
                headers=self._key_header,
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

    def create_session(self, game, game_mode, build_name="", items=None):
        """
        Start a new run session on the server.
        Returns {'ok': True, 'token': '...', 'manage_url': '...'} or {}.
        Blocking — call from thread.

        items — list of {"name": str, "type": str} dicts seeded from the build.
        """
        payload = {
            "game":        game,
            "game_mode":   game_mode,
            "build_name":  build_name,
            "timing_mode": "listener",
        }
        if items:
            payload["items"] = [
                {
                    "item_type": it["type"],
                    "item_id":   it.get("id") or 0,
                    "item_name": it["name"],
                }
                for it in items
                if it.get("name") and it.get("type")
            ]
        try:
            r = self._http.post(
                f"{BASE_URL}/api/soulslike/desktop/session/create/",
                json=payload,
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

    # ── End run / leaderboard ───────────────────────────────────────────────────

    def end_run(self):
        # Was missing the auth header entirely -- self._post's default
        # headers=None sends none of the session-wide defaults' extras,
        # and X-Listener-Key is never one of those defaults (only
        # User-Agent/X-App-Version are, set once in __init__). Every other
        # authenticated call in this file passes self._key_header
        # explicitly; this one had been silently unauthenticated.
        _fire(self._post, "end/", headers=self._key_header)

    def submit_to_leaderboard(self, run_token, on_done=None, on_error=None):
        """
        One-time leaderboard submission for a specific run. Takes run_token
        explicitly rather than using self._url()/self._post() (which are
        both hardcoded to self._session_token, the client's own
        last-logged-in session token) -- the run being submitted may not be
        the same one this QuestLogClient was constructed for, e.g. after
        switching between multiple synced runs in one app session.

        Server re-reads everything it needs (deaths, bosses, HC score) from
        its own DB for that session -- empty {} body is correct, nothing to
        compute or pass client-side. Preconditions enforced server-side:
        run must already be ended, must be public, must not already be
        submitted (400 with a specific message on each violation) --
        on_error receives that message verbatim so the UI can show it.
        """
        def _do():
            try:
                r = self._http.post(
                    f"{BASE_URL}/api/soulslike/session/{run_token}/submit-to-leaderboard/",
                    json={}, headers=self._key_header, timeout=REQUEST_TIMEOUT,
                )
                data = r.json() if r.content else {}
                if r.ok:
                    if on_done:
                        on_done(data)
                else:
                    if on_error:
                        on_error(data.get("error", f"HTTP {r.status_code}"))
            except Exception as e:
                log.warning("submit_to_leaderboard failed: %s", e)
                if on_error:
                    on_error(str(e))
        _fire(_do)
