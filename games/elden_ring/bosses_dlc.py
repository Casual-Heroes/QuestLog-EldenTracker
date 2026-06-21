from games.registry import ENEMY, GREAT_ENEMY, LEGEND, DEMIGOD, GOD

DLC = "Shadow of the Erdtree"

# Shadow of the Erdtree DLC bosses.
# All share the "Shadow of the Erdtree" tab group.
# Location = correct in-world sub-area for the RegionHeader within that tab.
BOSSES = [
    # ── GRAVESITE PLAIN ───────────────────────────────────────────────────────
    ("Blackgaol Knight",                  "Gravesite Plain",             DLC, ENEMY),
    ("Ghostflame Dragon",                 "Gravesite Plain",             DLC, GREAT_ENEMY),
    ("Death Knight",                      "Gravesite Plain",             DLC, GREAT_ENEMY),
    ("Demi-Human Swordsmaster Onze",      "Gravesite Plain",             DLC, ENEMY),
    ("Ancient Dragon-Man",                "Gravesite Plain",             DLC, GREAT_ENEMY),
    ("Divine Beast Dancing Lion",         "Gravesite Plain",             DLC, DEMIGOD),
    ("Rellana, Twin Moon Knight",         "Gravesite Plain",             DLC, LEGEND),

    # ── CERULEAN COAST ────────────────────────────────────────────────────────
    ("Dancer of Ranah",                   "Cerulean Coast",              DLC, ENEMY),
    ("Demi-Human Queen Marigga",          "Cerulean Coast",              DLC, ENEMY),
    ("Ghostflame Dragon",                 "Cerulean Coast",              DLC, GREAT_ENEMY),
    ("Putrescent Knight",                 "Cerulean Coast",              DLC, LEGEND),

    # ── SCADU ALTUS ───────────────────────────────────────────────────────────
    ("Ralva the Great Red Bear",          "Scadu Altus",                 DLC, GREAT_ENEMY),
    ("Red Bear",                          "Scadu Altus",                 DLC, ENEMY),
    ("Black Knight Garrew",               "Scadu Altus",                 DLC, ENEMY),
    ("Black Knight Edreed",               "Scadu Altus",                 DLC, ENEMY),
    ("Curseblade Labirith",               "Scadu Altus",                 DLC, ENEMY),
    ("Dryleaf Dane",                      "Scadu Altus",                 DLC, GREAT_ENEMY),
    ("Ghostflame Dragon",                 "Scadu Altus",                 DLC, GREAT_ENEMY),
    ("Jori, Elder Inquisitor",            "Scadu Altus",                 DLC, GREAT_ENEMY),
    ("Rakshasa",                          "Scadu Altus",                 DLC, ENEMY),
    ("Count Ymir, Mother of Fingers",     "Scadu Altus",                 DLC, ENEMY),
    ("Golden Hippopotamus",               "Scadu Altus",                 DLC, GREAT_ENEMY),
    ("Messmer the Impaler",               "Scadu Altus",                 DLC, DEMIGOD),
    ("Chief Bloodfiend",                  "Scadu Altus",                 DLC, GREAT_ENEMY),

    # ── ABYSSAL WOODS ─────────────────────────────────────────────────────────
    ("Midra, Lord of Frenzied Flame",     "Abyssal Woods",               DLC, DEMIGOD),

    # ── RAUH BASE ─────────────────────────────────────────────────────────────
    ("Death Knight",                      "Rauh Base",                   DLC, GREAT_ENEMY),
    ("Rugalea the Great Red Bear",        "Rauh Base",                   DLC, GREAT_ENEMY),

    # ── SCADUVIEW ─────────────────────────────────────────────────────────────
    ("Tree Sentinel",                     "Scaduview",                   DLC, GREAT_ENEMY),
    ("Fallingstar Beast",                 "Scaduview",                   DLC, GREAT_ENEMY),
    ("Scadutree Avatar",                  "Scaduview",                   DLC, DEMIGOD),
    ("Commander Gaius",                   "Scaduview",                   DLC, LEGEND),

    # ── JAGGED PEAK ───────────────────────────────────────────────────────────
    ("Jagged Peak Drake",                 "Jagged Peak",                 DLC, ENEMY),
    ("Jagged Peak Drake",                 "Jagged Peak",                 DLC, ENEMY),
    ("Ancient Dragon-Man",                "Jagged Peak",                 DLC, GREAT_ENEMY),
    ("Death Rite Bird",                   "Jagged Peak",                 DLC, GREAT_ENEMY),
    ("Ancient Dragon Senessax",           "Jagged Peak",                 DLC, LEGEND),
    ("Bayle the Dread",                   "Jagged Peak",                 DLC, GOD),

    # ── CHARO'S HIDDEN GRAVE ──────────────────────────────────────────────────
    ("Death Rite Bird",                   "Charo's Hidden Grave",        DLC, GREAT_ENEMY),
    ("Tibia Mariner",                     "Charo's Hidden Grave",        DLC, ENEMY),
    ("Lamenter",                          "Charo's Hidden Grave",        DLC, LEGEND),
    ("Demi-Human Queen Marigga",          "Charo's Hidden Grave",        DLC, ENEMY),

    # ── ANCIENT RUINS OF RAUH ─────────────────────────────────────────────────
    ("Divine Beast Dancing Lion",         "Ancient Ruins of Rauh",       DLC, DEMIGOD),
    ("Romina, Saint of the Bud",          "Ancient Ruins of Rauh",       DLC, DEMIGOD),
    ("Metyr, Mother of Fingers",          "Ancient Ruins of Rauh",       DLC, DEMIGOD),

    # ── ENIR-ILIM ─────────────────────────────────────────────────────────────
    ("Needle Knight Leda & Allies",       "Enir-Ilim",                   DLC, LEGEND),
    ("Promised Consort Radahn",           "Enir-Ilim",                   DLC, GOD),
]
