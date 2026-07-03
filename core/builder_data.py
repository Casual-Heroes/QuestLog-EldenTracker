"""
Build planner data loader.
Fetches all game data from the QuestLog API on startup, caches to disk.
All data is loaded into dicts keyed by id for O(1) lookup.
AR variants are lazy-loaded per weapon and cached in memory.
"""

import json
import os
import threading
import time
from core.paths import data as _data_path
from core.crash_logger import get_logger

log = get_logger("questlog.builder")

BASE_URL     = "https://questlog.casual-heroes.com"
CACHE_TTL_H  = 24    # hours before re-fetching from server
CACHE_DIR    = _data_path("builder_cache")


# ── In-memory data stores ──────────────────────────────────────────────────────

class BuilderData:
    """Holds all game data for one game (elden_ring or err)."""

    def __init__(self, game):
        self.game = game

        self.classes    = []          # list of class objects
        self.stat_caps  = {}          # {stat_name: cap_dict}
        self.ar_curves  = {}          # {graph_id: [150 floats]}
        self.ar_aec     = {}          # {aec_id: {dmg_type: {str,dex,...}}}
        self.ar_reinforce = {}        # {reinforce_type_id: {attack, scaling}}

        self.weapons_by_id   = {}     # {id: weapon_obj}
        self.weapons_by_name = {}     # {name: weapon_obj}
        self.armor_by_id     = {}
        self.armor_by_name   = {}
        self.talismans_by_id = {}
        self.spells_by_id    = {}
        self.aow_list        = []
        self.spirit_ashes    = []
        self.tears           = []

        # ERR only
        self.affinities  = []
        self.curios      = []
        self.runeforging = {}
        self.err_curves  = {}         # {vigor_hp: [...], mind_fp: [...], ...}

        # AR variant cache: {'weapon_name': [variant, ...]}
        self._variant_cache = {}
        self._variant_lock  = threading.Lock()

        self.loaded = False

    # ── Variant cache ──────────────────────────────────────────────────────────

    def get_variants(self, weapon_name, api_key=None):
        """Return cached variants or fetch from API. Blocks caller thread briefly."""
        with self._variant_lock:
            if weapon_name in self._variant_cache:
                return self._variant_cache[weapon_name]

        variants = self._fetch_variants(weapon_name, api_key)
        with self._variant_lock:
            self._variant_cache[weapon_name] = variants
        return variants

    def _cache_write(self, key, data):
        _cache_save(self.game, key, data)

    def _cache_read(self, key):
        return _cache_load(self.game, key)

    def _fetch_variants(self, weapon_name, api_key=None):
        import requests
        try:
            encoded = requests.utils.quote(weapon_name, safe='')
            url = f"{BASE_URL}/api/soulslike/weapons/{encoded}/ar-variants/?game={self.game}"
            headers = {'X-Listener-Key': api_key} if api_key else {}
            r = requests.get(url, headers=headers, timeout=10)
            if r.ok:
                variants = r.json().get('variants', [])
                self._cache_write(f"variants_{weapon_name}", {'variants': variants})
                return variants
        except Exception as e:
            log.warning("Failed to fetch AR variants for %s: %s", weapon_name, e)

        # Fall back to cached version
        cached = self._cache_read(f"variants_{weapon_name}")
        if cached:
            return cached.get('variants', [])
        return []


# ── Cache helpers ──────────────────────────────────────────────────────────────

def _cache_path(game, key):
    safe_key = key.replace('/', '_').replace(' ', '_')
    return _data_path("builder_cache", f"{game}_{safe_key}.json")


def _cache_valid(path):
    if not os.path.exists(path):
        return False
    age_hours = (time.time() - os.path.getmtime(path)) / 3600
    return age_hours < CACHE_TTL_H


def _cache_save(game, key, data):
    path = _cache_path(game, key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        log.warning("Cache write failed (%s): %s", key, e)


def _cache_load(game, key):
    path = _cache_path(game, key)
    if not _cache_valid(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


# ── Fetch helpers ──────────────────────────────────────────────────────────────

def _get(url, cache_game, cache_key, api_key=None):
    """Fetch URL, save to cache, return parsed JSON. Falls back to cache on error."""
    cached = _cache_load(cache_game, cache_key)
    if cached is not None:
        return cached

    import requests
    try:
        headers = {'X-Listener-Key': api_key} if api_key else {}
        r = requests.get(url, headers=headers, timeout=15)
        if r.ok:
            data = r.json()
            _cache_save(cache_game, cache_key, data)
            return data
        log.warning("API %s → %d", url, r.status_code)
    except Exception as e:
        log.warning("Fetch failed %s: %s", url, e)

    # Return stale cache if available
    path = _cache_path(cache_game, cache_key)
    if os.path.exists(path):
        try:
            with open(path) as f:
                log.info("Using stale cache for %s", cache_key)
                return json.load(f)
        except Exception:
            pass
    return {}


# ── Main loader ────────────────────────────────────────────────────────────────

def load_builder_data(game, api_key=None, on_progress=None):
    """
    Load all game data for `game` ('elden_ring' or 'err').
    Returns populated BuilderData instance.
    on_progress: optional callable(step: str, pct: int)
    """
    d = BuilderData(game)

    def progress(msg, pct):
        log.info("Builder data [%s] %d%% — %s", game, pct, msg)
        if on_progress:
            on_progress(msg, pct)

    def url(path):
        return f"{BASE_URL}{path}"

    progress("Loading classes", 5)
    resp = _get(url(f"/api/soulslike/classes/?game={game}"), game, "classes", api_key)
    d.classes = resp.get('classes', [])

    progress("Loading stat caps", 10)
    resp = _get(url(f"/api/soulslike/stat-caps/?game={game}"), game, "stat_caps", api_key)
    d.stat_caps = {c['stat']: c for c in resp.get('caps', [])}

    progress("Loading AR data", 20)
    resp = _get(url(f"/api/soulslike/ar-data/?game={game}"), game, "ar_data", api_key)
    d.ar_curves   = resp.get('curves', {})
    d.ar_aec      = resp.get('aec', {})
    d.ar_reinforce = resp.get('reinforce', {})

    progress("Loading weapons", 35)
    resp = _get(url(f"/api/soulslike/weapons/?game={game}&limit=2000"), game, "weapons", api_key)
    for w in resp.get('weapons', []):
        d.weapons_by_id[w['id']]     = w
        d.weapons_by_name[w['name']] = w

    progress("Loading armor", 45)
    # ERR reuses ER armor entirely
    armor_game = 'elden_ring'
    resp = _get(url(f"/api/soulslike/armor/?game={armor_game}&limit=2000"), armor_game, "armor", api_key)
    for a in resp.get('armor', []):
        d.armor_by_id[a['id']]     = a
        d.armor_by_name[a['name']] = a

    progress("Loading talismans", 52)
    resp = _get(url(f"/api/soulslike/talismans/?game={game}&limit=1000"), game, "talismans", api_key)
    for t in resp.get('talismans', []):
        d.talismans_by_id[t['id']] = t

    progress("Loading spells", 58)
    resp = _get(url(f"/api/soulslike/spells/?game={game}&limit=1000"), game, "spells", api_key)
    for s in resp.get('spells', []):
        d.spells_by_id[s['id']] = s

    progress("Loading spirit ashes", 64)
    resp = _get(url(f"/api/soulslike/spirit-ashes/?game={game}"), game, "spirit_ashes", api_key)
    d.spirit_ashes = resp.get('ashes', [])

    progress("Loading crystal tears", 70)
    if game == 'elden_ring':
        resp = _get(url("/api/soulslike/crystal-tears/?game=elden_ring"), game, "tears", api_key)
    else:
        resp = _get(url("/api/soulslike/err/crystal-tears/"), game, "tears", api_key)
    d.tears = resp.get('tears', [])

    progress("Loading Ashes of War", 78)
    if game == 'elden_ring':
        resp = _get(url("/api/soulslike/aow/?game=elden_ring&limit=500"), game, "aow", api_key)
        d.aow_list = resp.get('aow', [])
    else:
        resp = _get(url("/api/soulslike/err/aow-skills/?limit=500"), game, "aow", api_key)
        # Normalise ERR AoW to same shape as ER; exclude unique skills
        d.aow_list = [
            {
                'name':       s['name'],
                'affinity':   s.get('affinity', ''),
                'fp_cost':    0,
                'compatible': s.get('armaments', ''),
                'effect':     s.get('effect', ''),
                'is_unique_skill': s.get('is_unique_skill', False),
            }
            for s in resp.get('skills', [])
            if not s.get('is_unique_skill', False)
        ]

    if game == 'err':
        progress("Loading ERR systems", 86)

        resp = _get(url("/api/soulslike/err/affinities/"), game, "affinities", api_key)
        d.affinities = resp.get('affinities', [])

        resp = _get(url("/api/soulslike/err/curios/"), game, "curios", api_key)
        d.curios = resp.get('curios', [])

        resp = _get(url("/api/soulslike/err/runeforging/"), game, "runeforging", api_key)
        d.runeforging = resp

        resp = _get(url("/api/soulslike/derived-curves/?game=err"), game, "err_curves", api_key)
        d.err_curves = resp.get('curves', {})

    d.loaded = True
    progress("Ready", 100)
    return d


def load_builder_data_async(game, api_key=None, on_progress=None, on_done=None, on_error=None):
    """Load data in a background thread. Calls on_done(BuilderData) when complete."""
    def _run():
        try:
            data = load_builder_data(game, api_key=api_key, on_progress=on_progress)
            if on_done:
                on_done(data)
        except Exception as e:
            log.exception("Builder data load failed")
            if on_error:
                on_error(str(e))

    threading.Thread(target=_run, daemon=True).start()
