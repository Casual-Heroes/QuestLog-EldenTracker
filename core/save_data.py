"""
Loads reference ID tables (bosses/graces/items/event-flag block map) and
resolves parsed save data (core.save_parser.SlotData) into named results.

Vanilla-only for now — Reforged/Convergence tables don't exist yet and will
be added under games/elden_ring/save_data/<mode>/ following the same shape.
"""

import json
import os

from core.paths import games as _games_path
from core.save_parser import SlotData, is_event_flag_set

_VANILLA_DIR = _games_path("elden_ring", "save_data", "vanilla")

_FLAG_CATEGORIES = ("bosses", "graces", "cookbooks", "bell_bearings", "whetblades")
_INVENTORY_CATEGORIES = ("armament", "armor", "ashesOfWar", "magic", "spiritAshes", "talisman", "tools", "gestures", "crystal_tears", "paintings")


def _load(name: str):
    with open(os.path.join(_VANILLA_DIR, name), encoding="utf-8") as f:
        return json.load(f)


class SaveDataTables:
    """Loads and caches the reference JSON tables for a given game mode."""

    def __init__(self, include_dlc: bool = True):
        all_items = _load("all_items.json")
        bosses    = {"bosses": _load("bosses.json")["bosses"]}
        graces    = {"graces": _load("graces.json")["graces"]}
        cookbooks = {"cookbooks": _load("cookbooks.json")["cookbooks"]}
        bearings  = {"bell_bearings": _load("bell_bearings.json")["bell_bearings"]}
        whetblades = {"whetblades": _load("whetblades.json")["whetblades"]}
        paintings = {"paintings": _load("paintings.json")["paintings"]}

        self.categories = {
            **all_items,
            **bosses, **graces, **cookbooks, **bearings, **whetblades, **paintings,
        }

        if include_dlc:
            dlc = _load("dlc_items.json")
            for cat, items in dlc.items():
                if cat == "not-found":
                    continue
                self.categories.setdefault(cat, {})
                self.categories[cat] = {**self.categories[cat], **items}

        self.bst_map = _load("eventflag_bst.json")

    def category(self, name: str) -> dict:
        return self.categories.get(name, {})


class ParsedSlotResult:
    def __init__(self):
        self.owned_bosses = []      # list[str] names
        self.owned_graces = []      # list[str] names
        self.owned_flags = {}       # category -> list[str] names (cookbooks/bell_bearings/whetblades)
        self.owned_items = {}       # category -> list[str] names (inventory-based)
        self.unresolved_flag_ids = []
        self.unresolved_item_ids = []


def resolve_slot(slot: SlotData, tables: SaveDataTables) -> ParsedSlotResult:
    """Resolve a parsed SlotData's raw event flags + item IDs into named results."""
    result = ParsedSlotResult()

    for flag_category in _FLAG_CATEGORIES:
        entries = tables.category(flag_category)
        if not entries:
            continue
        owned_names = []
        for flag_id, info in entries.items():
            state = is_event_flag_set(slot.event_flags, int(flag_id), tables.bst_map)
            if state is None:
                result.unresolved_flag_ids.append(flag_id)
            elif state:
                owned_names.append(info["name"])
        if flag_category == "bosses":
            result.owned_bosses = owned_names
        elif flag_category == "graces":
            result.owned_graces = owned_names
        else:
            result.owned_flags[flag_category] = owned_names

    remaining_ids = set(slot.item_ids)
    for category in _INVENTORY_CATEGORIES:
        entries = tables.category(category)
        if not entries:
            continue
        owned_names = []
        for item_id in list(remaining_ids):
            info = entries.get(item_id)
            if info is not None:
                owned_names.append(info["name"])
                remaining_ids.discard(item_id)
        result.owned_items[category] = owned_names

    result.unresolved_item_ids = sorted(remaining_ids)
    return result
