from games.registry import ENEMY, GREAT_ENEMY, LEGEND, DEMIGOD, GOD

# (name, location, group, tier)
# group  = tab label in the UI
# location = RegionHeader within that tab
# Includes ALL bosses — field bosses, mini-bosses, and main bosses alike
BOSSES = [
    # ── LIMGRAVE ──────────────────────────────────────────────────────────────
    ("Soldier of Godrick",                "Fringefolk Hero's Grave",     "Limgrave",                    ENEMY),
    ("Tree Sentinel",                     "Limgrave",                    "Limgrave",                    GREAT_ENEMY),
    ("Flying Dragon Agheel",              "Limgrave",                    "Limgrave",                    GREAT_ENEMY),
    ("Erdtree Burial Watchdog",           "Stormfoot Catacombs",         "Limgrave",                    ENEMY),
    ("Stonedigger Troll",                 "Limgrave Tunnels",            "Limgrave",                    ENEMY),
    ("Beastman of Farum Azula",           "Groveside Cave",              "Limgrave",                    ENEMY),
    ("Demi-Human Chiefs",                 "Coastal Cave",                "Limgrave",                    ENEMY),
    ("Bell Bearing Hunter",               "Warmaster's Shack",           "Limgrave",                    GREAT_ENEMY),
    ("Grave Warden Duelist",              "Murkwater Catacombs",         "Limgrave",                    ENEMY),
    ("Mad Pumpkin Head",                  "Waypoint Ruins",              "Limgrave",                    ENEMY),
    ("Crucible Knight",                   "Stormhill Evergaol",          "Limgrave",                    GREAT_ENEMY),
    ("Bloodhound Knight Darriwil",        "Forlorn Hound Evergaol",      "Limgrave",                    GREAT_ENEMY),
    ("Night's Cavalry",                   "Limgrave",                    "Limgrave",                    GREAT_ENEMY),
    ("Black Knife Assassin",              "Deathtouched Catacombs",      "Limgrave",                    ENEMY),
    ("Tibia Mariner",                     "Summonwater Village",         "Limgrave",                    ENEMY),
    ("Margit, the Fell Omen",             "Stormveil Castle Gate",       "Limgrave",                    LEGEND),
    ("Ulcerated Tree Spirit",             "Fringefolk Hero's Grave",     "Limgrave",                    GREAT_ENEMY),
    ("Deathbird",                         "Limgrave",                    "Limgrave",                    ENEMY),
    ("Guardian Golem",                    "Highroad Cave",               "Limgrave",                    ENEMY),
    ("Patches",                           "Murkwater Cave",              "Limgrave",                    ENEMY),

    # ── STORMVEIL CASTLE ──────────────────────────────────────────────────────
    ("Grafted Scion",                     "Chapel of Anticipation",      "Limgrave",                    ENEMY),
    ("Grafted Scion",                     "Stormveil Castle",            "Stormveil Castle",            ENEMY),
    ("Crucible Knight",                   "Stormveil Castle",            "Stormveil Castle",            GREAT_ENEMY),
    ("Elder Lion",                        "Stormveil Castle",            "Stormveil Castle",            ENEMY),
    ("Godrick the Grafted",               "Stormveil Castle",            "Stormveil Castle",            DEMIGOD),

    # ── WEEPING PENINSULA ─────────────────────────────────────────────────────
    ("Erdtree Burial Watchdog",           "Impaler's Catacombs",         "Weeping Peninsula",           ENEMY),
    ("Runebear",                          "Earthbore Cave",              "Weeping Peninsula",           ENEMY),
    ("Night's Cavalry",                   "Weeping Peninsula",           "Weeping Peninsula",           GREAT_ENEMY),
    ("Scaly Misbegotten",                 "Morne Tunnel",                "Weeping Peninsula",           ENEMY),
    ("Cemetery Shade",                    "Tombsward Catacombs",         "Weeping Peninsula",           ENEMY),
    ("Ancient Hero of Zamor",             "Weeping Evergaol",            "Weeping Peninsula",           GREAT_ENEMY),
    ("Erdtree Avatar",                    "Weeping Peninsula",           "Weeping Peninsula",           GREAT_ENEMY),
    ("Leonine Misbegotten",               "Castle Morne",                "Weeping Peninsula",           LEGEND),
    ("Deathbird",                         "Weeping Peninsula",           "Weeping Peninsula",           ENEMY),
    ("Miranda the Blighted Bloom",        "Tombsward Cave",              "Weeping Peninsula",           ENEMY),

    # ── LIURNIA OF THE LAKES ──────────────────────────────────────────────────
    ("Grafted Scion",                     "Academy Gate Town",           "Liurnia of the Lakes",        ENEMY),
    ("Cleanrot Knight",                   "Stillwater Cave",             "Liurnia of the Lakes",        ENEMY),
    ("Adan, Thief of Fire",               "Malefactor's Evergaol",       "Liurnia of the Lakes",        ENEMY),
    ("Tibia Mariner",                     "Liurnia of the Lakes",        "Liurnia of the Lakes",        ENEMY),
    ("Erdtree Burial Watchdog",           "Cliffbottom Catacombs",       "Liurnia of the Lakes",        ENEMY),
    ("Night's Cavalry",                   "Liurnia of the Lakes",        "Liurnia of the Lakes",        GREAT_ENEMY),
    ("Erdtree Avatar",                    "Liurnia of the Lakes",        "Liurnia of the Lakes",        GREAT_ENEMY),
    ("Crystalian",                        "Academy Crystal Cave",        "Liurnia of the Lakes",        ENEMY),
    ("Crystalians (Spear & Staff)",       "Raya Lucaria Crystal Tunnel", "Liurnia of the Lakes",        GREAT_ENEMY),
    ("Red Wolf of Radagon",               "Raya Lucaria Academy",        "Liurnia of the Lakes",        GREAT_ENEMY),
    ("Rennala, Queen of the Full Moon",   "Raya Lucaria Academy",        "Liurnia of the Lakes",        DEMIGOD),
    ("Alabaster Lord",                    "Royal Grave Evergaol",        "Liurnia of the Lakes",        ENEMY),
    ("Royal Revenant",                    "Kingsrealm Ruins",            "Liurnia of the Lakes",        ENEMY),
    ("Royal Knight Loretta",              "Caria Manor",                 "Liurnia of the Lakes",        LEGEND),
    ("Bols, Carian Knight",               "Cuckoo's Evergaol",           "Liurnia of the Lakes",        GREAT_ENEMY),
    ("Alecto, Black Knife Ringleader",    "Black Knife Catacombs",       "Liurnia of the Lakes",        LEGEND),
    ("Spirit-Caller Snail",               "Road's End Catacombs",        "Liurnia of the Lakes",        ENEMY),
    ("Omenkiller",                        "Village of the Albinaurics",  "Liurnia of the Lakes",        ENEMY),
    ("Glintstone Dragon Adula",           "Liurnia of the Lakes",        "Liurnia of the Lakes",        LEGEND),
    ("Glintstone Dragon Smarag",          "Liurnia of the Lakes",        "Liurnia of the Lakes",        GREAT_ENEMY),
    ("Death Rite Bird",                   "Liurnia of the Lakes",        "Liurnia of the Lakes",        GREAT_ENEMY),
    ("Bell Bearing Hunter",               "Church of Vows",              "Liurnia of the Lakes",        GREAT_ENEMY),
    ("Deathbird",                         "Liurnia of the Lakes",        "Liurnia of the Lakes",        ENEMY),
    ("Black Knife Assassin",              "Black Knife Catacombs",       "Liurnia of the Lakes",        ENEMY),
    ("Bloodhound Knight",                 "Lakeside Crystal Cave",       "Liurnia of the Lakes",        GREAT_ENEMY),
    ("Cemetery Shade",                    "Liurnia of the Lakes",        "Liurnia of the Lakes",        ENEMY),
    ("Godskin Noble",                     "Temple of Eiglay",            "Liurnia of the Lakes",        LEGEND),

    # ── CAELID ────────────────────────────────────────────────────────────────
    ("Magma Wyrm",                        "Gael Tunnel",                 "Caelid",                      GREAT_ENEMY),
    ("Erdtree Avatar",                    "Caelid",                      "Caelid",                      GREAT_ENEMY),
    ("Mad Pumpkin Head",                  "Caelid",                      "Caelid",                      ENEMY),
    ("Erdtree Burial Watchdog",           "Caelid Catacombs",            "Caelid",                      ENEMY),
    ("Decaying Ekzykes",                  "Caelid",                      "Caelid",                      LEGEND),
    ("Night's Cavalry",                   "Caelid",                      "Caelid",                      GREAT_ENEMY),
    ("Commander O'Neil",                  "Swamp of Aeonia",             "Caelid",                      LEGEND),
    ("Nox Swordstress & Nox Priest",      "Sellia, Town of Sorcery",     "Caelid",                      GREAT_ENEMY),
    ("Black Blade Kindred",               "Bestial Sanctum",             "Caelid",                      GREAT_ENEMY),
    ("Fallingstar Beast",                 "Sellia Crystal Tunnel",       "Caelid",                      GREAT_ENEMY),
    ("Starscourge Radahn",                "Wailing Dunes",               "Caelid",                      DEMIGOD),
    ("Death Rite Bird",                   "Caelid",                      "Caelid",                      GREAT_ENEMY),
    ("Frenzied Duelist",                  "Gaol Cave",                   "Caelid",                      ENEMY),
    ("Cleanrot Knight",                   "Abandoned Cave",              "Caelid",                      ENEMY),
    ("Battlemage Hugues",                 "Sellia Evergaol",             "Caelid",                      ENEMY),
    ("Cemetery Shade",                    "Caelid Catacombs",            "Caelid",                      ENEMY),
    ("Crystalians (Duo)",                 "Sellia Crystal Tunnel",       "Caelid",                      GREAT_ENEMY),
    ("Crucible Knight & Misbegotten",     "Redmane Castle",              "Caelid",                      GREAT_ENEMY),
    ("Putrid Avatar",                     "Caelid",                      "Caelid",                      GREAT_ENEMY),

    # ── DRAGONBARROW ──────────────────────────────────────────────────────────
    ("Elder Dragon Greyoll",              "Dragonbarrow",                "Dragonbarrow",                LEGEND),
    ("Godskin Apostle",                   "Dragon Temple",               "Dragonbarrow",                LEGEND),
    ("Beastman of Farum Azula",           "Farum Azula Ruins",           "Dragonbarrow",                ENEMY),
    ("Flying Dragon Greyll",              "Dragonbarrow",                "Dragonbarrow",                GREAT_ENEMY),
    ("Bell Bearing Hunter",               "Dragonbarrow",                "Dragonbarrow",                GREAT_ENEMY),
    ("Black Blade Kindred",               "Dragonbarrow",                "Dragonbarrow",                GREAT_ENEMY),
    ("Putrid Avatar",                     "Dragonbarrow",                "Dragonbarrow",                GREAT_ENEMY),
    ("Night's Cavalry",                   "Dragonbarrow",                "Dragonbarrow",                GREAT_ENEMY),
    ("Putrid Tree Spirit",                "War-Dead Catacombs",          "Dragonbarrow",                GREAT_ENEMY),
    ("Cleanrot Knight (Duo)",             "Abandoned Cave",              "Dragonbarrow",                ENEMY),
    ("Putrid Crystalian (Trio)",          "Sellia Hideaway",             "Dragonbarrow",                GREAT_ENEMY),

    # ── ALTUS PLATEAU ─────────────────────────────────────────────────────────
    ("Stonedigger Troll",                 "Old Altus Tunnel",            "Altus Plateau",               ENEMY),
    ("Elemer of the Briar",               "The Shaded Castle",           "Altus Plateau",               LEGEND),
    ("Black Knife Assassin",              "Sage's Cave",                 "Altus Plateau",               ENEMY),
    ("Black Knife Assassin",              "Sainted Hero's Grave",        "Altus Plateau",               ENEMY),
    ("Godskin Apostle",                   "Dominula, Windmill Village",  "Altus Plateau",               LEGEND),
    ("Tibia Mariner",                     "Altus Plateau",               "Altus Plateau",               ENEMY),
    ("Necromancer Garris",                "Hidden Path to the Haligtree","Altus Plateau",               ENEMY),
    ("Erdtree Burial Watchdog",           "Unsightly Catacombs",         "Altus Plateau",               ENEMY),
    ("Tree Sentinel (Duo)",               "Altus Plateau",               "Altus Plateau",               GREAT_ENEMY),
    ("Draconic Tree Sentinel",            "Capital Outskirts",           "Altus Plateau",               LEGEND),
    ("Godefroy the Grafted",              "Golden Lineage Evergaol",     "Altus Plateau",               LEGEND),
    ("Demi-Human Queen Gilika",           "Lux Ruins",                   "Altus Plateau",               ENEMY),
    ("Night's Cavalry",                   "Altus Plateau",               "Altus Plateau",               GREAT_ENEMY),
    ("Sanguine Noble",                    "Writheblood Ruins",           "Altus Plateau",               ENEMY),
    ("Wormface",                          "Altus Plateau",               "Altus Plateau",               GREAT_ENEMY),
    ("Crystalians (Spear & Ringblade)",   "Altus Tunnel",                "Altus Plateau",               GREAT_ENEMY),
    ("Omenkiller & Miranda the Blighted", "Perfumer's Grotto",           "Altus Plateau",               GREAT_ENEMY),
    ("Fallingstar Beast",                 "Capital Outskirts",           "Altus Plateau",               GREAT_ENEMY),
    ("Ancient Hero of Zamor",             "Sainted Hero's Grave",        "Altus Plateau",               GREAT_ENEMY),
    ("Perfumer Tricia & Misbegotten",     "Unsightly Catacombs",         "Altus Plateau",               ENEMY),
    ("Ancient Dragon Lansseax",           "Altus Plateau",               "Altus Plateau",               LEGEND),
    ("Bell Bearing Hunter",               "Capital Outskirts",           "Altus Plateau",               GREAT_ENEMY),
    ("Fell Twins",                        "Capital Outskirts",           "Altus Plateau",               LEGEND),
    ("Crucible Knight & Crucible Knight Ordovis", "Auriza Hero's Grave", "Altus Plateau",               LEGEND),
    ("Grave Warden Duelist",              "Auriza Side Tomb",            "Altus Plateau",               ENEMY),
    ("Onyx Lord",                         "Sealed Tunnel",               "Altus Plateau",               ENEMY),
    ("Deathbird",                         "Capital Outskirts",           "Altus Plateau",               ENEMY),

    # ── MT. GELMIR ────────────────────────────────────────────────────────────
    ("Ancient Dragon Lansseax",           "Mt. Gelmir",                  "Mt. Gelmir",                  LEGEND),
    ("Perfumer Tricia",                   "Unsightly Catacombs",         "Mt. Gelmir",                  ENEMY),
    ("Grafted Scion",                     "Mt. Gelmir",                  "Mt. Gelmir",                  ENEMY),
    ("Ulcerated Tree Spirit",             "Mt. Gelmir",                  "Mt. Gelmir",                  GREAT_ENEMY),
    ("Full-Grown Fallingstar Beast",      "Mt. Gelmir",                  "Mt. Gelmir",                  LEGEND),
    ("Kindred of Rot (Duo)",              "Seethewater Cave",            "Mt. Gelmir",                  ENEMY),
    ("Demi-Human Queen Maggie",           "Hermit Village",              "Mt. Gelmir",                  ENEMY),
    ("Abductor Virgins (Duo)",            "Volcano Manor",               "Mt. Gelmir",                  GREAT_ENEMY),
    ("Omenkiller",                        "Volcano Manor",               "Mt. Gelmir",                  ENEMY),
    ("Demi-Human Queen Margot",           "Volcano Cave",                "Mt. Gelmir",                  ENEMY),
    ("God-Devouring Serpent / Rykard",    "Volcano Manor",               "Mt. Gelmir",                  DEMIGOD),
    ("Magma Wyrm",                        "Fort Laiedd",                 "Mt. Gelmir",                  GREAT_ENEMY),
    ("Red Wolf of the Champion",          "Gelmir Hero's Grave",         "Mt. Gelmir",                  GREAT_ENEMY),
    ("Godskin Noble",                     "Volcano Manor",               "Mt. Gelmir",                  LEGEND),

    # ── LEYNDELL, ROYAL CAPITAL ───────────────────────────────────────────────
    ("Divine Bridge Golem",               "Leyndell, Royal Capital",     "Leyndell",                    ENEMY),
    ("Bell Bearing Hunter",               "Leyndell, Royal Capital",     "Leyndell",                    GREAT_ENEMY),
    ("Draconic Tree Sentinel",            "Leyndell, Royal Capital",     "Leyndell",                    LEGEND),
    ("Crucible Knight Ordovis",           "Auriza Hero's Grave",         "Leyndell",                    LEGEND),
    ("Fell Twins",                        "Leyndell, Royal Capital",     "Leyndell",                    LEGEND),
    ("Morgott, the Omen King",            "Leyndell, Royal Capital",     "Leyndell",                    DEMIGOD),
    ("Onyx Lord",                         "Leyndell, Royal Capital",     "Leyndell",                    ENEMY),
    ("Erdtree Avatar",                    "Leyndell, Royal Capital",     "Leyndell",                    GREAT_ENEMY),
    ("Godfrey, First Elden Lord (Shade)", "Leyndell, Royal Capital",     "Leyndell",                    LEGEND),
    ("Deathbird",                         "Leyndell, Royal Capital",     "Leyndell",                    ENEMY),
    ("Margit, the Fell Omen",             "Leyndell, Royal Capital",     "Leyndell",                    LEGEND),
    ("Grave Warden Duelist",              "Leyndell, Royal Capital",     "Leyndell",                    ENEMY),
    ("Frenzied Duelist",                  "Leyndell, Royal Capital",     "Leyndell",                    ENEMY),
    ("Esgar, Priest of Blood",            "Leyndell, Royal Capital",     "Leyndell",                    ENEMY),
    ("Mohg, the Omen",                    "Leyndell, Royal Capital",     "Leyndell",                    LEGEND),

    # ── FORBIDDEN LANDS ───────────────────────────────────────────────────────
    ("Black Blade Kindred",               "Forbidden Lands",             "Forbidden Lands",             GREAT_ENEMY),
    ("Night's Cavalry",                   "Forbidden Lands",             "Forbidden Lands",             GREAT_ENEMY),
    ("Stray Mimic Tear",                  "Hidden Path to the Haligtree","Forbidden Lands",             LEGEND),

    # ── MOUNTAINTOPS OF THE GIANTS ────────────────────────────────────────────
    ("Borealis, the Freezing Fog",        "Mountaintops of the Giants",  "Mountaintops of the Giants",  LEGEND),
    ("Godskin Apostle & Godskin Noble",   "Spiritcaller's Cave",         "Mountaintops of the Giants",  LEGEND),
    ("Erdtree Avatar",                    "Mountaintops of the Giants",  "Mountaintops of the Giants",  GREAT_ENEMY),
    ("Fire Giant",                        "Mountaintops of the Giants",  "Mountaintops of the Giants",  DEMIGOD),
    ("Commander Niall",                   "Castle Sol",                  "Mountaintops of the Giants",  LEGEND),
    ("Roundtable Knight Vyke",            "Mountaintops of the Giants",  "Mountaintops of the Giants",  GREAT_ENEMY),
    ("Death Rite Bird",                   "Mountaintops of the Giants",  "Mountaintops of the Giants",  GREAT_ENEMY),
    ("Ancient Hero of Zamor",             "Giants' Mountaintop Catacombs","Mountaintops of the Giants", GREAT_ENEMY),
    ("Ulcerated Tree Spirit",             "Giants' Mountaintop Catacombs","Mountaintops of the Giants", GREAT_ENEMY),

    # ── CONSECRATED SNOWFIELD ─────────────────────────────────────────────────
    ("Night's Cavalry (Duo)",             "Consecrated Snowfield",       "Consecrated Snowfield",       GREAT_ENEMY),
    ("Putrid Grave Warden Duelist",       "Consecrated Snowfield",       "Consecrated Snowfield",       ENEMY),
    ("Death Rite Bird",                   "Consecrated Snowfield",       "Consecrated Snowfield",       GREAT_ENEMY),
    ("Putrid Avatar",                     "Consecrated Snowfield",       "Consecrated Snowfield",       GREAT_ENEMY),
    ("Astel, Stars of Darkness",          "Yelough Anix Tunnel",         "Consecrated Snowfield",       LEGEND),
    ("Great Wyrm Theodorix",              "Consecrated Snowfield",       "Consecrated Snowfield",       LEGEND),
    ("Misbegotten Crusader",              "Cave of the Forlorn",         "Consecrated Snowfield",       ENEMY),

    # ── MIQUELLA'S HALIGTREE ──────────────────────────────────────────────────
    ("Loretta, Knight of the Haligtree",  "Miquella's Haligtree",        "Miquella's Haligtree",        LEGEND),
    ("Malenia, Blade of Miquella",        "Elphael, Brace of the Haligtree", "Miquella's Haligtree",   GOD),

    # ── UNDERGROUND — SIOFRA RIVER ────────────────────────────────────────────
    ("Ancestor Spirit",                   "Hallowhorn Grounds",          "Underground",                 LEGEND),
    ("Dragonkin Soldier",                 "Siofra River",                "Underground",                 GREAT_ENEMY),
    ("Mohg, Lord of Blood",               "Mohgwyn Palace",              "Underground",                 DEMIGOD),

    # ── UNDERGROUND — NOKRON / ETERNAL CITY ───────────────────────────────────
    ("Mimic Tear",                        "Night's Sacred Ground",       "Underground",                 LEGEND),
    ("Regal Ancestor Spirit",             "Nokron, Eternal City",        "Underground",                 LEGEND),
    ("Valiant Gargoyle (Duo)",            "Siofra Aqueduct",             "Underground",                 LEGEND),

    # ── UNDERGROUND — AINSEL RIVER ────────────────────────────────────────────
    ("Dragonkin Soldier of Nokstella",    "Ainsel River",                "Underground",                 LEGEND),

    # ── UNDERGROUND — DEEPROOT DEPTHS ─────────────────────────────────────────
    ("Fia's Champions",                   "Deeproot Depths",             "Underground",                 LEGEND),
    ("Crucible Knight Siluria",           "Deeproot Depths",             "Underground",                 LEGEND),
    ("Lichdragon Fortissax",              "Deeproot Depths",             "Underground",                 LEGEND),
    ("Erdtree Avatar",                    "Deeproot Depths",             "Underground",                 GREAT_ENEMY),

    # ── UNDERGROUND — LAKE OF ROT ─────────────────────────────────────────────
    ("Dragonkin Soldier",                 "Lake of Rot",                 "Underground",                 GREAT_ENEMY),
    ("Astel, Naturalborn of the Void",    "Grand Cloister",              "Underground",                 LEGEND),

    # ── CRUMBLING FARUM AZULA ─────────────────────────────────────────────────
    ("Godskin Duo",                       "Crumbling Farum Azula",       "Crumbling Farum Azula",       LEGEND),
    ("Maliketh, the Black Blade",         "Crumbling Farum Azula",       "Crumbling Farum Azula",       DEMIGOD),
    ("Dragonlord Placidusax",             "Crumbling Farum Azula",       "Crumbling Farum Azula",       GOD),
    ("Draconic Tree Sentinel",            "Crumbling Farum Azula",       "Crumbling Farum Azula",       LEGEND),

    # ── LEYNDELL, ASHEN CAPITAL ───────────────────────────────────────────────
    ("Sir Gideon Ofnir, the All-Knowing", "Leyndell, Ashen Capital",     "Leyndell",                    LEGEND),
    ("Hoarah Loux / Godfrey",             "Leyndell, Ashen Capital",     "Leyndell",                    DEMIGOD),
    ("Radagon of the Golden Order",       "Elden Throne",                "Leyndell",                    GOD),
    ("Elden Beast",                       "Elden Throne",                "Leyndell",                    GOD),
]
