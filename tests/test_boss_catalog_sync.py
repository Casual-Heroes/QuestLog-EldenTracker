import json

from core.bosses import BossTracker


class FakeCatalogStore:
    def __init__(self, dataset):
        self.dataset = dataset

    def load(self, name):
        assert name == "bosses_err"
        return self.dataset


def test_boss_tracker_uses_catalog_metadata_and_preserves_state(tmp_path):
    boss_key = "Alabaster Lord (East of the Church of the Plague)"
    state_dir = tmp_path / "run"
    state_dir.mkdir()
    (state_dir / "bosses.json").write_text(
        json.dumps(
            {
                boss_key: {
                    "defeated": True,
                    "deaths": 44,
                    "defeated_at": 1780000000,
                }
            }
        ),
        encoding="utf-8",
    )

    catalog = FakeCatalogStore(
        {
            "dataset": "bosses_err",
            "bosses": [
                {
                    "key": boss_key,
                    "name": "Alabaster Lord",
                    "location": "East of the Church of the Plague",
                    "region": "Caelid",
                    "tier": "great_enemy",
                }
            ],
        }
    )

    tracker = BossTracker("elden_ring", "reforged", str(state_dir), catalog_store=catalog)

    boss = tracker.bosses[boss_key]
    assert boss["name"] == "Alabaster Lord"
    assert boss["location"] == "East of the Church of the Plague"
    assert boss["region"] == "Caelid"
    assert boss["group"] == "Caelid"
    assert boss["tier"] == "great_enemy"
    assert boss["defeated"] is True
    assert boss["deaths"] == 44
    assert boss["defeated_at"] == 1780000000


def test_boss_tracker_save_keeps_state_only(tmp_path):
    boss_key = "Leonine Misbegotten (War-Dead Catacombs)"
    catalog = FakeCatalogStore(
        {
            "dataset": "bosses_err",
            "bosses": [
                {
                    "key": boss_key,
                    "name": "Leonine Misbegotten",
                    "location": "War-Dead Catacombs",
                    "region": "Caelid",
                    "tier": "enemy",
                }
            ],
        }
    )

    tracker = BossTracker("elden_ring", "err", str(tmp_path), catalog_store=catalog)
    tracker.bosses[boss_key]["deaths"] = 3
    tracker.bosses[boss_key]["updated_at"] = 1780000100
    tracker.mark_defeated(boss_key)

    saved = json.loads((tmp_path / "bosses.json").read_text(encoding="utf-8"))
    assert saved == {
        boss_key: {
            "defeated": True,
            "deaths": 3,
            "updated_at": 1780000100,
        }
    }
