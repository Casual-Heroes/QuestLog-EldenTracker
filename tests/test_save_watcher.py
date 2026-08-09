import unittest
from types import SimpleNamespace
from unittest.mock import patch

from core.save_watcher import SaveWatcher


class SaveWatcherOverrideTests(unittest.TestCase):
    def test_reforged_override_replaces_vanilla_item(self):
        watcher = SaveWatcher.__new__(SaveWatcher)
        watcher._tables = SimpleNamespace(categories={
            "armament": {"00118C30": {"name": "Erdsteel Dagger"}},
        })
        watcher._err_lookup = {"unrelated": ("ERR: Weapons", "Unrelated")}
        slot = SimpleNamespace(item_ids=["00118C30"])
        resolved = SimpleNamespace(
            owned_items={"armament": ["Erdsteel Dagger"]},
            unresolved_item_ids=[],
        )

        with patch("core.save_watcher.resolve_slot", return_value=resolved):
            snapshot = watcher._named_snapshot(slot)

        self.assertIn("Brass Dagger (ERR: Weapons)", snapshot)
        self.assertNotIn("Erdsteel Dagger (armament)", snapshot)

    def test_vanilla_mode_keeps_vanilla_item(self):
        watcher = SaveWatcher.__new__(SaveWatcher)
        watcher._tables = SimpleNamespace(categories={
            "armament": {"00118C30": {"name": "Erdsteel Dagger"}},
        })
        watcher._err_lookup = None
        slot = SimpleNamespace(item_ids=["00118C30"])
        resolved = SimpleNamespace(
            owned_items={"armament": ["Erdsteel Dagger"]},
            unresolved_item_ids=[],
        )

        with patch("core.save_watcher.resolve_slot", return_value=resolved):
            snapshot = watcher._named_snapshot(slot)

        self.assertEqual(snapshot, {"Erdsteel Dagger (armament)"})


if __name__ == "__main__":
    unittest.main()
