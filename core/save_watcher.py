"""
Live save-file item tracking for the running app.

Ports the exact resolution/diff logic already proven out in
tools/live_save_diff.py (a standalone research script, "not wired into the
main app" per its own docstring) into a reusable class the app can poll on
its existing tick loop. No logic is simplified or dropped from that
script's approach -- same copy-then-read-then-parse method to avoid holding
a lock on the live save file, same vanilla-catalog-first-then-ERR-lookup
resolution order, same quantity-snapshot handling for stackable goods/key
items.

Scope: vanilla (.sl2) and Elden Ring Reforged (.err) only. Convergence
(.cnv) is intentionally not wired up here -- there isn't yet enough build/
item/wiki data to support Convergence as a build target, so there's no
point tracking it live. Items only -- bosses/graces/cookbooks/bell_bearings/
whetblades are a separate, deliberately deferred effort (the save file's
event-flag catalog can't disambiguate many recurring same-named field
bosses across different locations).
"""

import os
import shutil
import tempfile

from core.save_parser import (
    SaveParseError, parse_save_bytes, get_slot, get_inventory_items,
)
from core.save_data import SaveDataTables, resolve_slot
from core.err_debug_tool_data import get_lookup as get_err_lookup
from core.crash_logger import get_logger

log = get_logger("questlog.save_watcher")

_POLLABLE_ERRORS = (SaveParseError, FileNotFoundError, PermissionError, OSError)


def read_slot(path: str, slot_index: int):
    """
    Returns (SlotData, raw_slot_bytes) for slot_index, or (None, None) if
    not found. Copies the save file to a temp file first and reads off the
    copy -- identical approach to tools/live_save_diff.py:read_slot -- so a
    concurrent write by the game (autosave) never gets read mid-write and
    the live file is never held open/locked by this process.
    """
    with tempfile.NamedTemporaryFile(delete=False, suffix=".tmp") as tmp:
        tmp_path = tmp.name
    try:
        shutil.copy2(path, tmp_path)
        with open(tmp_path, "rb") as f:
            data = f.read()
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    slots = parse_save_bytes(data)
    for s in slots:
        if s.index == slot_index:
            return s, get_slot(data, slot_index)
    return None, None


class SaveWatcher:
    """
    Polls a live Elden Ring save file and resolves it into the same named
    owned-item view tools/live_save_diff.py's _named_snapshot()/
    _quantity_snapshot() already compute -- vanilla catalog checked first
    (SaveDataTables/resolve_slot), ERR-exclusive items (Fortunes, added
    weapons, etc. -- not in the vanilla catalog) resolved as a fallback
    layer for anything vanilla left unresolved, exactly mirroring that
    script's approach so nothing is dropped or simplified in the port.
    """

    #: Item categories only -- bosses/graces/cookbooks/bell_bearings/
    #: whetblades intentionally excluded (see module docstring: deferred,
    #: separate effort due to ambiguous same-named field bosses).
    _ITEM_CATEGORIES = (
        "armament", "armor", "ashesOfWar", "magic", "spiritAshes",
        "talisman", "tools", "gestures", "crystal_tears", "paintings",
    )

    def __init__(self, save_path: str, mode: str = "vanilla"):
        self.save_path = save_path
        self.mode = mode
        self._tables = SaveDataTables(include_dlc=True)
        self._err_lookup = get_err_lookup() if mode == "reforged" else None

    def list_slots(self) -> list:
        """Return populated character slots as [{'index': int, 'name': str}, ...]."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".tmp") as tmp:
            tmp_path = tmp.name
        try:
            shutil.copy2(self.save_path, tmp_path)
            with open(tmp_path, "rb") as f:
                data = f.read()
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        return [{"index": s.index, "name": s.name} for s in parse_save_bytes(data)]

    def _named_snapshot(self, slot) -> set:
        """
        Resolve a slot into the same named owned/not-owned view
        tools/live_save_diff.py's _named_snapshot() computes, restricted to
        item categories only (that script also includes bosses/graces/
        flags -- deliberately dropped here per this module's items-only
        scope, not because the underlying data doesn't support it).

        Vanilla is checked FIRST and wins: an ID vanilla already resolved
        must not also be looked up in the ERR catalog, or it would log
        twice under two different labels for the same item -- only IDs
        vanilla left unresolved (result.unresolved_item_ids) are checked
        against the ERR lookup. Same rule tools/live_save_diff.py already
        established.
        """
        result = resolve_slot(slot, self._tables)
        owned = set()
        for category in self._ITEM_CATEGORIES:
            names = result.owned_items.get(category, [])
            owned |= {f"{name} ({category})" for name in names}

        if self._err_lookup:
            for item_id in result.unresolved_item_ids:
                match = self._err_lookup.get(item_id)
                if match:
                    category, name = match
                    owned.add(f"{name} ({category})")

        return owned

    def _quantity_snapshot(self, slot_bytes) -> dict:
        """
        Resolve real per-item stack quantities for held goods + key items
        via get_inventory_items(), identical approach to
        tools/live_save_diff.py's _quantity_snapshot() -- reads actual
        EquipInventoryItem records instead of guessing presence from a flat
        ID scan, so a quantity INCREASE on an already-owned stackable item
        can be detected (a plain owned/not-owned set diff never could).
        """
        quantities = {}
        for it in get_inventory_items(slot_bytes):
            name = None
            for cat in self._tables.categories.values():
                info = cat.get(it.item_id)
                if info:
                    name = info["name"]
                    break
            if not name and self._err_lookup:
                match = self._err_lookup.get(it.item_id)
                if match:
                    category, err_name = match
                    name = f"{err_name} ({category})"
            if name:
                quantities[name] = quantities.get(name, 0) + it.quantity
        return quantities

    def poll(self, slot_index: int = 0):
        """
        Reads the save file and returns (named_snapshot, quantity_snapshot)
        for slot_index. Raises the same errors read_slot/parse_save_bytes
        can raise (SaveParseError, FileNotFoundError, PermissionError,
        OSError) -- callers are expected to catch these per-poll (the save
        file can be transiently locked or briefly missing mid-autosave) and
        keep the previous snapshot rather than treat a single failed read
        as "everything was lost."
        """
        slot, slot_bytes = read_slot(self.save_path, slot_index)
        if slot is None:
            return set(), {}
        return self._named_snapshot(slot), self._quantity_snapshot(slot_bytes)
