import unittest
from unittest.mock import patch

from core import save_parser


class SaveParserSlotVisibilityTests(unittest.TestCase):
    def _save_bytes_with_names_and_flags(self, names, flags):
        size = save_parser.NAME_OFFSETS[-1] + save_parser.NAME_LEN
        data = bytearray(size)
        data[:4] = save_parser.MAGIC
        data[save_parser.ACTIVE_SLOT_FLAGS_OFFSET:save_parser.ACTIVE_SLOT_FLAGS_OFFSET + len(flags)] = bytes(flags)
        for name, offset in zip(names, save_parser.NAME_OFFSETS):
            raw = name.encode("utf-16-le")[:save_parser.NAME_LEN]
            data[offset:offset + len(raw)] = raw
        return bytes(data)

    def test_parse_ignores_stale_profile_names_for_inactive_slots(self):
        names = [f"Slot {index}" for index in range(save_parser.SLOT_COUNT)]
        flags = [1, 1, 1, 1, 0, 0, 1, 1, 1, 0]
        data = self._save_bytes_with_names_and_flags(names, flags)

        with (
            patch("core.save_parser.get_slot", return_value=b"slot"),
            patch("core.save_parser.get_event_flags", return_value=b"flags"),
            patch("core.save_parser.get_item_ids", return_value=[]),
        ):
            slots = save_parser.parse_save_bytes(data)

        self.assertEqual([slot.index for slot in slots], [0, 1, 2, 3, 6, 7, 8])
        self.assertEqual([slot.name for slot in slots], ["Slot 0", "Slot 1", "Slot 2", "Slot 3", "Slot 6", "Slot 7", "Slot 8"])


if __name__ == "__main__":
    unittest.main()
