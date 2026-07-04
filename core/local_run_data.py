"""
Local run items + death log — for runs without QuestLog sync.

Items are seeded from a linked build (weapons, armor, talismans, spells,
spirit ash, tears). Deaths are appended on every death event. Both are
persisted to the run directory.
"""

import json
import os
import time

from core.paths import data as _data_path

SAVES_DIR = _data_path("builds")

WEAPON_SLOTS  = ["rh1", "rh2", "rh3", "lh1", "lh2", "lh3"]
ARMOR_SLOTS   = ["helm", "chest", "gauntlet", "leg"]
TALI_SLOTS    = ["talisman1", "talisman2", "talisman3", "talisman4"]
MAX_DEATHS    = 100

_AOW_SKIP = {
    "No Skill", "Stamp (Upward Cut)", "Kick", "Quickstep", "Parry",
}


def list_local_builds():
    """Return list of (display_name, file_path) for all saved builds."""
    if not os.path.isdir(SAVES_DIR):
        return []
    result = []
    for fn in sorted(os.listdir(SAVES_DIR)):
        if fn.endswith(".json"):
            path = os.path.join(SAVES_DIR, fn)
            try:
                with open(path) as f:
                    d = json.load(f)
                result.append((d.get("name", fn[:-5]), path))
            except Exception:
                pass
    return result


def items_from_build(build: dict) -> list:
    """Extract item checklist from a saved build dict."""
    items = []
    seen  = set()

    def _add(name, item_type, item_id=0):
        if name and name not in seen:
            seen.add(name)
            items.append({"name": name, "type": item_type, "id": item_id,
                          "collected": False, "collected_at": None, "hint": None})

    slots = build.get("slots", {})
    for slot in WEAPON_SLOTS:
        w = slots.get(slot)
        if w and isinstance(w, dict):
            _add(w.get("name"), "weapon", w.get("id") or 0)

    for slot in ARMOR_SLOTS:
        a = slots.get(slot)
        if a and isinstance(a, dict):
            _add(a.get("name"), "armor", a.get("id") or 0)

    for slot in TALI_SLOTS:
        t = slots.get(slot)
        if t and isinstance(t, dict):
            _add(t.get("name"), "talisman", t.get("id") or 0)

    for spell in build.get("spells", []):
        if spell and isinstance(spell, dict):
            _add(spell.get("name"), "spell", spell.get("id") or 0)

    ash = build.get("spirit_ash")
    if ash and isinstance(ash, dict):
        _add(ash.get("name"), "spirit_ash", 0)

    for tear in build.get("tears", []):
        if tear and isinstance(tear, dict):
            _add(tear.get("name"), "crystal_tear", 0)

    # AoW — skip utility / non-collectible skills
    aow_map = build.get("aow", {})
    for slot in WEAPON_SLOTS:
        aow = aow_map.get(slot)
        if aow:
            aow_name = aow.get("name") if isinstance(aow, dict) else str(aow)
            if aow_name and aow_name not in _AOW_SKIP:
                _add(aow_name, "aow", 0)

    # ERR-only: fortune, minor fortune, curios, binding runes
    fortune = build.get("fortune_name")
    if fortune:
        _add(fortune, "fortune", 0)

    minor_fortune = build.get("minor_fortune_name")
    if minor_fortune:
        _add(minor_fortune, "minor_fortune", 0)

    # curioSelections shape: {"Academy": {"active": True}, ...}
    for curio_name, state in build.get("curioSelections", {}).items():
        active = state.get("active") if isinstance(state, dict) else bool(state)
        if active:
            _add(curio_name, "curio", 0)

    for rune in build.get("runeInventory", []):
        if rune.get("name") and rune.get("copies", 0) > 0:
            _add(rune["name"], "binding_rune", 0)

    return items


class LocalRunData:
    """Manages items.json and deaths.json for a local (non-synced) run."""

    def __init__(self, run_dir: str):
        self._run_dir     = run_dir
        self._items_path  = os.path.join(run_dir, "items.json")
        self._deaths_path = os.path.join(run_dir, "deaths.json")
        self._items  = self._load_items()
        self._deaths = self._load_deaths()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load_items(self) -> list:
        if os.path.isfile(self._items_path):
            try:
                with open(self._items_path) as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def _save_items(self):
        with open(self._items_path, "w") as f:
            json.dump(self._items, f, indent=2)

    def _load_deaths(self) -> list:
        if os.path.isfile(self._deaths_path):
            try:
                with open(self._deaths_path) as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def _save_deaths(self):
        with open(self._deaths_path, "w") as f:
            json.dump(self._deaths, f, indent=2)

    # ── Items API ─────────────────────────────────────────────────────────────

    def seed_from_build(self, build: dict):
        """Seed items from a build. Only runs if items.json doesn't exist yet."""
        if os.path.isfile(self._items_path):
            return
        self._items = items_from_build(build)
        self._save_items()

    def get_items(self):
        """Returns (items_list, collected_count, total_count)."""
        collected = sum(1 for it in self._items if it["collected"])
        return list(self._items), collected, len(self._items)

    def collect_item(self, item_name: str):
        for it in self._items:
            if it["name"].lower() == item_name.lower():
                it["collected"]    = True
                it["collected_at"] = int(time.time())
                break
        self._save_items()

    def uncollect_item(self, item_name: str):
        for it in self._items:
            if it["name"].lower() == item_name.lower():
                it["collected"]    = False
                it["collected_at"] = None
                break
        self._save_items()

    # ── Deaths API ────────────────────────────────────────────────────────────

    def append_death(self, boss: str, life_sec: int, session_deaths: int, total_deaths: int):
        entry = {
            "boss":           boss or "",
            "at":             int(time.time()),
            "life":           life_sec,
            "session_deaths": session_deaths,
            "total_deaths":   total_deaths,
        }
        self._deaths.insert(0, entry)
        self._deaths = self._deaths[:MAX_DEATHS]
        self._save_deaths()

    def get_recent_deaths(self) -> list:
        return list(self._deaths[:10])

    def undo_last_death(self):
        if self._deaths:
            self._deaths.pop(0)
            self._save_deaths()
