from games.registry import ENEMY, GREAT_ENEMY, LEGEND, DEMIGOD, GOD
from games.elden_ring.bosses_vanilla import BOSSES as _VANILLA
from games.elden_ring.bosses_dlc import BOSSES as _DLC

# Vanilla/DLC bosses that Reforged removes or replaces.
# Key format: "name (location)" — matches BossTracker key generation.
_REPLACED = {
    "Soldier of Godrick (Fringefolk Hero's Grave)",         # → Crucible Knight Rhyacis
    "Crucible Knight & Misbegotten (Redmane Castle)",       # → Azash, Pride of the Redmanes
    "Leonine Misbegotten (Castle Morne)",                   # → Azash fight also covers this
    "Valiant Gargoyle (Duo) (Siofra Aqueduct)",             # → Gnoster, the False Sky
    "Ancient Hero of Zamor (Sainted Hero's Grave)",         # → Grave Sentinel Wyngrant
    "Adan, Thief of Fire (Malefactor's Evergaol)",          # → Thief-Taker Acacio
}

_VANILLA_FILTERED = [b for b in _VANILLA if f"{b[0]} ({b[1]})" not in _REPLACED]
_DLC_FILTERED     = [b for b in _DLC     if f"{b[0]} ({b[1]})" not in _REPLACED]

# New bosses added by Reforged — filed under their actual in-world area group.
# No separate "Reforged" tab; they belong to the world alongside vanilla bosses.
_REFORGED_NEW = [
    # ── LIMGRAVE ──────────────────────────────────────────────────────────────
    # Replaces Soldier of Godrick — Cave of Knowledge renamed to Gilded Cave of Knowledge
    ("Crucible Knight Rhyacis",           "Gilded Cave of Knowledge",    "Limgrave",                    GREAT_ENEMY),
    # New — broken bridge, northern Limgrave
    ("Fallen Cavalry",                    "Northern Limgrave",           "Limgrave",                    GREAT_ENEMY),

    # ── WEEPING PENINSULA ─────────────────────────────────────────────────────
    # New — Bridge of Sacrifice (scaled as Weeping Peninsula)
    ("Dismounted Tree Sentinel",          "Bridge of Sacrifice",         "Weeping Peninsula",           GREAT_ENEMY),

    # ── LIURNIA OF THE LAKES ──────────────────────────────────────────────────
    # New — ruins northeast of Sorcerer's Isle
    ("Fulminating Runebear",              "Liurnia of the Lakes",        "Liurnia of the Lakes",        GREAT_ENEMY),
    # Replaces Adan, Thief of Fire
    ("Thief-Taker Acacio",                "Malefactor's Evergaol",       "Liurnia of the Lakes",        ENEMY),
    # New — Four Belfries / Nokron waygate
    ("Crucible Knight Hirnan",            "Four Belfries",               "Liurnia of the Lakes",        LEGEND),

    # ── CAELID ────────────────────────────────────────────────────────────────
    # Replaces Leonine Misbegotten + Crucible Knight at Redmane Castle plaza
    ("Azash, Pride of the Redmanes",      "Redmane Castle",              "Caelid",                      LEGEND),

    # ── DRAGONBARROW ──────────────────────────────────────────────────────────
    # New — Farum Greatbridge
    ("Morion, the Unbound Death",         "Farum Greatbridge",           "Dragonbarrow",                LEGEND),

    # ── MT. GELMIR ────────────────────────────────────────────────────────────
    # New — end of Serpentine Depths
    ("Flamelost Knight",                  "Serpentine Depths",           "Mt. Gelmir",                  LEGEND),
    # New — Giant's Gravepost (also Ashen Leyndell, tracked as one entry)
    ("Fellthorn Spirit",                  "Giant's Gravepost",           "Mt. Gelmir",                  GREAT_ENEMY),

    # ── LEYNDELL ──────────────────────────────────────────────────────────────
    # New — Erdtree Sanctuary
    ("Royal Guardian Helicos",            "Erdtree Sanctuary",           "Leyndell",                    LEGEND),
    # New — Subterranean Shunning-Grounds
    ("Equilibrious Beast",                "Subterranean Shunning-Grounds","Leyndell",                   DEMIGOD),
    # New — post-game only
    ("Hallowed Avatar",                   "Erdtree (Post-Game)",         "Leyndell",                    GOD),

    # ── ALTUS PLATEAU ─────────────────────────────────────────────────────────
    # Replaces Ancient Hero of Zamor at Sainted Hero's Grave
    ("Grave Sentinel Wyngrant",           "Sainted Hero's Grave",        "Altus Plateau",               GREAT_ENEMY),

    # ── UNDERGROUND ───────────────────────────────────────────────────────────
    # Replaces Valiant Gargoyle duo at end of Siofra Aqueduct
    ("Gnoster, the False Sky",            "Siofra Aqueduct",             "Underground",                 LEGEND),
    # New — Night's Sacred Ground, Nokron
    ("Nox Nightmaiden",                   "Night's Sacred Ground",       "Underground",                 GREAT_ENEMY),

    # ── SHADOW OF THE ERDTREE ─────────────────────────────────────────────────
    # Replaces Divine Bird Warrior — accessed via Castle Ensis belfry waygate
    ("Fulghor, Champion of Rauh",         "Ancient Ruins of Rauh",       "Shadow of the Erdtree",       LEGEND),
]

# Full Reforged list: filtered vanilla + filtered DLC + new Reforged bosses
BOSSES = _VANILLA_FILTERED + _DLC_FILTERED + _REFORGED_NEW
