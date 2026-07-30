"""
Build Planner -- read-only viewer for saved character builds.

First milestone per CHARACTER_BUILDER_APP_HANDOFF.md: load and DISPLAY a
saved build (stats, class, every equipped slot) across the same 3-column
layout as the web builder. No editing/equipping yet -- that's the next
milestone once this layout and the API wiring are verified correct.

Response shape consumed here matches the doc's "Build detail response"
(section 3, GET /builds/<share_token>/ on web; the desktop equivalent is
QuestLogClient/QuestLogSync.get_build_detail(build_id)).
"""

from math import floor

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QTabWidget, QSizePolicy, QGridLayout, QLineEdit, QDialog, QComboBox,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from core.derived_stats import (
    get_derived, get_roll_type, get_stat_bar_state, calc_level,
    calc_total_weight, calc_total_weight_err, calc_poise,
    get_frame_type_err, calc_equip_load_err, calc_rune_derived_mults,
    apply_fortune_stat_bonuses, apply_fortune_multipliers,
)
from core.ar_calculator import (
    compute_ar, get_variant_for_affinity, apply_scadutree, aow_compatible, ER_AFFINITIES,
    calc_rune_bonuses, get_effective_stats,
)
from core.enkindling import (
    calc_enkindle_modifiers, calc_slot_damage_mult, apply_enkindle_to_derived,
    apply_enkindle_stat_flat, WEAPON_SLOTS as ENKINDLE_SLOTS, RARITY_TIER,
)
from core.crash_logger import get_logger
from core import local_builds as local_builds_store

log = get_logger("questlog.build_planner")

# Same palette as boss_tracker.py -- one visual language across the app.
BG_BASE      = "#09090f"
BG_SURFACE   = "#0f1018"
BG_CARD      = "#13141f"
BORDER_SOLID = "#1e1f2e"
ACCENT_GOLD  = "#c9a84c"
ACCENT_GOLD2 = "#e8c45a"
ACCENT_RED   = "#c0390f"
GREEN_LIVE   = "#22c55e"
TEXT_PRIMARY = "#f1f0f5"
TEXT_MUTED   = "#6b7280"
TEXT_DIM     = "#374151"

STAT_NAMES = ("vigor", "mind", "endurance", "strength", "dexterity", "intelligence", "faith", "arcane")
STAT_LABELS = {
    "vigor": "Vigor", "mind": "Mind", "endurance": "Endurance", "strength": "Strength",
    "dexterity": "Dexterity", "intelligence": "Intelligence", "faith": "Faith", "arcane": "Arcane",
}
STAT_DISPLAY_LABELS = {key: value.upper() for key, value in STAT_LABELS.items()}

WEAPON_SLOTS = ("rh1", "rh2", "rh3", "lh1", "lh2", "lh3")
WEAPON_SLOT_LABELS = {
    "rh1": "Right Hand 1", "rh2": "Right Hand 2", "rh3": "Right Hand 3",
    "lh1": "Left Hand 1",  "lh2": "Left Hand 2",  "lh3": "Left Hand 3",
}
ARMOR_SLOTS = ("helm", "chest", "gauntlet", "leg")
ARMOR_SLOT_LABELS = {"helm": "Helm", "chest": "Chest", "gauntlet": "Gauntlets", "leg": "Legs"}
NO_AFFINITY_WEAPON_TYPES = {"glintstone staff", "sacred seal"}


def _weapon_uses_affinity(weapon):
    if not weapon:
        return False
    if weapon.get("affinity") or weapon.get("affinities"):
        return True
    return (weapon.get("type") or "").strip().lower() not in NO_AFFINITY_WEAPON_TYPES


def _effective_weapon_affinity(weapon, affinity, game=None):
    primary_affinity = weapon.get("affinity") if weapon else None
    if primary_affinity and not affinity:
        return primary_affinity
    if not _weapon_uses_affinity(weapon):
        return None
    return affinity or "Standard"


def _weapon_affinity_display(weapon, affinity, game=None):
    affinities = weapon.get("affinities") if weapon else None
    if affinities:
        return ", ".join(str(a) for a in affinities if a) or "None"
    return _effective_weapon_affinity(weapon, affinity, game) or "None"


def _saved_or_minimum_level(build, stats, class_base, class_obj, game):
    """
    Saved level is authoritative; stat allocation only supplies the minimum.
    This preserves unallocated levels instead of collapsing level 105 to 97
    when non-stat UI such as Enkindling is saved.
    """
    cap = 200 if game == "err" else 713
    minimum = calc_level(stats, class_base, class_obj, game)
    stored = (
        build.get("level")
        if build.get("level") is not None
        else build.get("total_level", build.get("level_override"))
    )
    try:
        stored = int(stored)
    except (TypeError, ValueError):
        stored = minimum
    return min(cap, max(minimum, stored))


def _numeric_id(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _talisman_modifiers(talismans):
    mods = {
        "stat_flat": {},
        "hp_mult": 1.0,
        "fp_mult": 1.0,
        "stamina_mult": 1.0,
        "equip_load_mult": 1.0,
    }
    for talisman in talismans or []:
        if not talisman:
            continue
        name = talisman.get("name", "")
        equip_mult = talisman.get("equip_load_mult")
        if isinstance(equip_mult, (int, float)) and equip_mult > 0:
            mods["equip_load_mult"] *= float(equip_mult)

        if name == "Viridian Amber Medallion":
            mods["stat_flat"]["endurance"] = mods["stat_flat"].get("endurance", 0) + 3
            mods["stamina_mult"] *= 1.01
        elif name == "Viridian Amber Medallion +1":
            mods["stat_flat"]["endurance"] = mods["stat_flat"].get("endurance", 0) + 2
            mods["stamina_mult"] *= 1.09
        elif name == "Viridian Amber Medallion +2":
            mods["stat_flat"]["endurance"] = mods["stat_flat"].get("endurance", 0) + 1
            mods["stamina_mult"] *= 1.18
        elif name == "Viridian Amber Medallion +3":
            mods["stat_flat"]["endurance"] = mods["stat_flat"].get("endurance", 0) + 1
            mods["stamina_mult"] *= 1.20
        elif name == "Arsenal Charm" and not isinstance(equip_mult, (int, float)):
            mods["equip_load_mult"] *= 1.06
        elif name == "Arsenal Charm +1" and not isinstance(equip_mult, (int, float)):
            mods["equip_load_mult"] *= 1.125
        elif name == "Great-Jar's Arsenal" and not isinstance(equip_mult, (int, float)):
            mods["equip_load_mult"] *= 1.15
    return mods


def _apply_flat_stat_mods(stats, flat_mods):
    result = dict(stats)
    for stat, value in (flat_mods or {}).items():
        if stat in result:
            result[stat] = min(99, max(1, int(result.get(stat, 1)) + int(value)))
    return result


def _effective_build_stats(base_stats, game, fortune_name=None, rune_inventory=None,
                           talismans=None, enkindle_mods=None):
    stats = dict(base_stats or {})
    if game == "err":
        if rune_inventory:
            stats = get_effective_stats(stats, rune_inventory)
        if fortune_name:
            stats = apply_fortune_stat_bonuses(stats, fortune_name)
        stats = _apply_flat_stat_mods(stats, _talisman_modifiers(talismans)["stat_flat"])
        if enkindle_mods:
            stats = apply_enkindle_stat_flat(stats, enkindle_mods)
    return stats


def _compact_cap_label(label):
    label = str(label or "")
    if label.startswith("Soft 1"):
        return "S1"
    if label.startswith("Soft 2"):
        return "S2"
    if label.startswith("Soft 3"):
        return "S3"
    if "to soft cap" in label:
        return label.replace(" to soft cap", "")
    return label


def _panel(title=None):
    """A bordered card panel, optionally with a title row -- matches the web's panel style."""
    panel = QWidget()
    panel.setStyleSheet(f"""
        QWidget {{ background: {BG_CARD}; border: 1px solid {BORDER_SOLID}; border-radius: 8px; }}
    """)
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(8)
    if title:
        lbl = QLabel(title)
        lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color: {ACCENT_GOLD}; letter-spacing: 1.5px; background: transparent; border: none;")
        layout.addWidget(lbl)
    return panel, layout


class StatRow(QWidget):
    """One attribute row: name, editable value spinbox, and a soft-cap-colored progress bar."""

    value_changed = pyqtSignal(str, int)  # stat_key, new_value -- emitted only on genuine user edits

    def __init__(self, stat_key, parent=None):
        super().__init__(parent)
        self.stat_key = stat_key
        self._min_value = 1  # raised to the class's base stat via set_floor() once a build loads -- can't go below class starting value
        self._base_value = 10
        self._effective_bonus = 0
        self._loading = False  # True while set_value() is programmatically updating the spinbox -- suppresses value_changed
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 3, 0, 3)
        layout.setSpacing(0)

        name_lbl = QLabel(STAT_DISPLAY_LABELS[stat_key])
        name_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        name_lbl.setStyleSheet(f"color: #9ecbff; background: transparent; border: none; letter-spacing: 1px;")
        name_lbl.setFixedWidth(72)

        from PyQt6.QtWidgets import QSpinBox
        self._value_spin = QSpinBox()
        self._value_spin.setRange(1, 99)
        self._value_spin.setValue(10)
        self._value_spin.setFixedWidth(44)
        self._value_spin.setFixedHeight(28)
        self._value_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # QSpinBox's native up/down arrow subcontrols don't render reliably
        # once styled at all in this Qt build -- CSS-triangle borders on
        # ::up-arrow/::down-arrow rendered as solid blocks, not triangles,
        # even with image:none and explicit sizing (same underlying "half-
        # styled widget renders blank/wrong" issue as RuneRow's +/-/x
        # buttons, but the arrow subcontrol trick that fixes normal buttons
        # doesn't apply the same way to spinbox arrows). Simplest reliable
        # fix: turn off the native buttons entirely and use two explicit
        # QPushButtons with the exact same solid-fill styling already
        # confirmed working (visually verified, see RuneRow).
        self._value_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self._value_spin.setStyleSheet(f"""
            QSpinBox {{ background: #151515; border: 1px solid #333333; border-radius: 4px;
                       color: {ACCENT_GOLD2}; font-weight: 800; padding: 2px; }}
            QSpinBox:focus {{ border-color: {ACCENT_GOLD}; }}
        """)
        self._value_spin.valueChanged.connect(self._on_spin_changed)

        # Kept for compatibility with the existing update method, but hidden:
        # the value box itself now shows the effective site-style value.
        self._enkindle_bonus_lbl = QLabel("")
        self._enkindle_bonus_lbl.setFixedWidth(0)
        self._enkindle_bonus_lbl.setVisible(False)

        self._bar_track = QWidget()
        self._bar_track.setFixedHeight(6)
        self._bar_track.setMinimumWidth(22)
        self._bar_track.setStyleSheet(f"background: {BORDER_SOLID}; border-radius: 3px;")
        self._bar_fill = QWidget(self._bar_track)
        self._bar_fill.setFixedHeight(6)
        self._bar_fill.setStyleSheet(f"background: {GREEN_LIVE}; border-radius: 3px;")
        self._bar_fill.setFixedWidth(0)

        # Cap label sits BELOW the name/value/bar row instead of squeezed
        # into it as a 4th fixed-width column -- "Soft 1 (4 to S2)" style
        # text needs more room than a narrow column has to spare, and a
        # 4th rigid column is exactly what caused overlap at non-maximized
        # widths.
        self._cap_lbl = QLabel("")
        self._cap_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self._cap_lbl.setStyleSheet("color: #f5d142; background: #302b06; border: none; border-radius: 3px; padding: 3px 6px;")
        self._cap_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cap_lbl.setFixedWidth(50)

        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(name_lbl)
        row.addWidget(self._value_spin)
        row.addWidget(self._bar_track, 1)
        row.addWidget(self._cap_lbl)

        layout.addLayout(row)

    _CAP_COLORS = {
        'under': GREEN_LIVE, 'soft1': "#eab308", 'soft2': "#f97316", 'hard': ACCENT_RED,
    }

    def _on_spin_changed(self, value):
        self._apply_bar(value)
        if not self._loading:
            self._base_value = min(99, max(self._min_value, value - self._effective_bonus))
            self.value_changed.emit(self.stat_key, self._base_value)

    def set_floor(self, min_value):
        """
        Class base stat -- can't drop the spinbox below this (matches the
        web's floor behavior). setMinimum() can itself clamp-and-fire
        valueChanged if the spinbox's current value sits below the new
        floor (e.g. loading a new build while the old build's lower value
        is still showing) -- guard it the same way set_value() guards its
        own update, so this never looks like a user edit.
        """
        self._min_value = min_value
        was_loading = self._loading
        self._loading = True
        self._value_spin.setMinimum(min(99, max(1, min_value + self._effective_bonus)))
        self._loading = was_loading

    def set_value(self, value, caps=None):
        """
        caps: {'soft_cap_1','soft_cap_2','soft_cap_3','hard_cap'} from
        /stat-caps/, or None to fall back to a flat 99 hard cap with no
        soft-cap label (used only if that endpoint's data isn't available).
        Called from load() -- a programmatic update, not a user edit, so it
        must NOT fire value_changed (that would mark a freshly-loaded build
        as "dirty" with no actual user action).
        """
        self._base_value = min(99, max(self._min_value, int(value)))
        self._loading = True
        self._value_spin.setValue(min(99, max(1, self._base_value + self._effective_bonus)))
        self._loading = False
        self._apply_bar(self._value_spin.value(), caps)

    def set_enkindle_bonus(self, bonus, effective_value=None):
        """bonus: flat effective-stat delta from Fortune/Rune/Talisman/Enkindling."""
        self._effective_bonus = int(bonus or 0)
        self._enkindle_bonus_lbl.setVisible(False)
        self._loading = True
        self._value_spin.setMinimum(min(99, max(1, self._min_value + self._effective_bonus)))
        self._value_spin.setValue(min(99, max(1, effective_value if effective_value is not None else self._base_value + self._effective_bonus)))
        self._loading = False
        self._apply_bar(self._value_spin.value())

    def base_value(self):
        return self._base_value

    def _apply_bar(self, value, caps=None):
        caps = caps if caps is not None else getattr(self, "_last_caps", None) or {'hard_cap': 99}
        self._last_caps = caps
        hard_cap = caps.get('hard_cap') or 99
        pct = max(0.0, min(1.0, value / hard_cap))

        if 'soft_cap_1' in caps or 'soft_cap_2' in caps:
            color_key, label = get_stat_bar_state(value, caps)
            color = self._CAP_COLORS.get(color_key, GREEN_LIVE)
            self._cap_lbl.setText(_compact_cap_label(label))
            badge_bg = "#0c2d17" if color_key == "under" else ("#302b06" if color_key == "soft1" else ("#3a1d07" if color_key == "soft2" else "#3b0d0d"))
            self._cap_lbl.setStyleSheet(f"color: {color}; background: {badge_bg}; border: none; border-radius: 3px; padding: 3px 6px;")
        else:
            color = GREEN_LIVE if pct < 0.5 else ("#eab308" if pct < 0.75 else ("#f97316" if pct < 0.9 else ACCENT_RED))
        self._bar_fill.setStyleSheet(f"background: {color}; border-radius: 3px;")

        self._last_pct = pct
        def _resize():
            self._bar_fill.setFixedWidth(int(self._bar_track.width() * pct))
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, _resize)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Re-apply the fill width whenever the row is resized, since
        # _bar_track's width isn't known until layout has actually happened.
        pct = getattr(self, "_last_pct", None)
        if pct is not None:
            self._bar_fill.setFixedWidth(int(self._bar_track.width() * pct))


class ClassPickerDialog(QDialog):
    """
    Grid of class buttons (name + starting level), same idea as the web's
    Class tab. Picking one resets every attribute to that class's base
    stats (see CharacterColumn._apply_class).
    """
    def __init__(self, classes, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Choose Class")
        self.setMinimumSize(360, 420)
        self._selected = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title = QLabel("Select a class")
        title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none;")
        container = QWidget()
        grid = QGridLayout(container)
        grid.setSpacing(8)
        for i, c in enumerate(classes):
            btn = QPushButton(f"{c.get('name', '?')}\nLv {c.get('level', '?')}")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setMinimumHeight(56)
            btn.clicked.connect(lambda _, cls=c: self._choose(cls))
            grid.addWidget(btn, i // 2, i % 2)
        scroll.setWidget(container)
        layout.addWidget(scroll)

    def _choose(self, class_obj):
        self._selected = class_obj
        self.accept()

    @staticmethod
    def pick(classes, parent=None):
        dlg = ClassPickerDialog(classes, parent)
        dlg.exec()
        return dlg._selected


class _Cancelled:
    """Sentinel returned by _SearchableListDialog.pick() when the dialog was
    closed/escaped without clicking any row -- distinct from None, which is
    itself a legitimate "picked" value (every picker has an explicit
    "-- None --"/"-- Unequip --" row that returns real None on purpose).
    Without this distinction, closing a picker without choosing anything
    was indistinguishable from explicitly clearing the slot, which silently
    unequipped whatever was already selected (e.g. closing the Fortune
    picker without picking anything unequipped the current fortune)."""
    def __bool__(self):
        return False


CANCELLED = _Cancelled()


class _SearchableListDialog(QDialog):
    """
    Shared shell for Weapon/AoW/Affinity pickers: title, search box, scrollable
    list of clickable rows built by the subclass-provided row factory. Every
    picker in this module is "search + click a row to pick it", so the only
    thing that differs between them is how each row is rendered and what
    "clicked" returns -- both handled via the `rows` param (list of
    (display_widget_factory, search_text, return_value) tuples) rather than
    subclassing, since none of them need extra dialog-level behavior.
    """

    def __init__(self, title, rows, parent=None, extra_top_widget=None, filter_specs=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(420, 480)
        self._selected = CANCELLED
        self._row_widgets = []  # (widget, search_text, tags)
        self._filter_combos = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title_lbl = QLabel(title)
        title_lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        layout.addWidget(title_lbl)

        if extra_top_widget:
            layout.addWidget(extra_top_widget)

        if filter_specs:
            filter_box = QWidget()
            filter_layout = QGridLayout(filter_box)
            filter_layout.setContentsMargins(0, 0, 0, 0)
            filter_layout.setHorizontalSpacing(8)
            filter_layout.setVerticalSpacing(6)
            for i, spec in enumerate(filter_specs):
                label = QLabel(spec.get("label", "Filter").upper())
                label.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
                label.setStyleSheet(f"color: {TEXT_MUTED}; letter-spacing: 1px;")
                combo = QComboBox()
                combo.setStyleSheet(f"""
                    QComboBox {{ background: {BG_SURFACE}; border: 1px solid {BORDER_SOLID};
                                border-radius: 5px; color: {TEXT_PRIMARY}; padding: 5px 8px; }}
                    QComboBox QAbstractItemView {{ background: {BG_CARD}; border: 1px solid {BORDER_SOLID};
                                                   color: {TEXT_PRIMARY}; selection-background-color: rgba(201,168,76,0.18); }}
                """)
                combo.addItem("All", userData=None)
                for option in spec.get("options", []):
                    combo.addItem(str(option), userData=str(option).lower())
                combo.currentIndexChanged.connect(self._filter)
                self._filter_combos.append((spec.get("key"), combo))
                row = i // 2
                col = (i % 2) * 2
                filter_layout.addWidget(label, row, col)
                filter_layout.addWidget(combo, row, col + 1)
            layout.addWidget(filter_box)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search...")
        self._search.setStyleSheet(f"""
            QLineEdit {{ background: {BG_SURFACE}; border: 1px solid {BORDER_SOLID}; border-radius: 6px;
                        color: {TEXT_PRIMARY}; padding: 6px 10px; }}
        """)
        self._search.textChanged.connect(self._filter)
        layout.addWidget(self._search)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none;")
        container = QWidget()
        self._list_layout = QVBoxLayout(container)
        self._list_layout.setSpacing(4)
        for row_def in rows:
            if len(row_def) == 4:
                build_widget, search_text, value, tags = row_def
            else:
                build_widget, search_text, value = row_def
                tags = {}
            row = build_widget()
            row.setCursor(Qt.CursorShape.PointingHandCursor)
            row.setStyleSheet(f"""
                QWidget {{ background: {BG_SURFACE}; border: 1px solid {BORDER_SOLID}; border-radius: 6px; }}
                QWidget:hover {{ border-color: {ACCENT_GOLD}; }}
            """)
            row.mousePressEvent = lambda _e, v=value: self._choose(v)
            self._list_layout.addWidget(row)
            self._row_widgets.append((row, search_text.lower(), tags or {}))
        self._list_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll)

    def _tag_matches(self, tags, key, wanted):
        if not wanted:
            return True
        value = tags.get(key)
        if value is None:
            return False
        if isinstance(value, (list, tuple, set)):
            return wanted in {str(v).lower() for v in value}
        return wanted == str(value).lower()

    def _filter(self, _value=None):
        q = self._search.text().lower() if hasattr(self, "_search") else ""
        active_filters = [
            (key, combo.currentData())
            for key, combo in self._filter_combos
            if combo.currentData()
        ]
        for row, text, tags in self._row_widgets:
            visible = q in text
            if visible:
                visible = all(self._tag_matches(tags, key, wanted) for key, wanted in active_filters)
            row.setVisible(visible)

    def _choose(self, value):
        self._selected = value
        self.accept()

    @staticmethod
    def pick(title, rows, parent=None, extra_top_widget=None, filter_specs=None):
        dlg = _SearchableListDialog(title, rows, parent, extra_top_widget, filter_specs)
        dlg.exec()
        return dlg._selected


def _picker_row(primary, secondary=""):
    """One clickable row's content: bold primary line + optional dim secondary line."""
    row = QWidget()
    layout = QVBoxLayout(row)
    layout.setContentsMargins(10, 8, 10, 8)
    layout.setSpacing(1)
    p_lbl = QLabel(primary)
    p_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
    p_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent; border: none;")
    p_lbl.setWordWrap(True)
    layout.addWidget(p_lbl)
    if secondary:
        s_lbl = QLabel(secondary)
        s_lbl.setFont(QFont("Segoe UI", 9))
        s_lbl.setStyleSheet(f"color: {TEXT_MUTED}; background: transparent; border: none;")
        s_lbl.setWordWrap(True)
        layout.addWidget(s_lbl)
    return row


def _sorted_options(values):
    return sorted({str(v) for v in values if v not in ("", None)})


def _weight_bucket(weight, light=5.0, heavy=10.0):
    try:
        value = float(weight)
    except (TypeError, ValueError):
        return "Unknown"
    if value <= light:
        return "Light"
    if value >= heavy:
        return "Heavy"
    return "Medium"


def _effect_bucket(text):
    text_l = str(text or "").lower()
    buckets = [
        ("Equip Load", ("equip load", "weight load")),
        ("Stamina", ("stamina", "endurance")),
        ("HP", (" hp", "health", "vigor")),
        ("FP", (" fp", "focus", "mind")),
        ("Damage", ("damage", "attack", "power", "ar ")),
        ("Defense", ("defense", "negation", "resist", "guard")),
        ("Status", ("bleed", "blood", "poison", "scarlet", "rot", "frost", "sleep", "madness", "death blight")),
        ("Casting", ("spell", "sorcer", "incant", "cast")),
        ("Utility", ("rune", "discovery", "vision", "movement", "stealth")),
    ]
    for label, needles in buckets:
        if any(needle in text_l for needle in needles):
            return label
    return "Other"


def _spell_kind(spell):
    return spell.get("type") or spell.get("spell_type") or spell.get("school") or spell.get("category") or "Other"


class WeaponPickerDialog:
    """Weapon picker -- list from /weapons/?game=, click to pick, or None to clear the slot."""

    @staticmethod
    def pick(weapons, parent=None):
        def _weapon_meta(w):
            parts = [w.get("type", ""), f"{w.get('weight','?')} wt"]
            affinity_text = _weapon_affinity_display(w, None)
            if affinity_text != "None":
                parts.append(f"Affinity: {affinity_text}")
            return " - ".join(p for p in parts if p)

        rows = [
            (lambda w=w: _picker_row(w.get("name", "Unknown"), _weapon_meta(w)),
             " ".join(str(v) for v in (
                 w.get("name", ""), w.get("type", ""), _weapon_affinity_display(w, None),
                 w.get("default_skill", ""), w.get("special", ""),
             )),
             w,
             {
                 "type": w.get("type", "") or "Other",
                 "affinity": _weapon_affinity_display(w, None),
                 "upgrade": "Somber" if w.get("is_somber") else "Standard",
                 "skill": "Locked" if w.get("is_locked_skill") else "Swappable",
             })
            for w in weapons
        ]
        rows = [(lambda: _picker_row("-- Unequip --"), "", None)] + rows
        filters = [
            {"key": "type", "label": "Type", "options": _sorted_options(w.get("type", "") for w in weapons)},
            {"key": "affinity", "label": "Affinity", "options": _sorted_options(_weapon_affinity_display(w, None) for w in weapons)},
            {"key": "upgrade", "label": "Upgrade", "options": ("Standard", "Somber")},
            {"key": "skill", "label": "Skill", "options": ("Swappable", "Locked")},
        ]
        return _SearchableListDialog.pick("Choose Weapon", rows, parent, filter_specs=filters)


class AowPickerDialog:
    """
    AoW picker -- filtered to what's compatible with the currently-equipped
    weapon's type. ER uses `compatible` (weapon type list) against /aow/;
    ERR uses `armaments` against /err/aow-skills/ and excludes unique/
    weapon-locked skills (per handoff doc, those aren't swappable).
    """

    @staticmethod
    def pick(aow_list, weapon_type, game, parent=None):
        compat_field = "armaments" if game == "err" else "compatible"
        eligible = []
        for a in aow_list:
            if game == "err" and a.get("is_unique_skill"):
                continue
            if aow_compatible(a.get(compat_field, ""), weapon_type):
                eligible.append(a)

        rows = [
            (lambda a=a: _picker_row(a.get("name", "Unknown"), a.get("affinity", "") or a.get("effect", "")[:80]),
             " ".join(str(v) for v in (a.get("name", ""), a.get("affinity", ""), a.get("effect", ""), a.get(compat_field, ""))),
             a.get("name"),
             {"affinity": a.get("affinity", "") or "None"})
            for a in eligible
        ]
        rows = [(lambda: _picker_row("-- Default (weapon's own skill) --"), "", "")] + rows
        filters = [
            {"key": "affinity", "label": "Affinity", "options": _sorted_options(a.get("affinity", "") or "None" for a in eligible)},
        ]
        return _SearchableListDialog.pick("Choose Ash of War", rows, parent, filter_specs=filters)


class AffinityPickerDialog:
    """
    Affinity picker. ER: hardcoded ER_AFFINITIES list, narrowed to whichever
    of those actually have an AR variant for this weapon. ERR: server-provided
    /err/affinities/ list, same narrowing against variants.
    """

    @staticmethod
    def pick(game, err_affinities, variants, parent=None):
        if game == "err":
            names = [a.get("name", "") for a in err_affinities]
            meta = {a.get("name", ""): a.get("effect", "") for a in err_affinities}
            by_name = {a.get("name", ""): a for a in err_affinities}
        else:
            names = list(ER_AFFINITIES)
            meta = {}
            by_name = {}

        if variants:
            available = {v.get("affinity", "") for v in variants}
            filtered = [n for n in names if n in available]
            if filtered:
                names = filtered

        rows = []
        for n in names:
            affinity = by_name.get(n, {})
            rows.append((
                lambda n=n: _picker_row(n, meta.get(n, "")),
                f"{n} {meta.get(n, '')} {affinity.get('scaling_stat', '')} {affinity.get('whetblade', '')}",
                n,
                {
                    "stat": affinity.get("scaling_stat", "") or "Other",
                    "whetblade": affinity.get("whetblade", "") or "None",
                    "effect": _effect_bucket(meta.get(n, "")),
                },
            ))
        filters = []
        if game == "err":
            filters = [
                {"key": "stat", "label": "Scaling", "options": _sorted_options(a.get("scaling_stat", "") or "Other" for a in err_affinities)},
                {"key": "whetblade", "label": "Whetblade", "options": _sorted_options(a.get("whetblade", "") or "None" for a in err_affinities)},
                {"key": "effect", "label": "Effect", "options": _sorted_options(_effect_bucket(a.get("effect", "")) for a in err_affinities)},
            ]
        return _SearchableListDialog.pick("Choose Affinity", rows, parent, filter_specs=filters)


class ArmorPickerDialog:
    @staticmethod
    def pick(armor_list, parent=None):
        rows = [
            (lambda a=a: _picker_row(a.get("name", "Unknown"), f"{a.get('type','')} - {a.get('weight','?')} wt - {a.get('poise','?')} poise"),
             " ".join(str(v) for v in (a.get("name", ""), a.get("type", ""), a.get("weight", ""), a.get("poise", ""))),
             a,
             {"type": a.get("type", "") or "Other", "weight": _weight_bucket(a.get("weight"))})
            for a in armor_list
        ]
        rows = [(lambda: _picker_row("-- Unequip --"), "", None)] + rows
        filters = [
            {"key": "type", "label": "Slot", "options": _sorted_options(a.get("type", "") for a in armor_list)},
            {"key": "weight", "label": "Weight", "options": ("Light", "Medium", "Heavy", "Unknown")},
        ]
        return _SearchableListDialog.pick("Choose Armor", rows, parent, filter_specs=filters)


class TalismanPickerDialog:
    @staticmethod
    def pick(talisman_list, parent=None):
        rows = [
            (lambda t=t: _picker_row(t.get("name", "Unknown"), f"{t.get('effect','')} - {t.get('weight','?')} wt"),
             " ".join(str(v) for v in (t.get("name", ""), t.get("effect", ""), t.get("weight", ""))),
             t,
             {"effect": _effect_bucket(t.get("effect", "")), "weight": _weight_bucket(t.get("weight"), light=0.0, heavy=1.0)})
            for t in talisman_list
        ]
        rows = [(lambda: _picker_row("-- Unequip --"), "", None)] + rows
        filters = [
            {"key": "effect", "label": "Effect", "options": _sorted_options(_effect_bucket(t.get("effect", "")) for t in talisman_list)},
            {"key": "weight", "label": "Weight", "options": ("Light", "Medium", "Heavy", "Unknown")},
        ]
        return _SearchableListDialog.pick("Choose Talisman", rows, parent, filter_specs=filters)


class SpiritAshPickerDialog:
    @staticmethod
    def pick(ash_list, parent=None):
        rows = [
            (lambda a=a: _picker_row(a.get("name", "Unknown"), a.get("summon_type", "")),
             " ".join(str(v) for v in (a.get("name", ""), a.get("summon_type", ""), a.get("passive_behavior", ""), a.get("enraged_behavior", ""))),
             a.get("name"),
             {"type": a.get("summon_type", "") or "Other"})
            for a in ash_list
        ]
        rows = [(lambda: _picker_row("-- None --"), "", None)] + rows
        filters = [
            {"key": "type", "label": "Type", "options": _sorted_options(a.get("summon_type", "") or "Other" for a in ash_list)},
        ]
        return _SearchableListDialog.pick("Choose Spirit Ash", rows, parent, filter_specs=filters)


class PhysickPickerDialog:
    @staticmethod
    def pick(tear_list, parent=None):
        rows = [
            (lambda t=t: _picker_row(t.get("name", "Unknown"), t.get("effect", "")),
             f"{t.get('name', '')} {t.get('effect', '')}",
             t.get("name"),
             {"effect": _effect_bucket(t.get("effect", ""))})
            for t in tear_list
        ]
        rows = [(lambda: _picker_row("-- Empty --"), "", None)] + rows
        filters = [
            {"key": "effect", "label": "Effect", "options": _sorted_options(_effect_bucket(t.get("effect", "")) for t in tear_list)},
        ]
        return _SearchableListDialog.pick("Choose Crystal Tear", rows, parent, filter_specs=filters)


class SpellPickerDialog:
    @staticmethod
    def pick(spell_list, parent=None):
        rows = [
            (lambda s=s: _picker_row(
                s.get("name", "Unknown"),
                " - ".join(str(v) for v in (
                    _spell_kind(s),
                    f"FP {s.get('fp_cost')}" if s.get("fp_cost") is not None else "",
                    s.get("effect", ""),
                ) if v),
            ),
             " ".join(str(v) for v in (
                 s.get("name", ""), _spell_kind(s), s.get("effect", ""),
                 s.get("fp_cost", ""), s.get("slots", ""), s.get("int", ""),
                 s.get("fai", ""), s.get("arc", ""),
             )),
             s,
             {"kind": _spell_kind(s), "effect": _effect_bucket(s.get("effect", ""))})
            for s in spell_list
        ]
        rows = [(lambda: _picker_row("-- Empty --"), "", None)] + rows
        filters = [
            {"key": "kind", "label": "Kind", "options": _sorted_options(_spell_kind(s) for s in spell_list)},
            {"key": "effect", "label": "Effect", "options": _sorted_options(_effect_bucket(s.get("effect", "")) for s in spell_list)},
        ]
        return _SearchableListDialog.pick("Choose Spell", rows, parent, filter_specs=filters)


class FortunePickerDialog:
    @staticmethod
    def pick(fortune_list, title, parent=None):
        rows = [
            (lambda f=f: _picker_row(f.get("name", "Unknown"), f.get("fortune_type", "").capitalize()),
             " ".join(str(v) for v in (f.get("name", ""), f.get("fortune_type", ""), f.get("buffs", ""), f.get("drawbacks", ""), f.get("unique_effects", ""))),
             f.get("name"),
             {"type": f.get("fortune_type", "") or "Other"})
            for f in fortune_list
        ]
        rows = [(lambda: _picker_row("-- None --"), "", None)] + rows
        filters = [
            {"key": "type", "label": "Type", "options": _sorted_options(f.get("fortune_type", "") or "Other" for f in fortune_list)},
        ]
        return _SearchableListDialog.pick(title, rows, parent, filter_specs=filters)


class RunePickerDialog:
    @staticmethod
    def pick(rune_defs, parent=None):
        rows = [
            (lambda r=r: _picker_row(r.get("name", "Unknown"), f"{r.get('category','')} - {r.get('effect','')}"),
             " ".join(str(v) for v in (r.get("name", ""), r.get("category", ""), r.get("effect", ""))),
             r,
             {"category": r.get("category", "") or "Other"})
            for r in rune_defs
        ]
        filters = [
            {"key": "category", "label": "Category", "options": _sorted_options(r.get("category", "") or "Other" for r in rune_defs)},
        ]
        return _SearchableListDialog.pick("Add Binding Rune", rows, parent, filter_specs=filters)

class RuneRow(QWidget):
    """One held Binding Rune: name/effect/category text, a copies stepper
    (+/-, capped at [1, max_forge_level] per spec 2.4's adjust_rune_copies --
    dropping below 1 removes the rune from inventory entirely rather than
    showing a 0-copies row), and a remove button."""

    changed = pyqtSignal()  # a copies adjustment or removal -- real edit
    removed = pyqtSignal(object)  # self -- RuneInventoryWidget removes this row's widget

    def __init__(self, name, category, effect, copies, max_copies, parent=None):
        super().__init__(parent)
        self.name = name
        self.category = category
        self.effect = effect
        self.copies = copies
        self.max_copies = max_copies

        card, layout = _panel()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(card)

        header = QHBoxLayout()
        name_lbl = QLabel(name)
        name_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        name_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent; border: none;")
        header.addWidget(name_lbl, 1)

        # Explicit solid-fill background+color on every button here (not
        # just a border) with padding:0/margin:0 -- Qt's default button
        # theming/padding rendered these as blank boxes at this size
        # otherwise. Decrease = red, increase = gold, same split as
        # StatRow's -/+ buttons.
        minus_style = f"""
            QPushButton {{ background: {ACCENT_RED}; border: none; border-radius: 4px;
                          color: {TEXT_PRIMARY}; font-weight: 800; font-size: 14px;
                          padding: 0px; margin: 0px; }}
            QPushButton:hover {{ background: #e0490f; }}
            QPushButton:disabled {{ background: {BORDER_SOLID}; color: {TEXT_DIM}; }}
        """
        plus_style = f"""
            QPushButton {{ background: {ACCENT_GOLD}; border: none; border-radius: 4px;
                          color: {BG_BASE}; font-weight: 800; font-size: 14px;
                          padding: 0px; margin: 0px; }}
            QPushButton:hover {{ background: {ACCENT_GOLD2}; }}
            QPushButton:disabled {{ background: {BORDER_SOLID}; color: {TEXT_DIM}; }}
        """
        self._minus_btn = QPushButton("-")
        self._minus_btn.setFixedSize(30, 26)
        self._minus_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._minus_btn.setStyleSheet(minus_style)
        self._minus_btn.clicked.connect(lambda: self._adjust(-1))
        self._copies_lbl = QLabel()
        self._copies_lbl.setStyleSheet(f"color: {ACCENT_GOLD}; background: transparent; border: none; font-weight: 700;")
        self._copies_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._copies_lbl.setFixedWidth(50)
        self._plus_btn = QPushButton("+")
        self._plus_btn.setFixedSize(30, 26)
        self._plus_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._plus_btn.setStyleSheet(plus_style)
        self._plus_btn.clicked.connect(lambda: self._adjust(1))
        header.addWidget(self._minus_btn)
        header.addWidget(self._copies_lbl)
        header.addWidget(self._plus_btn)

        remove_btn = QPushButton("x")
        remove_btn.setFixedSize(30, 26)
        remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_btn.setStyleSheet(f"""
            QPushButton {{ background: {ACCENT_RED}; border: none; border-radius: 4px;
                          color: {TEXT_PRIMARY}; font-weight: 800; font-size: 14px;
                          padding: 0px; margin: 0px; }}
            QPushButton:hover {{ background: #e0490f; }}
        """)
        remove_btn.clicked.connect(lambda: self.removed.emit(self))
        header.addWidget(remove_btn)
        layout.addLayout(header)

        if category:
            cat_lbl = QLabel(category)
            cat_lbl.setStyleSheet(f"color: {TEXT_DIM}; font-size: 9px; background: transparent; border: none;")
            layout.addWidget(cat_lbl)
        if effect:
            eff_lbl = QLabel(effect)
            eff_lbl.setWordWrap(True)
            eff_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; background: transparent; border: none;")
            layout.addWidget(eff_lbl)

        self._refresh_copies_label()

    def _refresh_copies_label(self):
        self._copies_lbl.setText(f"{self.copies}/{self.max_copies}")
        self._minus_btn.setEnabled(True)  # dropping to 0 removes the row, always allowed
        self._plus_btn.setEnabled(self.copies < self.max_copies)

    def _adjust(self, delta):
        """Matches spec 2.4's adjust_rune_copies(): new_val < 1 removes the
        rune entirely; new_val > max_copies is a silent no-op (button is
        already disabled at the cap, this is just the belt-and-suspenders
        guard)."""
        new_val = self.copies + delta
        if new_val < 1:
            self.removed.emit(self)
            return
        if new_val > self.max_copies:
            return
        self.copies = new_val
        self._refresh_copies_label()
        self.changed.emit()

    def to_dict(self):
        return {"name": self.name, "category": self.category, "effect": self.effect,
                "copies": self.copies, "max_copies": self.max_copies}


class RuneInventoryWidget(QWidget):
    """
    Editable Binding Rune inventory: an "Add Rune" button opening
    RunePickerDialog over the full flattened reference list, then one
    RuneRow per held rune. Matches spec 2.4's add_rune()/adjust_rune_copies()
    -- adding an already-held rune increments its existing row instead of
    creating a duplicate (silently no-ops at the forge cap, same as the
    button-disable behavior).
    """

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rune_defs = []       # flattened reference list, [{name,category,effect,max_forge_level}]
        self._rows = {}            # rune name -> RuneRow

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        add_btn = QPushButton("+ Add Binding Rune")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self._open_add_picker)
        outer.addWidget(add_btn)

        self._empty_lbl = QLabel("No Binding Runes held.")
        self._empty_lbl.setStyleSheet(f"color: {TEXT_DIM}; background: transparent; border: none;")
        outer.addWidget(self._empty_lbl)

        self._rows_layout = QVBoxLayout()
        self._rows_layout.setSpacing(8)
        outer.addLayout(self._rows_layout)
        outer.addStretch()

    def configure(self, runeforging_data):
        """runeforging_data: the raw {'categories': [...]} from get_runeforging()."""
        self._rune_defs = []
        for cat in (runeforging_data or {}).get("categories", []):
            cat_name = cat.get("category", "")
            for r in cat.get("binding_runes", []):
                self._rune_defs.append({
                    "name": r.get("name", ""), "category": cat_name,
                    "effect": r.get("effect", ""), "max_forge_level": r.get("max_forge_level", 1),
                })

    def load(self, rune_inventory):
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._rows = {}

        defs_by_name = {d["name"]: d for d in self._rune_defs}
        for rune in rune_inventory or []:
            name = rune.get("name", "")
            d = defs_by_name.get(name, {})
            row = RuneRow(
                name, rune.get("category") or d.get("category", ""),
                rune.get("effect") or d.get("effect", ""),
                rune.get("copies", 1), rune.get("max_copies") or d.get("max_forge_level", 1),
            )
            row.changed.connect(self.changed.emit)
            row.removed.connect(self._on_row_removed)
            self._rows[name] = row
            self._rows_layout.addWidget(row)
        self._refresh_empty_state()

    def _refresh_empty_state(self):
        self._empty_lbl.setVisible(len(self._rows) == 0)

    def _open_add_picker(self):
        if not self._rune_defs:
            return
        picked = RunePickerDialog.pick(self._rune_defs, parent=self)
        if not picked:
            return
        name = picked["name"]
        if name in self._rows:
            # Already held -- increment like a real add_rune() call, capped
            # silently at the forge max (spec 2.4: "silently no-ops at max").
            self._rows[name]._adjust(1)
            return
        row = RuneRow(name, picked.get("category", ""), picked.get("effect", ""),
                      1, picked.get("max_forge_level", 1))
        row.changed.connect(self.changed.emit)
        row.removed.connect(self._on_row_removed)
        self._rows[name] = row
        self._rows_layout.addWidget(row)
        self._refresh_empty_state()
        self.changed.emit()

    def _on_row_removed(self, row):
        self._rows_layout.removeWidget(row)
        row.deleteLater()
        del self._rows[row.name]
        self._refresh_empty_state()
        self.changed.emit()

    def current_inventory(self):
        return [row.to_dict() for row in self._rows.values()]


class SimpleSlotWidget(QWidget):
    """
    One editable single-item slot (armor/talisman/physick-tear) -- unlike
    WeaponSlotWidget, no AoW/affinity sub-rows, just a single clickable row
    that opens a picker and swaps in whatever it returns. `picker_fn` is
    `dialog_cls.pick` (already bound), called as `picker_fn(items, parent=self)`.
    """

    changed = pyqtSignal()

    def __init__(self, label, min_height=56, parent=None):
        super().__init__(parent)
        self.value = None       # dict (armor/talisman) or str (tear name) or None
        self._loading = False
        self._items = []        # list passed to the picker
        self._picker_fn = None
        self._display = lambda v: (v.get("name", "Unknown") if isinstance(v, dict) else str(v)) if v else "Empty"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)
        name_lbl = QLabel(label)
        name_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        name_lbl.setStyleSheet(f"color: {TEXT_MUTED}; letter-spacing: 1px; background: transparent; border: none;")
        self._val_lbl = QLabel("Empty")
        self._val_lbl.setFont(QFont("Segoe UI", 11))
        self._val_lbl.setWordWrap(True)
        self._val_lbl.setStyleSheet(f"color: {TEXT_DIM}; background: transparent; border: none;")
        layout.addWidget(name_lbl)
        layout.addWidget(self._val_lbl)

        self.setMinimumHeight(min_height)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            SimpleSlotWidget {{ background: {BG_SURFACE}; border: 1px dashed {BORDER_SOLID}; border-radius: 6px; }}
        """)
        self.mousePressEvent = lambda _e: self._open_picker()

    def configure(self, items, picker_fn, display=None):
        self._items = items
        self._picker_fn = picker_fn
        if display:
            self._display = display

    def load(self, value):
        self._loading = True
        self.value = self._enrich_value(value)
        self._loading = False
        self._refresh_label()

    def current_value(self):
        return self.value

    def _refresh_label(self):
        text = self._display(self.value)
        if self.value:
            self._val_lbl.setText(text)
            self._val_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent; border: none;")
        else:
            self._val_lbl.setText("Empty")
            self._val_lbl.setStyleSheet(f"color: {TEXT_DIM}; background: transparent; border: none;")

    def _open_picker(self):
        if not self._picker_fn or not self._items:
            return
        picked = self._picker_fn(self._items, parent=self)
        if picked is CANCELLED:
            return  # dialog closed/escaped without choosing -- leave the slot untouched
        self.value = picked
        self._refresh_label()
        if not self._loading:
            self.changed.emit()

    def _enrich_value(self, value):
        if not isinstance(value, dict):
            return value
        for full in self._items or []:
            if not isinstance(full, dict):
                continue
            if (
                (value.get("id") is not None and full.get("id") == value.get("id"))
                or (value.get("name") and full.get("name") == value.get("name"))
            ):
                merged = dict(value)
                merged.update(full)
                return merged
        return value


class CharacterColumn(QWidget):
    """Column 1: class picker, editable attributes, derived character stats."""

    stats_changed = pyqtSignal()  # any stat or class edit -- BuildPlannerWidget uses this to mark the build dirty / enable Save
    class_changed = pyqtSignal(int)  # new class_id, after the user picks a class from the picker

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build = None
        self._refdata = {}
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(16)

        class_panel, class_layout = _panel("CLASS")
        class_row = QHBoxLayout()
        self._class_lbl = QLabel("—")
        self._class_lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        self._class_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent; border: none;")
        change_btn = QPushButton("Change")
        change_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        change_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: 1px solid {BORDER_SOLID}; border-radius: 6px;
                          color: {TEXT_MUTED}; padding: 4px 10px; font-size: 9px; }}
            QPushButton:hover {{ border-color: {ACCENT_GOLD}; color: {ACCENT_GOLD}; }}
        """)
        change_btn.clicked.connect(self._open_class_picker)
        class_row.addWidget(self._class_lbl, 1)
        class_row.addWidget(change_btn)
        class_layout.addLayout(class_row)
        outer.addWidget(class_panel)

        attr_panel, attr_layout = _panel("ATTRIBUTES")
        self._stat_rows = {}
        for stat_key in STAT_NAMES:
            row = StatRow(stat_key)
            row.value_changed.connect(self._on_stat_changed)
            self._stat_rows[stat_key] = row
            attr_layout.addWidget(row)

        level_row = QHBoxLayout()
        level_row.setContentsMargins(0, 8, 0, 0)
        level_row.setSpacing(10)
        level_text = QVBoxLayout()
        level_text.setSpacing(1)
        level_title = QLabel("CURRENT RUNE LEVEL")
        level_title.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        level_title.setStyleSheet(f"color: {TEXT_MUTED}; letter-spacing: 1px; background: transparent; border: none;")
        self._level_hint_lbl = QLabel("Minimum from stats")
        self._level_hint_lbl.setFont(QFont("Segoe UI", 8))
        self._level_hint_lbl.setStyleSheet(f"color: {TEXT_DIM}; background: transparent; border: none;")
        level_text.addWidget(level_title)
        level_text.addWidget(self._level_hint_lbl)
        self._level_lbl = QLabel("--")
        self._level_lbl.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self._level_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._level_lbl.setFixedWidth(64)
        self._level_lbl.setStyleSheet(f"""
            QLabel {{ background: #151515; border: 1px solid #333333; border-radius: 4px;
                      color: {ACCENT_GOLD2}; padding: 4px 8px; }}
        """)
        level_row.addLayout(level_text, 1)
        level_row.addWidget(self._level_lbl)
        attr_layout.addLayout(level_row)
        outer.addWidget(attr_panel)

        char_panel, char_layout = _panel("CHARACTER")
        grid = QGridLayout()
        grid.setSpacing(10)
        self._char_stat_lbls = {}
        for i, (key, label) in enumerate([
            ("hp", "HP"), ("fp", "FP"), ("stamina", "Stamina"), ("equip_load", "Equip Load"),
            ("poise", "Poise"), ("weight", "Weight"), ("roll_type", "Roll Type"),
        ]):
            col = i % 2
            row_idx = i // 2
            name_lbl = QLabel(label.upper())
            name_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            name_lbl.setStyleSheet(f"color: {TEXT_MUTED}; letter-spacing: 1px; background: transparent; border: none;")
            val_lbl = QLabel("—")
            val_lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
            val_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent; border: none;")
            val_lbl.setWordWrap(True)
            cell = QVBoxLayout()
            cell.setSpacing(2)
            cell.addWidget(name_lbl)
            cell.addWidget(val_lbl)
            wrap = QWidget()
            wrap.setLayout(cell)
            grid.addWidget(wrap, row_idx, col)
            self._char_stat_lbls[key] = val_lbl
        char_layout.addLayout(grid)
        outer.addWidget(char_panel)

        outer.addStretch()

    def load(self, build, refdata=None):
        self._build = build
        self._refdata = refdata or {}
        stats = build.get("stats", {})

        caps_list = self._refdata.get("stat_caps", [])
        caps_by_stat = {c["stat"]: c for c in caps_list} if caps_list else {}
        classes = self._refdata.get("classes", [])
        class_id = build.get("class_id")
        class_obj = next((c for c in classes if c.get("id") == class_id), None)

        for stat_key, row in self._stat_rows.items():
            if class_obj:
                row.set_floor(class_obj.get(stat_key, 1))
            row.set_value(stats.get(stat_key, 10), caps_by_stat.get(stat_key))

        self._update_class_label(class_obj, class_id)
        self._recompute_derived()

    def _update_class_label(self, class_obj, class_id):
        if class_obj:
            self._class_lbl.setText(f"{class_obj['name']}  (Lv {class_obj.get('level', '?')})")
        else:
            self._class_lbl.setText(f"Class ID {class_id}" if class_id is not None else "—")

    def current_stats(self):
        """Live stat values straight from the spinboxes -- reflects unsaved edits."""
        return {stat_key: row.base_value() for stat_key, row in self._stat_rows.items()}

    def _on_stat_changed(self, stat_key, value):
        self._recompute_derived()
        self.stats_changed.emit()

    def _weapon_weight(self, weapon, affinity=None, game="elden_ring"):
        """
        Look up a weapon's real weight from the reference /weapons/ list
        (refdata["weapons"]) by id/name -- the build payload's own weapon
        object is thin ({id,name,type} only, no weight field), same gap
        _enrich_weapon() in WeaponSlotWidget already works around for
        default_skill/is_locked_skill. This was previously left unfixed here
        specifically ("weapon weight isn't in the build data yet"), but the
        SAME reference list already used for those other fields also has
        weight -- it just was never read for this calc.
        """
        if not weapon:
            return 0
        if game == "err":
            variants = (self._refdata.get("ar_variant_cache", {}) or {}).get((game, weapon.get("name", "")))
            if variants is None:
                try:
                    from core.catalog_sync import CatalogStore
                    cached = CatalogStore().load_ar_variants_fallback(weapon.get("name", ""), game)
                    variants = cached.get("variants", []) if cached else None
                except Exception:
                    variants = None
            if variants:
                selected = get_variant_for_affinity(variants, affinity or _effective_weapon_affinity(weapon, None, game) or "Standard")
                if selected and selected.get("weight") is not None:
                    return selected.get("weight") or 0
        if "weight" in weapon:
            weight = weapon.get("weight") or 0
            if game == "err" and (affinity or _effective_weapon_affinity(weapon, None, game)) == "Gravitational":
                return floor(weight * 0.5 * 10) / 10
            return weight
        for full in self._refdata.get("weapons", []):
            if full.get("id") == weapon.get("id") or full.get("name") == weapon.get("name"):
                weight = full.get("weight") or 0
                if game == "err" and (affinity or _effective_weapon_affinity(full, None, game)) == "Gravitational":
                    return floor(weight * 0.5 * 10) / 10
                return weight
        return 0

    def _recompute_derived(self, armor_override=None, enkindle_mods=None, weapons_override=None):
        """
        Recomputes HP/FP/Stamina/Equip Load/Poise/Weight/Roll Type from
        whatever's CURRENTLY in the spinboxes (not necessarily what was
        originally loaded) -- shared by load(), every live stat edit, live
        armor edits (armor_override), live weapon edits (weapons_override),
        and live Enkindling edits (enkindle_mods, from
        core.enkindling.calc_enkindle_modifiers()). ONE shared function
        applying Enkindle mods, reused by every panel that shows these
        numbers -- the Enkindling spec's pitfall #4 is exactly two panels
        computing the same number two different ways after applying a
        multiplier in one place but not the other.
        """
        if not self._build:
            return
        build = self._build
        game = build.get("_game", "elden_ring")
        base_stats = self.current_stats()
        classes = self._refdata.get("classes", [])
        class_obj = next((c for c in classes if c.get("id") == build.get("class_id")), None)
        class_base = {s: class_obj.get(s, 1) for s in base_stats} if class_obj else {s: 1 for s in base_stats}
        minimum_level = calc_level(base_stats, class_base, class_obj, game)
        current_level = _saved_or_minimum_level(build, base_stats, class_base, class_obj, game)
        self._level_lbl.setText(str(current_level))
        self._level_hint_lbl.setText(f"Minimum from stats: {minimum_level}")
        rune_inventory = build.get("rune_inventory", []) or []
        talismans = build.get("talismans", []) or []
        talisman_mods = _talisman_modifiers(talismans)
        fortune_name = build.get("fortune_name") or None
        stats = _effective_build_stats(
            base_stats, game,
            fortune_name=fortune_name,
            rune_inventory=rune_inventory,
            talismans=talismans,
            enkindle_mods=enkindle_mods,
        )

        err_curves = self._refdata.get("derived_curves") if game == "err" else None
        derived = get_derived(stats, game, err_curves=err_curves, fortune_name=None)
        if game == "err" and fortune_name:
            derived = apply_fortune_multipliers(derived, fortune_name)

        if armor_override is not None:
            armor_slots = {slot: armor_override.get(slot) for slot in ARMOR_SLOTS}
        else:
            armor_slots = {slot: build.get("armor", {}).get(slot) for slot in ARMOR_SLOTS}
        poise = calc_poise(armor_slots)

        if weapons_override is not None:
            weapons = weapons_override
        else:
            weapons = build.get("weapons", {}) or {}
        weapon_slots_by_weight = {
            slot: {
                "weight": self._weapon_weight(
                    weapons.get(slot),
                    _effective_weapon_affinity(weapons.get(slot), weapons.get(f"{slot}_affinity"), game),
                    game,
                )
            }
            for slot in WEAPON_SLOTS
        }

        if game == "err":
            equip_load = calc_equip_load_err(fortune_name, rune_inventory)
            equip_load = round(equip_load * talisman_mods["equip_load_mult"], 1)
            total_weight = calc_total_weight_err({**armor_slots, **weapon_slots_by_weight})
            roll_type = get_frame_type_err(total_weight, equip_load, fortune_name)
        else:
            equip_load = derived["equip_load"]
            total_weight = calc_total_weight({**armor_slots, **weapon_slots_by_weight})
            roll_type = get_roll_type(total_weight, equip_load)

        hp, fp, stamina = derived["hp"], derived["fp"], derived["stamina"]

        # Rune HP/FP/Stamina/EquipLoad multipliers (Cursed Health/Cradled
        # Focus/Leonine Stamina/Leonine Weight) -- calc_rune_derived_mults()
        # existed correctly but was never actually called from the GUI.
        # equip_load's own rune mult is already folded in via
        # calc_equip_load_err() above; only apply the 'eqload' key here if
        # NOT already covered (avoid double-applying it).
        if game == "err" and rune_inventory:
            rune_mults = calc_rune_derived_mults(rune_inventory)
            hp = floor(hp * rune_mults["hp"])
            fp = floor(fp * rune_mults["fp"])
            stamina = floor(stamina * rune_mults["stamina"])
        if game == "err":
            hp = floor(hp * talisman_mods["hp_mult"])
            fp = floor(fp * talisman_mods["fp_mult"])
            stamina = floor(stamina * talisman_mods["stamina_mult"])

        if enkindle_mods:
            enk_derived = apply_enkindle_to_derived(hp, fp, stamina, equip_load, poise, enkindle_mods)
            hp, fp, stamina = enk_derived["hp"], enk_derived["fp"], enk_derived["stamina"]
            equip_load, poise = enk_derived["equip_load"], enk_derived["poise"]
        for stat_key, row in self._stat_rows.items():
            bonus = stats.get(stat_key, base_stats.get(stat_key, 0)) - base_stats.get(stat_key, 0)
            row.set_enkindle_bonus(bonus, stats.get(stat_key))
            row._apply_bar(stats.get(stat_key, base_stats.get(stat_key, 1)))

        self._char_stat_lbls["hp"].setText(str(round(hp)))
        self._char_stat_lbls["fp"].setText(str(round(fp)))
        self._char_stat_lbls["stamina"].setText(str(round(stamina)))
        self._char_stat_lbls["equip_load"].setText(str(round(equip_load, 1)))
        self._char_stat_lbls["poise"].setText(str(round(poise, 1)))
        self._char_stat_lbls["weight"].setText(str(total_weight))
        self._char_stat_lbls["weight"].setToolTip("")
        self._char_stat_lbls["roll_type"].setText(roll_type)

    def _open_class_picker(self):
        classes = self._refdata.get("classes", [])
        if not classes:
            return
        picked = ClassPickerDialog.pick(classes, parent=self)
        if not picked:
            return
        self._apply_class(picked)

    def _apply_class(self, class_obj):
        """
        Reset every stat to the new class's base values (matches the web's
        "Reset to Class" behavior) and update the floor on each spinbox so
        it can't be dragged below the new class's minimums.
        """
        if self._build is not None:
            self._build["class_id"] = class_obj.get("id")
        for stat_key, row in self._stat_rows.items():
            row.set_floor(class_obj.get(stat_key, 1))
            row.set_value(class_obj.get(stat_key, 1), row._last_caps)
        self._update_class_label(class_obj, class_obj.get("id"))
        self._recompute_derived()
        self.class_changed.emit(class_obj.get("id"))
        self.stats_changed.emit()


class CurioCard(QWidget):
    """
    One ERR Shadowed Curio: clickable header (toggles sealed/unsealed) +
    3 clickable effect rows (picking one also unseals this curio). Enforces
    nothing itself -- CurioCard only reports what was clicked via signals;
    the single-active-curio-across-all-9 rule lives one level up in
    EquipmentColumn, which is the only place that can see every other card.
    """

    toggled = pyqtSignal(str)             # curio_name -- header clicked
    effect_picked = pyqtSignal(str, int)  # curio_name, effect_index -- an effect row clicked

    def __init__(self, curio, parent=None):
        super().__init__(parent)
        self.name = curio.get("name", "Unknown")
        self._effects = curio.get("effects", [])

        self._card, layout = _panel()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._card)

        header = QWidget()
        header.setCursor(Qt.CursorShape.PointingHandCursor)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        self._name_lbl = QLabel(self.name)
        self._name_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self._state_lbl = QLabel("SEALED")
        self._state_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self._state_lbl.setStyleSheet(f"letter-spacing: 1px; background: transparent; border: none;")
        header_layout.addWidget(self._name_lbl, 1)
        header_layout.addWidget(self._state_lbl)
        header.mousePressEvent = lambda _e: self.toggled.emit(self.name)
        layout.addWidget(header)

        trigger = curio.get("trigger", "")
        if trigger:
            trig_lbl = QLabel(trigger)
            trig_lbl.setWordWrap(True)
            trig_lbl.setStyleSheet(f"color: {TEXT_DIM}; font-style: italic; background: transparent; border: none;")
            layout.addWidget(trig_lbl)

        self._effect_lbls = []
        for rank_i, effect_text in enumerate(self._effects):
            eff_lbl = QLabel(f"○ +{rank_i}: {effect_text}")
            eff_lbl.setWordWrap(True)
            eff_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
            eff_lbl.setStyleSheet(f"color: {TEXT_DIM}; background: transparent; border: none; font-size: 10px;")
            eff_lbl.mousePressEvent = lambda _e, idx=rank_i: self.effect_picked.emit(self.name, idx)
            layout.addWidget(eff_lbl)
            self._effect_lbls.append(eff_lbl)

    def set_state(self, active, effect_index):
        self._name_lbl.setStyleSheet(
            f"color: {ACCENT_GOLD if active else TEXT_MUTED}; background: transparent; border: none;"
        )
        self._state_lbl.setText("UNSEALED" if active else "SEALED")
        self._state_lbl.setStyleSheet(
            f"color: {GREEN_LIVE if active else TEXT_DIM}; letter-spacing: 1px; background: transparent; border: none;"
        )
        for rank_i, eff_lbl in enumerate(self._effect_lbls):
            is_selected = active and rank_i == effect_index
            eff_lbl.setText(f"{'●' if is_selected else '○'} +{rank_i}: {self._effects[rank_i]}")
            eff_lbl.setStyleSheet(
                f"color: {TEXT_PRIMARY if is_selected else TEXT_DIM}; background: transparent; border: none; font-size: 10px;"
            )


class WeaponSlotWidget(QWidget):
    """
    One editable weapon slot (rh1/rh2/.../lh3): a weapon row (click to open
    WeaponPickerDialog), plus AoW and Affinity sub-rows that only appear once
    a weapon is equipped (each opens its own picker). Holds its own edit
    state (`weapon`/`aow_name`/`affinity`) rather than writing back into the
    build dict directly on every click -- BuildPlannerWidget reads it via
    `current_selection()` only at save time, same pattern as StatRow/spinboxes.
    """

    changed = pyqtSignal()  # any weapon/AoW/affinity/enkindle edit -- real edit, not a load
    enkindle_eligible_needed = pyqtSignal(str, str)  # (slot, aow_name) -- ask BuildPlannerWidget to fetch+deliver the eligible-affix list for this AoW

    def __init__(self, slot, parent=None):
        super().__init__(parent)
        self.slot = slot
        self._loading = False
        self.weapon = None      # {'id','name','type',...} or None
        self.aow_name = None    # str or None (None = weapon default skill)
        self.affinity = None    # str or None
        self.enkindle_affix = None    # str or None
        self.enkindle_rarity = None   # 'common'|'rare'|'legendary'|None
        self._eligible_affixes = []   # cached per current aow_name, fetched async by BuildPlannerWidget
        self._refdata = {}
        self._game = "elden_ring"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)

        name_lbl = QLabel(WEAPON_SLOT_LABELS[slot].upper())
        name_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        name_lbl.setStyleSheet(f"color: {TEXT_MUTED}; letter-spacing: 1px; background: transparent; border: none;")
        layout.addWidget(name_lbl)

        self._weapon_row = QWidget()
        self._weapon_row.setCursor(Qt.CursorShape.PointingHandCursor)
        weapon_row_layout = QHBoxLayout(self._weapon_row)
        weapon_row_layout.setContentsMargins(0, 2, 0, 2)
        self._weapon_lbl = QLabel("Empty")
        self._weapon_lbl.setFont(QFont("Segoe UI", 11))
        self._weapon_lbl.setWordWrap(True)
        weapon_row_layout.addWidget(self._weapon_lbl, 1)
        self._weapon_row.mousePressEvent = lambda _e: self._open_weapon_picker()
        layout.addWidget(self._weapon_row)

        self._aow_row = QWidget()
        self._aow_row.setCursor(Qt.CursorShape.PointingHandCursor)
        aow_row_layout = QHBoxLayout(self._aow_row)
        aow_row_layout.setContentsMargins(0, 0, 0, 0)
        self._aow_lbl = QLabel("")
        self._aow_lbl.setFont(QFont("Segoe UI", 9))
        self._aow_lbl.setStyleSheet(f"color: {ACCENT_GOLD}; background: transparent; border: none;")
        self._aow_lbl.setWordWrap(True)
        aow_row_layout.addWidget(self._aow_lbl, 1)
        self._aow_row.mousePressEvent = lambda _e: self._open_aow_picker()
        layout.addWidget(self._aow_row)

        self._affinity_row = QWidget()
        self._affinity_row.setCursor(Qt.CursorShape.PointingHandCursor)
        affinity_row_layout = QHBoxLayout(self._affinity_row)
        affinity_row_layout.setContentsMargins(0, 0, 0, 0)
        self._affinity_lbl = QLabel("")
        self._affinity_lbl.setFont(QFont("Segoe UI", 9))
        self._affinity_lbl.setStyleSheet("color: #a78bfa; background: transparent; border: none;")
        self._affinity_lbl.setWordWrap(True)
        affinity_row_layout.addWidget(self._affinity_lbl, 1)
        self._affinity_row.mousePressEvent = lambda _e: self._open_affinity_picker()
        layout.addWidget(self._affinity_row)

        # ERR-only. Hidden entirely (not shown disabled/empty) for locked-
        # skill weapons -- per the Enkindling spec's explicit client rule:
        # a fixed AoW has nothing to enkindle, and showing an empty/Mundane
        # dropdown would wrongly imply the weapon supports it.
        self._enkindle_row = QWidget()
        enkindle_row_layout = QHBoxLayout(self._enkindle_row)
        enkindle_row_layout.setContentsMargins(0, 2, 0, 0)
        enkindle_row_layout.setSpacing(6)
        enkindle_lbl = QLabel("ENKINDLE")
        enkindle_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        enkindle_lbl.setStyleSheet(f"color: {ACCENT_GOLD}; letter-spacing: 1px; background: transparent; border: none;")
        self._enkindle_combo = QComboBox()
        self._enkindle_combo.setStyleSheet(f"""
            QComboBox {{ background: {BG_SURFACE}; border: 1px solid {BORDER_SOLID}; border-radius: 4px;
                        color: {ACCENT_GOLD}; padding: 3px 8px; font-size: 10px; }}
            QComboBox QAbstractItemView {{ background: {BG_CARD}; border: 1px solid {BORDER_SOLID};
                                           color: {TEXT_PRIMARY}; selection-background-color: rgba(201,168,76,0.15); }}
        """)
        self._enkindle_combo.addItem("No Enkindling", userData=None)
        self._enkindle_combo.currentIndexChanged.connect(self._on_enkindle_combo_changed)
        enkindle_row_layout.addWidget(enkindle_lbl)
        enkindle_row_layout.addWidget(self._enkindle_combo, 1)
        layout.addWidget(self._enkindle_row)
        self._enkindle_row.setVisible(False)

        self.setMinimumHeight(80)
        self.setStyleSheet(f"""
            WeaponSlotWidget {{ background: {BG_SURFACE}; border: 1px dashed {BORDER_SOLID}; border-radius: 6px; }}
        """)
        self._refresh_labels()

    def set_refdata(self, refdata, game):
        self._refdata = refdata or {}
        self._game = game

    def load(self, weapon, aow_name, affinity, enkindle_affix=None, enkindle_rarity=None):
        self._loading = True
        # The build detail payload's weapon object is thin ({id,name,type}
        # only) -- default_skill/is_locked_skill live on the full records
        # from /weapons/, not on the build. Enrich by lookup so an
        # already-equipped Colossal Sword's fixed skill still shows correctly
        # (not just weapons picked fresh via WeaponPickerDialog, which pass
        # the full record straight through already).
        self.weapon = self._enrich_weapon(weapon)
        self.aow_name = aow_name or None
        self.affinity = affinity or None
        # Per spec section 4.3: only apply a saved enkindle selection if the
        # affix name is actually in the current eligible list for this AoW --
        # BuildPlannerWidget validates this (it has the async eligible-fetch
        # machinery) and calls set_enkindle_state() after resolving, rather
        # than trusting the raw save-file value blindly here.
        self.enkindle_affix = None
        self.enkindle_rarity = None
        self._pending_enkindle_restore = (enkindle_affix, enkindle_rarity)
        self._loading = False
        self._refresh_labels()

    def _enrich_weapon(self, weapon):
        if not weapon or "default_skill" in weapon:
            return weapon
        for full in self._refdata.get("weapons", []):
            if full.get("id") == weapon.get("id") or full.get("name") == weapon.get("name"):
                return full
        return weapon

    def current_selection(self):
        return self.weapon, self.aow_name, _effective_weapon_affinity(self.weapon, self.affinity, self._game)

    def current_enkindle(self):
        return self.enkindle_affix, self.enkindle_rarity

    def _refresh_labels(self):
        if self.weapon:
            wtype = self.weapon.get("type", "")
            text = self.weapon.get("name", "Unknown")
            if wtype:
                text += f"  ({wtype})"
            self._weapon_lbl.setText(text)
            self._weapon_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent; border: none;")
            self._aow_row.setVisible(True)
            self._affinity_row.setVisible(True)

            # No custom AoW selected -- fall back to the weapon's OWN
            # default skill (e.g. Colossal Swords' unique arts, Meteorite
            # Staff's innate skill) instead of a generic "(default)" label,
            # which read as "no skill at all" rather than "using its own".
            locked = bool(self.weapon.get("is_locked_skill"))
            if self.aow_name:
                self._aow_lbl.setText(f"AoW: {self.aow_name}")
            else:
                default_skill = self.weapon.get("default_skill")
                if default_skill:
                    suffix = "  \U0001F512" if locked else ""
                    self._aow_lbl.setText(f"AoW: {default_skill}{suffix}")
                else:
                    self._aow_lbl.setText("AoW: (default)")
            self._aow_row.setCursor(
                Qt.CursorShape.ArrowCursor if locked else Qt.CursorShape.PointingHandCursor
            )

            # Affinity is gated on is_infusable, NOT is_locked_skill. Fixed
            # ERR affinities come from the weapon API's factual
            # affinity/affinities fields and are read-only, even on catalysts
            # such as Meteorite Staff.
            uses_affinity = _weapon_uses_affinity(self.weapon)
            not_infusable = not self.weapon.get("is_infusable", True)
            affinity_suffix = "  \U0001F512" if (not_infusable or not uses_affinity) else ""
            affinity_label = _weapon_affinity_display(self.weapon, self.affinity, self._game)
            self._affinity_lbl.setText(
                f"Affinity: {affinity_label}{affinity_suffix}"
            )
            self._affinity_row.setCursor(
                Qt.CursorShape.ArrowCursor if (not_infusable or not uses_affinity) else Qt.CursorShape.PointingHandCursor
            )

            # Enkindling: ERR-only, and hidden entirely (not shown empty/
            # disabled) for locked-skill weapons -- a fixed AoW has nothing
            # to enkindle (spec section 6's explicit client rule). Request
            # the eligible-affix list for whatever AoW is actually active
            # right now (custom pick, or the weapon's own default_skill) --
            # BuildPlannerWidget owns the async fetch+cache and calls back
            # into set_eligible_affixes() once it resolves.
            locked_skill = bool(self.weapon.get("is_locked_skill"))
            self._enkindle_row.setVisible(self._game == "err" and not locked_skill)
            if self._game == "err" and not locked_skill:
                active_aow = self.aow_name or self.weapon.get("default_skill")
                if active_aow:
                    self.enkindle_eligible_needed.emit(self.slot, active_aow)
        else:
            self._weapon_lbl.setText("Empty")
            self._weapon_lbl.setStyleSheet(f"color: {TEXT_DIM}; background: transparent; border: none;")
            self._aow_row.setVisible(False)
            self._affinity_row.setVisible(False)
            self._enkindle_row.setVisible(False)

    def _open_weapon_picker(self):
        weapons = self._refdata.get("weapons", [])
        if not weapons:
            return
        picked = WeaponPickerDialog.pick(weapons, parent=self)
        if picked is CANCELLED:
            return  # dialog closed/escaped without choosing -- leave the slot untouched
        self.weapon = picked
        self.aow_name = None
        self.affinity = None
        # Pitfall #1/#2 (Enkindling spec section 5): un-equipping OR swapping
        # a slot's weapon must clear its Enkindling selection -- the new
        # weapon's AoW may not even be eligible for the old affix, and a
        # cleared slot obviously has nothing to enkindle.
        self.enkindle_affix = None
        self.enkindle_rarity = None
        self._eligible_affixes = []
        self._refresh_labels()
        if not self._loading:
            self.changed.emit()

    def _open_aow_picker(self):
        if not self.weapon or self.weapon.get("is_locked_skill"):
            return
        game = self._game
        aow_list = self._refdata.get("err_aow_skills" if game == "err" else "aow", [])
        if not aow_list:
            return
        picked = AowPickerDialog.pick(aow_list, self.weapon.get("type", ""), game, parent=self)
        if picked is CANCELLED:
            return  # dialog closed/escaped without choosing -- leave the slot untouched
        self.aow_name = picked or None
        # Pitfall #2: swapping in a different AoW must clear the OLD
        # Enkindling selection before the new AoW's eligible list repopulates
        # -- the old affix may not even be a legal roll for the new AoW.
        self.enkindle_affix = None
        self.enkindle_rarity = None
        self._eligible_affixes = []
        self._refresh_labels()
        if not self._loading:
            self.changed.emit()

    def _open_affinity_picker(self):
        if not self.weapon or not _weapon_uses_affinity(self.weapon) or not self.weapon.get("is_infusable", True):
            return
        game = self._game
        err_affinities = self._refdata.get("err_affinities", []) if game == "err" else []
        cache = self._refdata.get("ar_variant_cache", {})
        variants = cache.get((game, self.weapon.get("name", "")))
        picked = AffinityPickerDialog.pick(game, err_affinities, variants, parent=self)
        if picked is CANCELLED or picked is None:
            return  # dialog closed/escaped -- leave the slot untouched (this picker has no "clear" row at all)
        self.affinity = picked
        self._refresh_labels()
        if not self._loading:
            self.changed.emit()

    def set_eligible_affixes(self, aow_name, affixes):
        """
        Called by BuildPlannerWidget once its async eligible-affix fetch for
        `aow_name` resolves. Ignores stale deliveries (user already changed
        weapon/AoW again before the fetch came back) by checking aow_name
        still matches what's currently active. Rebuilds the combo box, and
        if a saved enkindle selection is pending restore (build load), only
        applies it if the affix name is actually IN this eligible list --
        per spec 4.3, otherwise leave the slot cleared rather than carry a
        stale value.
        """
        active_aow = self.aow_name or (self.weapon or {}).get("default_skill")
        if active_aow != aow_name:
            return  # stale delivery, current AoW has since changed
        self._eligible_affixes = affixes or []

        was_loading = self._loading
        self._loading = True
        self._enkindle_combo.blockSignals(True)
        self._enkindle_combo.clear()
        self._enkindle_combo.addItem("No Enkindling", userData=None)
        for affix in self._eligible_affixes:
            name = affix.get("name", "")
            for rarity in ("common", "rare", "legendary"):
                label = f"{name} — {rarity.capitalize()} ({'★' * RARITY_TIER[rarity]})"
                self._enkindle_combo.addItem(label, userData=(name, rarity))

        restore_affix, restore_rarity = getattr(self, "_pending_enkindle_restore", (None, None))
        self._pending_enkindle_restore = (None, None)
        target_index = 0
        if restore_affix:
            eligible_names = {a.get("name") for a in self._eligible_affixes}
            if restore_affix in eligible_names:
                for i in range(self._enkindle_combo.count()):
                    data = self._enkindle_combo.itemData(i)
                    if data == (restore_affix, restore_rarity):
                        target_index = i
                        break
                if target_index:
                    self.enkindle_affix = restore_affix
                    self.enkindle_rarity = restore_rarity
            # else: affix no longer eligible for this AoW -- leave cleared,
            # matches the spec's explicit "don't carry a stale value" rule.
        self._enkindle_combo.setCurrentIndex(target_index)
        self._enkindle_combo.blockSignals(False)
        self._loading = was_loading

    def _on_enkindle_combo_changed(self, index):
        data = self._enkindle_combo.itemData(index)
        self.enkindle_affix, self.enkindle_rarity = data if data else (None, None)
        if not self._loading:
            self.changed.emit()


class EquipmentColumn(QWidget):
    """Column 2: Armament (editable) / Armor / Talismans / Spirit / Physick tabs."""

    weapon_changed = pyqtSignal()  # any WeaponSlotWidget edit -- BuildPlannerWidget marks the build dirty
    equipment_changed = pyqtSignal()  # any armor/talisman/spirit-ash/physick edit
    enkindle_eligible_needed = pyqtSignal(str, str)  # (slot, aow_name) -- forwarded up from whichever WeaponSlotWidget needs it

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: 1px solid {BORDER_SOLID}; border-radius: 8px; background: {BG_CARD}; }}
            QTabBar::tab {{
                background: transparent; color: {TEXT_MUTED}; padding: 8px 16px;
                font-size: 10px; font-weight: 700; letter-spacing: 1px;
            }}
            QTabBar::tab:selected {{ color: {ACCENT_GOLD}; border-bottom: 2px solid {ACCENT_GOLD}; }}
        """)

        self._armament_tab, self._weapon_slots = self._build_armament_tab()
        self._armor_tab, self._armor_widgets = self._build_armor_tab()
        self._talisman_tab, self._talisman_widgets = self._build_talisman_tab()
        self._spirit_tab, self._spirit_widget = self._build_spirit_tab()
        self._physick_tab, self._physick_widgets = self._build_physick_tab()
        self._curios_tab = self._build_curios_tab()
        self._fortunes_tab = self._build_fortunes_tab()
        self._runes_tab = self._build_runes_tab()

        self.tabs.addTab(self._armament_tab, "ARMAMENT")
        self.tabs.addTab(self._armor_tab, "ARMOR")
        self.tabs.addTab(self._talisman_tab, "TALISMANS")
        self.tabs.addTab(self._spirit_tab, "SPIRIT")
        self.tabs.addTab(self._physick_tab, "PHYSICK")
        self._err_tab_indices = [
            self.tabs.addTab(self._curios_tab, "CURIOS"),
            self.tabs.addTab(self._fortunes_tab, "FORTUNES"),
            self.tabs.addTab(self._runes_tab, "BINDING RUNES"),
        ]

        outer.addWidget(self.tabs)

    def _build_armament_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
        slots = {}
        for slot in WEAPON_SLOTS:
            w = WeaponSlotWidget(slot)
            w.changed.connect(self.weapon_changed.emit)
            w.enkindle_eligible_needed.connect(self.enkindle_eligible_needed.emit)
            slots[slot] = w
            layout.addWidget(w)
        layout.addStretch()
        return tab, slots

    def _build_armor_tab(self):
        tab = QWidget()
        layout = QGridLayout(tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
        widgets = {}
        for i, slot in enumerate(ARMOR_SLOTS):
            w = SimpleSlotWidget(ARMOR_SLOT_LABELS[slot].upper())
            w.changed.connect(self.equipment_changed.emit)
            widgets[slot] = w
            layout.addWidget(w, i // 2, i % 2)
        # Trailing stretch row -- QGridLayout has no addStretch(), so give
        # the row just past the real content all the leftover vertical
        # space instead, keeping the fixed-height slot rows compact at top.
        layout.setRowStretch(len(ARMOR_SLOTS) // 2, 1)
        return tab, widgets

    def _build_talisman_tab(self):
        tab = QWidget()
        layout = QGridLayout(tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
        widgets = []
        for i in range(4):
            w = SimpleSlotWidget(f"SLOT {i + 1}")
            w.changed.connect(self.equipment_changed.emit)
            widgets.append(w)
            layout.addWidget(w, i // 2, i % 2)
        layout.setRowStretch(2, 1)
        return tab, widgets

    def _build_spirit_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
        w = SimpleSlotWidget("SPIRIT ASH")
        w.changed.connect(self.equipment_changed.emit)
        layout.addWidget(w)
        layout.addStretch()
        return tab, w

    def _build_curios_tab(self):
        """
        Accordion of ERR Shadowed Curios. Content is rebuilt per-load() call
        (curios come from refdata, cross-referenced against the build's
        curio_selections) rather than built once here, since there's no
        data yet at __init__ time.
        """
        tab = QScrollArea()
        tab.setWidgetResizable(True)
        tab.setStyleSheet("border: none; background: transparent;")
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
        layout.addStretch()
        tab.setWidget(container)
        tab._content_layout = layout  # stash for load() to rebuild against
        return tab

    def _build_fortunes_tab(self):
        tab = QScrollArea()
        tab.setWidgetResizable(True)
        tab.setStyleSheet("border: none; background: transparent;")
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        main_widget = SimpleSlotWidget("MAIN FORTUNE")
        main_widget.changed.connect(self.equipment_changed.emit)
        minor_widget = SimpleSlotWidget("MINOR FORTUNE")
        minor_widget.changed.connect(self.equipment_changed.emit)
        layout.addWidget(main_widget)
        layout.addWidget(minor_widget)

        # Buffs/drawbacks text for whichever fortune is currently selected --
        # rebuilt on every load()/pick since it's purely descriptive (not
        # editable), same "info panel below the editable slot" idea as the
        # Armament tab's AR panel being separate from the weapon picker rows.
        info_container = QWidget()
        info_layout = QVBoxLayout(info_container)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(10)
        layout.addWidget(info_container)
        layout.addStretch()

        tab.setWidget(container)
        tab._main_widget = main_widget
        tab._minor_widget = minor_widget
        tab._info_layout = info_layout
        return tab

    def _build_runes_tab(self):
        tab = QScrollArea()
        tab.setWidgetResizable(True)
        tab.setStyleSheet("border: none; background: transparent;")
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
        inventory_widget = RuneInventoryWidget()
        inventory_widget.changed.connect(self.equipment_changed.emit)
        layout.addWidget(inventory_widget)
        tab.setWidget(container)
        tab._inventory_widget = inventory_widget
        return tab

    @staticmethod
    def _clear_layout(layout):
        """Remove every widget from a layout except its trailing stretch item."""
        while layout.count() > 1:
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _build_physick_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
        w1 = SimpleSlotWidget("CRYSTAL TEAR 1")
        w2 = SimpleSlotWidget("CRYSTAL TEAR 2")
        w1.changed.connect(self.equipment_changed.emit)
        w2.changed.connect(self.equipment_changed.emit)
        layout.addWidget(w1)
        layout.addWidget(w2)
        layout.addStretch()
        return tab, (w1, w2)

    def load(self, build, refdata=None):
        refdata = refdata or {}
        game = build.get("_game", "elden_ring")
        is_err = game == "err"
        for idx in self._err_tab_indices:
            self.tabs.setTabVisible(idx, is_err)
        if is_err:
            self._load_curios(build, refdata)
            self._load_fortunes(build, refdata)
            self._load_runes(build, refdata)

        weapons = build.get("weapons", {})
        weapon_refdata = {
            "weapons":          refdata.get("weapons", []),
            "aow":              refdata.get("aow", []),
            "err_aow_skills":   refdata.get("err_aow_skills", []),
            "err_affinities":   refdata.get("err_affinities", []),
            "ar_variant_cache": refdata.get("ar_variant_cache", {}),
        }
        for slot, slot_widget in self._weapon_slots.items():
            slot_widget.set_refdata(weapon_refdata, game)
            w = weapons.get(slot)
            aow = weapons.get(f"{slot}_aow")
            affinity = weapons.get(f"{slot}_affinity")
            enkindle_affix = weapons.get(f"{slot}_enkindle_affix")
            enkindle_rarity = weapons.get(f"{slot}_enkindle_rarity")
            slot_widget.load(w, aow, affinity, enkindle_affix, enkindle_rarity)

        armor_list = refdata.get("armor", [])
        armor = build.get("armor", {})
        for slot, widget in self._armor_widgets.items():
            widget.configure(armor_list, ArmorPickerDialog.pick)
            widget.load(armor.get(slot))

        talisman_list = refdata.get("talismans", [])
        talismans = build.get("talismans", [])
        for i, widget in enumerate(self._talisman_widgets):
            widget.configure(talisman_list, TalismanPickerDialog.pick)
            widget.load(talismans[i] if i < len(talismans) else None)

        ash_list = refdata.get("spirit_ashes", [])
        self._spirit_widget.configure(
            ash_list, SpiritAshPickerDialog.pick,
            display=lambda v: f"{v}  (+{build.get('spirit_ash_upgrade', 0)})" if v else "Empty",
        )
        self._spirit_widget.load(build.get("spirit_ash_name"))

        tear_list = refdata.get("crystal_tears", [])
        tear_names = (build.get("tear_1_name"), build.get("tear_2_name"))
        for widget, tear_name in zip(self._physick_widgets, tear_names):
            widget.configure(tear_list, PhysickPickerDialog.pick)
            widget.load(tear_name)

    def current_weapons(self):
        """{slot: (weapon_or_None, aow_name_or_None, affinity_or_None)} -- live edit state for save."""
        return {slot: w.current_selection() for slot, w in self._weapon_slots.items()}

    def current_enkindle_selections(self):
        """{slot: {'affix': name, 'rarity': str} or None} -- shape expected by
        core.enkindling.calc_enkindle_modifiers()."""
        result = {}
        for slot, w in self._weapon_slots.items():
            affix, rarity = w.current_enkindle()
            result[slot] = {"affix": affix, "rarity": rarity} if affix else None
        return result

    def set_slot_eligible_affixes(self, slot, aow_name, affixes):
        widget = self._weapon_slots.get(slot)
        if widget:
            widget.set_eligible_affixes(aow_name, affixes)

    def current_equipment(self):
        """{armor: {slot: dict|None}, talismans: [dict|None x4], spirit_ash_name: str|None,
        tear_1_name/tear_2_name: str|None} -- live edit state for save, mirrors build detail shape."""
        return {
            "armor": {slot: w.current_value() for slot, w in self._armor_widgets.items()},
            "talismans": [w.current_value() for w in self._talisman_widgets],
            "spirit_ash_name": self._spirit_widget.current_value(),
            "tear_1_name": self._physick_widgets[0].current_value(),
            "tear_2_name": self._physick_widgets[1].current_value(),
        }

    def _load_curios(self, build, refdata):
        layout = self._curios_tab._content_layout
        self._clear_layout(layout)
        self._curio_cards = {}
        # Deep-copy so editing doesn't mutate the loaded build dict in place
        # (same "edit state lives separately from the loaded build" pattern
        # as every other editable widget in this column).
        raw = build.get("curio_selections") or {}
        self._curio_selections = {
            name: {"active": bool(sel.get("active")), "effectIndex": sel.get("effectIndex", 0)}
            for name, sel in raw.items()
        }

        all_curios = refdata.get("curios", [])
        if not all_curios:
            lbl = QLabel("No Curio data available.")
            lbl.setStyleSheet(f"color: {TEXT_DIM}; background: transparent; border: none;")
            layout.insertWidget(0, lbl)
            return

        for i, curio in enumerate(all_curios):
            card = CurioCard(curio)
            card.toggled.connect(self._on_curio_toggled)
            card.effect_picked.connect(self._on_curio_effect_picked)
            self._curio_cards[card.name] = card
            layout.insertWidget(i, card)

        self._refresh_curio_cards()

    def _refresh_curio_cards(self):
        for name, card in self._curio_cards.items():
            sel = self._curio_selections.get(name, {"active": False, "effectIndex": 0})
            card.set_state(sel["active"], sel["effectIndex"])

    def _on_curio_toggled(self, name):
        """
        Matches the spec's toggle_curio() exactly: turning ON seals every
        other curio first (only one can be unsealed across all 9), turning
        OFF just seals this one.
        """
        sel = self._curio_selections.setdefault(name, {"active": False, "effectIndex": 0})
        turning_on = not sel["active"]
        if turning_on:
            for other in self._curio_selections.values():
                other["active"] = False
        sel["active"] = turning_on
        self._refresh_curio_cards()
        self.equipment_changed.emit()

    def _on_curio_effect_picked(self, name, effect_index):
        """
        Matches the spec's select_curio_effect(): picking an effect ALSO
        unseals this curio and seals every other one -- same invariant as
        toggling, enforced here too rather than assuming the toggle path
        alone covers it.
        """
        sel = self._curio_selections.setdefault(name, {"active": False, "effectIndex": 0})
        sel["effectIndex"] = effect_index
        for other_name, other in self._curio_selections.items():
            other["active"] = (other_name == name)
        self._refresh_curio_cards()
        self.equipment_changed.emit()

    def current_curio_selections(self):
        """{curio_name: {'active': bool, 'effectIndex': int}} -- only curios
        the user has interacted with need to be present, per spec 7.3."""
        return {name: dict(sel) for name, sel in getattr(self, "_curio_selections", {}).items()}

    def _load_fortunes(self, build, refdata):
        all_fortunes = refdata.get("fortunes", [])
        by_name = {f.get("name"): f for f in all_fortunes}
        main_widget = self._fortunes_tab._main_widget
        minor_widget = self._fortunes_tab._minor_widget

        main_widget.configure(all_fortunes, lambda items, parent: FortunePickerDialog.pick(items, "Choose Main Fortune", parent))
        minor_widget.configure(all_fortunes, lambda items, parent: FortunePickerDialog.pick(items, "Choose Minor Fortune", parent))
        main_widget.load(build.get("fortune_name"))
        minor_widget.load(build.get("minor_fortune_name"))

        self._refresh_fortune_info(by_name)
        # Rebuild the info panel again whenever either slot's selection
        # changes -- SimpleSlotWidget's own `changed` signal already bubbles
        # up to equipment_changed, but that alone won't refresh the
        # buffs/drawbacks text below it, so hook the info refresh in
        # separately per fortune slot.
        main_widget.changed.connect(lambda: self._refresh_fortune_info(by_name))
        minor_widget.changed.connect(lambda: self._refresh_fortune_info(by_name))

    def _refresh_fortune_info(self, by_name):
        layout = self._fortunes_tab._info_layout
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        main_widget = self._fortunes_tab._main_widget
        minor_widget = self._fortunes_tab._minor_widget
        for label, widget, accent in (
            ("MAIN FORTUNE DETAILS", main_widget, ACCENT_GOLD),
            ("MINOR FORTUNE DETAILS", minor_widget, "#6c5ce7"),
        ):
            name = widget.current_value()
            if not name:
                continue
            f = by_name.get(name, {})
            card, card_layout = _panel(label)
            name_lbl = QLabel(name)
            name_lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
            name_lbl.setStyleSheet(f"color: {accent}; background: transparent; border: none;")
            card_layout.addWidget(name_lbl)
            for section, items in (("Buffs", f.get("buffs")), ("Drawbacks", f.get("drawbacks"))):
                if not items:
                    continue
                text = ", ".join(items) if isinstance(items, list) else str(items)
                sec_lbl = QLabel(f"{section}: {text}")
                sec_lbl.setWordWrap(True)
                sec_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; background: transparent; border: none;")
                card_layout.addWidget(sec_lbl)
            layout.addWidget(card)

    def _load_runes(self, build, refdata):
        inventory_widget = self._runes_tab._inventory_widget
        inventory_widget.configure(refdata.get("runeforging", {}))
        inventory_widget.load(build.get("rune_inventory"))

    def current_rune_inventory(self):
        """[{name, category, effect, copies, max_copies}] -- live edit state for save."""
        return self._runes_tab._inventory_widget.current_inventory()


class SummaryColumn(QWidget):
    """Column 3: Attack Rating panel + build info (name, level, playstyle, description)."""

    _ar_computed = pyqtSignal(dict)  # background thread -> main thread handoff, {slot: {"name":..., "ar":int|None, "error":str|None}}

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ar_computed.connect(self._apply_ar_results)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(16)

        ar_panel, ar_layout = _panel("ATTACK RATING")
        self._ar_rows = {}
        for slot in WEAPON_SLOTS:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 2, 0, 2)
            name_lbl = QLabel("")
            name_lbl.setFont(QFont("Segoe UI", 10))
            name_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent; border: none;")
            ar_lbl = QLabel("")
            ar_lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
            ar_lbl.setStyleSheet(f"color: {ACCENT_GOLD}; background: transparent; border: none;")
            ar_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
            row_layout.addWidget(name_lbl, 1)
            row_layout.addWidget(ar_lbl)
            row.setVisible(False)
            ar_layout.addWidget(row)
            self._ar_rows[slot] = (row, name_lbl, ar_lbl)

        self._ar_empty_lbl = QLabel("No weapons equipped")
        self._ar_empty_lbl.setStyleSheet(f"color: {TEXT_DIM}; background: transparent; border: none;")
        ar_layout.addWidget(self._ar_empty_lbl)
        outer.addWidget(ar_panel)

        info_panel, info_layout = _panel("BUILD INFO")
        self._name_lbl = QLabel("—")
        self._name_lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        self._name_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent; border: none;")
        self._name_lbl.setWordWrap(True)

        self._level_lbl = QLabel("—")
        self._level_lbl.setFont(QFont("Segoe UI", 10))
        self._level_lbl.setStyleSheet(f"color: {ACCENT_GOLD}; background: transparent; border: none;")

        self._tag_lbl = QLabel("—")
        self._tag_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self._tag_lbl.setStyleSheet(f"color: {TEXT_MUTED}; letter-spacing: 1px; background: transparent; border: none;")

        self._author_lbl = QLabel("")
        self._author_lbl.setFont(QFont("Segoe UI", 9))
        self._author_lbl.setStyleSheet(f"color: {TEXT_DIM}; background: transparent; border: none;")

        self._desc_lbl = QLabel("")
        self._desc_lbl.setFont(QFont("Segoe UI", 10))
        self._desc_lbl.setStyleSheet(f"color: {TEXT_MUTED}; background: transparent; border: none;")
        self._desc_lbl.setWordWrap(True)

        info_layout.addWidget(self._name_lbl)
        info_layout.addWidget(self._level_lbl)
        info_layout.addWidget(self._tag_lbl)
        info_layout.addWidget(self._author_lbl)
        info_layout.addWidget(self._desc_lbl)
        outer.addWidget(info_panel)

        outer.addStretch()

    def load(self, build, refdata=None, api=None, ar_variant_cache=None,
             enkindle_selections=None, enkindle_affixes_by_name=None):
        self._name_lbl.setText(build.get("name", "Untitled Build"))
        self._level_lbl.setText(f"Level {build.get('level', '—')}  ·  {build.get('tag', 'pve').upper()}")
        self._tag_lbl.setText("PUBLIC" if build.get("is_public") else "PRIVATE")
        author = build.get("author", "")
        self._author_lbl.setText(f"by {author}" if author else "")
        self._author_lbl.setVisible(bool(author))
        desc = build.get("description", "")
        self._desc_lbl.setText(desc)
        self._desc_lbl.setVisible(bool(desc))

        for slot, (row, _name_lbl, _ar_lbl) in self._ar_rows.items():
            row.setVisible(False)
        self._ar_empty_lbl.setVisible(True)

        if not api or not refdata or not refdata.get("ar_data"):
            return  # AR data not available yet -- nothing to compute against

        weapons = build.get("weapons", {})
        equipped = {slot: weapons.get(slot) for slot in WEAPON_SLOTS if weapons.get(slot)}
        if not equipped:
            return

        game = build.get("_game", "elden_ring")
        enkindle_mods = None
        if enkindle_selections and enkindle_affixes_by_name:
            enkindle_mods = calc_enkindle_modifiers(enkindle_selections, enkindle_affixes_by_name)
        stats = _effective_build_stats(
            build.get("stats", {}),
            game,
            fortune_name=build.get("fortune_name") or None,
            rune_inventory=build.get("rune_inventory", []) or [],
            talismans=build.get("talismans", []) or [],
            enkindle_mods=enkindle_mods,
        )
        ar_data = refdata["ar_data"]
        ar_curves = ar_data.get("curves", {})
        ar_aec = ar_data.get("aec", {})
        ar_reinforce = ar_data.get("reinforce", {})
        scadutree = build.get("scadutree_level", 0) or 0
        cache = ar_variant_cache if ar_variant_cache is not None else {}

        import threading
        def _fetch():
            results = {}
            for slot, w in equipped.items():
                name = w.get("name", "")
                affinity = _effective_weapon_affinity(w, weapons.get(f"{slot}_affinity"), game) or "Standard"
                cache_key = (game, name)
                variants = cache.get(cache_key)
                if variants is None:
                    variants = api.get_ar_variants(name, game=game)
                    cache[cache_key] = variants
                if not variants:
                    results[slot] = {"name": name, "ar": None, "error": "no AR data"}
                    continue
                variant = get_variant_for_affinity(variants, affinity)
                if not variant:
                    results[slot] = {"name": name, "ar": None, "error": "no matching affinity"}
                    continue
                try:
                    computed = compute_ar(variant, stats, ar_curves, ar_aec, ar_reinforce)
                    ar_total = apply_scadutree(computed["total"], scadutree)
                    # Order of operations per spec 3.1: base AR -> Scadutree
                    # -> Enkindle damage_mult, THIS slot's own selection only
                    # (never dedupe/aggregate damage_mult across slots).
                    if enkindle_selections and enkindle_affixes_by_name:
                        dmg_mult = calc_slot_damage_mult(slot, enkindle_selections, enkindle_affixes_by_name)
                        ar_total = int(ar_total * dmg_mult)
                    results[slot] = {"name": name, "ar": ar_total, "error": None}
                except Exception as e:
                    results[slot] = {"name": name, "ar": None, "error": str(e)}
            self._ar_computed.emit(results)
        threading.Thread(target=_fetch, daemon=True).start()

    def _apply_ar_results(self, results):
        any_shown = False
        for slot, (row, name_lbl, ar_lbl) in self._ar_rows.items():
            r = results.get(slot)
            if not r:
                continue
            row.setVisible(True)
            any_shown = True
            name_lbl.setText(f"{WEAPON_SLOT_LABELS[slot]}: {r['name']}")
            ar_lbl.setText(str(r["ar"]) if r["ar"] is not None else "—")
        self._ar_empty_lbl.setVisible(not any_shown)


class BuildPlannerWidget(QWidget):
    """
    Top-level Build Planner tab content. Shows a build list (from
    QuestLogClient/QuestLogSync.get_builds()) plus a 3-column read-only
    viewer for whichever build is selected. No editing yet -- see module
    docstring.
    """

    _builds_fetched   = pyqtSignal(list)  # background thread -> main thread handoff for refresh_list()
    _build_loaded     = pyqtSignal(dict)  # background thread -> main thread handoff for _load_build()
    _refdata_fetched  = pyqtSignal(str, dict)  # game, {classes,stat_caps,derived_curves,ar_data} -- see _fetch_refdata
    _save_result      = pyqtSignal(dict)  # background thread -> main thread handoff for _save_current_build()
    _enkindling_fetched = pyqtSignal(dict)  # background thread -> main thread handoff for the one-time /err/enkindling/ fetch
    _eligible_fetched   = pyqtSignal(str, str, list)  # (slot, aow_name, affixes) -- background thread -> main thread handoff for one eligible-affix fetch

    def __init__(self, api=None, parent=None):
        super().__init__(parent)
        self._api = api  # QuestLogClient or QuestLogSync -- either exposes get_builds()/get_build_detail()
        self._builds_fetched.connect(self._populate_list)
        self._build_loaded.connect(self._show_build)
        self._refdata_fetched.connect(self._on_refdata_fetched)
        self._save_result.connect(self._on_save_result)
        self._enkindling_fetched.connect(self._on_enkindling_fetched)
        self._eligible_fetched.connect(self._on_eligible_fetched)
        self._refdata = {}       # game -> {classes, stat_caps, derived_curves, ar_data}
        self._ar_variant_cache = {}  # (game, weapon_name) -> variants list
        self._pending_build = None   # build detail waiting on refdata to finish loading
        self._pending_new_build = None  # (game, is_local) waiting on refdata before the class picker can open
        self._enkindling_affixes_by_name = None  # ERR-only, fetched once, {name: {name, affinity, tiers}}
        self._eligible_cache = {}    # aow_name -> [affixes] (per spec 2.2, static at runtime, safe to cache indefinitely)
        self._pending_eligible_fetches = set()  # aow_names currently in flight, avoid duplicate fetches
        self._eligible_pending_slots = set()    # slots whose eligible-affix fetch hasn't resolved yet since the current build started loading -- gates the final render per spec pitfall #5
        self.setStyleSheet(f"background: {BG_BASE};")

        outer = QHBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(16)

        # ── Build list sidebar ──────────────────────────────────────
        list_panel, list_layout = _panel("MY BUILDS")
        list_panel.setFixedWidth(220)

        from PyQt6.QtWidgets import QComboBox
        self._game_selector = QComboBox()
        self._game_selector.addItem("Elden Ring", userData="elden_ring")
        self._game_selector.addItem("ERR (Reforged)", userData="err")
        self._game_selector.setItemData(1, "Elden Ring Reforged", Qt.ItemDataRole.ToolTipRole)
        self._game_selector.setStyleSheet(f"""
            QComboBox {{ background: {BG_SURFACE}; border: 1px solid {BORDER_SOLID}; border-radius: 6px;
                        color: {TEXT_PRIMARY}; padding: 6px 10px; }}
            QComboBox QAbstractItemView {{ background: {BG_CARD}; border: 1px solid {BORDER_SOLID};
                                           color: {TEXT_PRIMARY}; selection-background-color: rgba(201,168,76,0.15); }}
        """)
        self._game_selector.currentIndexChanged.connect(lambda _: self.refresh_list())
        list_layout.addWidget(self._game_selector)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search builds...")
        self._search.setStyleSheet(f"""
            QLineEdit {{ background: {BG_SURFACE}; border: 1px solid {BORDER_SOLID}; border-radius: 6px;
                        color: {TEXT_PRIMARY}; padding: 6px 10px; }}
        """)
        self._search.textChanged.connect(self._filter_list)
        list_layout.addWidget(self._search)

        self._list_scroll = QScrollArea()
        self._list_scroll.setWidgetResizable(True)
        self._list_scroll.setStyleSheet("border: none; background: transparent;")
        self._list_container = QWidget()
        self._list_container_layout = QVBoxLayout(self._list_container)
        self._list_container_layout.setContentsMargins(0, 0, 0, 0)
        self._list_container_layout.setSpacing(6)
        self._list_container_layout.addStretch()
        self._list_scroll.setWidget(self._list_container)
        list_layout.addWidget(self._list_scroll)

        create_row = QHBoxLayout()
        create_row.setSpacing(6)
        self._create_local_btn = QPushButton("+ Local Build")
        self._create_local_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._create_local_btn.setToolTip("Saved to disk only -- never uploaded, no QuestLog account needed")
        self._create_local_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: 1px solid {BORDER_SOLID}; border-radius: 6px;
                          color: {TEXT_MUTED}; padding: 6px; font-size: 9px; }}
            QPushButton:hover {{ border-color: {TEXT_PRIMARY}; color: {TEXT_PRIMARY}; }}
        """)
        self._create_local_btn.clicked.connect(lambda: self._create_new_build(local=True))
        self._create_cloud_btn = QPushButton("+ QuestLog Build")
        self._create_cloud_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._create_cloud_btn.setToolTip("Saved to your QuestLog account -- visible on questlog.casual-heroes.com too")
        self._create_cloud_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: 1px solid {BORDER_SOLID}; border-radius: 6px;
                          color: {ACCENT_GOLD}; padding: 6px; font-size: 9px; }}
            QPushButton:hover {{ border-color: {ACCENT_GOLD}; background: rgba(201,168,76,0.1); }}
        """)
        self._create_cloud_btn.clicked.connect(lambda: self._create_new_build(local=False))
        create_row.addWidget(self._create_local_btn)
        create_row.addWidget(self._create_cloud_btn)
        list_layout.addLayout(create_row)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: 1px solid {BORDER_SOLID}; border-radius: 6px;
                          color: {TEXT_MUTED}; padding: 6px; font-size: 10px; }}
            QPushButton:hover {{ border-color: {ACCENT_GOLD}; color: {ACCENT_GOLD}; }}
            QPushButton:disabled {{ color: {TEXT_DIM}; border-color: {TEXT_DIM}; }}
        """)
        self._refresh_btn.clicked.connect(self._on_refresh_clicked)
        list_layout.addWidget(self._refresh_btn)

        outer.addWidget(list_panel)

        # ── 3-column viewer ───────────────────────────────────────────
        # Wrapped in a horizontally-scrolling QScrollArea instead of letting
        # the columns compress when the window is narrower than the content
        # needs -- a fixed/minimum column width alone still let Qt squeeze
        # StatRow's labels below their functional minimum and overlap. This
        # matches the web's own spec (collapses to tabs below 1024px) in
        # spirit: content keeps its real size, the viewport scrolls instead
        # of squashing it.
        self._viewer = QWidget()
        viewer_layout = QHBoxLayout(self._viewer)
        viewer_layout.setContentsMargins(0, 0, 0, 0)
        viewer_layout.setSpacing(16)

        self._char_col = CharacterColumn()
        self._equip_col = EquipmentColumn()
        self._summary_col = SummaryColumn()

        self._char_col.setFixedWidth(244)     # 16px narrower than the wrapping scroll area to leave room for its scrollbar
        self._equip_col.setMinimumWidth(420)
        self._summary_col.setFixedWidth(224)

        def _vscroll(widget, content_width):
            """Wrap a column in its own vertical-only scroll area -- each
            column's content height can exceed the window independently
            (e.g. Character's Class+Attributes+Character panels stacked can
            be taller than Armament's weapon list), so they need to scroll
            independently rather than sharing one scrollbar for the whole row."""
            sa = QScrollArea()
            sa.setWidgetResizable(True)
            sa.setStyleSheet("border: none; background: transparent;")
            sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            sa.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            sa.setWidget(widget)
            sa.setFixedWidth(content_width + 16)  # +16 leaves room for the vertical scrollbar without clipping content
            return sa

        viewer_layout.addWidget(_vscroll(self._char_col, 244))
        viewer_layout.addWidget(self._equip_col, 1)
        viewer_layout.addWidget(_vscroll(self._summary_col, 224))

        self._viewer_scroll = QScrollArea()
        self._viewer_scroll.setWidgetResizable(True)
        self._viewer_scroll.setStyleSheet("border: none; background: transparent;")
        self._viewer_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._viewer_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._viewer_scroll.setWidget(self._viewer)

        self._empty_lbl = QLabel("Select a build to view it.")
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_lbl.setStyleSheet(f"color: {TEXT_DIM}; font-size: 13px;")

        # ── Save bar -- shown above the viewer once a build is loaded ──
        save_bar = QWidget()
        save_bar_layout = QHBoxLayout(save_bar)
        save_bar_layout.setContentsMargins(0, 0, 0, 8)
        self._dirty_lbl = QLabel("")
        self._dirty_lbl.setStyleSheet(f"color: {ACCENT_GOLD}; font-size: 10px;")
        self._save_btn = QPushButton("Save Changes")
        self._save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._save_btn.setEnabled(False)
        self._save_btn.setStyleSheet(f"""
            QPushButton {{ background: {ACCENT_GOLD}; border: none; border-radius: 6px;
                          color: {BG_BASE}; padding: 8px 20px; font-size: 11px; font-weight: 700; }}
            QPushButton:hover {{ background: {ACCENT_GOLD2}; }}
            QPushButton:disabled {{ background: {BG_SURFACE}; color: {TEXT_DIM}; border: 1px solid {BORDER_SOLID}; }}
        """)
        self._save_btn.clicked.connect(self._save_current_build)

        self._reset_btn = QPushButton("Reset Build")
        self._reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._reset_btn.setToolTip("Discard unsaved changes and reload this build as last saved")
        self._reset_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: 1px solid {BORDER_SOLID}; border-radius: 6px;
                          color: {TEXT_MUTED}; padding: 8px 16px; font-size: 11px; }}
            QPushButton:hover {{ border-color: {ACCENT_RED}; color: {ACCENT_RED}; }}
        """)
        self._reset_btn.clicked.connect(self._reload_current_build)

        save_bar_layout.addWidget(self._dirty_lbl)
        save_bar_layout.addStretch()
        save_bar_layout.addWidget(self._reset_btn)
        save_bar_layout.addWidget(self._save_btn)
        self._save_bar = save_bar
        save_bar.setVisible(False)

        self._viewer_stack = QWidget()
        stack_layout = QVBoxLayout(self._viewer_stack)
        stack_layout.setContentsMargins(0, 0, 0, 0)
        stack_layout.addWidget(save_bar)
        stack_layout.addWidget(self._empty_lbl)
        stack_layout.addWidget(self._viewer_scroll)
        self._viewer_scroll.setVisible(False)

        outer.addWidget(self._viewer_stack, 1)

        # Routes through _on_weapon_changed (not just _mark_dirty) because a
        # stat edit must also re-render the AR panel -- AR depends on
        # effective stats, so raising Strength etc. needs to recompute AR
        # live, not just mark the build dirty. _on_weapon_changed already
        # does exactly this (rebuild a live build dict from current stats +
        # weapons, re-run SummaryColumn.load()) and also calls _mark_dirty()
        # itself, so this single connection covers both without double-firing.
        self._char_col.stats_changed.connect(self._on_weapon_changed)
        self._char_col.class_changed.connect(self._on_class_changed)
        self._equip_col.weapon_changed.connect(self._on_weapon_changed)
        self._equip_col.equipment_changed.connect(self._on_equipment_changed)
        self._equip_col.enkindle_eligible_needed.connect(self._on_enkindle_eligible_needed)
        self._is_dirty = False

        self._build_summaries = []
        self._all_row_widgets = []

    def set_api(self, api):
        """
        Called whenever login/reconnect gives us a fresh API client -- often
        AFTER this widget's first showEvent already fired with no api set
        (e.g. the tab was visible pre-login, when refresh_list() silently
        no-oped). Re-fetch immediately so the list doesn't sit empty until
        some unrelated event happens to re-trigger showEvent.
        """
        self._api = api
        if api:
            self.refresh_list()

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh_list()

    def _on_refresh_clicked(self):
        """
        Visible feedback for the Refresh button -- refresh_list() itself
        gives no indication anything happened if the fetched list is
        identical to what's already shown (e.g. only 1 build exists), which
        reads as "the button doesn't work" even when the fetch succeeded.

        Also discards any unsaved edits on the currently-open build by
        reloading it fresh from the server -- Refresh is a reset point, not
        just a list re-fetch.
        """
        self._refresh_btn.setEnabled(False)
        self._refresh_btn.setText("Refreshing...")
        self.refresh_list()
        self._reload_current_build()

    def _reload_current_build(self):
        """
        Re-fetches the currently-open build from disk/server, discarding any
        unsaved local edits (stat changes, class change) -- shared by the
        Refresh button and the Reset Build button. No-op if nothing is
        currently open, or if the open build was never saved (no id yet --
        happens right after "+ Local/QuestLog Build" before the user's first
        Save Changes -- there's nothing on disk/server to reload yet).
        """
        build = self._char_col._build
        if not build or not build.get("id"):
            return
        build_key = build.get("share_token") if not build.get("_is_local") else build.get("id")
        self._load_build(build_key or build["id"], is_local=build.get("_is_local"))

    def refresh_list(self):
        game = self._game_selector.currentData()
        # Local builds need no API/login at all -- list them immediately.
        # If we also have an API, fetch cloud builds in the background and
        # merge them in once they arrive (_populate_list is additive-safe
        # to call twice in a row since it always clears+rebuilds the list).
        local = local_builds_store.list_local_builds(game)
        if not self._api:
            self._populate_list(local)
            return
        import threading
        def _fetch():
            cloud = self._api.get_builds(game=game) or []
            for b in cloud:
                b["is_local"] = False
            # Emit a signal rather than calling QTimer.singleShot directly
            # from this background thread -- QTimer needs an event loop on
            # the calling thread, which this thread doesn't have. A signal
            # crossing threads is queued to the receiver's (main) thread
            # automatically by Qt, which is what actually delivers this
            # safely. This was the real bug behind builds fetching fine
            # (confirmed in logs) but never reaching the UI.
            self._builds_fetched.emit(local + cloud)
        threading.Thread(target=_fetch, daemon=True).start()
        self._ensure_refdata(game)

    def _ensure_refdata(self, game):
        """Fetch classes/stat-caps/derived-curves/ar-data/weapons/aow(+ERR variants)/
        armor/talismans/spirit-ashes/crystal-tears (+ ERR-only curios/fortunes/
        runeforging/affinities) for `game` once, cache it."""
        if not self._api or game in self._refdata:
            return
        import threading
        def _fetch():
            weapons_data = self._api.get_weapons(game=game)
            data = {
                'classes':          self._api.get_classes(game=game),
                'stat_caps':        self._api.get_stat_caps(game=game),
                'derived_curves':   self._api.get_derived_curves(game=game),
                'ar_data':          self._api.get_ar_data(game=game),
                'weapons':          weapons_data.get('weapons', []) if weapons_data else [],
                'aow':              [],
                'err_aow_skills':   [],
                'err_affinities':   [],
                'curios':           [],
                'fortunes':         [],
                'runeforging':      {},
                'ar_variant_cache': self._ar_variant_cache,
                # Armor is ALWAYS game=elden_ring per the API (ERR reuses vanilla
                # armor data unchanged -- see CHARACTER_BUILDER_APP_HANDOFF.md's
                # ER-vs-ERR differences table), so get_armor() takes no game param.
                'armor':            self._api.get_armor(),
                'talismans':        self._api.get_talismans(game=game),
                'spirit_ashes':     self._api.get_spirit_ashes(game=game),
                'crystal_tears':    self._api.get_crystal_tears(game=game),
            }
            if game == 'err':
                data['err_aow_skills'] = self._api.get_err_aow_skills()
                data['err_affinities'] = self._api.get_affinities_err()
                curios_data = self._api.get_curios()
                data['curios'] = curios_data.get('curios', []) if curios_data else []
                data['fortunes'] = self._api.get_fortunes()
                data['runeforging'] = self._api.get_runeforging() or {}
            else:
                data['aow'] = self._api.get_aow(game=game)
            self._refdata_fetched.emit(game, data)
        threading.Thread(target=_fetch, daemon=True).start()

    def _on_refdata_fetched(self, game, data):
        self._refdata[game] = data
        # If a build finished loading while we were still waiting on
        # refdata, render it now that both are available.
        if self._pending_build and self._pending_build.get("_game") == game:
            build = self._pending_build
            self._pending_build = None
            self._render_build(build)
        pending_new = getattr(self, "_pending_new_build", None)
        if pending_new and pending_new[0] == game:
            self._pending_new_build = None
            self._open_class_picker_for_new_build(game, pending_new[1], data)

    def _ensure_enkindling_data(self):
        """Fetch the full Enkindling affix reference (/err/enkindling/) once,
        ever -- ERR-only, static data, cached for the lifetime of the widget."""
        if not self._api or self._enkindling_affixes_by_name is not None:
            return
        import threading
        def _fetch():
            data = self._api.get_enkindling() or {}
            self._enkindling_fetched.emit(data)
        threading.Thread(target=_fetch, daemon=True).start()

    def _on_enkindling_fetched(self, data):
        affixes = data.get("affixes", [])
        self._enkindling_affixes_by_name = {a.get("name"): a for a in affixes}

    def _on_enkindle_eligible_needed(self, slot, aow_name):
        """
        A WeaponSlotWidget needs the eligible-affix list for `aow_name`.
        Cached per AoW name indefinitely (spec 2.2: static at runtime).
        Multiple slots asking for the same AoW share one in-flight fetch.
        """
        self._eligible_pending_slots.add(slot)
        if aow_name in self._eligible_cache:
            self._equip_col.set_slot_eligible_affixes(slot, aow_name, self._eligible_cache[aow_name])
            self._eligible_pending_slots.discard(slot)
            self._maybe_render_after_eligible_resolved()
            return
        if aow_name in self._pending_eligible_fetches:
            return  # already in flight for some other slot asking about the same AoW
        self._pending_eligible_fetches.add(aow_name)
        import threading
        def _fetch():
            affixes = self._api.get_enkindling_eligible(aow_name)
            self._eligible_fetched.emit(slot, aow_name, affixes)
        threading.Thread(target=_fetch, daemon=True).start()

    def _on_eligible_fetched(self, slot, aow_name, affixes):
        self._pending_eligible_fetches.discard(aow_name)
        self._eligible_cache[aow_name] = affixes
        # Deliver to EVERY slot currently waiting on this same AoW, not just
        # the one that triggered the fetch (rh1/rh2 could share an AoW).
        for s, w in self._equip_col._weapon_slots.items():
            active_aow = w.aow_name or (w.weapon or {}).get("default_skill")
            if active_aow == aow_name:
                self._equip_col.set_slot_eligible_affixes(s, aow_name, affixes)
                self._eligible_pending_slots.discard(s)
        self._maybe_render_after_eligible_resolved()

    def _maybe_render_after_eligible_resolved(self):
        """
        Pitfall #5 (spec section 5): don't render final stat/AR/poise numbers
        until every per-slot Enkindling restore has resolved, or the initial
        render flashes without bonuses applied. Once the last pending slot
        clears, do one real recompute pass.
        """
        if self._eligible_pending_slots:
            return
        self._recompute_all_enkindle_dependent()

    def _current_enkindle_context(self):
        """(selections, affixes_by_name) or (None, None) if not ERR / not ready yet."""
        build = self._char_col._build
        if not build or build.get("_game") != "err" or not self._enkindling_affixes_by_name:
            return None, None
        return self._equip_col.current_enkindle_selections(), self._enkindling_affixes_by_name

    def _recompute_all_enkindle_dependent(self):
        """Shared recompute entry point -- called after every Enkindle combo
        change AND once all eligible-affix restores finish on build load.
        Reuses the exact same calc_enkindle_modifiers() call for both the
        Character column's derived stats and the Summary column's AR, so
        they can never show two different numbers for the same build."""
        selections, affixes_by_name = self._current_enkindle_context()
        if selections is None:
            return
        mods = calc_enkindle_modifiers(selections, affixes_by_name)
        self._char_col._recompute_derived(enkindle_mods=mods)

        build = self._char_col._build
        game = build.get("_game", "elden_ring")
        refdata = self._refdata.get(game, {})
        self._summary_col.load(
            build, refdata, self._api, self._ar_variant_cache,
            enkindle_selections=selections, enkindle_affixes_by_name=affixes_by_name,
        )

    def _populate_list(self, builds):
        self._refresh_btn.setEnabled(True)
        self._refresh_btn.setText("Refresh")
        self._build_summaries = builds
        # Clear existing rows (keep the trailing stretch)
        while self._list_container_layout.count() > 1:
            item = self._list_container_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._all_row_widgets = []

        for b in builds:
            # QPushButton doesn't word-wrap its text (long build names just
            # clip/ellipsize at the button's fixed width) -- a clickable
            # QLabel-based row lets the name actually wrap to a 2nd line
            # instead of being cut off.
            name = b.get('name', 'Untitled')
            row = QWidget()
            row.setCursor(Qt.CursorShape.PointingHandCursor)
            row.setStyleSheet(f"""
                QWidget {{ background: {BG_SURFACE}; border: 1px solid {BORDER_SOLID}; border-radius: 6px; }}
                QWidget:hover {{ border-color: {ACCENT_GOLD}; }}
            """)
            row_layout = QVBoxLayout(row)
            row_layout.setContentsMargins(10, 8, 10, 8)
            row_layout.setSpacing(2)
            name_row = QHBoxLayout()
            name_lbl = QLabel(name)
            name_lbl.setWordWrap(True)
            name_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            name_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent; border: none;")
            name_row.addWidget(name_lbl, 1)
            is_local = b.get("is_local", local_builds_store.is_local_id(b.get("id")))
            badge_lbl = QLabel("LOCAL" if is_local else "CLOUD")
            badge_lbl.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
            badge_color = TEXT_MUTED if is_local else ACCENT_GOLD
            badge_lbl.setStyleSheet(f"color: {badge_color}; letter-spacing: 1px; background: transparent; border: none;")
            name_row.addWidget(badge_lbl)
            meta_lbl = QLabel(f"Lv {b.get('level', '?')} · {b.get('tag', 'pve')}")
            meta_lbl.setFont(QFont("Segoe UI", 9))
            meta_lbl.setStyleSheet(f"color: {TEXT_MUTED}; background: transparent; border: none;")
            row_layout.addLayout(name_row)
            row_layout.addWidget(meta_lbl)
            build_key = b.get("id") if is_local else (b.get("share_token") or b.get("id"))
            row.mousePressEvent = lambda _e, bid=build_key, loc=is_local: self._load_build(bid, is_local=loc)
            self._list_container_layout.insertWidget(self._list_container_layout.count() - 1, row)
            self._all_row_widgets.append((row, name.lower()))

    def _filter_list(self, query):
        q = query.lower()
        for btn, name in self._all_row_widgets:
            btn.setVisible(q in name)

    def _create_new_build(self, local: bool):
        """
        "+ Local Build" / "+ QuestLog Build" -- opens the same ClassPickerDialog
        used for "Change Class" so a fresh build starts from a real class's
        base stats (matching how a new character actually starts in-game)
        rather than an all-1s blank slate. Renders immediately in the editor
        with no server/disk round-trip yet -- nothing is persisted until the
        user's first Save Changes, same as any other edit in this column.
        """
        game = self._game_selector.currentData()
        self._ensure_refdata(game)
        refdata = self._refdata.get(game)
        if not refdata or not refdata.get("classes"):
            # Reference data isn't back yet -- stash the intent and retry
            # once _on_refdata_fetched delivers it, same pattern _show_build
            # already uses for a build arriving before refdata does.
            self._pending_new_build = (game, local)
            return
        self._open_class_picker_for_new_build(game, local, refdata)

    def _open_class_picker_for_new_build(self, game, local, refdata):
        classes = refdata.get("classes", [])
        picked_class = ClassPickerDialog.pick(classes, parent=self)
        if not picked_class:
            return
        stats = {s: picked_class.get(s, 10) for s in STAT_NAMES}
        weapons = {slot: None for slot in WEAPON_SLOTS}
        for slot in WEAPON_SLOTS:
            weapons[f"{slot}_aow"] = None
            weapons[f"{slot}_affinity"] = None
        detail = {
            "id": None,  # unsaved -- Save Changes assigns a real id (local uuid or server id)
            "name": "New Build",
            "description": "",
            "author": "",
            "class_id": picked_class.get("id"),
            "level": picked_class.get("level", 1),
            "tag": "pve",
            "is_public": False,
            "stats": stats,
            "weapons": weapons,
            "armor": {slot: None for slot in ARMOR_SLOTS},
            "talismans": [None, None, None, None],
            "spirit_ash_name": None,
            "spirit_ash_upgrade": 0,
            "tear_1_name": None,
            "tear_2_name": None,
            "scadutree_level": 0,
            "_game": game,
            "_is_local": local,
        }
        if game == "err":
            detail["curio_selections"] = {}
            detail["fortune_name"] = None
            detail["minor_fortune_name"] = None
            detail["rune_inventory"] = []
        self._render_build(detail)
        self._mark_dirty()  # a brand new build has nothing saved yet -- Save Changes should be enabled immediately

    def _load_build(self, build_id, is_local=None):
        if build_id is None:
            return
        game = self._game_selector.currentData()
        if is_local is None:
            is_local = local_builds_store.is_local_id(build_id)
        if is_local:
            # No thread/signal needed -- local disk read is fast and synchronous,
            # unlike the network round-trip the cloud path needs.
            detail = local_builds_store.load_local_build(build_id, game)
            if detail:
                detail["_game"] = game
                detail["_is_local"] = True
            self._show_build(detail or {})
            return
        if not self._api:
            return
        import threading
        def _fetch():
            detail = self._api.get_build_detail(build_id, game=game)
            if detail:
                detail["_game"] = game
                detail["_is_local"] = False
                if not detail.get("share_token") and _numeric_id(build_id) is None:
                    detail["share_token"] = build_id
            # Same cross-thread signal fix as refresh_list() above. dict
            # signal can't carry None, so normalize to {} -- _show_build's
            # `if not detail` check treats both the same way.
            self._build_loaded.emit(detail or {})
        threading.Thread(target=_fetch, daemon=True).start()

    def _show_build(self, detail):
        if not detail or detail.get("error"):
            self._empty_lbl.setText("Could not load this build.")
            self._empty_lbl.setVisible(True)
            self._viewer_scroll.setVisible(False)
            return

        game = detail.get("_game", "elden_ring")
        self._ensure_refdata(game)
        if game not in self._refdata:
            # Reference data (classes/stat-caps/derived-curves/ar-data)
            # isn't back yet -- stash the build and render once
            # _on_refdata_fetched delivers it, rather than showing partial
            # (blank HP/FP/AR) data that then silently updates a moment
            # later with no visual cue anything changed.
            self._pending_build = detail
            return
        self._render_build(detail)

    def _render_build(self, detail):
        game = detail.get("_game", "elden_ring")
        refdata = self._refdata.get(game, {})
        # Reset per-build Enkindling gating state BEFORE EquipmentColumn.load()
        # runs, since loading each slot immediately fires
        # enkindle_eligible_needed for any equipped weapon with a swappable
        # skill -- that handler adds to _eligible_pending_slots, so it must
        # start empty for this build's own pending set to be accurate.
        self._eligible_pending_slots = set()
        if game == "err":
            self._ensure_enkindling_data()
        self._char_col.load(detail, refdata)
        self._equip_col.load(detail, refdata)
        equipment = self._equip_col.current_equipment()
        detail["armor"] = equipment["armor"]
        detail["talismans"] = equipment["talismans"]
        detail["spirit_ash_name"] = equipment["spirit_ash_name"]
        detail["tear_1_name"] = equipment["tear_1_name"]
        detail["tear_2_name"] = equipment["tear_2_name"]
        self._char_col._recompute_derived(armor_override=equipment["armor"])
        self._summary_col.load(detail, refdata, self._api, self._ar_variant_cache)
        self._empty_lbl.setVisible(False)
        self._viewer_scroll.setVisible(True)
        self._save_bar.setVisible(True)
        self._is_dirty = False
        self._save_btn.setEnabled(False)
        self._dirty_lbl.setText("")

    def _mark_dirty(self):
        self._is_dirty = True
        self._save_btn.setEnabled(True)
        self._dirty_lbl.setText("Unsaved changes")

    def _on_class_changed(self, class_id):
        self._mark_dirty()

    def _on_weapon_changed(self):
        """
        A weapon/AoW/affinity/Enkindle edit changed -- re-render the AR panel
        (and, if ERR, re-derive HP/FP/Stamina/EquipLoad/Poise) against the
        live selection, not the originally-loaded build, and mark dirty.
        Rebuilds a throwaway build dict with the current weapon slots so
        SummaryColumn.load() computes AR off what's actually equipped now.
        """
        self._mark_dirty()
        build = self._char_col._build
        if not build:
            return
        game = build.get("_game", "elden_ring")
        refdata = self._refdata.get(game, {})
        live = dict(build)
        weapons = dict(build.get("weapons", {}))
        for slot, (weapon, aow_name, affinity) in self._equip_col.current_weapons().items():
            weapons[slot] = weapon
            weapons[f"{slot}_aow"] = aow_name
            weapons[f"{slot}_affinity"] = affinity
        live["weapons"] = weapons
        live["stats"] = self._char_col.current_stats()
        # Keep _char_col._build's "weapons" in sync -- _current_enkindle_context()
        # and _recompute_all_enkindle_dependent() both read live selections off
        # EquipmentColumn directly, but SummaryColumn.load() below needs the
        # up-to-date weapons dict passed explicitly since it takes `build` as
        # a plain argument, not a shared reference.
        self._char_col._build["weapons"] = weapons

        selections, affixes_by_name = self._current_enkindle_context()
        if selections is not None:
            mods = calc_enkindle_modifiers(selections, affixes_by_name)
            self._char_col._recompute_derived(enkindle_mods=mods)
            self._summary_col.load(
                live, refdata, self._api, self._ar_variant_cache,
                enkindle_selections=selections, enkindle_affixes_by_name=affixes_by_name,
            )
        else:
            self._summary_col.load(live, refdata, self._api, self._ar_variant_cache)

    def _on_equipment_changed(self):
        """
        An armor/talisman/spirit-ash/physick/curio/fortune/rune edit changed
        -- recompute HP/FP/Stamina/EquipLoad/Poise/RollType against the live
        selection and mark dirty. Fortune and Binding Runes both feed these
        calcs (per the Fortunes & Binding Runes spec), so unlike the older
        armor-only comment here, this must also refresh _char_col._build's
        fortune_name/rune_inventory in place before recomputing -- otherwise
        _recompute_derived() reads the ORIGINAL build's stale fortune/rune
        values (it reads them off self._build, not a passed-in override,
        since there was never a fortune/rune equivalent of armor_override).
        Talismans/spirit-ash/physick/curios still don't feed any of these
        calcs (curios per spec: pure selection state, no calculable math).
        """
        self._mark_dirty()
        build = self._char_col._build
        if not build:
            return
        if build.get("_game") == "err":
            build["fortune_name"] = self._equip_col._fortunes_tab._main_widget.current_value()
            build["minor_fortune_name"] = self._equip_col._fortunes_tab._minor_widget.current_value()
            build["rune_inventory"] = self._equip_col.current_rune_inventory()
        live_equipment = self._equip_col.current_equipment()
        build["armor"] = live_equipment["armor"]
        build["talismans"] = live_equipment["talismans"]
        build["spirit_ash_name"] = live_equipment["spirit_ash_name"]
        build["tear_1_name"] = live_equipment["tear_1_name"]
        build["tear_2_name"] = live_equipment["tear_2_name"]
        self._char_col._recompute_derived(armor_override=live_equipment["armor"])

        # Fortune/rune edits change effective stats, which AR depends on --
        # re-render the AR panel too, same as a stat/weapon/enkindle change
        # already does, so raising a fortune's flat stat bonus (etc.) moves
        # the AR number instead of only updating HP/FP/Stamina/EquipLoad.
        game = build.get("_game", "elden_ring")
        refdata = self._refdata.get(game, {})
        selections, affixes_by_name = self._current_enkindle_context()
        if selections is not None:
            enkindle_mods = calc_enkindle_modifiers(selections, affixes_by_name)
            self._summary_col.load(
                build, refdata, self._api, self._ar_variant_cache,
                enkindle_selections=selections, enkindle_affixes_by_name=affixes_by_name,
            )
        else:
            self._summary_col.load(build, refdata, self._api, self._ar_variant_cache)

    def _save_current_build(self):
        if not self._char_col._build:
            return
        build = self._char_col._build
        game = build.get("_game", "elden_ring")

        if build.get("_is_local"):
            self._save_local_build(build, game)
            return

        if not self._api:
            return
        stats = self._char_col.current_stats()

        refdata = self._refdata.get(game, {})
        classes = refdata.get("classes", [])
        class_obj = next((c for c in classes if c.get("id") == build.get("class_id")), None)
        class_base = {s: class_obj.get(s, 1) for s in stats} if class_obj else {s: 1 for s in stats}
        total_level = _saved_or_minimum_level(build, stats, class_base, class_obj, game)

        build_id = _numeric_id(build.get("id"))
        share_token = build.get("share_token") or (build.get("id") if build_id is None else None)
        payload = {
            "id": build_id,
            "share_token": share_token,
            "name": build.get("name", "Untitled Build"),
            "description": build.get("description", ""),
            "class_id": build.get("class_id"),
            "total_level": total_level,
            "playstyle_tag": build.get("tag", "pve"),
            "is_public": build.get("is_public", False),
            **stats,
        }
        for slot, (weapon, aow_name, affinity) in self._equip_col.current_weapons().items():
            payload[f"{slot}_weapon_id"] = weapon.get("id") if weapon else None
            payload[f"{slot}_aow_name"] = aow_name
            payload[f"{slot}_affinity"] = affinity
        for slot, sel in self._equip_col.current_enkindle_selections().items():
            payload[f"{slot}_enkindle_affix"] = sel["affix"] if sel else None
            payload[f"{slot}_enkindle_rarity"] = sel["rarity"] if sel else None
        log.info(
            "Saving build id=%r share_token=%r enkindling=%s",
            payload.get("id"),
            payload.get("share_token"),
            {
                slot: {
                    "affix": payload.get(f"{slot}_enkindle_affix"),
                    "rarity": payload.get(f"{slot}_enkindle_rarity"),
                }
                for slot in WEAPON_SLOTS
            },
        )

        equipment = self._equip_col.current_equipment()
        armor = equipment["armor"]
        payload["helm_id"] = (armor.get("helm") or {}).get("id")
        payload["chest_id"] = (armor.get("chest") or {}).get("id")
        payload["gauntlet_id"] = (armor.get("gauntlet") or {}).get("id")
        payload["leg_id"] = (armor.get("leg") or {}).get("id")
        talismans = equipment["talismans"]
        for i in range(4):
            t = talismans[i] if i < len(talismans) else None
            payload[f"talisman_{i + 1}_id"] = (t or {}).get("id")
        payload["spirit_ash_name"] = equipment["spirit_ash_name"]
        payload["spirit_ash_upgrade"] = build.get("spirit_ash_upgrade", 0)
        payload["tear_1_name"] = equipment["tear_1_name"]
        payload["tear_2_name"] = equipment["tear_2_name"]
        payload["scadutree_level"] = build.get("scadutree_level", 0)
        if game == "err":
            payload["curio_selections"] = self._equip_col.current_curio_selections()
            payload["fortune_name"] = self._equip_col._fortunes_tab._main_widget.current_value()
            payload["minor_fortune_name"] = self._equip_col._fortunes_tab._minor_widget.current_value()
            payload["rune_inventory"] = self._equip_col.current_rune_inventory()
        self._save_btn.setEnabled(False)
        self._dirty_lbl.setText("Saving...")

        import threading
        def _do_save():
            result = self._api.save_build(payload, game=game)
            self._save_result.emit(result or {})
        threading.Thread(target=_do_save, daemon=True).start()

    def _save_local_build(self, build, game):
        """
        Local builds are stored in the SAME shape as a cloud build-detail
        response (weapons/armor/talismans as nested dicts, not the cloud
        save endpoint's flat {slot}_weapon_id fields) -- local save/load
        never goes through the flat payload format at all, so there's no
        translation step needed when re-loading it later via
        local_builds.load_local_build() straight into _render_build().
        """
        stats = self._char_col.current_stats()
        weapons = {}
        for slot, (weapon, aow_name, affinity) in self._equip_col.current_weapons().items():
            weapons[slot] = weapon
            weapons[f"{slot}_aow"] = aow_name
            weapons[f"{slot}_affinity"] = affinity
        for slot, sel in self._equip_col.current_enkindle_selections().items():
            weapons[f"{slot}_enkindle_affix"] = sel["affix"] if sel else None
            weapons[f"{slot}_enkindle_rarity"] = sel["rarity"] if sel else None

        equipment = self._equip_col.current_equipment()
        refdata = self._refdata.get(game, {})
        classes = refdata.get("classes", [])
        class_obj = next((c for c in classes if c.get("id") == build.get("class_id")), None)
        class_base = {s: class_obj.get(s, 1) for s in stats} if class_obj else {s: 1 for s in stats}
        total_level = _saved_or_minimum_level(build, stats, class_base, class_obj, game)

        detail = {
            "id": build.get("id") or local_builds_store.new_local_id(),
            "name": build.get("name", "Untitled Build"),
            "description": build.get("description", ""),
            "author": build.get("author", ""),
            "class_id": build.get("class_id"),
            "level": total_level,
            "tag": build.get("tag", "pve"),
            "is_public": False,
            "stats": stats,
            "weapons": weapons,
            "armor": equipment["armor"],
            "talismans": equipment["talismans"],
            "spirit_ash_name": equipment["spirit_ash_name"],
            "spirit_ash_upgrade": build.get("spirit_ash_upgrade", 0),
            "tear_1_name": equipment["tear_1_name"],
            "tear_2_name": equipment["tear_2_name"],
            "scadutree_level": build.get("scadutree_level", 0),
        }
        if game == "err":
            detail["curio_selections"] = self._equip_col.current_curio_selections()
            detail["fortune_name"] = self._equip_col._fortunes_tab._main_widget.current_value()
            detail["minor_fortune_name"] = self._equip_col._fortunes_tab._minor_widget.current_value()
            detail["rune_inventory"] = self._equip_col.current_rune_inventory()

        self._save_btn.setEnabled(False)
        self._dirty_lbl.setText("Saving...")
        saved = local_builds_store.save_local_build(detail, game)
        saved["_game"] = game
        saved["_is_local"] = True
        self._char_col._build["id"] = saved["id"]
        self._is_dirty = False
        self._dirty_lbl.setText("Saved")
        self.refresh_list()

    def _on_save_result(self, result):
        if result.get("ok") or result.get("build_id") or result.get("id"):
            self._is_dirty = False
            self._dirty_lbl.setText("Saved")
            self._save_btn.setEnabled(False)
            new_id = result.get("build_id") or result.get("id")
            if new_id and self._char_col._build:
                self._char_col._build["id"] = new_id
            new_token = result.get("share_token")
            if new_token and self._char_col._build:
                self._char_col._build["share_token"] = new_token
            if self._char_col._build and not self._char_col._build.get("_is_local"):
                reload_key = (
                    result.get("build_id")
                    or result.get("id")
                    or self._char_col._build.get("id")
                    or self._char_col._build.get("share_token")
                )
                if reload_key:
                    self._load_build(reload_key, is_local=False)
            self.refresh_list()
        else:
            message = result.get("error") or result.get("detail") or "Save failed -- try again"
            self._dirty_lbl.setText(str(message)[:120])
            self._save_btn.setEnabled(True)
