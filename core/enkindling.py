"""
ERR Ash of War Enkindling -- rarity/affix system. Faithful port of the web
builder's calcEnkindleModifiers() (see the Enkindling Integration Spec
artifact, 2026-07). ERR-only; vanilla Elden Ring never has enkindled AoWs.

Enkindling an Ash of War gives it a rarity (common/rare/legendary, unlocking
1/1-2/1-2-3 effect tiers) and a randomly-rolled Affix (one of 39, fetched
from /api/soulslike/err/enkindling/). Each tier's static_effect (if any) is
a calculable bonus; tiers with static_effect=None are conditional/combat-
triggered and stay descriptive-only, contributing nothing here.

WEAPON_SLOTS = ('rh1','rh2','rh3','lh1','lh2','lh3') -- selections dict is
keyed by slot: {slot: {'affix': name, 'rarity': 'common'|'rare'|'legendary'}}
or the slot absent/None if nothing enkindled there.
"""

RARITY_TIER = {"common": 1, "rare": 2, "legendary": 3}

WEAPON_SLOTS = ("rh1", "rh2", "rh3", "lh1", "lh2", "lh3")


def _empty_mods():
    return {
        "stat_flat": {},
        "hp_mult": 1.0,
        "fp_mult": 1.0,
        "stamina_mult": 1.0,
        "equip_load_mult": 1.0,
        "poise_flat": 0,
    }


def calc_enkindle_modifiers(selections, affixes_by_name):
    """
    Character-wide aggregation across all 6 weapon slots.

    selections: {slot: {'affix': name, 'rarity': str} or None}
    affixes_by_name: {affix_name: {name, affinity, tiers: [{star, text, static_effect}]}}

    Returns the mods dict (stat_flat/hp_mult/fp_mult/stamina_mult/
    equip_load_mult/poise_flat). damage_mult / damage_mult_vs_enemy_type are
    deliberately NOT included here -- those are per-weapon only, see
    calc_slot_damage_mult() below. Dedupes identical passives (same affix +
    same tier) across weapons so an effect doesn't double-count if the same
    affix happens to be enkindled on two slots.
    """
    mods = _empty_mods()
    seen = set()

    for slot in WEAPON_SLOTS:
        sel = selections.get(slot)
        if not sel or not sel.get("affix"):
            continue
        affix = affixes_by_name.get(sel["affix"])
        if not affix:
            continue
        max_tier = RARITY_TIER.get(sel.get("rarity"), 1)

        for tier in affix.get("tiers", []):
            if tier.get("star", 0) > max_tier:
                continue
            effect = tier.get("static_effect")
            if effect is None:
                continue
            key = f"{sel['affix']}:{tier['star']}"
            if key in seen:
                continue
            seen.add(key)
            _apply_static_effect(mods, effect)

    return mods


def _apply_static_effect(mods, effect):
    etype = effect.get("type")
    if etype == "stat_flat":
        stat = effect["stat"]
        mods["stat_flat"][stat] = mods["stat_flat"].get(stat, 0) + effect["value"]
    elif etype == "stat_flat_multi":
        for stat, value in effect.get("stats", {}).items():
            mods["stat_flat"][stat] = mods["stat_flat"].get(stat, 0) + value
    elif etype == "hp_mult":
        mods["hp_mult"] *= effect["value"]
    elif etype == "fp_mult":
        mods["fp_mult"] *= effect["value"]
    elif etype == "stamina_mult":
        mods["stamina_mult"] *= effect["value"]
    elif etype == "equip_load_mult":
        mods["equip_load_mult"] *= effect["value"]
    elif etype == "hp_fp_stamina_mult":
        mods["hp_mult"] *= effect["hp"]
        mods["fp_mult"] *= effect["fp"]
        mods["stamina_mult"] *= effect["stamina"]
    elif etype == "poise_flat":
        mods["poise_flat"] += effect["value"]
    elif etype == "poise_and_equip_load":
        mods["poise_flat"] += effect["poise"]
        mods["equip_load_mult"] *= effect["equip_load_mult"]
    # damage_mult / damage_mult_vs_enemy_type: per-weapon only, not
    # aggregated into character-wide mods -- see calc_slot_damage_mult().


def calc_slot_damage_mult(slot, selections, affixes_by_name, vs_enemy_type=None):
    """
    Per-weapon AR multiplier for one slot's enkindled affix. NEVER dedupe or
    aggregate across slots -- each weapon's own AR only looks at its own
    slot's selection.

    vs_enemy_type: pass the active "vs this enemy type" AR toggle (e.g.
    'dragon'/'undead'/'divine') if the UI has one; damage_mult_vs_enemy_type
    tiers only apply when it matches, otherwise they're ignored (not an
    error, just inapplicable this call).
    """
    sel = selections.get(slot)
    mult = 1.0
    if not sel or not sel.get("affix"):
        return mult
    affix = affixes_by_name.get(sel["affix"])
    if not affix:
        return mult
    max_tier = RARITY_TIER.get(sel.get("rarity"), 1)

    for tier in affix.get("tiers", []):
        if tier.get("star", 0) > max_tier:
            continue
        effect = tier.get("static_effect")
        if effect is None:
            continue
        etype = effect.get("type")
        if etype == "damage_mult":
            mult *= effect["value"]
        elif etype == "damage_mult_vs_enemy_type":
            if vs_enemy_type and effect.get("enemy_type") == vs_enemy_type:
                mult *= effect["value"]

    return mult


def apply_enkindle_to_derived(base_hp, base_fp, base_stamina, base_equip_load, base_poise, mods):
    """Apply the aggregated mods to derived stats -- one shared function, called
    from every panel that shows these numbers (Character column AND any AR/
    Equip Load summary), so they can never drift apart from each other."""
    return {
        "hp": base_hp * mods["hp_mult"],
        "fp": base_fp * mods["fp_mult"],
        "stamina": base_stamina * mods["stamina_mult"],
        "equip_load": base_equip_load * mods["equip_load_mult"],
        "poise": base_poise + mods["poise_flat"],
    }


def apply_enkindle_stat_flat(stats, mods):
    """{stat: base_value + mods.stat_flat[stat]} for all 8 attributes."""
    return {
        stat: value + mods["stat_flat"].get(stat, 0)
        for stat, value in stats.items()
    }
