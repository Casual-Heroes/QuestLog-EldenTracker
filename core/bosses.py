import json
import os

from core.catalog_sync import CatalogStore, CatalogSyncError
from games.registry import TIER_DECAY, ENEMY, GREAT_ENEMY, LEGEND, DEMIGOD, GOD, load_boss_list

# Re-export tier constants so existing imports keep working
TIER_ENEMY       = ENEMY
TIER_GREAT_ENEMY = GREAT_ENEMY
TIER_LEGEND      = LEGEND
TIER_DEMIGOD     = DEMIGOD
TIER_GOD         = GOD


class BossTracker:
    def __init__(self, game_id, mode_id, run_dir, catalog_store=None):
        self._state_file = os.path.join(run_dir, "bosses.json")
        self._catalog_store = catalog_store or CatalogStore()

        self.bosses = {}
        for boss in self._load_catalog_bosses(game_id, mode_id):
            key = boss["key"]
            self.bosses[key] = {
                "name":     boss["name"],
                "location": boss["location"],
                "region":   boss["region"],
                "group":    boss["region"],
                "defeated": False,
                "tier":     boss["tier"],
                "deaths":   0,
            }
        self._load()

    @staticmethod
    def _dataset_name(game_id, mode_id):
        mode = {"err": "reforged"}.get(mode_id, mode_id)
        if game_id == "elden_ring" and mode == "reforged":
            return "bosses_err"
        if game_id == "elden_ring" and mode == "vanilla":
            return "bosses_vanilla"
        return None

    def _load_catalog_bosses(self, game_id, mode_id):
        dataset_name = self._dataset_name(game_id, mode_id)
        if dataset_name:
            try:
                dataset = self._catalog_store.load(dataset_name)
                bosses = dataset.get("bosses") if isinstance(dataset, dict) else None
                if isinstance(bosses, list) and bosses:
                    return [self._canonical_boss(row) for row in bosses]
            except (CatalogSyncError, KeyError, TypeError, ValueError):
                pass

        # Offline safety fallback for games/modes that have not been migrated
        # to QuestLog datasets yet. Elden Ring/ERR should normally never need
        # this once a bundled or cached catalog is present.
        raw = load_boss_list(game_id, mode_id)
        return [
            {
                "key": f"{name} ({location})",
                "name": name,
                "location": location,
                "region": group,
                "tier": tier,
            }
            for name, location, group, tier in raw
        ]

    @staticmethod
    def _canonical_boss(row):
        key = str(row["key"])
        name = str(row.get("name") or key)
        location = str(row.get("location") or "")
        region = str(row.get("region") or location or "Other")
        tier = str(row.get("tier") or ENEMY)
        return {
            "key": key,
            "name": name,
            "location": location,
            "region": region,
            "tier": tier,
        }

    def _load(self):
        if os.path.isfile(self._state_file):
            try:
                with open(self._state_file) as f:
                    saved = json.load(f)
                for key, state in saved.items():
                    if key in self.bosses:
                        self.bosses[key]["defeated"] = state.get("defeated", False)
                        self.bosses[key]["deaths"] = int(state.get("deaths", 0) or 0)
                        for field in ("defeated_at", "last_death_at", "updated_at"):
                            if field in state:
                                self.bosses[key][field] = state[field]
            except Exception:
                pass

    def save(self):
        os.makedirs(os.path.dirname(self._state_file), exist_ok=True)
        state = {}
        for key, boss in self.bosses.items():
            entry = {
                "defeated": boss["defeated"],
                "deaths": int(boss.get("deaths", 0) or 0),
            }
            for field in ("defeated_at", "last_death_at", "updated_at"):
                if field in boss:
                    entry[field] = boss[field]
            state[key] = entry
        with open(self._state_file, "w") as f:
            json.dump(state, f, indent=2)

    def mark_defeated(self, key):
        if key in self.bosses:
            self.bosses[key]["defeated"] = True
            self.save()

    def mark_undefeated(self, key):
        if key in self.bosses:
            self.bosses[key]["defeated"] = False
            self.save()

    def reset_all(self):
        for b in self.bosses.values():
            b["defeated"] = False
        self.save()

    def defeated_count(self):
        return sum(1 for b in self.bosses.values() if b["defeated"])

    def total_count(self):
        return len(self.bosses)

    def get_tier(self, key):
        return self.bosses[key]["tier"] if key in self.bosses else None

    def export(self):
        return [
            {
                "key":      key,
                "name":     d["name"],
                "location": d["location"],
                "region":   d.get("region", d["group"]),
                "group":    d["group"],
                "defeated": d["defeated"],
                "tier":     d["tier"],
                "deaths":   int(d.get("deaths", 0) or 0),
            }
            for key, d in self.bosses.items()
        ]
