"""
Loads item ID -> name tables from ERR-Debug-Tool-Resources (a community ERR
debug tool's resource files, vendored at the project root) as a second
lookup layer, separate from the vanilla catalog in
games/elden_ring/save_data/vanilla/.

This covers ground the vanilla catalog doesn't: ERR-added items (new
weapons, Fortunes, Binding Runes, Shadowed Curios), and also plain vanilla
categories the vanilla catalog never included at all (upgrade materials,
crafting materials, key items, flasks, etc. -- CasualHeroes' checklist
tool never tracked these either, since it targets 100%-completion
categories, not full inventory).

Driven entirely by Resources/ItemCategories.txt, the debug tool's own
file-to-category-base map, rather than a hand-maintained duplicate --
that file is the authoritative source for which .txt covers which
category and what base to add to its raw (undecorated) IDs.
"""

import os
from core.paths import ROOT

_RESOURCES_DIR = os.path.join(ROOT, "ERR-Debug-Tool-Resources", "Resources")
_CATEGORIES_FILE = os.path.join(_RESOURCES_DIR, "ItemCategories.txt")

_lookup = None  # hex_id -> (category_label, name), built lazily
_lookups_by_root = {}  # resources_dir -> hex_id -> (category_label, name), for build_lookup()


def _parse_categories_file(path: str) -> list:
    """Returns list of (category_base, relative_txt_path, label), skipping comments."""
    entries = []
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            parts = line.split(None, 2)
            if len(parts) < 3:
                continue
            base_str, _flag, rest = parts
            # rest is "<relative/path.txt> <label...>"
            path_and_label = rest.split(None, 1)
            if len(path_and_label) != 2:
                continue
            rel_path, label = path_and_label
            try:
                base = int(base_str, 16)
            except ValueError:
                continue
            entries.append((base, rel_path, label))
    return entries


def _parse_item_file(path: str, base: int) -> dict:
    entries = {}
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            parts = line.split(None, 1)
            if len(parts) != 2:
                continue
            raw_id_str, name = parts
            try:
                raw_id = int(raw_id_str)
            except ValueError:
                continue
            full_id = raw_id + base
            entries[f"{full_id:08X}"] = name
    return entries


def build_lookup(resources_dir: str) -> dict:
    """
    Same ItemCategories.txt-driven build as get_lookup(), but for an
    arbitrary debug-tool resource root -- e.g. ConvergenceDebugTool/, which
    follows the identical ItemCategories.txt + per-category .txt layout as
    ERR-Debug-Tool-Resources (same base-address scheme too: 0x40000000
    goods/key-items, 0x10000000 armor, 0x20000000 talismans, 0x80000000
    AoW, 0x00000000 weapons -- confirmed empirically, not assumed). Cached
    per resources_dir so repeated calls don't re-parse the files.
    """
    if resources_dir in _lookups_by_root:
        return _lookups_by_root[resources_dir]

    lookup = {}
    categories_file = os.path.join(resources_dir, "ItemCategories.txt")
    if os.path.isfile(categories_file):
        for base, rel_path, label in _parse_categories_file(categories_file):
            full_path = os.path.join(resources_dir, *rel_path.split("/"))
            if not os.path.isfile(full_path):
                continue
            for hex_id, name in _parse_item_file(full_path, base).items():
                lookup.setdefault(hex_id, (label, name))

    _lookups_by_root[resources_dir] = lookup
    return lookup


def get_lookup() -> dict:
    """Returns hex_id -> (category_label, name) for ERR. Built once, cached."""
    global _lookup
    if _lookup is not None:
        return _lookup
    _lookup = build_lookup(_RESOURCES_DIR)
    return _lookup
