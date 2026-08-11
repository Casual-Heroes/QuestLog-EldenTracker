"""Audit live-save lookup coverage for bundled EldenTracker catalog data."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIVE_DIR = ROOT / "resources" / "catalog" / "live"
sys.path.insert(0, str(ROOT))

from core.err_debug_tool_data import get_lookup as get_err_lookup
from core.item_name_normalizer import item_key as _item_key
from core.live_catalog_item_lookup import get_lookup as get_live_lookup
from core.save_watcher import _ERR_ITEM_ID_OVERRIDES
from core.save_data import SaveDataTables

SUPPORTED_LIVE_RESOURCES = {
    "weapons": "weapons",
    "armor": "armor",
    "talismans": "talismans",
    "spells": "spells",
    "spirit_ashes": "ashes",
    "crystal_tears": "tears",
}

VANILLA_CATEGORY_NAMES = {
    "armament",
    "armor",
    "ashesOfWar",
    "magic",
    "spiritAshes",
    "talisman",
    "tools",
    "gestures",
    "crystal_tears",
    "paintings",
}

EXPECTED_ERR_GAPS = {
    # These are build planner concepts, not save-inventory items.
    "weapons_err": {"Unarmed"},
    # Present in the site catalog but not in extracted save/name sources.
    # These remain manually trackable checklist rows.
    "talismans_vanilla": {"Furled Fingers Trick-Mirror Talisman"},
    "crystal_tears_vanilla": {"Perfume Bottle (Crystal Tear form)"},
    "talismans_err": {"Furled Fingers Trick-Mirror Talisman"},
}


def _load_live(resource: str) -> list[dict]:
    payload = json.loads((LIVE_DIR / f"{resource}.json").read_text(encoding="utf-8"))
    field = SUPPORTED_LIVE_RESOURCES[resource.rsplit("_", 1)[0]]
    return payload.get(field, [])


def _live_names(resource: str) -> set[str]:
    return {
        str(row.get("name") or "").strip()
        for row in _load_live(resource)
        if isinstance(row, dict) and str(row.get("name") or "").strip()
    }


def _vanilla_save_names() -> set[str]:
    tables = SaveDataTables(include_dlc=True)
    names = set()
    for category in VANILLA_CATEGORY_NAMES:
        for info in tables.category(category).values():
            name = str(info.get("name") or "").strip()
            if name:
                names.add(name)
    for _item_id, (_category, name) in get_live_lookup("vanilla").items():
        if name:
            names.add(str(name).strip())
    return names


def _err_save_names() -> set[str]:
    names = set(_vanilla_save_names())
    for _item_id, (_category, name) in get_live_lookup("reforged").items():
        if name:
            names.add(str(name).strip())
    for _item_id, (_category, name) in get_err_lookup().items():
        if name:
            names.add(str(name).strip())
    for _item_id, (_category, name) in _ERR_ITEM_ID_OVERRIDES.items():
        if name:
            names.add(str(name).strip())
    return names


def audit() -> tuple[bool, list[str]]:
    failures = []
    save_names_by_mode = {
        "vanilla": {_item_key(name) for name in _vanilla_save_names()},
        "err": {_item_key(name) for name in _err_save_names()},
    }
    for mode in ("vanilla", "err"):
        for stem in SUPPORTED_LIVE_RESOURCES:
            resource = f"{stem}_{mode}"
            live_names = _live_names(resource)
            expected = {_item_key(name) for name in EXPECTED_ERR_GAPS.get(resource, set())}
            missing = sorted(
                name for name in live_names
                if _item_key(name) not in save_names_by_mode[mode]
                and _item_key(name) not in expected
            )
            if missing:
                failures.append(
                    f"{resource}: {len(missing)} missing from live-save lookup: "
                    + ", ".join(missing[:20])
                    + (" ..." if len(missing) > 20 else "")
                )
    return not failures, failures


def main() -> int:
    ok, failures = audit()
    if ok:
        print("save lookup coverage ok")
        return 0
    for failure in failures:
        print(failure)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
