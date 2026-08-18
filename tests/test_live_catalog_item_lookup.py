import unittest
from types import SimpleNamespace

from core.live_catalog_item_lookup import build_lookup


class LiveCatalogItemLookupTests(unittest.TestCase):
    def test_vanilla_calculation_ids_resolve_save_item_ids(self):
        store = SimpleNamespace(
            load=lambda name: {
                "payload": {
                    "weapons": {"Rellana's Twin Blades": {"Standard": {"regulation_id": 67520000}}},
                    "armor": {"Alberich's Robe (Altered)": {"regulation_id": 121100}},
                    "talismans": {"Crusade Insignia": {"regulation_id": 8050}},
                }
            },
            load_live=lambda name: {
                "spells": [{"id": 208, "name": "Terra Magica"}],
            },
        )

        lookup = build_lookup("vanilla", store=store)

        self.assertEqual(lookup["04064600"], ("armament", "Rellana's Twin Blades"))
        self.assertEqual(lookup["1001D90C"], ("armor", "Alberich's Robe (Altered)"))
        self.assertEqual(lookup["20001F72"], ("talisman", "Crusade Insignia"))
        self.assertEqual(lookup["400000D0"], ("magic", "Terra Magica"))

    def test_reforged_uses_vanilla_weapon_ids_when_err_weapon_ids_are_absent(self):
        def load(name):
            if name == "vanilla_calculations":
                return {
                    "payload": {
                        "weapons": {"Rellana's Twin Blades": {"Standard": {"regulation_id": 67520000}}},
                    }
                }
            return {
                "payload": {
                    "weapons": {"Rellana's Twin Blades": {"Standard": {"weight": 9}}},
                    "armor": {},
                    "talismans": {},
                }
            }

        store = SimpleNamespace(load=load, load_live=lambda name: {"spells": []})

        lookup = build_lookup("reforged", store=store)

        self.assertEqual(lookup["04064600"], ("ERR: Weapons", "Rellana's Twin Blades"))
