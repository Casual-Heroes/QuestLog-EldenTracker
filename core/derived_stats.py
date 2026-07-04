"""
Derived stat calculations for the build planner.
ER: piecewise linear formulas verified against Fextralife wiki.
ERR: lookup tables fetched from /api/soulslike/derived-curves/?game=err
"""

from math import floor

ALL_STATS = ['vigor', 'mind', 'endurance', 'strength', 'dexterity',
             'intelligence', 'faith', 'arcane']

WRETCH_BASE_SUM = 79   # sum of Wretch's base stats; optimizer constant

LEVEL_CAP = {'elden_ring': 713, 'err': 200}

ROLL_THRESHOLDS = [
    (0.299, 'Light Roll'),
    (0.699, 'Medium Roll'),
    (0.999, 'Heavy Roll'),
]

# ── ERR equip load constants ───────────────────────────────────────────────────

FORTUNE_EQ_MULTS = {
    'Sentinel':  1.08,
    'Barbarian': 0.84,
    'Dynasts':   0.85,
}

FRAME_COLORS = {
    'Nimble Frame':   '#60a5fa',
    'Balanced Frame': '#4ade80',
    'Solid Frame':    '#facc15',
    'Massive Frame':  '#f87171',
}


# ── ER piecewise formulas ──────────────────────────────────────────────────────

def calc_hp(vig):
    if vig <= 25:  return round(300  + (vig - 1)  * (500  / 24))
    if vig <= 40:  return round(800  + (vig - 25) * (650  / 15))
    if vig <= 60:  return round(1450 + (vig - 40) * (450  / 20))
    return             round(1900 + (vig - 60) * (200  / 39))


def calc_fp(mnd):
    if mnd <= 15:  return round(40  + (mnd - 1)  * (55  / 14))
    if mnd <= 40:  return round(95  + (mnd - 15) * (140 / 25))
    if mnd <= 60:  return round(235 + (mnd - 40) * (115 / 20))
    return             round(350 + (mnd - 60) * (100 / 39))


def calc_stamina(end):
    if end <= 15:  return round(80  + (end - 1)  * (25 / 14))
    if end <= 30:  return round(105 + (end - 15) * (25 / 15))
    if end <= 50:  return round(130 + (end - 30) * (25 / 20))
    return             round(155 + (end - 50) * (15 / 49))


def calc_equip_load(end):
    if end <= 8:   return round(45.0  + (end - 1)  * (1.5  / 7),  1)
    if end <= 25:  return round(46.5  + (end - 8)  * (25.5 / 17), 1)
    if end <= 60:  return round(72.0  + (end - 25) * (48.0 / 35), 1)
    return             round(120.0 + (end - 60) * (40.0 / 39), 1)


def calc_equip_load_err(fortune_name: str, rune_inventory: list) -> float:
    """ERR equip load. Base = 100. Endurance has no effect."""
    fortune_mult = FORTUNE_EQ_MULTS.get(fortune_name or '', 1.0)
    leonine = next((r for r in rune_inventory if r.get('name') == 'Leonine Weight'), None)
    rune_mult = (1.004 ** leonine['copies']) if leonine and leonine.get('copies') else 1.0
    return round(100.0 * fortune_mult * rune_mult, 1)


def calc_total_weight_err(slots: dict) -> float:
    """ERR weapon weight: heaviest RH + heaviest LH only. All 4 armor slots count fully."""
    def _w(slot_val):
        return (slot_val or {}).get('weight', 0) or 0
    rh    = max(_w(slots.get(s)) for s in ('rh1', 'rh2', 'rh3'))
    lh    = max(_w(slots.get(s)) for s in ('lh1', 'lh2', 'lh3'))
    armor = sum(_w(slots.get(s)) for s in ('helm', 'chest', 'gauntlet', 'leg'))
    return round(rh + lh + armor, 1)


def get_frame_type_err(total_weight: float, max_equip_load: float, fortune_name: str) -> str:
    if fortune_name == 'Bulwark':
        return 'Massive Frame'
    if max_equip_load <= 0:
        return 'Massive Frame'
    ratio = total_weight / max_equip_load
    if ratio < 0.333:  return 'Nimble Frame'
    if ratio < 0.666:  return 'Balanced Frame'
    if ratio < 1.0:    return 'Solid Frame'
    return 'Massive Frame'


def rune_cost_to_level_er(level):
    """Runes required to gain one level at `level` (ER formula)."""
    L = (level + 1) + 81
    x = max(0, (L - 92) * 0.02)
    return floor((x + 0.1) * L * L) + 1


# ── ERR lookup wrappers ────────────────────────────────────────────────────────

def calc_hp_err(vig, curves):
    return int(curves['vigor_hp'][max(0, min(149, vig))])


def calc_fp_err(mnd, curves):
    return int(curves['mind_fp'][max(0, min(149, mnd))])


def calc_stamina_err(end, curves):
    return int(curves['endurance_stamina'][max(0, min(149, end))])


def rune_cost_to_level_err(level, curves):
    return int(curves['rune_cost_to_level'][max(0, min(149, level))])


# ── Unified interface ──────────────────────────────────────────────────────────

# ── ERR Fortune tables ────────────────────────────────────────────────────────

# Flat stat bonuses applied BEFORE calculating HP/FP/Stamina. Cap at 99.
FORTUNE_STAT_BONUSES = {
    "Spellsword":  {"mind": 6},
    "Adherent":    {"faith": 2},
    "Apothecary":  {"arcane": 3},
    "Heretic":     {"vigor": -3},
    "Sage":        {"vigor": -1},
    "Sentinel":    {"arcane": -3},
    "Brave":       {"vigor": 2, "endurance": 2},
    "Bulwark":     {"endurance": 6},
    "Godslayers":  {"dexterity": 2},
    "Houses":      {"strength": -3, "dexterity": -3, "intelligence": 2, "faith": 2},
    "Warmaster":   {"strength": 1, "dexterity": 1},
}

# ── Binding rune derived-stat multipliers ────────────────────────────────────────
# Compound per copy: N copies of base = base^N (not base*N).
# Applied AFTER fortune multipliers. Use int() (floor) on final result.
RUNE_DERIVED_MULTS = {
    'Cursed Health':   {'hp':      1.006},
    'Cradled Focus':   {'fp':      1.007},
    'Leonine Stamina': {'stamina': 1.008},
    'Leonine Weight':  {'eqload':  1.004},
}


def calc_rune_derived_mults(rune_inventory: list) -> dict:
    result = {'hp': 1.0, 'fp': 1.0, 'stamina': 1.0, 'eqload': 1.0}
    for rune in rune_inventory:
        name   = rune.get('name', '')
        copies = rune.get('copies', 0)
        m = RUNE_DERIVED_MULTS.get(name)
        if not m or not copies:
            continue
        for key, base in m.items():
            result[key] *= base ** copies
    return result


# Multipliers applied AFTER deriving HP/FP/Stamina from effective stats. Use floor().
FORTUNE_MULTIPLIERS = {
    "Bold":      {"hp": 1.05,  "fp": 0.94},
    "Cunning":   {"hp": 0.95,  "stamina": 1.12},
    "Wise":      {"fp": 1.085, "stamina": 0.93},
    "Assassin":  {"hp": 0.91},
    "Barbarian": {"fp": 0.9,   "stamina": 1.15},
    "Cleric":    {"hp": 1.1,   "stamina": 0.85},
    "Dancer":    {"fp": 0.65},
    "Sage":      {"fp": 1.1},
    "Veteran":   {"hp": 1.02,  "fp": 1.03, "stamina": 1.04},
    "Haima":     {"fp": 0.8},
    "Latenna":   {"fp": 1.1},
    "Sorcerer":  {"stamina": 0.95},
}


def apply_fortune_stat_bonuses(stats: dict, fortune_name: str) -> dict:
    """
    Return a new stats dict with Fortune flat bonuses applied, capped at 99.
    Does not mutate the input.
    """
    bonuses = FORTUNE_STAT_BONUSES.get(fortune_name, {})
    if not bonuses:
        return stats
    result = dict(stats)
    for stat, delta in bonuses.items():
        result[stat] = min(99, max(1, result.get(stat, 1) + delta))
    return result


def apply_fortune_multipliers(derived: dict, fortune_name: str) -> dict:
    """
    Return a new derived dict with Fortune HP/FP/Stamina multipliers applied (floor).
    Does not mutate the input.
    """
    mults = FORTUNE_MULTIPLIERS.get(fortune_name, {})
    if not mults:
        return derived
    result = dict(derived)
    for key, factor in mults.items():
        if key in result:
            result[key] = floor(result[key] * factor)
    return result


def get_derived(stats, game, err_curves=None, fortune_name=None):
    """
    Return {'hp', 'fp', 'stamina', 'equip_load'} for any game.
    err_curves: dict from /api/soulslike/derived-curves/?game=err (required if game='err')
    fortune_name: ERR Fortune name — applies stat bonuses then HP/FP/Stamina multipliers.
    """
    effective_stats = stats
    if game == 'err' and fortune_name:
        effective_stats = apply_fortune_stat_bonuses(stats, fortune_name)

    end = effective_stats['endurance']
    vig = effective_stats['vigor']
    mnd = effective_stats['mind']

    if game == 'err' and err_curves:
        derived = {
            'hp':         calc_hp_err(vig, err_curves),
            'fp':         calc_fp_err(mnd, err_curves),
            'stamina':    calc_stamina_err(end, err_curves),
            'equip_load': calc_equip_load(end),
        }
    else:
        derived = {
            'hp':         calc_hp(vig),
            'fp':         calc_fp(mnd),
            'stamina':    calc_stamina(end),
            'equip_load': calc_equip_load(end),
        }

    if game == 'err' and fortune_name:
        derived = apply_fortune_multipliers(derived, fortune_name)

    return derived


def get_roll_type(total_weight, equip_load):
    if equip_load <= 0:
        return 'Overloaded'
    ratio = total_weight / equip_load
    for threshold, label in ROLL_THRESHOLDS:
        if ratio <= threshold:
            return label
    return 'Overloaded'


def calc_level(build_stats, class_base, selected_class, game):
    """Total rune level for current stat allocation."""
    points = sum(
        max(0, build_stats[s] - class_base.get(s, 0))
        for s in ALL_STATS
    )
    class_level = selected_class['level'] if selected_class else 1
    return min(LEVEL_CAP[game], class_level + points)


def calc_total_weight(slots):
    """Sum weights for all equipped weapons and armor."""
    weapon_slots = ('rh1', 'rh2', 'rh3', 'lh1', 'lh2', 'lh3')
    armor_slots  = ('helm', 'chest', 'gauntlet', 'leg')
    total = 0.0
    for slot in weapon_slots:
        w = slots.get(slot)
        if w:
            total += w.get('weight', 0)
    for slot in armor_slots:
        a = slots.get(slot)
        if a:
            total += a.get('weight', 0)
    return round(total, 1)


def calc_poise(slots):
    """Sum poise from all equipped armor pieces."""
    armor_slots = ('helm', 'chest', 'gauntlet', 'leg')
    return round(sum(
        slots.get(slot, {}).get('poise', 0)
        for slot in armor_slots
        if slots.get(slot)
    ), 1)


def get_stat_bar_state(val, caps):
    """
    Return (color_key, badge_text) for a stat bar.
    caps = {'soft_cap_1': N, 'soft_cap_2': N, 'soft_cap_3': None, 'hard_cap': 99}
    color_key: 'under' | 'soft1' | 'soft2' | 'hard'
    """
    c1 = caps.get('soft_cap_1') or 99
    c2 = caps.get('soft_cap_2') or 99
    c3 = caps.get('soft_cap_3')
    hc = caps.get('hard_cap', 99)

    if val >= hc:
        return 'hard', 'MAX'
    if c3 and val >= c2:
        remaining = c3 - val
        return 'soft2', f'Soft 2 ({remaining} to S3)' if val < c3 else 'Soft 3'
    if val >= c1:
        remaining = c2 - val
        return 'soft1', f'Soft 1 ({remaining} to S2)'
    remaining = c1 - val
    return 'under', f'{remaining} to soft cap'


# ── Class optimizer ────────────────────────────────────────────────────────────

def calc_required_level(class_obj, targets):
    """
    Minimum rune level to reach all target stats with this class.
    targets: {stat: value} — 0 means unconstrained.
    """
    stat_sum = 0
    for stat in ALL_STATS:
        base = class_obj[stat]
        tgt  = targets.get(stat, 0)
        stat_sum += max(base, tgt) if tgt > 0 else base
    return stat_sum - WRETCH_BASE_SUM


def find_optimal_class(classes, targets):
    """
    Rank all classes by required level for the given targets.
    Returns list of {'class': obj, 'level': int, 'diff': int} sorted best first.
    diff=0 is optimal, diff=N means N extra levels vs best.
    """
    results = [
        {'class': c, 'level': calc_required_level(c, targets)}
        for c in classes
    ]
    results.sort(key=lambda x: x['level'])
    best = results[0]['level'] if results else 0
    for r in results:
        r['diff'] = r['level'] - best
    return results
