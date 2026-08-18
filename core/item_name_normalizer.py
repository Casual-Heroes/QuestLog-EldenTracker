"""Shared item-name normalization for save inventory reconciliation."""

from __future__ import annotations

import re

_ALIASES = {
    "ambassador's greatshield": "ambassador's towershield",
    "backhand blade": "backhand blades",
    "blaidd the half-wolf": "blaidd",
    "crimsonwhorl bubbletear": "crimsonwhorl crystal tear",
    "curseblade's cirque": "curseblade's cirques",
    "dancing blade of ranah": "dancing blades of ranah",
    "deadly poison perfume bottle": "poison perfume bottle",
    "flamelost spear": "flamelost war spear",
    "greenburst crystal tear": "viridianburst crystal tear",
    "greenspill crystal tear": "viridianspill crystal tear",
    "horned warrior's sword": "horned warrior's swords",
    "nox flowing fist": "nox flowing fists",
    "ornamental straight sword": "ornamental straight swords",
    "pumpkin head sledgehammer": "pumpkin sledge",
    "smithscript cirque": "smithscript cirques",
    "starscourge greatsword": "starscourge greatswords",
    "windy crystal tear": "windy cracked tear",
    "zweihander": "zweihänder",
}


def item_key(name: str) -> str:
    value = str(name or "").strip().casefold()
    value = re.sub(r"\s+\+\d+$", "", value)
    if value.startswith("greatsword of radahn"):
        return "greatswords of radahn"
    if value.endswith(" ashes"):
        without_suffix = value[:-6]
        value = _ALIASES.get(without_suffix, without_suffix)
    return _ALIASES.get(value, value)
