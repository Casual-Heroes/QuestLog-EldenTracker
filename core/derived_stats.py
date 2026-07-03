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

def get_derived(stats, game, err_curves=None):
    """
    Return {'hp', 'fp', 'stamina', 'equip_load'} for any game.
    err_curves: dict from /api/soulslike/derived-curves/?game=err (required if game='err')
    """
    end = stats['endurance']
    vig = stats['vigor']
    mnd = stats['mind']

    if game == 'err' and err_curves:
        return {
            'hp':         calc_hp_err(vig, err_curves),
            'fp':         calc_fp_err(mnd, err_curves),
            'stamina':    calc_stamina_err(end, err_curves),
            'equip_load': calc_equip_load(end),   # ERR reuses ER equip load formula
        }
    return {
        'hp':         calc_hp(vig),
        'fp':         calc_fp(mnd),
        'stamina':    calc_stamina(end),
        'equip_load': calc_equip_load(end),
    }


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
