import unittest
from types import SimpleNamespace
from unittest.mock import patch

from core.save_watcher import SaveWatcher
from core.err_debug_tool_data import _merge_live_spells


class SaveWatcherOverrideTests(unittest.TestCase):
    def test_live_err_spell_catalog_extends_save_lookup(self):
        lookup = {}
        store = SimpleNamespace(load_live=lambda name: {
            "spells": [
                {"id": 10104, "name": "Blazing Wall"},
                {"id": 10105, "name": "Fist of the Heavens"},
            ]
        })

        with patch("core.catalog_sync.CatalogStore", return_value=store):
            _merge_live_spells(lookup)

        self.assertEqual(lookup["40002778"], ("ERR: Magic", "Blazing Wall"))
        self.assertEqual(lookup["40002779"], ("ERR: Magic", "Fist of the Heavens"))

    def test_reforged_override_replaces_vanilla_item(self):
        watcher = SaveWatcher.__new__(SaveWatcher)
        watcher._tables = SimpleNamespace(categories={
            "armament": {"00118C30": {"name": "Erdsteel Dagger"}},
        })
        watcher._live_lookup = {}
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
        watcher._live_lookup = {}
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
