import json
import os
import importlib

# Tier constants — shared across all games
ENEMY       = "enemy"
GREAT_ENEMY = "great_enemy"
LEGEND      = "legend"
DEMIGOD     = "demigod"
GOD         = "god"

TIER_DECAY = {
    ENEMY:       25,
    GREAT_ENEMY: 50,
    LEGEND:      100,
    DEMIGOD:     125,
    GOD:         999,
}

from core.paths import games as _games_path
GAMES_DIR = _games_path()


def list_games():
    """Return list of available game dicts from games/*/meta.json."""
    games = []
    for name in sorted(os.listdir(GAMES_DIR)):
        meta_path = os.path.join(GAMES_DIR, name, "meta.json")
        if os.path.isfile(meta_path):
            with open(meta_path) as f:
                games.append(json.load(f))
    return games


def get_game(game_id):
    meta_path = os.path.join(GAMES_DIR, game_id, "meta.json")
    with open(meta_path) as f:
        return json.load(f)


def load_boss_list(game_id, mode_id):
    """
    Import games/<game_id>/bosses_<mode_id>.py and return its BOSSES list.
    For modes that include DLC, also imports bosses_dlc.py and appends it.
    Returns list of (name, location, group, tier) tuples.
    """
    game_meta = get_game(game_id)
    mode_meta = next((m for m in game_meta["modes"] if m["id"] == mode_id), None)
    if mode_meta is None:
        raise ValueError(f"Unknown mode '{mode_id}' for game '{game_id}'")

    mod = importlib.import_module(f"games.{game_id}.bosses_{mode_id}")
    bosses = list(mod.BOSSES)

    if mode_meta.get("includes_dlc"):
        try:
            dlc_mod = importlib.import_module(f"games.{game_id}.bosses_dlc")
            bosses += list(dlc_mod.BOSSES)
        except ModuleNotFoundError:
            pass

    return bosses
