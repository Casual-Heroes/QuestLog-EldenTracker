import struct

from core.save_parser import SlotData
from core.save_parser import get_equipped_item_ids
from core.save_watcher import SaveWatcher


def test_get_equipped_item_ids_reads_chrasm_armor_and_talismans():
    slot = bytearray(0x20000)

    chrasm_offset = 4 + 4 + 0x18
    chrasm_offset += 0x1400 * 8
    chrasm_offset += 432
    chrasm_offset += 0xD0
    chrasm_offset += 88

    values = [0] * 29
    values[19] = 0x00015F90  # Perfumer Hood -> armor base
    values[20] = 0x00015FF4  # Perfumer Robe -> armor base
    values[21] = 0x00016058  # Perfumer Gloves -> armor base
    values[22] = 0x000160BC  # Perfumer Sarong -> armor base
    values[24] = 0x000003E8  # Crimson Amber Medallion -> talisman base
    struct.pack_into("<29I", slot, chrasm_offset, *values)

    assert get_equipped_item_ids(bytes(slot)) == [
        "10015F90",
        "10015FF4",
        "10016058",
        "100160BC",
        "200003E8",
    ]


def test_reforged_perfumer_starter_aliases_equipped_traveler_set():
    slot_bytes = bytearray(0x20000)

    chrasm_offset = 4 + 4 + 0x18
    chrasm_offset += 0x1400 * 8
    chrasm_offset += 432
    chrasm_offset += 0xD0
    chrasm_offset += 88

    values = [0] * 29
    values[19] = 0x000186A0  # Traveler's Hat -> Perfumer Hood alias
    values[20] = 0x00018704  # Perfumer's Traveling Garb -> Perfumer Robe alias
    values[21] = 0x00018768  # Traveler's Gloves -> Perfumer Gloves alias
    values[22] = 0x000187CC  # Traveler's Slops -> Perfumer Sarong alias
    struct.pack_into("<29I", slot_bytes, chrasm_offset, *values)

    slot = SlotData(index=0, name="Perfumer", event_flags=bytes(0x20000), item_ids=[])
    watcher = SaveWatcher("unused.err", mode="reforged")

    owned = watcher._named_snapshot(slot, bytes(slot_bytes))

    assert "Traveler's Hat (armor)" in owned
    assert "Perfumer's Traveling Garb (armor)" in owned
    assert "Traveler's Gloves (armor)" in owned
    assert "Traveler's Slops (armor)" in owned
    assert "Perfumer Hood (armor)" in owned
    assert "Perfumer Robe (armor)" in owned
    assert "Perfumer Gloves (armor)" in owned
    assert "Perfumer Sarong (armor)" in owned
