"""
Read-only Elden Ring save file parser.

Works against vanilla (.sl2), Elden Ring Reforged (.err), and Elden Ring
Convergence (.cnv) saves — all three use the same BND4 container, slot
layout, and event-flag bit-packing scheme; only the item/boss/flag IDs
differ per mod.

Ported from CasualHeroes/Elden-Ring-Automatic-Checklist (MIT), see
games/elden_ring/save_data/vanilla/SOURCE.md. Algorithm cross-verified
against the event-flag bit-packing logic documented independently by
The-Grand-Archives/Elden-Ring-CT-TGA and Nordgaren/Erd-Tools.

No decryption, no writes — this module only ever reads bytes off disk.
"""

import struct
from dataclasses import dataclass, field

MAGIC = b"BND4"

SLOT_COUNT = 10
SLOT_SIZE  = 0x280010          # 2,621,456 bytes per character slot
SLOT0_START = 0x310

NAME_OFFSETS = [
    0x1901D0E, 0x1901F5A, 0x19021A6, 0x19023F2, 0x190263E,
    0x190288A, 0x1902AD6, 0x1902D22, 0x1902F6E, 0x19031BA,
]
NAME_LEN = 32  # bytes (16 UTF-16 code units)

INVENTORY_PATTERN     = bytes([0xB0, 0xAD, 0x01, 0x00, 0x01, 0xFF, 0xFF, 0xFF])
INVENTORY_PATTERN_DLC = bytes([0xB0, 0xAD, 0x01, 0x00, 0x01])


class SaveParseError(Exception):
    pass


@dataclass
class SlotData:
    index: int
    name: str
    event_flags: bytes
    item_ids: list = field(default_factory=list)   # list[str], zero-padded uppercase hex, big-endian-ish (matches all_items.json keys)


def _slot_bounds(index: int) -> tuple:
    start = SLOT0_START + index * SLOT_SIZE
    return start, start + SLOT_SIZE


def get_names(data: bytes) -> list:
    """Return the 10 character-slot display names (empty string for unused slots)."""
    names = []
    for off in NAME_OFFSETS:
        raw = data[off:off + NAME_LEN]
        name = raw.decode("utf-16-le", errors="ignore").replace("\x00", "")
        names.append(name)
    return names


def get_slot(data: bytes, index: int) -> bytes:
    if not 0 <= index < SLOT_COUNT:
        raise SaveParseError(f"slot index out of range: {index}")
    start, end = _slot_bounds(index)
    return data[start:end]


def _find(haystack: bytes, needle: bytes) -> int:
    return haystack.find(needle)


def _get_inventory_bytes(slot: bytes) -> tuple:
    """Returns (raw_inventory_bytes, is_dlc_layout)."""
    idx = _find(slot, INVENTORY_PATTERN)
    is_dlc = False
    if idx != -1:
        start = idx + len(INVENTORY_PATTERN) + 8
    else:
        idx = _find(slot, INVENTORY_PATTERN_DLC)
        if idx == -1:
            raise SaveParseError("inventory marker pattern not found in slot")
        start = idx + len(INVENTORY_PATTERN_DLC) + 3
        is_dlc = True

    zero_run = bytes(50)
    end_rel = _find(slot[start:], zero_run)
    if end_rel == -1:
        raise SaveParseError("inventory end marker not found in slot")
    end = start + end_rel + 6

    return slot[start:end], is_dlc


def _id_reversed(raw4: bytes) -> str:
    """Match the JS getIdReversed: reverse first 4 bytes, hex-pad each to 2 chars, upper."""
    return "".join(f"{b:02X}" for b in reversed(raw4[:4]))


def get_item_ids(slot: bytes) -> list:
    """Return the list of hex item-ID strings (matches all_items.json key format)."""
    raw, is_dlc = _get_inventory_bytes(slot)
    chunk_size = 8 if is_dlc else 16
    ids = []
    for i in range(0, len(raw) - 3, chunk_size):
        rec = raw[i:i + 4]
        if len(rec) < 4:
            break
        ids.append(_id_reversed(rec))
    return ids


EQUIP_INVENTORY_COMMON_SLOTS = 0xA80
EQUIP_INVENTORY_KEY_SLOTS = 0x180
EQUIP_INVENTORY_ITEM_SIZE = 12  # ga_item_handle: u32, quantity: u32, inventory_index: u32


def _offset_to_held_inventory(slot: bytes) -> int:
    """
    Returns the byte offset of EquipInventoryData (the character's HELD
    inventory, as opposed to storage-box inventory) within a slot — i.e.
    the offset of its leading common_inventory_items_distinct_count u32.
    Mechanical structure walk, same fields/order as get_event_flags below
    up to that point (kept in sync with it — don't let these two drift).
    """
    offset = 0
    offset += 4 + 4 + 0x18  # ver(4) + map_id(4) + _0x18(24)

    for _ in range(0x1400):
        item_id = struct.unpack_from("<I", slot, offset + 4)[0]
        offset += 8
        if item_id != 0 and (item_id & 0xF0000000) == 0:
            offset += 13
        elif item_id != 0 and (item_id & 0xF0000000) == 0x10000000:
            offset += 8

    offset += 432          # PlayerGameData
    offset += 0xD0          # _0xd0
    offset += 88            # EquipData (22 x u32)
    offset += 116           # ChrAsm (29 x u32)
    offset += 88            # ChrAsm2 (22 x u32)
    return offset


@dataclass
class InventoryItem:
    item_id: str        # hex item ID, same format/reversal as get_item_ids
    quantity: int
    inventory_index: int
    is_key_item: bool


def _read_equip_inventory_item(slot: bytes, offset: int) -> tuple:
    """Reads one 12-byte EquipInventoryItem record: (ga_item_handle, quantity, inventory_index)."""
    ga_item_handle, quantity, inventory_index = struct.unpack_from("<III", slot, offset)
    return ga_item_handle, quantity, inventory_index


# Confirmed empirically (2026-07-07 live save test): a goods-category
# ga_item_handle like 0xB00C350A (Rune Piece) does NOT share its top nibble
# with the item ID's own category base (0x40000000 for goods/key items in
# all_items.json / ERR-Debug-Tool-Resources' scheme) -- masking the handle's
# top nibble to 0 gives the raw id (0x000C350A), and the real item id is
# that raw id OR'd with 0x40000000 (0x400C350A), which matched Rune Piece by
# name in the ERR catalog exactly. Only 5 category bases exist in
# ItemCategories.txt (0x00000000, 0x10000000 armor, 0x20000000 talismans,
# 0x40000000 goods/key items, 0x80000000 AoW/gems); goods/key items (what
# get_inventory_items reads) are always 0x40000000, so hard-code it here
# rather than guess-and-check against catalogs for every item.
_GOODS_ITEM_ID_BASE = 0x40000000


def _gaitem_handle_to_item_id(handle: int) -> str:
    """
    Recovers the plain item ID (matching all_items.json / ERR-Debug-Tool-
    Resources' key format) from a raw ga_item_handle for a common/key
    inventory item. See _GOODS_ITEM_ID_BASE for how this was confirmed.
    """
    raw_id = handle & 0x0FFFFFFF
    return f"{raw_id | _GOODS_ITEM_ID_BASE:08X}"


def get_inventory_items(slot: bytes) -> list:
    """
    Returns real (item_id, quantity) pairs from the character's HELD
    inventory — common_items (stackable goods, up to 0xA80 distinct slots)
    and key_items (up to 0x180 slots) — read as the actual EquipInventoryItem
    records (12 bytes: ga_item_handle, quantity, inventory_index), not the
    guessed flat ID scan get_item_ids() does. Ground truth for this layout:
    ClayAmore/ER-Save-Editor's EquipInventoryData::read (Rust, Apache-2.0),
    cross-checked against get_event_flags' offset math below which already
    knows the correct byte stride for these two arrays (0xA80*12, 0x180*12)
    -- it just skips over them instead of parsing them.
    """
    offset = _offset_to_held_inventory(slot)

    items = []

    common_count = struct.unpack_from("<I", slot, offset)[0]
    offset += 4
    for i in range(EQUIP_INVENTORY_COMMON_SLOTS):
        rec_offset = offset + i * EQUIP_INVENTORY_ITEM_SIZE
        handle, quantity, inv_index = _read_equip_inventory_item(slot, rec_offset)
        if handle != 0xFFFFFFFF and quantity > 0:
            items.append(InventoryItem(_gaitem_handle_to_item_id(handle), quantity, inv_index, False))
    offset += EQUIP_INVENTORY_COMMON_SLOTS * EQUIP_INVENTORY_ITEM_SIZE

    key_count = struct.unpack_from("<I", slot, offset)[0]
    offset += 4
    for i in range(EQUIP_INVENTORY_KEY_SLOTS):
        rec_offset = offset + i * EQUIP_INVENTORY_ITEM_SIZE
        handle, quantity, inv_index = _read_equip_inventory_item(slot, rec_offset)
        if handle != 0xFFFFFFFF and quantity > 0:
            items.append(InventoryItem(_gaitem_handle_to_item_id(handle), quantity, inv_index, True))

    return items


def get_event_flags(slot: bytes) -> bytes:
    """
    Walk the fixed-layout character save structure to reach the event-flag
    block. Field sizes below are copied 1:1 from the validated JS port
    (assets/js/script.js:getEventFlags) — this is mechanical structure
    layout, not something to "simplify" without re-validating against a
    real save.
    """
    offset = _offset_to_held_inventory(slot)
    offset += 4 + (0xA80 * 12) + 4 + (0x180 * 12) + 4 + 4   # EquipInventoryData
    offset += 116           # EquipMagicData
    offset += 140           # EquipItemData
    offset += 24            # equip_gesture_data

    projectile_count = struct.unpack_from("<i", slot, offset)[0]
    offset += 4 + projectile_count * 8

    offset += 156           # EquippedItems (39 x u32)
    offset += 8             # EquipPhysicsData
    offset += 4             # _0x4
    offset += 0x12F          # _face_data
    offset += 4 + (0x780 * 12) + 4 + (0x80 * 12) + 4 + 4     # EquipInventoryData 2
    offset += 256            # gesture_game_data

    regions_count = struct.unpack_from("<I", slot, offset)[0]
    offset += 4 + regions_count * 4

    offset += 40             # RideGameData
    offset += 77             # _0x1 + _0x40 + _0x4_1 + _0x4_2 + _0x4_3
    offset += 0x1008          # _menu_profile_save_load
    offset += 0x34            # _trophy_equip_data
    offset += 4 + 4 + (0x1B58 * 16)   # GaItemData
    offset += 0x408           # _tutorial_data
    offset += 0x1D            # _0x1d

    end = offset + 0x1BF99F
    if end > len(slot):
        raise SaveParseError(
            f"event-flag block runs past end of slot (offset={offset:#x}, slot_len={len(slot):#x}) — "
            "save structure may not match the expected layout for this file"
        )
    return slot[offset:end]


def is_event_flag_set(event_flags: bytes, event_id: int, bst_map: dict) -> bool | None:
    """
    Look up a single event flag's boolean state.

    Returns None if the flag's block_id has no entry in bst_map (unresolvable —
    treat as "unknown", not "not owned").
    """
    block_id = event_id // 1000
    bst_val = bst_map.get(str(block_id), bst_map.get(block_id))
    if bst_val is None:
        return None

    block_offset = bst_val * 125 + ((event_id % 1000) // 8)
    bit_index = 7 - (event_id % 8)

    if block_offset >= len(event_flags):
        return None

    byte = event_flags[block_offset]
    return (byte & (1 << bit_index)) != 0


def parse_save_bytes(data: bytes) -> list:
    """
    Parse a full save file's bytes into per-slot data.

    Returns a list of SlotData for every populated slot (empty slots —
    identified by a blank display name — are skipped).
    """
    if data[:4] != MAGIC:
        raise SaveParseError(f"not a valid save file (missing {MAGIC!r} magic bytes)")

    names = get_names(data)
    slots = []
    for i, name in enumerate(names):
        if not name:
            continue
        slot = get_slot(data, i)
        event_flags = get_event_flags(slot)
        item_ids = get_item_ids(slot)
        slots.append(SlotData(index=i, name=name, event_flags=event_flags, item_ids=item_ids))
    return slots


def parse_save_file(path: str) -> list:
    with open(path, "rb") as f:
        data = f.read()
    return parse_save_bytes(data)
