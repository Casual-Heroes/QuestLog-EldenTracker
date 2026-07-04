import json
import os
from core.paths import overlay as _overlay_path

_OVERLAY_FILE = _overlay_path("stats.json")


def write_state(session, death_tracker, boss_tracker, run_dir=None, rage_label="Rage Index"):
    rage_pct, rage_name, rage_color = death_tracker.rage_state()
    hollow_streak = death_tracker.hollow_streak()

    payload = {
        "session_active":  session.active,
        "session_deaths":  session.session_deaths,
        "total_deaths":    session.total_deaths,
        "elapsed":         session.elapsed_str(),
        "deaths_per_hour": death_tracker.deaths_per_hour(),   # None = under 10-min threshold
        "rage_label":      rage_label,
        "rage_pct":        rage_pct,
        "rage_name":       rage_name,
        "rage_color":      rage_color,
        "hollow_streak":   hollow_streak,
        "is_hollow":       rage_pct >= 100,
        "bosses_defeated": boss_tracker.defeated_count(),
        "bosses_total":    boss_tracker.total_count(),
        "boss_list":       boss_tracker.export(),
    }

    # Write to run-specific stats file
    if run_dir:
        run_stats = os.path.join(run_dir, "stats.json")
        os.makedirs(run_dir, exist_ok=True)
        with open(run_stats, "w") as f:
            json.dump(payload, f)

    # Always update the legacy overlay file so OBS stays in sync
    os.makedirs(os.path.dirname(_OVERLAY_FILE), exist_ok=True)
    with open(_OVERLAY_FILE, "w") as f:
        json.dump(payload, f)
