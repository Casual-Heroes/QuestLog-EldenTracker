import json
import os
from games.registry import TIER_DECAY, ENEMY, GREAT_ENEMY, LEGEND, DEMIGOD, GOD, load_boss_list

# Re-export tier constants so existing imports keep working
TIER_ENEMY       = ENEMY
TIER_GREAT_ENEMY = GREAT_ENEMY
TIER_LEGEND      = LEGEND
TIER_DEMIGOD     = DEMIGOD
TIER_GOD         = GOD


class BossTracker:
    def __init__(self, game_id, mode_id, run_dir):
        self._state_file = os.path.join(run_dir, "bosses.json")
        raw = load_boss_list(game_id, mode_id)

        self.bosses = {}
        for name, location, group, tier in raw:
            key = f"{name} ({location})"
            self.bosses[key] = {
                "name":     name,
                "location": location,
                "group":    group,
                "defeated": False,
                "tier":     tier,
            }
        self._load()

    def _load(self):
        if os.path.isfile(self._state_file):
            try:
                with open(self._state_file) as f:
                    saved = json.load(f)
                for key, state in saved.items():
                    if key in self.bosses:
                        self.bosses[key]["defeated"] = state.get("defeated", False)
            except Exception:
                pass

    def save(self):
        os.makedirs(os.path.dirname(self._state_file), exist_ok=True)
        with open(self._state_file, "w") as f:
            json.dump(
                {k: {"defeated": v["defeated"]} for k, v in self.bosses.items()},
                f, indent=2,
            )

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
                "group":    d["group"],
                "defeated": d["defeated"],
                "tier":     d["tier"],
            }
            for key, d in self.bosses.items()
        ]
