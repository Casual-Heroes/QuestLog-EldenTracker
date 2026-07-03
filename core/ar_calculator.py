"""
AR Calculator — port of QuestLog's computeAR() JS function.
Pure Python, no network calls. Feed it the three data tables from
/api/soulslike/ar-data/?game=... and it calculates attack rating instantly.
"""

from math import floor
import re

STAT_MAP = {
    'str': 'strength',
    'dex': 'dexterity',
    'int': 'intelligence',
    'fai': 'faith',
    'arc': 'arcane',
}

DEFAULT_GRAPH = '0'

SCADU_DMG_MULT = [
    1.000, 1.025, 1.050, 1.075, 1.100,
    1.125, 1.150, 1.175, 1.200, 1.225,
    1.250, 1.275, 1.300, 1.325, 1.350,
    1.375, 1.400, 1.450, 1.500, 1.550, 1.600,
]

ER_AFFINITIES = [
    'Standard', 'Heavy', 'Keen', 'Quality', 'Fire', 'Flame Art',
    'Lightning', 'Sacred', 'Magic', 'Cold', 'Poison', 'Blood', 'Occult',
]


def compute_ar(variant, stats, ar_curves, ar_aec, ar_reinforce):
    """
    Compute attack rating for a weapon variant given effective stats.

    variant    — one affinity entry from /api/soulslike/weapons/<name>/ar-variants/
    stats      — {'strength':40,'dexterity':18,...} effective stats
                 For ERR: pass get_effective_stats(build_stats, rune_inventory)
    ar_curves  — AR_CURVES dict from /api/soulslike/ar-data/
    ar_aec     — AR_AEC dict from /api/soulslike/ar-data/
    ar_reinforce — AR_REINFORCE dict from /api/soulslike/ar-data/

    Returns {'total': int, 'breakdown': {0..4: {base,scaling,total}|None}, 'ineffective': [str]}
    """
    aec       = ar_aec.get(str(variant.get('aec_id', 0)), {})
    reinforce = ar_reinforce.get(str(variant.get('reinforce_type_id', 0)), {})
    atk_mult  = reinforce.get('attack', {})
    scl_mult  = reinforce.get('scaling', {})   # ERR: always {} → defaults to 1.0

    requirements = variant.get('requirements', {})
    attack       = variant.get('attack', {})
    scaling      = variant.get('scaling', {})
    graph_ids    = variant.get('calc_correct_graph_ids', {})

    # Determine which stats fail requirements
    ineffective = [
        k for k in STAT_MAP
        if requirements.get(k, 0) and stats.get(STAT_MAP[k], 1) < requirements[k]
    ]

    breakdown = {}
    total = 0.0

    for dmg_idx in range(5):
        idx = str(dmg_idx)
        raw_base = attack.get(idx)
        if not raw_base:
            breakdown[dmg_idx] = None
            continue

        # Max-upgrade base damage
        atk_mult_val = float(atk_mult.get(idx, atk_mult.get('0', 1)))
        max_base = raw_base * atk_mult_val

        scaling_attrs = aec.get(idx, {})

        # 40% penalty if ANY scaling stat for this damage type is below req
        if any(k in ineffective for k in scaling_attrs if scaling_attrs.get(k)):
            penalized = max_base * 0.6
            breakdown[dmg_idx] = {
                'base': round(penalized), 'scaling': 0, 'total': round(penalized),
            }
            total += penalized
            continue

        # Scaling bonus via correction curves
        graph_id = str(graph_ids.get(idx, DEFAULT_GRAPH))
        curve = ar_curves.get(graph_id, [])
        scaling_bonus = 0.0

        for stat_key, full_stat in STAT_MAP.items():
            if not scaling_attrs.get(stat_key):
                continue
            scl_mult_val = float(scl_mult.get(stat_key, 1))
            scl_value = (scaling.get(stat_key) or 0) * scl_mult_val
            if not scl_value or not curve:
                continue
            stat_val = max(0, min(149, stats.get(full_stat, 1)))
            correction = curve[stat_val]
            scaling_bonus += correction * scl_value

        scaling_value = max_base * scaling_bonus
        dmg_total = max_base + scaling_value
        breakdown[dmg_idx] = {
            'base':    floor(max_base),
            'scaling': floor(scaling_value),
            'total':   floor(dmg_total),
        }
        total += dmg_total

    return {
        'total':       floor(total),
        'breakdown':   breakdown,
        'ineffective': ineffective,
    }


def apply_scadutree(ar_total, level):
    """Multiply AR by Scadutree blessing multiplier. level is 0-20."""
    level = max(0, min(20, level))
    return floor(ar_total * SCADU_DMG_MULT[level])


def get_variant_for_affinity(variants, affinity):
    """Find variant matching affinity name. Falls back to Standard, then first."""
    for v in variants:
        if v.get('affinity', '').lower() == affinity.lower():
            return v
    for v in variants:
        if v.get('affinity', '').lower() == 'standard':
            return v
    return variants[0] if variants else None


def get_effective_stats(build_stats, rune_inventory):
    """ERR only — add binding rune bonuses to base stats, cap each at 99."""
    bonuses = calc_rune_bonuses(rune_inventory)
    return {
        stat: min(99, build_stats[stat] + bonuses.get(stat, 0))
        for stat in build_stats
    }


def calc_rune_bonuses(rune_inventory):
    """
    Parse '+N Stat' pattern from each rune's effect text, multiply by copies.
    e.g. '+1 (+4) Vigor' with copies=3 → vigor: 3
    """
    bonuses = {}
    pattern = re.compile(r'\+(\d+)(?:\s*\([^)]+\))?\s+(\w+)\s*$', re.IGNORECASE)
    for rune in rune_inventory:
        m = pattern.search(rune.get('effect', ''))
        if m:
            val  = int(m.group(1)) * rune.get('copies', 0)
            stat = m.group(2).lower()
            bonuses[stat] = bonuses.get(stat, 0) + val
    return bonuses


def aow_compatible(compatible_str, weapon_type):
    """Check if an AoW can be applied to a weapon type. Exact match, not substring."""
    if not compatible_str:
        return True
    s = compatible_str.lower()
    if any(x in s for x in ('all_melee', 'all melee', 'all armaments')):
        return True
    parts = [p.strip().lower() for p in compatible_str.split(',')]
    return weapon_type.lower() in parts
