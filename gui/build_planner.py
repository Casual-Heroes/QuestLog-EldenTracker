"""
Build Planner UI — full ER + ERR character builder.

Layout: left column (class + stats) | center (equipment slots) | right (AR panel + spells)
Picker: modal-style panel that slides in over center/right for item selection.
"""

import json
import os
import threading
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QLineEdit, QComboBox, QFrame, QSizePolicy,
    QStackedWidget, QSlider, QSpinBox, QGridLayout, QButtonGroup,
    QAbstractButton, QSplitter, QToolButton, QLayout, QWidgetItem,
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QTimer, QRect, QSize, QPoint, QEvent
from PyQt6.QtGui import QFont, QColor

from core.crash_logger import get_logger
from core.paths import data as _data_path

log = get_logger("questlog.builder")

# ── Palette (matches boss_tracker.py) ─────────────────────────────────────────
BG_BASE      = "#09090f"
BG_SURFACE   = "#0f1018"
BG_CARD      = "#13141f"
BG_CARD_HOV  = "#181926"
BORDER       = "rgba(255,255,255,0.06)"
BORDER_SOLID = "#2e3048"
ACCENT_GOLD  = "#c9a84c"
ACCENT_GOLD2 = "#e8c45a"
ACCENT_RED   = "#8B0000"
ACCENT_RED2  = "#c0390f"
GREEN_LIVE   = "#22c55e"
GREEN_DIM    = "#166534"
TEXT_PRIMARY = "#f1f0f5"
TEXT_MUTED   = "#6b7280"
TEXT_DIM     = "#8892a4"
PURPLE       = "#6c5ce7"

STAT_COLOR_UNDER = "#22c55e"   # under soft cap  — green
STAT_COLOR_SOFT1 = "#eab308"   # at soft cap 1   — yellow
STAT_COLOR_SOFT2 = "#f97316"   # at soft cap 2   — orange
STAT_COLOR_HARD  = "#ef4444"   # at hard cap      — red

STAT_KEYS = ["vigor", "mind", "endurance", "strength",
             "dexterity", "intelligence", "faith", "arcane"]
STAT_LABELS = {
    "vigor": "Vigor", "mind": "Mind", "endurance": "Endurance",
    "strength": "Strength", "dexterity": "Dexterity",
    "intelligence": "Intelligence", "faith": "Faith", "arcane": "Arcane",
}

WEAPON_SLOTS = ["rh1", "rh2", "rh3", "lh1", "lh2", "lh3"]
ARMOR_SLOTS  = ["helm", "chest", "gauntlet", "leg"]
TALI_SLOTS   = ["talisman1", "talisman2", "talisman3", "talisman4"]
SLOT_LABELS  = {
    "rh1": "R Hand 1", "rh2": "R Hand 2", "rh3": "R Hand 3",
    "lh1": "L Hand 1", "lh2": "L Hand 2", "lh3": "L Hand 3",
    "helm": "Helm", "chest": "Chest", "gauntlet": "Gauntlet", "leg": "Leg",
    "talisman1": "Talisman 1", "talisman2": "Talisman 2",
    "talisman3": "Talisman 3", "talisman4": "Talisman 4",
}

PLAYSTYLE_TAGS = ["pve", "pvp", "boss_rush", "challenge", "beginner"]

SAVES_DIR = _data_path("builds")

def _get_spell_schools_for_type(spells: list, spell_type: str) -> list[str]:
    """Derive sorted school list from live spell data for a given type."""
    return sorted({s["school"] for s in spells
                   if s.get("type") == spell_type and s.get("school")})


# ── Signal bridge for bg thread → Qt UI ───────────────────────────────────────
class _DataReady(QObject):
    ready = pyqtSignal(object)   # passes BuilderData


class _VariantReady(QObject):
    ready = pyqtSignal(str, list)   # weapon_name, variants


# ── BUILD state dict helpers ───────────────────────────────────────────────────
def _empty_build(game="elden_ring"):
    return {
        "game":         game,
        "name":         "Untitled Build",
        "description":  "",
        "class_id":     None,
        "class_name":   "",
        "playstyle_tag": "pve",
        "scadutree":    0,
        "stats":        {s: 10 for s in STAT_KEYS},
        "class_base":   {s: 1  for s in STAT_KEYS},
        "slots": {
            "rh1": None, "rh2": None, "rh3": None,
            "lh1": None, "lh2": None, "lh3": None,
            "helm": None, "chest": None, "gauntlet": None, "leg": None,
            "talisman1": None, "talisman2": None, "talisman3": None, "talisman4": None,
        },
        "aow":          {s: None for s in WEAPON_SLOTS},
        "affinities":   {s: "Standard" for s in WEAPON_SLOTS},
        "spells":       [],
        "spirit_ash":   None,
        "spirit_ash_upgrade": 0,
        "tears":        [None, None],
        "curioSelections": {},
        "runeInventory":   [],
    }


# ─────────────────────────────────────────────────────────────────────────────
# QSS
# ─────────────────────────────────────────────────────────────────────────────
QSS = f"""
* {{
    font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
    font-size: 13px;
    color: {TEXT_PRIMARY};
    background: {BG_BASE};
}}
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{
    background: {BG_BASE}; width: 5px; border: none; margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BORDER_SOLID}; border-radius: 2px; min-height: 40px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QLineEdit {{
    background: {BG_SURFACE}; border: 1px solid #3a3b52;
    border-radius: 7px; color: {TEXT_PRIMARY};
    padding: 8px 14px; font-size: 13px;
}}
QLineEdit:hover {{ border-color: #5a5b7a; }}
QLineEdit:focus {{ border-color: {ACCENT_GOLD}; }}
QComboBox {{
    background: {BG_SURFACE}; border: 1px solid {BORDER_SOLID};
    border-radius: 6px; color: {TEXT_PRIMARY};
    padding: 6px 32px 6px 12px; font-size: 12px; min-height: 32px;
}}
QComboBox:hover {{ border-color: #5a5b7a; }}
QComboBox:on {{ border-color: {ACCENT_GOLD}; }}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 24px; border: none; background: transparent;
}}
QComboBox::down-arrow {{
    width: 10px; height: 10px;
}}
QComboBox QAbstractItemView {{
    background: {BG_CARD}; border: 1px solid {BORDER_SOLID};
    color: {TEXT_PRIMARY}; padding: 4px;
    selection-background-color: rgba(201,168,76,0.15);
    selection-color: {ACCENT_GOLD};
    outline: none;
}}
QComboBox QAbstractItemView::item {{
    padding: 6px 12px; min-height: 28px;
}}
QComboBox QAbstractItemView::item:hover {{
    background: rgba(255,255,255,0.06);
}}
QPushButton {{
    background: transparent; border: 1px solid {BORDER_SOLID};
    border-radius: 7px; color: {TEXT_MUTED};
    padding: 7px 18px; font-size: 11px; font-weight: 600; letter-spacing: 1px;
    min-height: 32px;
}}
QPushButton:hover {{
    border-color: {ACCENT_GOLD}; color: {ACCENT_GOLD};
    background: rgba(201,168,76,0.06);
}}
QPushButton#primary {{
    background: rgba(201,168,76,0.12); border-color: {ACCENT_GOLD};
    color: {ACCENT_GOLD};
}}
QPushButton#primary:hover {{ background: rgba(201,168,76,0.22); }}
QPushButton#danger:hover {{
    border-color: {ACCENT_RED2}; color: {ACCENT_RED2};
    background: rgba(192,57,15,0.08);
}}
QPushButton#chip {{
    border-radius: 14px; font-size: 10px; padding: 4px 12px;
    letter-spacing: 0.5px; min-height: 26px;
}}
QPushButton#chip:checked {{
    background: rgba(201,168,76,0.18); border-color: {ACCENT_GOLD}; color: {ACCENT_GOLD};
}}
QSlider::groove:horizontal {{
    height: 4px; background: {BORDER_SOLID}; border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {ACCENT_GOLD}; border: none;
    width: 16px; height: 16px; margin: -6px 0; border-radius: 8px;
}}
QSlider::sub-page:horizontal {{ background: {ACCENT_GOLD}; border-radius: 2px; }}
"""


# ─────────────────────────────────────────────────────────────────────────────
# Small reusable widgets
# ─────────────────────────────────────────────────────────────────────────────

def _section_label(text):
    lbl = QLabel(text)
    lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
    lbl.setStyleSheet(f"color: {TEXT_MUTED}; letter-spacing: 2.5px; background: transparent; padding-top: 4px;")
    return lbl


def _card(radius=8):
    w = QWidget()
    w.setStyleSheet(f"background: {BG_CARD}; border: 1px solid {BORDER_SOLID}; border-radius: {radius}px;")
    return w


def _muted(text, size=11):
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: {size}px; background: transparent;")
    return lbl


class FlowLayout(QLayout):
    """Wraps child widgets left-to-right, breaking into new rows as needed."""

    def __init__(self, parent=None, h_spacing=5, v_spacing=5):
        super().__init__(parent)
        self._h_spacing = h_spacing
        self._v_spacing = v_spacing
        self._items: list = []

    def addWidget(self, widget):
        self.addItem(QWidgetItem(widget))

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), dry_run=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, dry_run=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        size += QSize(m.left() + m.right(), m.top() + m.bottom())
        return size

    def _do_layout(self, rect, dry_run):
        m = self.contentsMargins()
        x = rect.x() + m.left()
        y = rect.y() + m.top()
        right = rect.right() - m.right()
        row_height = 0

        for item in self._items:
            w = item.sizeHint().width()
            h = item.sizeHint().height()
            if x + w > right and x != rect.x() + m.left():
                x = rect.x() + m.left()
                y += row_height + self._v_spacing
                row_height = 0
            if not dry_run:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))
            x += w + self._h_spacing
            row_height = max(row_height, h)

        used_height = y + row_height - rect.y() + m.bottom()
        return used_height


class ChipButton(QPushButton):
    """Toggle button styled as a pill chip."""
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setObjectName("chip")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)


# ─────────────────────────────────────────────────────────────────────────────
# Stat row widget
# ─────────────────────────────────────────────────────────────────────────────
class StatRow(QWidget):
    value_changed = pyqtSignal(str, int)   # stat_key, new_value

    def __init__(self, key, parent=None):
        super().__init__(parent)
        self.key = key
        self._caps = {}
        self._rune_bonus = 0
        self.setFixedHeight(52)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 4, 0, 4)
        root.setSpacing(4)

        # Top row: label | − | value | +
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(8)

        self._label = QLabel(STAT_LABELS[key])
        self._label.setFixedWidth(96)
        self._label.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 13px; font-weight: 500; background: transparent;")

        btn_style = f"""
            QPushButton {{
                background: {BG_SURFACE}; border: 1px solid {BORDER_SOLID};
                border-radius: 5px; color: {TEXT_MUTED}; font-size: 15px;
                font-weight: 300; padding: 0; min-height: 0;
            }}
            QPushButton:hover {{ border-color: {ACCENT_GOLD}; color: {ACCENT_GOLD}; background: rgba(201,168,76,0.08); }}
        """
        self._minus = QPushButton("−")
        self._minus.setFixedSize(26, 26)
        self._minus.setStyleSheet(btn_style)

        self._spin = QSpinBox()
        self._spin.setRange(1, 99)
        self._spin.setValue(10)
        self._spin.setFixedSize(52, 26)
        self._spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self._spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._spin.setStyleSheet(f"""
            QSpinBox {{
                background: {BG_SURFACE}; border: 1px solid {BORDER_SOLID};
                border-radius: 5px; color: {TEXT_PRIMARY};
                font-size: 15px; font-weight: 700; padding: 0; min-height: 0;
            }}
        """)

        self._plus = QPushButton("+")
        self._plus.setFixedSize(26, 26)
        self._plus.setStyleSheet(btn_style)

        self._badge = QLabel("")
        self._badge.setStyleSheet(f"color: {TEXT_DIM}; font-size: 10px; background: transparent;")

        top.addWidget(self._label)
        top.addWidget(self._minus)
        top.addWidget(self._spin)
        top.addWidget(self._plus)
        top.addStretch()
        top.addWidget(self._badge)
        root.addLayout(top)

        # Bottom: progress bar
        self._bar_track = QWidget()
        self._bar_track.setFixedHeight(3)
        self._bar_track.setStyleSheet(f"background: {BORDER_SOLID}; border-radius: 1px;")
        self._bar_fill = QWidget(self._bar_track)
        self._bar_fill.setFixedHeight(3)
        self._bar_fill.move(0, 0)
        self._bar_fill.setStyleSheet(f"background: {STAT_COLOR_UNDER}; border-radius: 1px;")
        root.addWidget(self._bar_track)

        self._min_val = 1   # current enforced minimum (updated by set_value)

        self._minus.clicked.connect(self._decrement)
        self._plus.clicked.connect(self._increment)
        self._spin.valueChanged.connect(self._on_changed)
        self._spin.editingFinished.connect(self._on_editing_finished)

    def _decrement(self):
        new = max(self._min_val, self._spin.value() - 1)
        self._spin.setValue(new)

    def _increment(self):
        new = min(99, self._spin.value() + 1)
        self._spin.setValue(new)

    def _on_changed(self, val):
        self._refresh_bar()
        self.value_changed.emit(self.key, val)

    def _on_editing_finished(self):
        # Clamp typed value to [min_val, 99] when user leaves the field
        clamped = max(self._min_val, min(99, self._spin.value()))
        if clamped != self._spin.value():
            self._spin.blockSignals(True)
            self._spin.setValue(clamped)
            self._spin.blockSignals(False)
            self._refresh_bar()
            self.value_changed.emit(self.key, clamped)

    def set_min(self, min_val):
        self._min_val = max(1, min_val)
        self._spin.setMinimum(self._min_val)

    def set_value(self, val, min_val=1):
        self._min_val = max(1, min_val)
        self._spin.blockSignals(True)
        self._spin.setRange(self._min_val, 99)
        self._spin.setValue(max(self._min_val, min(99, val)))
        self._spin.blockSignals(False)
        self._refresh_bar()

    def get_value(self):
        return self._spin.value()

    def set_caps(self, caps):
        self._caps = caps or {}
        self._refresh_bar()

    def set_rune_bonus(self, bonus):
        self._rune_bonus = bonus
        self._refresh_bar()

    def _refresh_bar(self):
        base = self._spin.value()
        effective = min(99, base + self._rune_bonus)

        track_w = max(1, self._bar_track.width() or 160)
        fill_w = max(2, int(effective / 99 * track_w))
        self._bar_fill.setFixedWidth(fill_w)

        if not self._caps:
            self._badge.setText("")
            return

        s1 = self._caps.get("soft_cap_1") or 99
        s2 = self._caps.get("soft_cap_2") or 99
        s3 = self._caps.get("soft_cap_3")
        hc = self._caps.get("hard_cap", 99)

        if effective >= hc:
            color, badge = STAT_COLOR_HARD, "MAX"
        elif s3 and effective >= s2:
            rem = s3 - effective
            color = STAT_COLOR_SOFT2
            badge = f"Soft 2  {rem}→S3" if effective < s3 else "Soft 3"
        elif effective >= s1:
            rem = s2 - effective
            color = STAT_COLOR_SOFT1
            badge = f"Soft 1  {rem}→S2" if s3 else "Soft 1"
        else:
            rem = s1 - effective
            color, badge = STAT_COLOR_UNDER, f"{rem} to soft cap"

        self._bar_fill.setStyleSheet(f"background: {color}; border-radius: 1px;")
        self._badge.setStyleSheet(f"color: {color}; font-size: 10px; background: transparent;")
        self._badge.setText(badge)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refresh_bar()


# ─────────────────────────────────────────────────────────────────────────────
# Equipment slot button
# ─────────────────────────────────────────────────────────────────────────────
class SlotButton(QWidget):
    clicked = pyqtSignal(str)
    cleared = pyqtSignal(str)

    def __init__(self, slot_key, parent=None):
        super().__init__(parent)
        self.slot_key = slot_key
        self._item = None
        self._filled = False
        self.setFixedHeight(32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("SlotButton")
        self._update_style()

        root = QHBoxLayout(self)
        root.setContentsMargins(10, 0, 6, 0)
        root.setSpacing(8)

        # Slot label — fixed width, dim small caps
        self._slot_lbl = QLabel(SLOT_LABELS.get(slot_key, slot_key.upper()))
        self._slot_lbl.setFixedWidth(62)
        self._slot_lbl.setStyleSheet(
            f"color: {TEXT_DIM}; font-size: 9px; font-weight: 700; "
            f"letter-spacing: 1px; background: transparent;"
        )
        root.addWidget(self._slot_lbl)

        # Thin divider
        div = QWidget()
        div.setFixedSize(1, 14)
        div.setStyleSheet(f"background: {BORDER_SOLID};")
        root.addWidget(div)

        # Item name — grows to fill
        self._name_lbl = QLabel("Empty")
        self._name_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; background: transparent;")
        root.addWidget(self._name_lbl, 1)

        # Gold accent dot when filled
        self._dot = QLabel("●")
        self._dot.setFixedWidth(12)
        self._dot.setStyleSheet(f"color: transparent; font-size: 8px; background: transparent;")
        root.addWidget(self._dot)

        # Clear button
        self._clear_btn = QToolButton()
        self._clear_btn.setText("×")
        self._clear_btn.setFixedSize(16, 16)
        self._clear_btn.setStyleSheet(f"""
            QToolButton {{ background: transparent; border: none; color: {TEXT_DIM}; font-size: 12px; }}
            QToolButton:hover {{ color: {ACCENT_RED2}; }}
        """)
        self._clear_btn.setVisible(False)
        self._clear_btn.clicked.connect(lambda: self.cleared.emit(self.slot_key))
        root.addWidget(self._clear_btn)

    def _update_style(self):
        if self._filled:
            self.setStyleSheet(f"""
                QWidget#SlotButton {{ background: rgba(201,168,76,0.04); border: none; }}
                QWidget#SlotButton:hover {{ background: rgba(201,168,76,0.09); }}
            """)
        else:
            self.setStyleSheet(f"""
                QWidget#SlotButton {{ background: transparent; border: none; }}
                QWidget#SlotButton:hover {{ background: rgba(255,255,255,0.04); }}
            """)

    def set_item(self, item):
        self._item = item
        self._filled = bool(item)
        if item:
            name = item.get("name", "")
            self._name_lbl.setText(name)
            self._name_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 11px; font-weight: 600; background: transparent;")
            self._dot.setStyleSheet(f"color: {ACCENT_GOLD}; font-size: 8px; background: transparent;")
            self._clear_btn.setVisible(True)
        else:
            self._name_lbl.setText("Empty")
            self._name_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; background: transparent;")
            self._dot.setStyleSheet(f"color: transparent; font-size: 8px; background: transparent;")
            self._clear_btn.setVisible(False)
        self._update_style()

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        child = self.childAt(event.pos())
        if child is None or not isinstance(child, QToolButton):
            self.clicked.emit(self.slot_key)

    def mouseDoubleClickEvent(self, event):
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Ash of War sub-row (shown below each weapon SlotButton)
# ─────────────────────────────────────────────────────────────────────────────
class AoWRow(QWidget):
    """Compact AoW row shown beneath each weapon slot when a weapon is equipped."""
    pick_requested  = pyqtSignal(str)   # slot_key
    cleared         = pyqtSignal(str)   # slot_key

    def __init__(self, slot_key, parent=None):
        super().__init__(parent)
        self.slot_key = slot_key
        self._aow = None
        self.setFixedHeight(24)
        self.setVisible(False)   # hidden until weapon equipped
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("AoWRow")
        self.setStyleSheet(f"""
            QWidget#AoWRow {{ background: transparent; }}
            QWidget#AoWRow:hover {{ background: rgba(255,255,255,0.03); }}
        """)

        root = QHBoxLayout(self)
        root.setContentsMargins(10, 0, 6, 0)
        root.setSpacing(8)

        # Indent marker — matches slot label column width (62px) + div (1px) + spacing (8px)
        indent = QWidget()
        indent.setFixedWidth(71)
        indent.setStyleSheet("background: transparent;")
        root.addWidget(indent)

        self._aow_lbl = QLabel("No Ash of War")
        self._aow_lbl.setStyleSheet(
            f"color: {TEXT_DIM}; font-size: 9px; font-style: italic; background: transparent;"
        )
        root.addWidget(self._aow_lbl, 1)

        self._clear_btn = QToolButton()
        self._clear_btn.setText("×")
        self._clear_btn.setFixedSize(16, 16)
        self._clear_btn.setStyleSheet(f"""
            QToolButton {{ background: transparent; border: none; color: {TEXT_DIM}; font-size: 12px; }}
            QToolButton:hover {{ color: {ACCENT_RED2}; }}
        """)
        self._clear_btn.setVisible(False)
        self._clear_btn.clicked.connect(lambda: self.cleared.emit(self.slot_key))
        root.addWidget(self._clear_btn)

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        child = self.childAt(event.pos())
        if child is None or not isinstance(child, QToolButton):
            self.pick_requested.emit(self.slot_key)

    def set_weapon(self, weapon):
        """Show/hide row based on whether a weapon is equipped (and not locked skill)."""
        if weapon and not weapon.get("is_locked_skill", False):
            self.setVisible(True)
        else:
            self.setVisible(False)
            self._aow = None

    def set_aow(self, aow):
        self._aow = aow
        if aow:
            name = aow if isinstance(aow, str) else aow.get("name", "")
            self._aow_lbl.setText(name)
            self._aow_lbl.setStyleSheet(
                f"color: {ACCENT_GOLD}; font-size: 10px; font-style: normal; background: transparent;"
            )
            self._clear_btn.setVisible(True)
        else:
            self._aow_lbl.setText("No Ash of War")
            self._aow_lbl.setStyleSheet(
                f"color: {TEXT_DIM}; font-size: 10px; font-style: italic; background: transparent;"
            )
            self._clear_btn.setVisible(False)


# ─────────────────────────────────────────────────────────────────────────────
# Affinity sub-row (shown below AoWRow when a weapon with variants is equipped)
# ─────────────────────────────────────────────────────────────────────────────
class AffinityRow(QWidget):
    affinity_changed = pyqtSignal(str, str)   # slot_key, affinity_name

    def __init__(self, slot_key, parent=None):
        super().__init__(parent)
        self.slot_key = slot_key
        self.setFixedHeight(24)
        self.setVisible(False)

        root = QHBoxLayout(self)
        root.setContentsMargins(10, 0, 6, 0)
        root.setSpacing(8)

        indent = QWidget()
        indent.setFixedWidth(71)
        indent.setStyleSheet("background: transparent;")
        root.addWidget(indent)

        cap = QLabel("AFFINITY")
        cap.setStyleSheet(f"color: {TEXT_DIM}; font-size: 9px; font-weight: 700; letter-spacing: 1px; background: transparent;")
        cap.setFixedWidth(58)
        root.addWidget(cap)

        self._combo = QComboBox()
        self._combo.setStyleSheet(f"""
            QComboBox {{
                background: {BG_SURFACE}; border: 1px solid {BORDER_SOLID};
                border-radius: 4px; color: {ACCENT_GOLD}; font-size: 10px;
                font-weight: 600; padding: 0 6px; min-height: 0; max-height: 20px;
            }}
            QComboBox::drop-down {{ border: none; width: 16px; }}
            QComboBox QAbstractItemView {{
                background: {BG_SURFACE}; border: 1px solid {BORDER_SOLID};
                color: {TEXT_PRIMARY}; selection-background-color: rgba(201,168,76,0.2);
            }}
        """)
        self._combo.currentTextChanged.connect(
            lambda t: self.affinity_changed.emit(self.slot_key, t)
        )
        root.addWidget(self._combo, 1)

    def set_affinities(self, affinities: list, current: str):
        self._combo.blockSignals(True)
        self._combo.clear()
        if affinities:
            for a in affinities:
                self._combo.addItem(a)
            idx = self._combo.findText(current)
            self._combo.setCurrentIndex(idx if idx >= 0 else 0)
            self.setVisible(True)
        else:
            self.setVisible(False)
        self._combo.blockSignals(False)

    def set_current(self, affinity: str):
        self._combo.blockSignals(True)
        idx = self._combo.findText(affinity)
        if idx >= 0:
            self._combo.setCurrentIndex(idx)
        self._combo.blockSignals(False)

    def hide_row(self):
        self.setVisible(False)


# ─────────────────────────────────────────────────────────────────────────────
# Item picker panel (replaces right column when open)
# ─────────────────────────────────────────────────────────────────────────────


class PickerPanel(QWidget):
    item_picked       = pyqtSignal(str, object)
    closed            = pyqtSignal()
    category_switched = pyqtSignal(str)   # emits category key: "weapon","armor","talisman","spell","spirit_ash"
    nav_tab_changed   = pyqtSignal(int)   # emits nav tab index when user clicks a nav tab

    # Maps category key → (display label, default slot key)
    _CAT_TABS = [
        ("WEAPONS",    "weapon",    "rh1"),
        ("ARMOR",      "armor",     "helm"),
        ("TALISMANS",  "talisman",  "talisman1"),
        ("SPELLS",     "spell",     "spell"),
        ("SPIRIT ASH", "spirit_ash","spirit_ash"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {BG_BASE};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Permanent equipment-category bar ──────────────────────────────────
        # Use a scroll area so tabs never get clipped when pane is narrow
        cat_bar_scroll = QScrollArea()
        cat_bar_scroll.setFixedHeight(48)
        cat_bar_scroll.setWidgetResizable(True)
        cat_bar_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        cat_bar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        cat_bar_scroll.setStyleSheet(f"""
            QScrollArea {{ background: #12131e; border: none; border-bottom: 2px solid {ACCENT_GOLD}; }}
        """)
        cat_bar = QWidget()
        cat_bar.setStyleSheet(f"background: #12131e;")
        cat_layout = QHBoxLayout(cat_bar)
        cat_layout.setContentsMargins(8, 0, 8, 0)
        cat_layout.setSpacing(2)
        self._cat_btns: dict[str, QPushButton] = {}
        _cat_tab_style = f"""
            QPushButton {{
                background: transparent; border: none;
                border-bottom: 3px solid transparent;
                color: {TEXT_PRIMARY}; font-size: 11px; font-weight: 700;
                letter-spacing: 1px; padding: 0 12px; min-height: 46px; min-width: 60px;
            }}
            QPushButton:checked {{
                color: {ACCENT_GOLD}; border-bottom: 3px solid {ACCENT_GOLD};
                background: rgba(201,168,76,0.08);
            }}
            QPushButton:hover:!checked {{
                color: {ACCENT_GOLD}; background: rgba(201,168,76,0.04);
            }}
        """
        for label, cat_key, _ in self._CAT_TABS:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setStyleSheet(_cat_tab_style)
            btn.clicked.connect(lambda _, k=cat_key: self.category_switched.emit(k))
            cat_layout.addWidget(btn)
            self._cat_btns[cat_key] = btn
        cat_layout.addStretch()

        # close button pinned right
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(32, 32)
        close_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: 1px solid {BORDER_SOLID}; border-radius: 6px;
                          color: {TEXT_MUTED}; font-size: 14px; min-height: 0; padding: 0; }}
            QPushButton:hover {{ color: {ACCENT_GOLD}; border-color: {ACCENT_GOLD}; }}
        """)
        close_btn.clicked.connect(self.closed.emit)
        cat_layout.addWidget(close_btn)
        cat_bar_scroll.setWidget(cat_bar)
        root.addWidget(cat_bar_scroll)

        # ── Slot title line ───────────────────────────────────────────────────
        title_bar = QWidget()
        title_bar.setFixedHeight(36)
        title_bar.setStyleSheet(f"background: {BG_SURFACE}; border-bottom: 1px solid {BORDER_SOLID};")
        tb = QHBoxLayout(title_bar)
        tb.setContentsMargins(16, 0, 16, 0)
        self._title = QLabel("Select Item")
        self._title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self._title.setStyleSheet(f"color: {TEXT_MUTED}; background: transparent;")
        tb.addWidget(self._title)
        root.addWidget(title_bar)

        # ── Sub-category nav tabs (ALL/MELEE/RANGED etc) ─────────────────────
        self._nav_bar = QWidget()
        self._nav_bar.setFixedHeight(38)
        self._nav_bar.setStyleSheet(f"background: {BG_SURFACE}; border-bottom: 1px solid {BORDER_SOLID};")
        self._nav_layout = QHBoxLayout(self._nav_bar)
        self._nav_layout.setContentsMargins(12, 0, 12, 0)
        self._nav_layout.setSpacing(0)
        self._nav_tabs: list[QPushButton] = []
        root.addWidget(self._nav_bar)
        self._nav_bar.setVisible(False)

        # ── Body: left filter sidebar + right results ─────────────────────────
        body = QWidget()
        body.setStyleSheet(f"background: {BG_BASE};")
        body_row = QHBoxLayout(body)
        body_row.setContentsMargins(0, 0, 0, 0)
        body_row.setSpacing(0)
        root.addWidget(body, 1)

        # Left sidebar — filter list (shown only when filters exist)
        self._filter_sidebar = QWidget()
        self._filter_sidebar.setFixedWidth(160)
        self._filter_sidebar.setStyleSheet(
            f"background: {BG_SURFACE}; border-right: 1px solid {BORDER_SOLID};"
        )
        sidebar_v = QVBoxLayout(self._filter_sidebar)
        sidebar_v.setContentsMargins(0, 0, 0, 0)
        sidebar_v.setSpacing(0)

        filter_hdr = QWidget()
        filter_hdr.setFixedHeight(36)
        filter_hdr.setStyleSheet(f"background: {BG_CARD}; border-bottom: 1px solid {BORDER_SOLID};")
        fh = QHBoxLayout(filter_hdr)
        fh.setContentsMargins(12, 0, 12, 0)
        fh_lbl = QLabel("FILTER")
        fh_lbl.setStyleSheet(f"color: {TEXT_DIM}; font-size: 9px; font-weight: 700; letter-spacing: 2px; background: transparent;")
        fh.addWidget(fh_lbl)
        sidebar_v.addWidget(filter_hdr)

        filter_scroll = QScrollArea()
        filter_scroll.setWidgetResizable(True)
        filter_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        filter_scroll.setStyleSheet(f"QScrollArea {{ background: {BG_SURFACE}; border: none; }}")
        self._filter_list_widget = QWidget()
        self._filter_list_widget.setStyleSheet(f"background: {BG_SURFACE};")
        self._filter_list_layout = QVBoxLayout(self._filter_list_widget)
        self._filter_list_layout.setContentsMargins(0, 4, 0, 8)
        self._filter_list_layout.setSpacing(0)
        self._filter_list_layout.addStretch()
        filter_scroll.setWidget(self._filter_list_widget)
        sidebar_v.addWidget(filter_scroll, 1)
        body_row.addWidget(self._filter_sidebar)
        self._filter_sidebar.setVisible(False)

        # Right side: search + results
        right_col = QWidget()
        right_col.setStyleSheet(f"background: {BG_BASE};")
        right_v = QVBoxLayout(right_col)
        right_v.setContentsMargins(0, 0, 0, 0)
        right_v.setSpacing(0)

        search_wrap = QWidget()
        search_wrap.setFixedHeight(50)
        search_wrap.setStyleSheet(f"background: {BG_SURFACE}; border-bottom: 1px solid {BORDER_SOLID};")
        sw = QHBoxLayout(search_wrap)
        sw.setContentsMargins(14, 8, 14, 8)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search…")
        self._search.textChanged.connect(self._apply_filter)
        sw.addWidget(self._search)
        right_v.addWidget(search_wrap)

        results_scroll = QScrollArea()
        results_scroll.setWidgetResizable(True)
        results_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        results_scroll.setStyleSheet(f"background: {BG_BASE}; border: none;")
        self._results_widget = QWidget()
        self._results_widget.setStyleSheet(f"background: {BG_BASE};")
        self._results_layout = QVBoxLayout(self._results_widget)
        self._results_layout.setContentsMargins(10, 8, 10, 8)
        self._results_layout.setSpacing(2)
        self._results_layout.addStretch()
        results_scroll.setWidget(self._results_widget)
        right_v.addWidget(results_scroll, 1)
        body_row.addWidget(right_col, 1)

        self._slot_key      = ""
        self._category      = ""
        self._all_items     = []
        self._filters_def   = []
        self._active_chip   = -1
        self._filter_btns:  list[QPushButton] = []
        self._chip_widgets: list[QPushButton] = []
        self._picking       = False   # guard against double-click firing twice

    def open_for(self, slot_key, category, items, title="Select Item",
                 filters=None, nav_tabs=None, active_filter="", active_chip=0):
        """
        filters: list of (label, filter_fn) — shown as wrapping chips
        nav_tabs: list of (label, filter_fn) — shown as top tab buttons
        """
        self._slot_key      = slot_key
        self._category      = category
        self._all_items     = items
        self._active_chip   = -1
        self._picking       = False
        self._chip_slot_remap: dict[int, str] = {}   # chip idx → slot_key to re-open

        # Highlight the correct category tab
        for key, btn in self._cat_btns.items():
            btn.setChecked(key == category)
        self._title.setText(title)
        self._search.clear()

        # Nav tabs — clear all items including stretch spacers
        while self._nav_layout.count():
            it = self._nav_layout.takeAt(0)
            if it.widget():
                it.widget().hide()
                it.widget().setParent(None)
        self._nav_tabs = []
        if nav_tabs:
            for i, (label, fn) in enumerate(nav_tabs):
                btn = QPushButton(label)
                btn.setCheckable(True)
                btn.setChecked(i == 0)
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: transparent; border: none; border-bottom: 2px solid transparent;
                        color: {TEXT_MUTED}; font-size: 11px; font-weight: 700;
                        letter-spacing: 1.2px; padding: 0 16px; min-height: 38px;
                    }}
                    QPushButton:checked {{
                        color: {ACCENT_GOLD}; border-bottom: 2px solid {ACCENT_GOLD};
                    }}
                    QPushButton:hover:!checked {{ color: {TEXT_MUTED}; }}
                """)
                btn.clicked.connect(lambda _, idx=i: self._nav_clicked(idx))
                self._nav_layout.addWidget(btn)
                self._nav_tabs.append(btn)
            self._nav_layout.addStretch()
            self._nav_tabs_def = nav_tabs
            self._active_nav   = 0
            self._nav_bar.setVisible(True)
        else:
            self._nav_tabs_def = []
            self._active_nav   = -1
            self._nav_bar.setVisible(False)

        # Rebuild filter sidebar
        while self._filter_list_layout.count() > 1:
            it = self._filter_list_layout.takeAt(0)
            if it and it.widget():
                it.widget().hide()
                it.widget().setParent(None)
                it.widget().deleteLater()
        self._filter_btns = []
        self._chip_widgets = self._filter_btns   # alias

        if filters:
            _btn_style = f"""
                QPushButton {{
                    background: transparent; border: none; border-left: 3px solid transparent;
                    color: {TEXT_MUTED}; font-size: 11px; text-align: left;
                    padding: 8px 12px 8px 14px; min-height: 32px;
                }}
                QPushButton:hover {{ color: {TEXT_PRIMARY}; background: rgba(255,255,255,0.04); }}
                QPushButton:checked {{
                    color: {ACCENT_GOLD}; border-left: 3px solid {ACCENT_GOLD};
                    background: rgba(201,168,76,0.08); font-weight: 700;
                }}
            """
            for i, (label, fn) in enumerate(filters):
                btn = QPushButton(label)
                btn.setCheckable(True)
                btn.setChecked(i == active_chip)
                btn.setStyleSheet(_btn_style)
                btn.clicked.connect(lambda _, idx=i: self._chip_clicked(idx))
                self._filter_list_layout.insertWidget(
                    self._filter_list_layout.count() - 1, btn
                )
                self._filter_btns.append(btn)

            self._filters_def = filters
            self._active_chip = active_chip
            self._filter_sidebar.setVisible(True)
        else:
            self._filters_def = []
            self._filter_sidebar.setVisible(False)

        self._render()

    def _nav_clicked(self, idx):
        self._active_nav = idx
        for i, b in enumerate(self._nav_tabs):
            b.setChecked(i == idx)
        # Reset chip selection
        self._active_chip = 0
        for i, c in enumerate(self._chip_widgets):
            c.setChecked(i == 0)
        self.nav_tab_changed.emit(idx)
        self._apply_filter()

    def set_filters(self, filters):
        """Swap the sidebar filter list without re-opening the picker."""
        while self._filter_list_layout.count() > 1:
            it = self._filter_list_layout.takeAt(0)
            if it and it.widget():
                it.widget().hide()
                it.widget().setParent(None)
                it.widget().deleteLater()
        self._filter_btns = []
        self._chip_widgets = self._filter_btns
        self._active_chip = 0

        if filters:
            _btn_style = f"""
                QPushButton {{
                    background: transparent; border: none; border-left: 3px solid transparent;
                    color: {TEXT_MUTED}; font-size: 11px; text-align: left;
                    padding: 8px 12px 8px 14px; min-height: 32px;
                }}
                QPushButton:hover {{ color: {TEXT_PRIMARY}; background: rgba(255,255,255,0.04); }}
                QPushButton:checked {{
                    color: {ACCENT_GOLD}; border-left: 3px solid {ACCENT_GOLD};
                    background: rgba(201,168,76,0.08); font-weight: 700;
                }}
            """
            for i, (label, fn) in enumerate(filters):
                btn = QPushButton(label)
                btn.setCheckable(True)
                btn.setChecked(i == 0)
                btn.setStyleSheet(_btn_style)
                btn.clicked.connect(lambda _, idx=i: self._chip_clicked(idx))
                self._filter_list_layout.insertWidget(self._filter_list_layout.count() - 1, btn)
                self._filter_btns.append(btn)
            self._filters_def = filters
            self._filter_sidebar.setVisible(True)
        else:
            self._filters_def = []
            self._filter_sidebar.setVisible(False)

        self._apply_filter()

    def _chip_clicked(self, idx):
        self._active_chip = idx
        for i, c in enumerate(self._chip_widgets):
            c.setChecked(i == idx)
        # If this chip remaps to a different slot (e.g. armor type switch), re-open
        if idx in self._chip_slot_remap:
            new_slot = self._chip_slot_remap[idx]
            self._slot_key = new_slot
            self.category_switched.emit(new_slot)
            return
        self._apply_filter()

    def _apply_filter(self):
        query = self._search.text().lower()
        items = self._all_items

        # Nav tab filter (outer category)
        if self._nav_tabs_def and 0 <= self._active_nav < len(self._nav_tabs_def):
            _, fn = self._nav_tabs_def[self._active_nav]
            if fn is not None:
                items = [x for x in items if fn(x)]

        # Chip filter (sub-type)
        if self._filters_def and 0 <= self._active_chip < len(self._filters_def):
            _, fn = self._filters_def[self._active_chip]
            if fn is not None:
                items = [x for x in items if fn(x)]

        if query:
            items = [x for x in items if
                     query in x.get("name", "").lower() or
                     query in x.get("type", "").lower() or
                     query in x.get("effect", "").lower()]

        self._render(items)

    def _render(self, items=None):
        if items is None:
            items = self._all_items

        while self._results_layout.count() > 1:
            it = self._results_layout.takeAt(0)
            w = it.widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()

        for data in items[:400]:
            self._results_layout.insertWidget(
                self._results_layout.count() - 1, self._make_row(data))

    def _make_row(self, data):
        row = QWidget()
        row.setFixedHeight(50)
        row.setCursor(Qt.CursorShape.PointingHandCursor)
        row.setObjectName("PickerRow")
        row.setStyleSheet(f"""
            QWidget#PickerRow {{ background: {BG_CARD}; border-radius: 6px; border: 1px solid transparent; }}
            QWidget#PickerRow:hover {{ background: {BG_CARD_HOV}; border-color: #3a3b52; }}
        """)
        rl = QHBoxLayout(row)
        rl.setContentsMargins(14, 0, 14, 0)
        rl.setSpacing(10)

        name_col = QVBoxLayout()
        name_col.setSpacing(2)
        nl = QLabel(data.get("name", ""))
        nl.setFont(QFont("Segoe UI", 12))
        nl.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")
        sub_parts = []
        for key in ("type", "effect", "fp_cost"):
            v = data.get(key)
            if v and key == "fp_cost":
                sub_parts.append(f"FP {v}")
            elif v:
                sub_parts.append(str(v)[:45])
        sl = QLabel("  ·  ".join(sub_parts[:2]))
        sl.setStyleSheet(f"color: {TEXT_DIM}; font-size: 10px; background: transparent;")
        name_col.addWidget(nl)
        name_col.addWidget(sl)
        rl.addLayout(name_col, 1)

        right_parts = []
        if "weight" in data:
            right_parts.append(f"{data['weight']}w")
        if "slots" in data:
            right_parts.append(f"{data['slots']} slot{'s' if data['slots'] != 1 else ''}")

        if right_parts:
            rb = QLabel("  ".join(right_parts))
            rb.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; background: transparent;")
            rl.addWidget(rb)

        # Click handler via mouse event
        slot_key = self._slot_key
        cat      = self._category
        item_sig = self.item_picked

        def _press(event, _data=data, _slot=slot_key):
            if event.button() == Qt.MouseButton.LeftButton and not self._picking:
                self._picking = True
                item_sig.emit(_slot, _data)

        row.mousePressEvent = _press
        return row



# ─────────────────────────────────────────────────────────────────────────────
# AR display panel
# ─────────────────────────────────────────────────────────────────────────────
class ARPanel(QWidget):
    """Shows AR breakdown for the currently-selected weapon slot."""
    close_requested  = pyqtSignal()
    aow_pick_requested = pyqtSignal(str)   # emits slot_key

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet(f"background: {BG_BASE};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Top bar: WEAPON AR label + slot selector + close ─────────────────
        top_bar = QWidget()
        top_bar.setFixedHeight(48)
        top_bar.setStyleSheet(f"background: {BG_SURFACE}; border-bottom: 1px solid {BORDER_SOLID};")
        tb = QHBoxLayout(top_bar)
        tb.setContentsMargins(20, 0, 8, 0)
        tb.setSpacing(8)
        lbl_ar = QLabel("WEAPON AR")
        lbl_ar.setStyleSheet(f"color: {TEXT_DIM}; font-size: 10px; font-weight: 700; letter-spacing: 2px; background: transparent;")
        tb.addWidget(lbl_ar, 1)
        self._slot_combo = QComboBox()
        for s in WEAPON_SLOTS:
            self._slot_combo.addItem(SLOT_LABELS[s], s)
        self._slot_combo.setFixedWidth(110)
        tb.addWidget(self._slot_combo)
        close_btn = QToolButton()
        close_btn.setText("×")
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet(f"""
            QToolButton {{ background: transparent; border: none; color: {TEXT_DIM}; font-size: 16px; }}
            QToolButton:hover {{ color: {TEXT_PRIMARY}; }}
        """)
        close_btn.clicked.connect(self.close_requested.emit)
        tb.addWidget(close_btn)
        root.addWidget(top_bar)

        # ── Stacked: empty state / filled state ───────────────────────────────
        self._stack = QStackedWidget()
        root.addWidget(self._stack, 1)

        # Empty state page
        empty_page = QWidget()
        empty_page.setStyleSheet(f"background: {BG_BASE};")
        ep = QVBoxLayout(empty_page)
        ep.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_icon = QLabel("⚔")
        empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_icon.setStyleSheet(f"color: {BORDER_SOLID}; font-size: 48px; background: transparent;")
        empty_msg = QLabel("No weapon equipped")
        empty_msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_msg.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 13px; background: transparent;")
        empty_hint = QLabel("Select a weapon slot in the center panel")
        empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_hint.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px; background: transparent;")
        ep.addWidget(empty_icon)
        ep.addSpacing(8)
        ep.addWidget(empty_msg)
        ep.addSpacing(4)
        ep.addWidget(empty_hint)
        self._stack.addWidget(empty_page)   # index 0

        # Filled state page
        filled_page = QWidget()
        filled_page.setStyleSheet(f"background: {BG_BASE};")
        fp = QVBoxLayout(filled_page)
        fp.setContentsMargins(20, 20, 20, 20)
        fp.setSpacing(0)

        # Weapon name + affinity row
        name_row = QHBoxLayout()
        self._weapon_lbl = QLabel("")
        self._weapon_lbl.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        self._weapon_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")
        name_row.addWidget(self._weapon_lbl, 1)
        self._affinity_combo = QComboBox()
        self._affinity_combo.setFixedWidth(130)
        self._affinity_combo.setVisible(False)
        name_row.addWidget(self._affinity_combo)
        fp.addLayout(name_row)
        fp.addSpacing(8)

        # AoW row — clickable, shows current ash of war
        aow_row_w = QWidget()
        aow_row_w.setCursor(Qt.CursorShape.PointingHandCursor)
        aow_row_w.setObjectName("ARPanelAoW")
        aow_row_w.setStyleSheet(f"""
            QWidget#ARPanelAoW {{
                background: {BG_SURFACE}; border: 1px solid {BORDER_SOLID};
                border-radius: 6px;
            }}
            QWidget#ARPanelAoW:hover {{
                border-color: {ACCENT_GOLD}; background: rgba(201,168,76,0.06);
            }}
        """)
        aow_row_l = QHBoxLayout(aow_row_w)
        aow_row_l.setContentsMargins(12, 6, 12, 6)
        aow_row_l.setSpacing(8)
        aow_cap = QLabel("ASH OF WAR")
        aow_cap.setStyleSheet(f"color: {TEXT_DIM}; font-size: 9px; font-weight: 700; letter-spacing: 1.5px; background: transparent;")
        aow_row_l.addWidget(aow_cap)
        self._aow_lbl = QLabel("None")
        self._aow_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; background: transparent;")
        aow_row_l.addWidget(self._aow_lbl, 1)
        aow_change = QLabel("change")
        aow_change.setStyleSheet(f"color: {TEXT_DIM}; font-size: 9px; background: transparent;")
        aow_row_l.addWidget(aow_change)

        def _aow_clicked(event):
            if event.button() == Qt.MouseButton.LeftButton:
                slot = self._slot_combo.currentData() or "rh1"
                self.aow_pick_requested.emit(slot)
        aow_row_w.mousePressEvent = _aow_clicked

        fp.addWidget(aow_row_w)
        fp.addSpacing(12)

        # Total AR hero block
        ar_hero = QWidget()
        ar_hero.setStyleSheet(
            f"background: rgba(201,168,76,0.05); border: 1px solid rgba(201,168,76,0.18); border-radius: 10px;"
        )
        ar_hero_l = QHBoxLayout(ar_hero)
        ar_hero_l.setContentsMargins(20, 16, 20, 16)
        ar_col = QVBoxLayout()
        ar_col.setSpacing(3)
        ar_cap = QLabel("TOTAL AR")
        ar_cap.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 9px; font-weight: 700; letter-spacing: 2px; background: transparent;")
        self._ar_val = QLabel("—")
        self._ar_val.setFont(QFont("Segoe UI", 40, QFont.Weight.Bold))
        self._ar_val.setStyleSheet(f"color: {ACCENT_GOLD}; background: transparent;")
        ar_col.addWidget(ar_cap)
        ar_col.addWidget(self._ar_val)
        ar_hero_l.addLayout(ar_col)
        ar_hero_l.addStretch()
        fp.addWidget(ar_hero)
        fp.addSpacing(20)

        # Damage type breakdown table
        # Header
        hdr_row = QHBoxLayout()
        hdr_row.setContentsMargins(4, 0, 0, 0)
        for txt, w in [("TYPE", 130), ("BASE", 60), ("SCALING", 70), ("TOTAL", 0)]:
            h = QLabel(txt)
            h.setStyleSheet(f"color: {TEXT_DIM}; font-size: 9px; font-weight: 700; letter-spacing: 1.5px; background: transparent;")
            if w:
                h.setFixedWidth(w)
            else:
                h.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            hdr_row.addWidget(h, 0 if w else 1)
        fp.addLayout(hdr_row)
        fp.addSpacing(6)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {BORDER_SOLID};")
        fp.addWidget(sep)

        self._dmg_rows = {}
        DMG_LABELS = ["Physical", "Magic", "Fire", "Lightning", "Holy"]
        DMG_ICONS  = ["⚔", "✦", "🔥", "⚡", "✝"]
        DMG_COLORS = [TEXT_PRIMARY, "#60a5fa", "#f97316", "#facc15", "#a78bfa"]
        for i, (name, icon, clr) in enumerate(zip(DMG_LABELS, DMG_ICONS, DMG_COLORS)):
            row_w = QWidget()
            row_w.setFixedHeight(40)
            row_w.setStyleSheet(
                f"QWidget {{ background: transparent; border-bottom: 1px solid rgba(255,255,255,0.04); }}"
            )
            row = QHBoxLayout(row_w)
            row.setContentsMargins(4, 0, 0, 0)
            row.setSpacing(0)

            # Left color bar
            bar = QWidget()
            bar.setFixedWidth(3)
            bar.setFixedHeight(22)
            bar.setStyleSheet(f"background: {clr}; border-radius: 2px;")
            row.addWidget(bar)
            row.addSpacing(10)

            type_lbl = QLabel(name)
            type_lbl.setFixedWidth(117)
            type_lbl.setStyleSheet(f"color: {clr}; font-size: 12px; background: transparent;")
            row.addWidget(type_lbl)

            base_lbl = QLabel("—")
            base_lbl.setFixedWidth(60)
            base_lbl.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px; background: transparent;")
            row.addWidget(base_lbl)

            scaling_lbl = QLabel("")
            scaling_lbl.setFixedWidth(70)
            scaling_lbl.setStyleSheet(f"color: {ACCENT_GOLD}; font-size: 11px; background: transparent;")
            row.addWidget(scaling_lbl)

            tot_lbl = QLabel("—")
            tot_lbl.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
            tot_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")
            tot_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row.addWidget(tot_lbl, 1)

            fp.addWidget(row_w)
            self._dmg_rows[i] = (row_w, type_lbl, base_lbl, scaling_lbl, tot_lbl)

        fp.addSpacing(12)
        self._reqs_lbl = QLabel("")
        self._reqs_lbl.setStyleSheet(f"color: {ACCENT_RED2}; font-size: 11px; background: transparent;")
        self._reqs_lbl.setWordWrap(True)
        fp.addWidget(self._reqs_lbl)
        fp.addStretch(1)

        self._stack.addWidget(filled_page)  # index 1
        self._stack.setCurrentIndex(0)

    def clear(self):
        self._stack.setCurrentIndex(0)
        self._affinity_combo.setVisible(False)
        self._aow_lbl.setText("None")
        self._aow_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; background: transparent;")
        self._ar_val.setText("—")
        self._reqs_lbl.setText("")
        for i, (rw, tl, bl, sl, tot) in self._dmg_rows.items():
            bl.setText("—")
            sl.setText("")
            tot.setText("—")
            rw.setVisible(True)

    def set_aow(self, aow_name):
        if aow_name:
            self._aow_lbl.setText(aow_name)
            self._aow_lbl.setStyleSheet(f"color: {ACCENT_GOLD}; font-size: 11px; background: transparent;")
        else:
            self._aow_lbl.setText("None")
            self._aow_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; background: transparent;")

    def show_ar(self, weapon, ar_result, affinity="Standard", affinities=None):
        self._weapon_lbl.setText(weapon.get("name", ""))
        self._stack.setCurrentIndex(1)

        if affinities:
            self._affinity_combo.blockSignals(True)
            self._affinity_combo.clear()
            for a in affinities:
                self._affinity_combo.addItem(a)
            idx = self._affinity_combo.findText(affinity)
            if idx >= 0:
                self._affinity_combo.setCurrentIndex(idx)
            self._affinity_combo.blockSignals(False)
            self._affinity_combo.setVisible(True)
        else:
            self._affinity_combo.setVisible(False)

        if not ar_result:
            self._ar_val.setText("—")
            for i in range(5):
                rw, tl, bl, sl, tot = self._dmg_rows[i]
                rw.setVisible(False)
            return

        total = ar_result.get("total", 0)
        self._ar_val.setText(str(total))
        breakdown = ar_result.get("breakdown", {})

        for i in range(5):
            rw, tl, bl, sl, tot = self._dmg_rows[i]
            d = breakdown.get(i)
            if d:
                bl.setText(str(d["base"]))
                sl.setText(f"+{d['scaling']}" if d.get("scaling") else "")
                tot.setText(str(d["total"]))
                rw.setVisible(True)
            else:
                rw.setVisible(False)

        ineff = ar_result.get("ineffective", [])
        if ineff:
            stat_names = {"str": "STR", "dex": "DEX", "int": "INT", "fai": "FAI", "arc": "ARC"}
            self._reqs_lbl.setText("Reqs not met: " + ", ".join(stat_names.get(k, k) for k in ineff))
        else:
            self._reqs_lbl.setText("")


# ─────────────────────────────────────────────────────────────────────────────
# Saved builds list sidebar
# ─────────────────────────────────────────────────────────────────────────────
class BuildListPanel(QWidget):
    load_requested   = pyqtSignal(dict)
    delete_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(220)
        self.setStyleSheet(f"background: {BG_SURFACE}; border-right: 1px solid {BORDER_SOLID};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        hdr = QWidget()
        hdr.setFixedHeight(44)
        hdr.setStyleSheet(f"background: {BG_CARD}; border-bottom: 1px solid {BORDER_SOLID};")
        hh = QHBoxLayout(hdr)
        hh.setContentsMargins(12, 0, 8, 0)
        lbl = QLabel("SAVED BUILDS")
        lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color: {TEXT_MUTED}; letter-spacing: 2px; background: transparent;")
        hh.addWidget(lbl, 1)
        root.addWidget(hdr)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list_widget = QWidget()
        self._list_widget.setStyleSheet(f"background: {BG_SURFACE};")
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(8, 8, 8, 8)
        self._list_layout.setSpacing(4)
        self._list_layout.addStretch()
        scroll.setWidget(self._list_widget)
        root.addWidget(scroll, 1)

        self.refresh()

    def refresh(self):
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        builds = _list_saved_builds()
        if not builds:
            ph = _muted("No saved builds yet.\nCreate one and save it.", 11)
            ph.setWordWrap(True)
            ph.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px; background: transparent; padding: 12px;")
            self._list_layout.insertWidget(0, ph)
            return

        for b in builds:
            card = self._make_card(b)
            self._list_layout.insertWidget(self._list_layout.count() - 1, card)

    def _make_card(self, build):
        card = QWidget()
        card.setFixedHeight(56)
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.setStyleSheet(f"""
            QWidget {{ background: {BG_CARD}; border: 1px solid {BORDER_SOLID}; border-radius: 7px; }}
            QWidget:hover {{ border-color: rgba(201,168,76,0.4); }}
        """)
        cl = QHBoxLayout(card)
        cl.setContentsMargins(10, 0, 6, 0)
        cl.setSpacing(6)

        col = QVBoxLayout()
        col.setSpacing(1)
        name_lbl = QLabel(build.get("name", "Build"))
        name_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 11px; font-weight: 600; background: transparent;")
        game = build.get("game", "elden_ring").replace("_", " ").title()
        lvl  = build.get("level", "?")
        sub  = _muted(f"{game}  ·  Lv {lvl}", 9)
        col.addWidget(name_lbl)
        col.addWidget(sub)
        cl.addLayout(col, 1)

        del_btn = QToolButton()
        del_btn.setText("×")
        del_btn.setFixedSize(18, 18)
        del_btn.setStyleSheet(f"QToolButton {{ background: transparent; border: none; color: {TEXT_DIM}; }} QToolButton:hover {{ color: {ACCENT_RED2}; }}")

        build_name = build.get("name", "")
        del_btn.clicked.connect(lambda: self.delete_requested.emit(build_name))
        cl.addWidget(del_btn)

        card.mousePressEvent = lambda e, b=build: self.load_requested.emit(b) if e.button() == Qt.MouseButton.LeftButton else None
        return card


# ─────────────────────────────────────────────────────────────────────────────
# Local save / load
# ─────────────────────────────────────────────────────────────────────────────
def _list_saved_builds():
    if not os.path.isdir(SAVES_DIR):
        return []
    builds = []
    for fn in os.listdir(SAVES_DIR):
        if fn.endswith(".json"):
            try:
                with open(os.path.join(SAVES_DIR, fn)) as f:
                    builds.append(json.load(f))
            except Exception:
                pass
    builds.sort(key=lambda b: b.get("saved_at", 0), reverse=True)
    return builds


def _save_build_local(build: dict):
    import time, re
    os.makedirs(SAVES_DIR, exist_ok=True)
    name = build.get("name", "build")
    safe = re.sub(r"[^\w\s-]", "", name).strip().replace(" ", "_")[:40]
    path = os.path.join(SAVES_DIR, f"{safe}.json")
    build["saved_at"] = time.time()
    with open(path, "w") as f:
        json.dump(build, f, indent=2)


def _delete_build_local(name: str):
    import re
    safe = re.sub(r"[^\w\s-]", "", name).strip().replace(" ", "_")[:40]
    path = os.path.join(SAVES_DIR, f"{safe}.json")
    if os.path.isfile(path):
        os.remove(path)


def _update_build_cloud_id(name: str, cloud_id: int):
    """Persist cloud_id into the local save file after a successful cloud upsert."""
    import re
    safe = re.sub(r"[^\w\s-]", "", name).strip().replace(" ", "_")[:40]
    path = os.path.join(SAVES_DIR, f"{safe}.json")
    if not os.path.isfile(path):
        return
    try:
        with open(path) as f:
            build = json.load(f)
        build["cloud_id"] = cloud_id
        with open(path, "w") as f:
            json.dump(build, f, indent=2)
    except Exception as e:
        log.warning("_update_build_cloud_id failed: %s", e)


# ─────────────────────────────────────────────────────────────────────────────
# Class optimizer widget
# ─────────────────────────────────────────────────────────────────────────────
class OptimizerWidget(QWidget):
    class_picked = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {BG_CARD}; border: 1px solid {BORDER_SOLID}; border-radius: 8px;")
        self._classes = []
        self._debounce = QTimer()
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(250)
        self._debounce.timeout.connect(self._run)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)

        root.addWidget(_section_label("CLASS OPTIMIZER"))

        hint = QLabel("Set target stats — results update live")
        hint.setStyleSheet(f"color: {TEXT_DIM}; font-size: 10px; background: transparent;")
        root.addWidget(hint)

        inputs_grid = QGridLayout()
        inputs_grid.setSpacing(6)
        inputs_grid.setColumnStretch(0, 1)
        inputs_grid.setColumnStretch(2, 1)
        self._inputs = {}
        for i, key in enumerate(STAT_KEYS):
            lbl = QLabel(STAT_LABELS[key][:3].upper())
            lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; font-weight: 700; letter-spacing: 1px; background: transparent;")
            sp  = QSpinBox()
            sp.setRange(0, 99)
            sp.setValue(0)
            sp.setFixedWidth(52)
            sp.setFixedHeight(28)
            sp.setToolTip(f"Target {STAT_LABELS[key]} (0 = don't care)")
            sp.setStyleSheet(f"""
                QSpinBox {{
                    background: {BG_SURFACE}; border: 1px solid #3a3b52;
                    border-radius: 5px; color: {TEXT_PRIMARY}; font-size: 12px;
                    font-weight: 600; padding: 0 4px;
                }}
                QSpinBox:focus {{ border-color: {ACCENT_GOLD}; }}
            """)
            sp.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
            sp.valueChanged.connect(self._debounce.start)
            r, col = divmod(i, 2)
            inputs_grid.addWidget(lbl, r, col * 2,     Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            inputs_grid.addWidget(sp,  r, col * 2 + 1, Qt.AlignmentFlag.AlignLeft)
            self._inputs[key] = sp
        root.addLayout(inputs_grid)

        # Results — shown inline, no fixed-height scroll
        self._result_widget = QWidget()
        self._result_widget.setStyleSheet(f"background: transparent;")
        self._result_layout = QVBoxLayout(self._result_widget)
        self._result_layout.setContentsMargins(0, 4, 0, 0)
        self._result_layout.setSpacing(2)
        root.addWidget(self._result_widget)

    def set_classes(self, classes):
        self._classes = classes
        self._run()

    def _run(self):
        from core.derived_stats import find_optimal_class
        targets = {k: self._inputs[k].value() for k in STAT_KEYS}

        while self._result_layout.count() > 0:
            item = self._result_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._classes or not any(v > 0 for v in targets.values()):
            placeholder = QLabel("Set a stat target above to rank classes")
            placeholder.setStyleSheet(f"color: {TEXT_DIM}; font-size: 10px; background: transparent; padding: 4px 0;")
            self._result_layout.addWidget(placeholder)
            return

        results = find_optimal_class(self._classes, targets)
        for r in results:
            cls  = r["class"]
            lvl  = r["level"]
            diff = r["diff"]
            is_best = diff == 0

            row = QWidget()
            row.setCursor(Qt.CursorShape.PointingHandCursor)
            row.setStyleSheet(f"""
                QWidget {{
                    background: {"rgba(201,168,76,0.08)" if is_best else "transparent"};
                    border-radius: 5px;
                    border: {"1px solid rgba(201,168,76,0.3)" if is_best else "1px solid transparent"};
                }}
                QWidget:hover {{ background: rgba(201,168,76,0.12); border-color: rgba(201,168,76,0.4); }}
            """)
            rl = QHBoxLayout(row)
            rl.setContentsMargins(8, 5, 8, 5)
            rl.setSpacing(8)

            name_lbl = QLabel(cls.get("name", ""))
            name_lbl.setStyleSheet(f"color: {TEXT_PRIMARY if is_best else TEXT_MUTED}; font-size: 12px; font-weight: {'700' if is_best else '400'}; background: transparent; border: none;")

            lvl_lbl = QLabel(f"Lv {lvl}")
            lvl_lbl.setStyleSheet(f"color: {ACCENT_GOLD if is_best else TEXT_DIM}; font-size: 11px; background: transparent; border: none;")

            badge_lbl = QLabel("✓ OPTIMAL" if is_best else f"+{diff}")
            badge_lbl.setStyleSheet(f"color: {ACCENT_GOLD if is_best else TEXT_DIM}; font-size: 10px; font-weight: 700; background: transparent; border: none;")

            rl.addWidget(name_lbl, 1)
            rl.addWidget(lvl_lbl)
            rl.addWidget(badge_lbl)
            row.mousePressEvent = lambda e, c=cls: self.class_picked.emit(c) if e.button() == Qt.MouseButton.LeftButton else None
            self._result_layout.addWidget(row)


# ─────────────────────────────────────────────────────────────────────────────
# ERR Curio panel
# ─────────────────────────────────────────────────────────────────────────────
class CurioPanel(QWidget):
    selection_changed = pyqtSignal(dict)   # emits full curioSelections dict

    def __init__(self, parent=None):
        super().__init__(parent)
        self._curios = []
        self._selections = {}
        self.setStyleSheet("background: transparent;")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._inner = QWidget()
        self._inner.setStyleSheet("background: transparent;")
        self._inner_layout = QVBoxLayout(self._inner)
        self._inner_layout.setContentsMargins(0, 0, 0, 0)
        self._inner_layout.setSpacing(4)
        self._scroll.setWidget(self._inner)
        root.addWidget(self._scroll, 1)

    def set_curios(self, curios):
        self._curios = curios
        for name in [c["name"] for c in curios]:
            if name not in self._selections:
                self._selections[name] = {"active": False, "effectIndex": 0, "collapsed": True}
        self._rebuild()

    def get_selections(self):
        return dict(self._selections)

    def _rebuild(self):
        while self._inner_layout.count():
            item = self._inner_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for curio in self._curios:
            name   = curio["name"]
            sel    = self._selections.get(name, {"active": False, "effectIndex": 0, "collapsed": True})
            active = sel["active"]

            card = QWidget()
            card.setStyleSheet(f"""
                QWidget {{
                    background: {'rgba(201,168,76,0.06)' if active else BG_SURFACE};
                    border: 1px solid {ACCENT_GOLD if active else BORDER_SOLID};
                    border-radius: 6px;
                }}
            """)
            cl = QVBoxLayout(card)
            cl.setContentsMargins(10, 8, 10, 8)
            cl.setSpacing(4)

            top = QHBoxLayout()
            name_lbl = QLabel(name)
            name_lbl.setStyleSheet(f"color: {ACCENT_GOLD if active else TEXT_PRIMARY}; font-size: 12px; font-weight: 600; background: transparent;")
            toggle_btn = QPushButton("UNSEALED" if active else "SEALED")
            toggle_btn.setFixedHeight(22)
            toggle_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {'rgba(201,168,76,0.15)' if active else 'transparent'};
                    border: 1px solid {ACCENT_GOLD if active else BORDER_SOLID};
                    border-radius: 4px; color: {ACCENT_GOLD if active else TEXT_DIM};
                    font-size: 9px; font-weight: 700; padding: 0 8px; letter-spacing: 1px;
                }}
            """)
            toggle_btn.clicked.connect(lambda _, n=name: self._toggle(n))
            top.addWidget(name_lbl, 1)
            top.addWidget(toggle_btn)
            cl.addLayout(top)

            trigger = curio.get("trigger", "")
            if trigger:
                trig_lbl = _muted(f"Trigger: {trigger}", 10)
                trig_lbl.setWordWrap(True)
                cl.addWidget(trig_lbl)

            if active:
                effects = curio.get("effects", [])
                for idx, eff in enumerate(effects[:3]):
                    eff_btn = QPushButton(str(eff))
                    eff_btn.setCheckable(True)
                    eff_btn.setChecked(sel["effectIndex"] == idx)
                    eff_btn.setStyleSheet(f"""
                        QPushButton {{
                            background: transparent; border: 1px solid {BORDER_SOLID};
                            border-radius: 4px; color: {TEXT_MUTED};
                            font-size: 10px; padding: 3px 8px; text-align: left;
                        }}
                        QPushButton:checked {{
                            background: rgba(201,168,76,0.12); border-color: {ACCENT_GOLD}; color: {ACCENT_GOLD};
                        }}
                    """)
                    eff_btn.clicked.connect(lambda _, n=name, i=idx: self._pick_effect(n, i))
                    cl.addWidget(eff_btn)

            self._inner_layout.addWidget(card)

        self._inner_layout.addStretch()

    def _toggle(self, name):
        active = self._selections[name]["active"]
        if not active:
            # Seal all others
            for n in self._selections:
                self._selections[n]["active"] = False
        self._selections[name]["active"] = not active
        self._rebuild()
        self.selection_changed.emit(dict(self._selections))

    def _pick_effect(self, name, idx):
        for n in self._selections:
            self._selections[n]["active"] = False
        self._selections[name]["active"] = True
        self._selections[name]["effectIndex"] = idx
        self._rebuild()
        self.selection_changed.emit(dict(self._selections))


# ─────────────────────────────────────────────────────────────────────────────
# Main Build Planner Widget
# ─────────────────────────────────────────────────────────────────────────────
class BuildPlannerWidget(QWidget):
    """
    Top-level build planner widget. Embed in a tab or window.

    Signals:
        start_run_requested(dict) — emits build dict so caller can pre-fill NewRunPanel
    """
    start_run_requested = pyqtSignal(dict)

    def __init__(self, api_key=None, parent=None):
        super().__init__(parent)
        self._api_key    = api_key
        self._data              = None    # BuilderData, loaded async
        self._build             = _empty_build("elden_ring")
        self._loading           = False
        self._picker_open       = False
        self._pending_cloud_builds: list = []   # re-applied after each game's data loads
        self._synced_cloud_ids: set     = set() # cloud IDs already upserted this session
        self._pending_build_load: bool  = False  # True when a game switch is in flight

        self.setStyleSheet(QSS)
        self._data_bridge    = _DataReady()
        self._variant_bridge = _VariantReady()
        self._data_bridge.ready.connect(self._on_data_ready)
        self._variant_bridge.ready.connect(self._on_variants_ready)

        self._variant_cache: dict[str, list] = {}
        self._spell_sorc_chips: list = []
        self._spell_inca_chips: list = []

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Main area (stacked: loading screen | planner) ─────────────────────
        self._stack = QStackedWidget()
        root.addWidget(self._stack, 1)

        # Loading screen
        self._loading_page = QWidget()
        ll = QVBoxLayout(self._loading_page)
        ll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._loading_lbl = QLabel("Loading game data…")
        self._loading_lbl.setFont(QFont("Segoe UI", 14))
        self._loading_lbl.setStyleSheet(f"color: {TEXT_MUTED}; background: transparent;")
        self._loading_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ll.addWidget(self._loading_lbl)
        self._stack.addWidget(self._loading_page)

        # Planner page
        self._planner_page = QWidget()
        self._planner_page.setStyleSheet(f"background: {BG_BASE};")
        self._build_planner_layout(self._planner_page)
        self._stack.addWidget(self._planner_page)

        self._stack.setCurrentIndex(0)

        # Start loading
        self._load_data("elden_ring")

    # ── Data loading ───────────────────────────────────────────────────────────

    def _load_data(self, game):
        self._stack.setCurrentIndex(0)
        self._loading_lbl.setText(f"Loading {game.replace('_', ' ').title()} data…")
        self._data = None

        from core.builder_data import load_builder_data_async

        def _on_progress(step, pct):
            self._loading_lbl.setText(f"Loading… {step} ({pct}%)")

        def _on_done(data):
            self._data_bridge.ready.emit(data)

        def _on_error(msg):
            self._loading_lbl.setText(f"Load failed: {msg}\n(cached data may be used)")
            self._data_bridge.ready.emit(None)

        load_builder_data_async(
            game,
            api_key=self._api_key,
            on_progress=_on_progress,
            on_done=_on_done,
            on_error=_on_error,
        )

    def _on_data_ready(self, data):
        self._data = data
        if data:
            self._populate_class_picker()
            self._populate_optimizer()
            if data.game == "err":
                self._curio_panel.set_curios(data.curios)
                self._curios_tab_btn.setVisible(True)
            else:
                self._curios_tab_btn.setVisible(False)
                # Switch away from CURIOS tab if it was active
                if self._current_center_tab == 6:
                    self._switch_center_tab(0)
            # Apply stat caps to stat rows
            for key, row in self._stat_rows.items():
                row.set_caps(data.stat_caps.get(key, {}))
            # Re-apply any cloud builds that arrived before this game's data was ready
            if self._pending_cloud_builds:
                self._sync_cloud_builds(self._pending_cloud_builds)
            # If a build was pending a game switch, apply it now
            if self._pending_build_load and self._build.get("game") == data.game:
                self._pending_build_load = False
                self._load_build(self._build)
        self._recalc()
        self._stack.setCurrentIndex(1)

    def receive_cloud_builds(self, cloud_builds: list):
        """Called from main thread when profile API returns builds."""
        if not cloud_builds:
            return
        # Reset session sync tracking on fresh profile fetch
        self._synced_cloud_ids.clear()
        # Cache so we can re-apply after each game's data finishes loading
        self._pending_cloud_builds = cloud_builds
        if self._data:
            self._sync_cloud_builds(cloud_builds)

    def _sync_cloud_builds(self, cloud_builds: list):
        """Upsert all cloud builds. ID resolution uses current data if game matches, else stores stubs."""
        local_by_name = {b.get("name", ""): b for b in _list_saved_builds()}
        changed = False
        for cb in cloud_builds:
            name = cb.get("name", "")
            cloud_id = cb.get("id")
            if not name:
                continue
            if cloud_id in self._synced_cloud_ids:
                continue   # already processed this session
            local = local_by_name.get(name)
            cloud_ts = cb.get("updated_at", 0) or 0
            local_ts = float(local.get("saved_at", 0) or 0) if local else 0
            if local is None:
                normalised = self._normalise_cloud_build(cb)
                _save_build_local(normalised)
                changed = True
                log.info("Cloud sync new: %s (game=%s)", name, cb.get("game"))
            elif local_ts > cloud_ts:
                # Local is newer — keep it, skip cloud overwrite
                log.info("Cloud sync skip (local newer): %s local_ts=%.0f cloud_ts=%d", name, local_ts, cloud_ts)
            else:
                normalised = self._normalise_cloud_build(cb)
                _save_build_local(normalised)
                changed = True
                log.info("Cloud sync updated: %s (game=%s)", name, cb.get("game"))
            if cloud_id:
                self._synced_cloud_ids.add(cloud_id)
        if changed:
            self._refresh_saved_builds()

    def _normalise_cloud_build(self, cb: dict) -> dict:
        """Convert profile API build dict into local build dict."""
        game = cb.get("game", "elden_ring")
        build = _empty_build(game)
        build["name"]          = cb.get("name", "Cloud Build")
        build["cloud_id"]      = cb.get("id")
        build["class_id"]      = cb.get("class_id")
        build["playstyle_tag"] = cb.get("tag", "pve")
        build["scadutree"]     = cb.get("scadutree_level", 0)
        build["level"]         = cb.get("level", 1)
        build["saved_at"]      = cb.get("updated_at", 0)
        # Stats
        stats = cb.get("stats", {})
        for s in STAT_KEYS:
            if s in stats:
                build["stats"][s] = stats[s]
        # Only resolve IDs if the loaded data matches this build's game
        data = self._data if (self._data and self._data.game == game) else None

        # class_base — needed for correct level calculation
        if data and cb.get("class_id"):
            cls = next((c for c in data.classes if c.get("id") == cb["class_id"]), None)
            if cls:
                build["class_name"] = cls.get("name", "")
                for s in STAT_KEYS:
                    build["class_base"][s] = cls.get(s, 1)

        # Weapons
        weapons = cb.get("weapons", {})
        for ws in WEAPON_SLOTS:
            side = "rh" if ws.startswith("r") else "lh"
            num  = ws[-1]
            key  = f"{side}{num}"
            wid  = weapons.get(key)
            if wid:
                full = data.weapons_by_id.get(wid) if data else None
                build["slots"][ws] = full if full else {"id": wid}  # stub if data not loaded
            aow = weapons.get(f"{key}_aow")
            if aow:
                build["aow"][ws] = aow
            aff = weapons.get(f"{key}_affinity")
            build["affinities"][ws] = aff if aff else "Standard"

        # Armor
        armor = cb.get("armor", {})
        for slot in ARMOR_SLOTS:
            aid = armor.get(slot)
            if aid:
                full = data.armor_by_id.get(aid) if data else None
                build["slots"][slot] = full if full else {"id": aid}

        # Talismans
        talismans = cb.get("talismans", [])
        for i, tid in enumerate(talismans[:4]):
            if tid:
                full = data.talismans_by_id.get(tid) if data else None
                build["slots"][f"talisman{i+1}"] = full if full else {"id": tid}

        # Spells
        for sid in cb.get("spell_ids", []):
            sp = data.spells_by_id.get(sid) if data else None
            if sp:
                build["spells"].append(sp)
            elif sid:
                build["spells"].append({"id": sid})  # stub resolved on load

        # Spirit ash (name-based — store name for later resolution if data missing)
        ash_name = cb.get("spirit_ash_name")
        if ash_name:
            ash = next((a for a in data.spirit_ashes if a.get("name") == ash_name), None) if data else None
            build["spirit_ash"] = ash if ash else ash_name  # store name as fallback

        build["spirit_ash_upgrade"] = cb.get("spirit_ash_upgrade", 0)

        # Tears (name-based)
        t1 = cb.get("tear_1_name")
        t2 = cb.get("tear_2_name")
        def _find_tear(name):
            if not name:
                return None
            return next((t for t in data.tears if t.get("name") == name), None) if data else name
        build["tears"] = [_find_tear(t1), _find_tear(t2)]

        # ERR extras
        build["curioSelections"] = cb.get("curio_selections", {})
        build["runeInventory"]   = cb.get("rune_inventory", [])
        return build

    # ── Planner layout ─────────────────────────────────────────────────────────

    def _build_planner_layout(self, parent):
        layout = QHBoxLayout(parent)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet(f"QSplitter::handle {{ background: {BORDER_SOLID}; }}")
        layout.addWidget(splitter)

        # ── Left column: controls ────────────────────────────────────────────
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setMinimumWidth(300)
        left_scroll.setMaximumWidth(800)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left_scroll.setStyleSheet(f"background: {BG_BASE}; border: none;")
        left_inner = QWidget()
        left_inner.setStyleSheet(f"background: {BG_BASE};")
        left_inner.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        left_layout = QVBoxLayout(left_inner)
        left_layout.setContentsMargins(16, 14, 16, 14)
        left_layout.setSpacing(10)
        left_scroll.setWidget(left_inner)
        splitter.addWidget(left_scroll)

        # Game selector + build name
        top_row = QHBoxLayout()
        self._game_combo = QComboBox()
        self._game_combo.addItem("Elden Ring", "elden_ring")
        self._game_combo.addItem("Elden Ring Reforged", "err")
        self._game_combo.currentIndexChanged.connect(self._on_game_changed)
        top_row.addWidget(self._game_combo, 1)
        left_layout.addLayout(top_row)

        self._build_name_input = QLineEdit()
        self._build_name_input.setPlaceholderText("Build name…")
        self._build_name_input.setText(self._build["name"])
        self._build_name_input.textChanged.connect(lambda t: self._build.update({"name": t}))
        left_layout.addWidget(self._build_name_input)

        # Class picker + optimizer (combined section)
        left_layout.addWidget(_section_label("CLASS"))
        self._class_combo = QComboBox()
        self._class_combo.addItem("— Select Class —", None)
        self._class_combo.currentIndexChanged.connect(self._on_class_changed)
        left_layout.addWidget(self._class_combo)

        self._optimizer = OptimizerWidget()
        self._optimizer.class_picked.connect(self._apply_class)
        left_layout.addWidget(self._optimizer)

        # Stats
        left_layout.addWidget(_section_label("STATS"))
        stats_card = _card()
        sc_layout = QVBoxLayout(stats_card)
        sc_layout.setContentsMargins(10, 8, 10, 8)
        sc_layout.setSpacing(0)

        self._stat_rows = {}
        for key in STAT_KEYS:
            row = StatRow(key)
            row.value_changed.connect(self._on_stat_changed)
            sc_layout.addWidget(row)
            self._stat_rows[key] = row
        left_layout.addWidget(stats_card)

        # Derived stats — clean 4-column row (label/val pairs)
        derived_card = _card()
        derived_card.setStyleSheet(f"background: {BG_CARD}; border: 1px solid {BORDER_SOLID}; border-radius: 10px;")
        dc_outer = QVBoxLayout(derived_card)
        dc_outer.setContentsMargins(14, 10, 14, 10)
        dc_outer.setSpacing(8)

        self._derived_labels = {}
        # Row 1: Level, HP, FP, STAM
        # Row 2: EQ Load, Poise, Roll
        rows_def = [
            [("level", "LEVEL"), ("hp", "HP"), ("fp", "FP"), ("stamina", "STAM")],
            [("equip_load", "EQ LOAD"), ("poise", "POISE"), ("roll", "ROLL TYPE")],
        ]
        for row_items in rows_def:
            row_w = QHBoxLayout()
            row_w.setSpacing(0)
            for key, label in row_items:
                cell = QVBoxLayout()
                cell.setSpacing(2)
                lbl_w = QLabel(label)
                lbl_w.setStyleSheet(f"color: {TEXT_DIM}; font-size: 9px; font-weight: 700; letter-spacing: 1.5px; background: transparent;")
                val_w = QLabel("—")
                val_w.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
                val_w.setStyleSheet(f"color: {ACCENT_GOLD}; background: transparent;")
                cell.addWidget(lbl_w)
                cell.addWidget(val_w)
                row_w.addLayout(cell, 1)
                self._derived_labels[key] = val_w
            dc_outer.addLayout(row_w)
        left_layout.addWidget(derived_card)

        # Scadutree
        left_layout.addWidget(_section_label("SCADUTREE BLESSING"))
        scadu_card = _card()
        scadu_card.setStyleSheet(f"background: {BG_CARD}; border: 1px solid {BORDER_SOLID}; border-radius: 10px;")
        scadu_cl = QHBoxLayout(scadu_card)
        scadu_cl.setContentsMargins(12, 8, 12, 8)
        scadu_cl.setSpacing(12)
        self._scadu_slider = QSlider(Qt.Orientation.Horizontal)
        self._scadu_slider.setRange(0, 20)
        self._scadu_slider.setValue(0)
        self._scadu_slider.valueChanged.connect(self._on_scadu_changed)
        self._scadu_lbl = QLabel("0 / 20")
        self._scadu_lbl.setFixedWidth(44)
        self._scadu_lbl.setStyleSheet(f"color: {ACCENT_GOLD}; font-weight: 700; font-size: 12px; background: transparent;")
        scadu_cl.addWidget(self._scadu_slider, 1)
        scadu_cl.addWidget(self._scadu_lbl)
        left_layout.addWidget(scadu_card)

        # Playstyle tag
        left_layout.addWidget(_section_label("PLAYSTYLE"))
        tag_row = QHBoxLayout()
        tag_row.setSpacing(6)
        self._tag_buttons = {}
        for tag in PLAYSTYLE_TAGS:
            btn = ChipButton(tag.replace("_", " ").upper())
            btn.setChecked(tag == "pve")
            btn.clicked.connect(lambda checked, t=tag: self._set_tag(t))
            tag_row.addWidget(btn)
            self._tag_buttons[tag] = btn
        tag_row.addStretch()
        left_layout.addLayout(tag_row)

        # Save / start run buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        save_btn = QPushButton("SAVE BUILD")
        save_btn.setObjectName("primary")
        save_btn.setFixedHeight(36)
        save_btn.clicked.connect(self._save_build)
        start_btn = QPushButton("START RUN")
        start_btn.setObjectName("primary")
        start_btn.setFixedHeight(36)
        start_btn.setToolTip("Create a run with this build's name and game")
        start_btn.clicked.connect(self._request_start_run)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(start_btn)
        left_layout.addLayout(btn_row)

        # Saved builds list (inline, below the action buttons)
        left_layout.addSpacing(6)
        left_layout.addWidget(_section_label("SAVED BUILDS"))
        self._saved_scroll = QScrollArea()
        self._saved_scroll.setWidgetResizable(True)
        self._saved_scroll.setMinimumHeight(100)
        self._saved_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._saved_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._saved_inner = QWidget()
        self._saved_inner.setStyleSheet(f"background: {BG_BASE};")
        self._saved_layout = QVBoxLayout(self._saved_inner)
        self._saved_layout.setContentsMargins(0, 0, 0, 0)
        self._saved_layout.setSpacing(4)
        self._saved_layout.addStretch()
        self._saved_scroll.setWidget(self._saved_inner)
        left_layout.addWidget(self._saved_scroll, 1)
        self._refresh_saved_builds()

        # ── Content area: equipment tabs + floating AR/picker overlay ────────
        # The overlay (_right_stack) is a child of content_area with absolute
        # positioning. An event filter repositions it whenever content_area resizes.
        content_area = QWidget()
        content_area.setStyleSheet(f"background: {BG_BASE};")
        content_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        splitter.addWidget(content_area)

        content_outer = QVBoxLayout(content_area)
        content_outer.setContentsMargins(0, 0, 0, 0)
        content_outer.setSpacing(0)

        center_col = QWidget()
        center_col.setStyleSheet(f"background: {BG_BASE};")
        center_col_layout = QVBoxLayout(center_col)
        center_col_layout.setContentsMargins(0, 0, 0, 0)
        center_col_layout.setSpacing(0)
        content_outer.addWidget(center_col, 1)

        # Tab bar
        _CTR_TABS = ["ARMAMENT", "ARMOR", "TALISMANS", "SPIRIT", "PHYSICK", "SPELLS"]
        tab_bar_w = QWidget()
        tab_bar_w.setFixedHeight(38)
        tab_bar_w.setStyleSheet(f"background: {BG_SURFACE}; border-bottom: 2px solid {BORDER_SOLID};")
        tab_bar_l = QHBoxLayout(tab_bar_w)
        tab_bar_l.setContentsMargins(8, 0, 8, 0)
        tab_bar_l.setSpacing(0)
        self._center_tabs: dict[str, QPushButton] = {}
        self._center_stack = QStackedWidget()
        self._center_stack.setStyleSheet(f"background: {BG_BASE};")

        def _make_center_tab(label, idx):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setFixedHeight(38)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; border: none; border-bottom: 2px solid transparent;
                    color: {TEXT_DIM}; font-size: 10px; font-weight: 700; letter-spacing: 1px;
                    padding: 0 10px; margin-bottom: -2px;
                }}
                QPushButton:checked {{
                    color: {ACCENT_GOLD}; border-bottom: 2px solid {ACCENT_GOLD};
                }}
                QPushButton:hover:!checked {{ color: {TEXT_PRIMARY}; }}
            """)
            btn.clicked.connect(lambda _, i=idx: self._switch_center_tab(i))
            tab_bar_l.addWidget(btn)
            self._center_tabs[label] = btn

        for i, lbl in enumerate(_CTR_TABS):
            _make_center_tab(lbl, i)
        tab_bar_l.addStretch()

        # CURIOS tab — ERR only, hidden by default
        self._curios_tab_btn = QPushButton("CURIOS")
        self._curios_tab_btn.setCheckable(True)
        self._curios_tab_btn.setFixedHeight(38)
        self._curios_tab_btn.setVisible(False)
        self._curios_tab_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none; border-bottom: 2px solid transparent;
                color: {TEXT_DIM}; font-size: 10px; font-weight: 700; letter-spacing: 1px;
                padding: 0 10px; margin-bottom: -2px;
            }}
            QPushButton:checked {{ color: {ACCENT_GOLD}; border-bottom: 2px solid {ACCENT_GOLD}; }}
            QPushButton:hover:!checked {{ color: {TEXT_PRIMARY}; }}
        """)
        curios_tab_idx = len(_CTR_TABS)
        self._curios_tab_btn.clicked.connect(lambda: self._switch_center_tab(curios_tab_idx))
        tab_bar_l.insertWidget(tab_bar_l.count() - 1, self._curios_tab_btn)
        self._center_tabs["CURIOS"] = self._curios_tab_btn

        center_col_layout.addWidget(tab_bar_w)
        center_col_layout.addWidget(self._center_stack, 1)

        self._slot_buttons: dict[str, SlotButton] = {}
        self._aow_rows: dict[str, AoWRow] = {}
        self._affinity_rows: dict[str, AffinityRow] = {}

        def _tab_scroll_page():
            page = QWidget()
            page.setStyleSheet(f"background: {BG_BASE};")
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroll.setStyleSheet(f"background: {BG_BASE}; border: none;")
            inner = QWidget()
            inner.setStyleSheet(f"background: {BG_BASE};")
            layout = QVBoxLayout(inner)
            layout.setContentsMargins(12, 12, 12, 12)
            layout.setSpacing(8)
            scroll.setWidget(inner)
            pl = QVBoxLayout(page)
            pl.setContentsMargins(0, 0, 0, 0)
            pl.addWidget(scroll)
            return page, layout

        def _slot_card(slots, show_aow=False):
            card = QWidget()
            card.setStyleSheet(f"background: {BG_CARD}; border: 1px solid {BORDER_SOLID}; border-radius: 6px;")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(0, 0, 0, 0)
            cl.setSpacing(0)
            for i, s in enumerate(slots):
                if i > 0:
                    sep = QWidget()
                    sep.setFixedHeight(1)
                    sep.setStyleSheet(f"background: {BORDER_SOLID};")
                    cl.addWidget(sep)
                btn = SlotButton(s)
                btn.clicked.connect(lambda sk=s: self._open_picker(sk))
                btn.cleared.connect(self._clear_slot)
                cl.addWidget(btn)
                self._slot_buttons[s] = btn
                if show_aow:
                    aow_row = AoWRow(s)
                    aow_row.pick_requested.connect(lambda sk=s: self._open_picker(f"aow_{sk}"))
                    aow_row.cleared.connect(self._clear_aow)
                    cl.addWidget(aow_row)
                    self._aow_rows[s] = aow_row
                    aff_row = AffinityRow(s)
                    aff_row.affinity_changed.connect(self._on_slot_affinity_changed)
                    cl.addWidget(aff_row)
                    self._affinity_rows[s] = aff_row
            return card

        # Tab 0 — ARMAMENT
        pg, lay = _tab_scroll_page()
        # AR button in the armament header
        arm_hdr = QHBoxLayout()
        arm_hdr.addWidget(_section_label("RIGHT HAND"))
        arm_hdr.addStretch()
        ar_btn = QPushButton("⚔ VIEW AR")
        ar_btn.setFixedHeight(24)
        ar_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(201,168,76,0.12); border: 1px solid rgba(201,168,76,0.3);
                border-radius: 4px; color: {ACCENT_GOLD}; font-size: 9px; font-weight: 700;
                letter-spacing: 1px; padding: 0 8px;
            }}
            QPushButton:hover {{ background: rgba(201,168,76,0.22); }}
        """)
        ar_btn.clicked.connect(self._show_ar_overlay)
        arm_hdr.addWidget(ar_btn)
        lay.addLayout(arm_hdr)
        lay.addWidget(_slot_card([s for s in WEAPON_SLOTS if s.startswith("r")], show_aow=True))
        lay.addWidget(_section_label("LEFT HAND"))
        lay.addWidget(_slot_card([s for s in WEAPON_SLOTS if s.startswith("l")], show_aow=True))
        lay.addStretch()
        self._center_stack.addWidget(pg)

        # Tab 1 — ARMOR
        pg, lay = _tab_scroll_page()
        lay.addWidget(_slot_card(ARMOR_SLOTS))
        lay.addStretch()
        self._center_stack.addWidget(pg)

        # Tab 2 — TALISMANS
        pg, lay = _tab_scroll_page()
        lay.addWidget(_slot_card(TALI_SLOTS))
        lay.addStretch()
        self._center_stack.addWidget(pg)

        # Tab 3 — SPIRIT ASH
        pg, lay = _tab_scroll_page()
        ash_card = QWidget()
        ash_card.setStyleSheet(f"background: {BG_CARD}; border: 1px solid {BORDER_SOLID}; border-radius: 8px;")
        ash_cl = QVBoxLayout(ash_card)
        ash_cl.setContentsMargins(0, 4, 0, 8)
        ash_cl.setSpacing(4)
        self._ash_btn = SlotButton("spirit_ash")
        self._ash_btn.clicked.connect(lambda: self._open_picker("spirit_ash"))
        self._ash_btn.cleared.connect(self._clear_slot)
        ash_cl.addWidget(self._ash_btn)
        upgrade_row = QHBoxLayout()
        upgrade_row.setContentsMargins(12, 0, 12, 0)
        upgrade_row.addWidget(_muted("Upgrade", 10))
        self._ash_upgrade = QSpinBox()
        self._ash_upgrade.setRange(0, 10)
        self._ash_upgrade.setFixedWidth(50)
        self._ash_upgrade.setStyleSheet(f"""
            QSpinBox {{
                background: {BG_SURFACE}; border: 1px solid {BORDER_SOLID};
                border-radius: 4px; color: {TEXT_PRIMARY}; font-size: 11px; padding: 2px;
            }}
        """)
        self._ash_upgrade.valueChanged.connect(lambda v: self._build.update({"spirit_ash_upgrade": v}))
        upgrade_row.addWidget(self._ash_upgrade)
        upgrade_row.addStretch()
        ash_cl.addLayout(upgrade_row)
        lay.addWidget(ash_card)
        lay.addStretch()
        self._center_stack.addWidget(pg)

        # Tab 4 — PHYSICK
        pg, lay = _tab_scroll_page()
        tear_card = _card()
        tear_l = QVBoxLayout(tear_card)
        tear_l.setContentsMargins(8, 8, 8, 8)
        tear_l.setSpacing(4)
        self._tear_btns = []
        for i in range(2):
            tb = SlotButton(f"tear{i}")
            tb.clicked.connect(lambda _, idx=i: self._open_picker(f"tear{idx}"))
            tb.cleared.connect(self._clear_slot)
            tear_l.addWidget(tb)
            self._tear_btns.append(tb)
        lay.addWidget(tear_card)
        lay.addStretch()
        self._center_stack.addWidget(pg)

        # Tab 5 — SPELLS
        pg, lay = _tab_scroll_page()
        slots_hdr = QHBoxLayout()
        slots_hdr.addStretch()
        self._spell_slots_lbl = QLabel("0 / 12 slots")
        self._spell_slots_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 9px; font-weight: 600; letter-spacing: 1px; background: transparent;")
        slots_hdr.addWidget(self._spell_slots_lbl)
        lay.addLayout(slots_hdr)
        spell_add_btn = QPushButton("+ ADD SPELL")
        spell_add_btn.clicked.connect(lambda: self._open_picker("spell"))
        lay.addWidget(spell_add_btn)
        self._spell_list_layout = QVBoxLayout()
        self._spell_list_layout.setSpacing(4)
        lay.addLayout(self._spell_list_layout)
        lay.addStretch()
        self._center_stack.addWidget(pg)

        # Tab 6 — CURIOS (ERR only)
        pg, lay = _tab_scroll_page()
        self._curio_panel = CurioPanel()
        self._curio_panel.selection_changed.connect(
            lambda sel: self._build.update({"curioSelections": sel})
        )
        lay.addWidget(self._curio_panel)
        lay.addStretch()
        self._center_stack.addWidget(pg)

        # Activate first tab
        self._current_center_tab = 0
        self._switch_center_tab(0)

        # ── AR / Picker overlay — floats centered-right over content_area ──────
        # AR panel is narrower (380px), picker is wider (600px).
        # The overlay always allocates picker width; AR panel is right-anchored inside.
        PICKER_W = 600
        AR_W     = 380
        self._overlay_picker_w = PICKER_W
        self._overlay_ar_w     = AR_W

        self._right_stack = QStackedWidget(content_area)
        self._right_stack.setStyleSheet(
            f"background: {BG_SURFACE}; border-left: 1px solid {BORDER_SOLID};"
        )
        self._right_stack.hide()

        # AR info page
        ar_page = QWidget()
        ar_page.setStyleSheet(f"background: {BG_SURFACE};")
        ar_page.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        ar_layout = QVBoxLayout(ar_page)
        ar_layout.setContentsMargins(0, 0, 0, 0)
        ar_layout.setSpacing(0)
        self._ar_panel = ARPanel()
        self._ar_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._ar_panel.slot_combo_changed = self._ar_panel._slot_combo.currentIndexChanged
        self._ar_panel._slot_combo.currentIndexChanged.connect(
            lambda: self._recalc_ar(self._ar_panel._slot_combo.currentData())
        )
        self._ar_panel._affinity_combo.currentTextChanged.connect(self._on_affinity_changed)
        self._ar_panel.close_requested.connect(self._dismiss_overlay)
        self._ar_panel.aow_pick_requested.connect(lambda sk: self._open_picker(f"aow_{sk}"))
        ar_layout.addWidget(self._ar_panel, 1)
        self._right_stack.addWidget(ar_page)

        # Picker page
        self._picker = PickerPanel()
        self._picker.item_picked.connect(self._on_item_picked)
        self._picker.closed.connect(self._close_picker)
        self._picker.category_switched.connect(self._on_picker_category_switched)
        self._right_stack.addWidget(self._picker)

        self._right_stack.setCurrentIndex(0)

        # Reposition overlay whenever content_area is resized or page changes
        def _reposition_overlay(h=None, w=None):
            if h is None:
                h = content_area.height()
            if w is None:
                w = self._right_stack.width() or PICKER_W
            x = max(0, content_area.width() - w)
            self._right_stack.setGeometry(x, 0, w, h)

        self._reposition_overlay = _reposition_overlay

        class _OverlayFilter(QObject):
            def __init__(self_, parent_widget):
                super().__init__(parent_widget)
                self_._w = parent_widget
            def eventFilter(self_, obj, event):
                if obj is self_._w and event.type() == QEvent.Type.Resize:
                    _reposition_overlay(event.size().height())
                return False


        self._overlay_filter = _OverlayFilter(content_area)
        content_area.installEventFilter(self._overlay_filter)

        # Give the splitter initial proportions: 50% left | 50% center
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

    # ── Overlay helpers ────────────────────────────────────────────────────────

    def _show_ar_overlay(self):
        self._right_stack.setCurrentIndex(0)
        self._reposition_overlay(w=self._overlay_ar_w)
        self._right_stack.show()
        self._right_stack.raise_()
        self._recalc_ar(self._ar_panel._slot_combo.currentData())

    def _dismiss_overlay(self):
        self._right_stack.hide()
        self._picker_open = False
        try:
            self._picker.nav_tab_changed.disconnect(self._on_spell_nav_changed)
        except Exception:
            pass

    # ── Game / class ──────────────────────────────────────────────────────────

    def _switch_center_tab(self, idx: int):
        self._current_center_tab = idx
        self._center_stack.setCurrentIndex(idx)
        tab_labels = ["ARMAMENT", "ARMOR", "TALISMANS", "SPIRIT", "PHYSICK", "SPELLS", "CURIOS"]
        for i, lbl in enumerate(tab_labels):
            btn = self._center_tabs.get(lbl)
            if btn:
                btn.setChecked(i == idx)

    def _on_game_changed(self):
        game = self._game_combo.currentData()
        if not self._pending_build_load:
            # Manual game switch — start a fresh empty build
            self._build = _empty_build(game)
            self._build_name_input.setText(self._build["name"])
        self._reset_slot_ui()
        self._reset_spell_ui()
        self._load_data(game)

    def _populate_class_picker(self):
        self._class_combo.blockSignals(True)
        self._class_combo.clear()
        self._class_combo.addItem("— Select Class —", None)
        if self._data:
            for cls in self._data.classes:
                self._class_combo.addItem(cls["name"], cls)
        self._class_combo.blockSignals(False)

    def _populate_optimizer(self):
        if self._data:
            self._optimizer.set_classes(self._data.classes)

    def _on_class_changed(self, idx):
        cls = self._class_combo.currentData()
        if cls:
            self._apply_class(cls)

    def _apply_class(self, cls):
        self._build["class_id"]   = cls.get("id")
        self._build["class_name"] = cls.get("name", "")
        for key in STAT_KEYS:
            base = cls.get(key, 1)
            self._build["class_base"][key] = base
            if self._build["stats"][key] < base:
                self._build["stats"][key] = base

        # Update combo selection
        for i in range(self._class_combo.count()):
            if self._class_combo.itemData(i) == cls:
                self._class_combo.blockSignals(True)
                self._class_combo.setCurrentIndex(i)
                self._class_combo.blockSignals(False)
                break

        self._sync_stat_rows()
        self._recalc()

    def _sync_stat_rows(self):
        for key, row in self._stat_rows.items():
            base = self._build["class_base"].get(key, 1)
            row.set_value(self._build["stats"][key], min_val=base)

    # ── Stat changes ──────────────────────────────────────────────────────────

    def _on_stat_changed(self, key, val):
        base = self._build["class_base"].get(key, 1)
        clamped = max(base, min(99, val))
        self._build["stats"][key] = clamped
        if clamped != val:
            self._stat_rows[key].set_value(clamped, min_val=base)
        else:
            # Keep min enforced on the spinbox even if value didn't change
            self._stat_rows[key].set_min(base)

        # ERR: update rune bonuses on stat rows
        if self._build["game"] == "err":
            from core.ar_calculator import calc_rune_bonuses
            bonuses = calc_rune_bonuses(self._build.get("runeInventory", []))
            for k, row in self._stat_rows.items():
                row.set_rune_bonus(bonuses.get(k, 0))

        self._recalc()

    def _on_scadu_changed(self, val):
        self._build["scadutree"] = val
        self._scadu_lbl.setText(f"{val} / 20")
        self._recalc_ar(self._ar_panel._slot_combo.currentData())

    def _set_tag(self, tag):
        self._build["playstyle_tag"] = tag
        for t, btn in self._tag_buttons.items():
            btn.setChecked(t == tag)

    # ── Derived stats ─────────────────────────────────────────────────────────

    def _recalc(self):
        from core.derived_stats import (
            get_derived, calc_level, calc_total_weight, calc_poise, get_roll_type,
        )
        build  = self._build
        game   = build["game"]
        stats  = build["stats"]
        err_curves = self._data.err_curves if self._data and game == "err" else None
        cls    = None
        if self._data and build["class_id"]:
            cls = next((c for c in self._data.classes if c.get("id") == build["class_id"]), None)

        d = get_derived(stats, game, err_curves)
        level = calc_level(stats, build["class_base"], cls, game)
        weight = calc_total_weight(build["slots"])
        poise  = calc_poise(build["slots"])
        roll   = get_roll_type(weight, d["equip_load"])

        self._derived_labels["level"].setText(str(level))
        self._derived_labels["hp"].setText(str(d["hp"]))
        self._derived_labels["fp"].setText(str(d["fp"]))
        self._derived_labels["stamina"].setText(str(d["stamina"]))
        self._derived_labels["equip_load"].setText(f"{weight}/{d['equip_load']}")
        self._derived_labels["poise"].setText(str(poise))
        roll_colors = {"Light Roll": GREEN_LIVE, "Medium Roll": ACCENT_GOLD,
                       "Heavy Roll": ACCENT_RED2, "Overloaded": "#ef4444"}
        self._derived_labels["roll"].setText(roll)
        self._derived_labels["roll"].setStyleSheet(
            f"color: {roll_colors.get(roll, TEXT_PRIMARY)}; background: transparent;"
        )

        self._build["level"] = level

        # Spell slot counter
        used = sum(sp.get("slots", 1) for sp in self._build.get("spells", []) if isinstance(sp, dict))
        self._spell_slots_lbl.setText(f"{used} / 12 slots")
        self._spell_slots_lbl.setStyleSheet(
            f"color: {'#ef4444' if used > 12 else TEXT_MUTED}; font-size: 9px; font-weight: 600; letter-spacing: 1px; background: transparent;"
        )

        self._recalc_ar(self._ar_panel._slot_combo.currentData())

    def _recalc_ar(self, slot_key=None):
        if slot_key is None:
            slot_key = "rh1"
        weapon = self._build["slots"].get(slot_key)
        if not weapon:
            self._ar_panel.clear()
            return
        affinity = self._build["affinities"].get(slot_key, "Standard")
        aow = self._build.get("aow", {}).get(slot_key)
        aow_name = (aow if isinstance(aow, str) else aow.get("name", "")) if aow else None
        self._ar_panel.set_aow(aow_name)
        self._fetch_and_show_ar(slot_key, weapon, affinity)

    def _fetch_and_show_ar(self, slot_key, weapon, affinity):
        name = weapon.get("name", "")
        game = self._build["game"]
        cache_key = f"{game}|{name}"

        if cache_key in self._variant_cache:
            self._show_ar_from_variants(slot_key, weapon, affinity, self._variant_cache[cache_key])
            return

        # Show weapon name immediately while fetch runs in background
        self._ar_panel.show_ar(weapon, None)

        if not self._data:
            return

        def _fetch():
            try:
                variants = self._data.get_variants(name, self._api_key)
            except Exception as e:
                log.warning("AR variant fetch failed for %s: %s", name, e)
                variants = []
            self._variant_cache[cache_key] = variants
            self._variant_bridge.ready.emit(f"{slot_key}|{name}|{affinity}", variants)

        threading.Thread(target=_fetch, daemon=True).start()

    def _on_variants_ready(self, key, variants):
        parts = key.split("|", 2)
        if len(parts) != 3:
            return
        slot_key, name, affinity = parts
        weapon = self._build["slots"].get(slot_key)
        if not weapon or weapon.get("name") != name:
            return
        self._show_ar_from_variants(slot_key, weapon, affinity, variants)

    def _show_ar_from_variants(self, slot_key, weapon, affinity, variants):
        from core.ar_calculator import (
            compute_ar, apply_scadutree, get_variant_for_affinity, ER_AFFINITIES,
        )
        if not self._data:
            return
        variant = get_variant_for_affinity(variants, affinity)
        if not variant:
            self._ar_panel.show_ar(weapon, None)
            return

        game  = self._build["game"]
        stats = self._build["stats"]
        if game == "err":
            from core.ar_calculator import get_effective_stats
            eff_stats = get_effective_stats(stats, self._build.get("runeInventory", []))
        else:
            eff_stats = stats

        result = compute_ar(variant, eff_stats, self._data.ar_curves, self._data.ar_aec, self._data.ar_reinforce)
        scadu  = self._build.get("scadutree", 0)
        if scadu > 0:
            result["total"] = apply_scadutree(result["total"], scadu)

        # Available affinities for this weapon
        if game == "err" and self._data.affinities:
            avail_names = [a["name"] for a in self._data.affinities
                           if any(v["affinity"] == a["name"] for v in variants)]
        else:
            avail_names = list({v.get("affinity", "Standard") for v in variants})
            avail_names = [a for a in ER_AFFINITIES if a in avail_names]

        self._ar_panel.show_ar(weapon, result, affinity=affinity, affinities=avail_names)

        # Populate inline affinity row in the armament card
        aff_row = self._affinity_rows.get(slot_key)
        if aff_row:
            current_aff = self._build["affinities"].get(slot_key, "Standard")
            aff_row.set_affinities(avail_names, current_aff)

    def _on_affinity_changed(self, affinity):
        slot_key = self._ar_panel._slot_combo.currentData() or "rh1"
        self._build["affinities"][slot_key] = affinity
        # Sync inline affinity row if not already the source
        aff_row = self._affinity_rows.get(slot_key)
        if aff_row:
            aff_row.set_current(affinity)
        weapon = self._build["slots"].get(slot_key)
        if weapon:
            variants = self._variant_cache.get(f"{self._build['game']}|{weapon.get('name')}", [])
            if variants:
                self._show_ar_from_variants(slot_key, weapon, affinity, variants)

    def _on_slot_affinity_changed(self, slot_key, affinity):
        """Called when user picks affinity from the inline slot row."""
        self._build["affinities"][slot_key] = affinity
        # Sync AR panel combo if it's showing this slot
        if self._ar_panel._slot_combo.currentData() == slot_key:
            self._ar_panel._affinity_combo.blockSignals(True)
            idx = self._ar_panel._affinity_combo.findText(affinity)
            if idx >= 0:
                self._ar_panel._affinity_combo.setCurrentIndex(idx)
            self._ar_panel._affinity_combo.blockSignals(False)
        weapon = self._build["slots"].get(slot_key)
        if weapon:
            variants = self._variant_cache.get(f"{self._build['game']}|{weapon.get('name')}", [])
            if variants:
                self._show_ar_from_variants(slot_key, weapon, affinity, variants)

    # ── Picker ────────────────────────────────────────────────────────────────

    def _open_picker(self, slot_key):
        if not self._data:
            return
        self._right_stack.setCurrentIndex(1)
        self._reposition_overlay(w=self._overlay_picker_w)
        self._right_stack.show()
        self._right_stack.raise_()
        self._picker_open = True
        cat = self._slot_category(slot_key)

        if cat == "weapon":
            items = list(self._data.weapons_by_name.values())
            # Group weapon types into nav tabs
            _MELEE_TYPES = {
                "Axe","Backhand Blade","Ballista","Beast Claw","Claw",
                "Colossal Sword","Colossal Weapon","Curved Greatsword",
                "Curved Sword","Dagger","Fist","Flail","Great Hammer",
                "Great Katana","Great Spear","Greataxe","Greatbow","Greatsword",
                "Halberd","Hammer","Hand-to-Hand Art","Katana","Light Greatsword",
                "Reaper","Spear","Straight Sword","Thrusting Sword","Twinblade","Whip",
            }
            _RANGED_TYPES = {"Bow","Crossbow","Ballista","Greatbow","Light Bow"}
            _SHIELD_TYPES = {"Greatshield","Medium Shield","Small Shield","Torch"}
            _CATALYST_TYPES = {"Glintstone Staff","Sacred Seal","Perfume Bottle"}
            nav_tabs = [
                ("ALL",      None),
                ("MELEE",    lambda x: x.get("type","") in _MELEE_TYPES),
                ("RANGED",   lambda x: x.get("type","") in _RANGED_TYPES),
                ("SHIELDS",  lambda x: x.get("type","") in _SHIELD_TYPES),
                ("CATALYSTS",lambda x: x.get("type","") in _CATALYST_TYPES),
            ]
            wtypes = sorted({w.get("type","") for w in items if w.get("type")})
            type_chips = [("All types", None)] + [(t, lambda x,t=t: x.get("type")==t) for t in wtypes]
            self._picker.open_for(
                slot_key, cat, items,
                f"Select Weapon — {SLOT_LABELS[slot_key]}",
                filters=type_chips, nav_tabs=nav_tabs)

        elif cat == "armor":
            all_armor = list(self._data.armor_by_name.values())
            slot_type_map = {"helm":"Helm","chest":"Chest","gauntlet":"Gauntlet","leg":"Leg"}
            slot_type = slot_type_map.get(slot_key, "Helm")

            _WT_LIGHT = {"helm":3.5,"chest":7.0,"gauntlet":2.5,"leg":4.0}
            _WT_HEAVY = {"helm":7.0,"chest":14.0,"gauntlet":5.0,"leg":8.0}

            def _wclass(a, sk):
                w = a.get("weight") or 0
                return "light" if w < _WT_LIGHT.get(sk,7.0) else (
                       "heavy" if w >= _WT_HEAVY.get(sk,14.0) else "medium")

            # All armor for this slot type, sorted heaviest first
            slot_items = sorted(
                [a for a in all_armor if a.get("type","").lower() == slot_type.lower()],
                key=lambda a: (-(a.get("weight") or 0), a.get("name",""))
            )[:150]

            # Nav tabs = weight class filter
            nav_tabs = [
                ("ALL",    None),
                ("LIGHT",  lambda x, sk=slot_key: _wclass(x, sk) == "light"),
                ("MEDIUM", lambda x, sk=slot_key: _wclass(x, sk) == "medium"),
                ("HEAVY",  lambda x, sk=slot_key: _wclass(x, sk) == "heavy"),
            ]
            # Chips = slot switcher so user can jump between Helm/Chest/etc
            # We need different items per slot chip — use a special per-chip override
            # by wiring chip clicks to re-open with different slot_key
            slot_chips = [
                ("Helm",     lambda x: x.get("type","").lower() == "helm"),
                ("Chest",    lambda x: x.get("type","").lower() == "chest"),
                ("Gauntlet", lambda x: x.get("type","").lower() == "gauntlet"),
                ("Leg",      lambda x: x.get("type","").lower() == "leg"),
            ]
            # Pass all armor as items (chips filter by type), pre-select current slot chip
            all_sorted = sorted(all_armor,
                                key=lambda a: (-(a.get("weight") or 0), a.get("name","")))
            slot_chip_labels = [l for l,_ in slot_chips]
            active_chip_idx = slot_chip_labels.index(slot_type) if slot_type in slot_chip_labels else 0
            _slot_remap = {"Helm":"helm","Chest":"chest","Gauntlet":"gauntlet","Leg":"leg"}
            self._picker.open_for(
                slot_key, cat, all_sorted,
                f"Select Armor — {slot_type}",
                filters=slot_chips,
                nav_tabs=nav_tabs,
                active_chip=active_chip_idx,
            )
            # Tell picker: clicking a slot chip should re-open for that slot
            self._picker._chip_slot_remap = {
                i: _slot_remap[label]
                for i, (label, _) in enumerate(slot_chips)
                if label in _slot_remap
            }

        elif cat == "talisman":
            items = list(self._data.talismans_by_id.values())
            self._picker.open_for(slot_key, cat, items, "Select Talisman")

        elif cat == "spirit_ash":
            items = self._data.spirit_ashes
            filters = [("All", None),
                       ("Grave", lambda x: x.get("summon_type") == "grave"),
                       ("Ghost", lambda x: x.get("summon_type") == "ghost")]
            self._picker.open_for(slot_key, cat, items, "Select Spirit Ash", filters=filters)

        elif cat == "tear":
            items = self._data.tears
            self._picker.open_for(slot_key, cat, items, "Select Crystal Tear")

        elif cat == "spell":
            items = list(self._data.spells_by_id.values())
            # Build school lists from live data — API now returns school on every spell
            sorc_schools = _get_spell_schools_for_type(items, "Sorcery")
            inca_schools = _get_spell_schools_for_type(items, "Incantation")
            sorc_chips = [("All Schools", lambda x: x.get("type") == "Sorcery")] + [
                (s, lambda x, sc=s: x.get("type") == "Sorcery" and x.get("school") == sc)
                for s in sorc_schools
            ]
            inca_chips = [("All Schools", lambda x: x.get("type") == "Incantation")] + [
                (s, lambda x, sc=s: x.get("type") == "Incantation" and x.get("school") == sc)
                for s in inca_schools
            ]
            nav_tabs = [
                ("ALL",          None),
                ("SORCERIES",    lambda x: x.get("type") == "Sorcery"),
                ("INCANTATIONS", lambda x: x.get("type") == "Incantation"),
            ]
            self._spell_sorc_chips = sorc_chips
            self._spell_inca_chips = inca_chips

            try:
                self._picker.nav_tab_changed.disconnect(self._on_spell_nav_changed)
            except Exception:
                pass
            self._picker.nav_tab_changed.connect(self._on_spell_nav_changed)

            self._picker.open_for(slot_key, cat, items, "Select Spell",
                                  filters=None, nav_tabs=nav_tabs)

        elif cat == "aow":
            ws     = slot_key[4:]   # strip "aow_" → weapon slot key
            weapon = self._build["slots"].get(ws)
            wtype  = weapon.get("type", "") if weapon else ""
            from core.ar_calculator import aow_compatible
            items  = [a for a in self._data.aow_list if aow_compatible(a.get("compatible", ""), wtype)]
            self._picker.open_for(slot_key, cat, items, f"Ash of War — {SLOT_LABELS.get(ws, ws)}")

    def _slot_category(self, slot_key):
        if slot_key.startswith("aow_"): return "aow"
        if slot_key in WEAPON_SLOTS:   return "weapon"
        if slot_key in ARMOR_SLOTS:    return "armor"
        if slot_key in TALI_SLOTS:     return "talisman"
        if slot_key == "spirit_ash":   return "spirit_ash"
        if slot_key.startswith("tear"): return "tear"
        if slot_key == "spell":        return "spell"
        return "unknown"

    def _close_picker(self):
        self._dismiss_overlay()

    def _on_spell_nav_changed(self, idx):
        # idx 0=ALL, 1=SORCERIES, 2=INCANTATIONS
        if idx == 1:
            self._picker.set_filters(self._spell_sorc_chips)
        elif idx == 2:
            self._picker.set_filters(self._spell_inca_chips)
        else:
            self._picker.set_filters(None)

    def _on_picker_category_switched(self, cat_key):
        _cat_default_slot = {
            "weapon":     "rh1",
            "armor":      "helm",
            "talisman":   "talisman1",
            "spell":      "spell",
            "spirit_ash": "spirit_ash",
        }
        # armor slot keys come through directly when user clicks a slot chip
        slot = _cat_default_slot.get(cat_key, cat_key)
        self._open_picker(slot)

    def _on_item_picked(self, slot_key, item):
        cat = self._slot_category(slot_key)
        if cat == "aow":
            ws = slot_key[4:]   # strip "aow_" prefix → weapon slot key
            self._build["aow"][ws] = item.get("name", "") if isinstance(item, dict) else item
            if ws in self._aow_rows:
                self._aow_rows[ws].set_aow(item)
            self._close_picker()
            return

        if cat == "weapon":
            self._build["slots"][slot_key] = item
            self._slot_buttons[slot_key].set_item(item)
            # Reset affinity to Standard for newly equipped weapon
            self._build["affinities"][slot_key] = "Standard"
            # Reset AoW for new weapon (skill may be locked or incompatible)
            self._build["aow"][slot_key] = None
            if slot_key in self._aow_rows:
                self._aow_rows[slot_key].set_weapon(item)
                self._aow_rows[slot_key].set_aow(None)
            # Switch overlay to AR panel (keep it open so user sees damage stats)
            self._right_stack.setCurrentIndex(0)
            self._reposition_overlay(w=self._overlay_ar_w)
            self._right_stack.show()
            self._right_stack.raise_()
            self._picker_open = False
            try:
                self._picker.nav_tab_changed.disconnect(self._on_spell_nav_changed)
            except Exception:
                pass
            self._recalc()
            # Kick off AR fetch immediately
            self._ar_panel._slot_combo.setCurrentIndex(
                [self._ar_panel._slot_combo.itemData(i) for i in range(6)].index(slot_key)
                if slot_key in [self._ar_panel._slot_combo.itemData(i) for i in range(6)] else 0
            )
            self._recalc_ar(slot_key)

        elif cat == "armor":
            self._build["slots"][slot_key] = item
            self._slot_buttons[slot_key].set_item(item)
            self._close_picker()
            self._recalc()

        elif cat == "talisman":
            self._build["slots"][slot_key] = item
            self._slot_buttons[slot_key].set_item(item)
            self._close_picker()

        elif cat == "spirit_ash":
            self._build["spirit_ash"] = item
            self._ash_btn.set_item(item)
            self._close_picker()

        elif cat == "tear":
            idx = int(slot_key.replace("tear", ""))
            self._build["tears"][idx] = item
            self._tear_btns[idx].set_item(item)
            self._close_picker()

        elif cat == "spell":
            # Avoid duplicates
            if not any(s.get("id") == item.get("id") for s in self._build["spells"]):
                self._build["spells"].append(item)
                self._add_spell_row(item)
            self._close_picker()

    def _clear_aow(self, slot_key):
        self._build["aow"][slot_key] = None
        if slot_key in self._aow_rows:
            self._aow_rows[slot_key].set_aow(None)

    def _clear_slot(self, slot_key):
        cat = self._slot_category(slot_key)
        if cat == "weapon":
            self._build["slots"][slot_key] = None
            self._slot_buttons[slot_key].set_item(None)
            self._build["aow"][slot_key] = None
            if slot_key in self._aow_rows:
                self._aow_rows[slot_key].set_weapon(None)
                self._aow_rows[slot_key].set_aow(None)
            if slot_key in self._affinity_rows:
                self._affinity_rows[slot_key].hide_row()
            self._recalc()
        elif cat == "armor":
            self._build["slots"][slot_key] = None
            self._slot_buttons[slot_key].set_item(None)
            self._recalc()
        elif cat == "talisman":
            self._build["slots"][slot_key] = None
            self._slot_buttons[slot_key].set_item(None)
        elif cat == "spirit_ash":
            self._build["spirit_ash"] = None
            self._ash_btn.set_item(None)
        elif cat == "tear":
            idx = int(slot_key.replace("tear", ""))
            self._build["tears"][idx] = None
            self._tear_btns[idx].set_item(None)

    # ── Spell list UI ─────────────────────────────────────────────────────────

    def _add_spell_row(self, spell):
        row = QWidget()
        row.setFixedHeight(44)
        row.setStyleSheet(f"""
            QWidget {{ background: {BG_SURFACE}; border: 1px solid {BORDER_SOLID}; border-radius: 6px; }}
            QWidget:hover {{ border-color: rgba(201,168,76,0.3); }}
        """)
        rl = QHBoxLayout(row)
        rl.setContentsMargins(10, 0, 6, 0)
        rl.setSpacing(8)

        # Left: name + type/school sub-label
        col = QVBoxLayout()
        col.setSpacing(1)
        name_lbl = QLabel(spell.get("name", ""))
        name_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 11px; font-weight: 600; background: transparent; border: none;")
        school = spell.get("school") or spell.get("type", "")
        sub_lbl = QLabel(school)
        sub_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 9px; background: transparent; border: none;")
        col.addWidget(name_lbl)
        col.addWidget(sub_lbl)
        rl.addLayout(col, 1)

        # Right: slot count + FP badges
        slots_n = spell.get("slots", 1)
        fp_n    = spell.get("fp_cost", 0)

        slot_badge = QLabel(f"{slots_n}{'▪' * slots_n}")
        slot_badge.setStyleSheet(f"color: {ACCENT_GOLD}; font-size: 9px; font-weight: 700; background: transparent; border: none;")
        slot_badge.setToolTip(f"{slots_n} memory slot{'s' if slots_n != 1 else ''}")

        fp_badge = QLabel(f"FP {fp_n}")
        fp_badge.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 9px; background: transparent; border: none;")

        del_btn = QToolButton()
        del_btn.setText("×")
        del_btn.setFixedSize(18, 18)
        del_btn.setStyleSheet(f"QToolButton {{ background: transparent; border: none; color: {TEXT_DIM}; font-size: 13px; }} QToolButton:hover {{ color: {ACCENT_RED2}; }}")
        del_btn.mouseDoubleClickEvent = lambda e: None

        spell_ref = spell
        row_ref   = row

        def _remove():
            self._build["spells"] = [s for s in self._build["spells"] if s.get("id") != spell_ref.get("id")]
            row_ref.hide()
            row_ref.setParent(None)
            row_ref.deleteLater()

        del_btn.clicked.connect(_remove)
        rl.addWidget(slot_badge)
        rl.addWidget(fp_badge)
        rl.addWidget(del_btn)
        self._spell_list_layout.addWidget(row)

    def _reset_spell_ui(self):
        while self._spell_list_layout.count():
            item = self._spell_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _reset_slot_ui(self):
        for btn in self._slot_buttons.values():
            btn.set_item(None)
        for aow_row in self._aow_rows.values():
            aow_row.set_weapon(None)
            aow_row.set_aow(None)
        for aff_row in self._affinity_rows.values():
            aff_row.hide_row()
        self._ash_btn.set_item(None)
        for tb in self._tear_btns:
            tb.set_item(None)

    # ── Save / Load ───────────────────────────────────────────────────────────

    def _save_build(self):
        build = dict(self._build)
        build["level"] = self._derived_labels["level"].text()
        for slot in WEAPON_SLOTS + ARMOR_SLOTS + TALI_SLOTS:
            item = build["slots"].get(slot)
            if item:
                build["slots"][slot] = {"id": item.get("id"), "name": item.get("name")}
        _save_build_local(build)
        self._refresh_saved_builds()
        log.info("Build saved locally: %s", build.get("name"))
        if self._api_key:
            threading.Thread(target=self._cloud_save, args=(build,), daemon=True).start()

    def _cloud_save(self, build: dict):
        try:
            from core.questlog_sync import QuestLogSync, BASE_URL
            game  = build.get("game", "elden_ring")
            slots = build.get("slots", {})
            tears = build.get("tears", [None, None])
            aows  = build.get("aow", {})
            affinities = build.get("affinities", {})

            def _id(slot_key):
                item = slots.get(slot_key)
                return item.get("id") if isinstance(item, dict) else None

            def _aow_name(slot_key):
                aow = aows.get(slot_key)
                return aow.get("name") if isinstance(aow, dict) else aow

            def _tear_name(idx):
                t = tears[idx] if len(tears) > idx else None
                return t.get("name") if isinstance(t, dict) else t

            # Nested weapons dict: {rh1: id, rh1_aow: name, rh1_affinity: str, ...}
            weapons = {}
            for ws in WEAPON_SLOTS:
                side = "rh" if ws.startswith("r") else "lh"
                num  = ws[-1]
                key  = f"{side}{num}"
                weapons[key]              = _id(ws)
                weapons[f"{key}_aow"]     = _aow_name(ws)
                weapons[f"{key}_affinity"] = affinities.get(ws, "Standard")

            # Nested armor dict: {helm: id, chest: id, gauntlet: id, leg: id}
            armor = {slot: _id(slot) for slot in ARMOR_SLOTS}

            # Talismans list: [id_or_null, id_or_null, id_or_null, id_or_null]
            talismans = [_id(f"talisman{i}") for i in range(1, 5)]

            ash = build.get("spirit_ash")
            payload = {
                "name":             build.get("name", "Untitled Build"),
                "class_id":         build.get("class_id"),
                "level":            int(build.get("level", 1)),
                "tag":              build.get("playstyle_tag", "pve"),
                "scadutree_level":  build.get("scadutree", 0),
                "stats":            {s: build.get("stats", {}).get(s, 1) for s in STAT_KEYS},
                "weapons":          weapons,
                "armor":            armor,
                "talismans":        talismans,
                "spell_ids":        [sp.get("id") for sp in build.get("spells", []) if isinstance(sp, dict)],
                "spirit_ash_name":    ash.get("name") if isinstance(ash, dict) else ash,
                "spirit_ash_upgrade": build.get("spirit_ash_upgrade", 0),
                "tear_1_name":      _tear_name(0),
                "tear_2_name":      _tear_name(1),
            }
            if game == "err":
                payload["curio_selections"] = build.get("curioSelections", {})
                payload["rune_inventory"]   = build.get("runeInventory", [])

            import requests
            r = requests.post(
                f"{BASE_URL}/api/soulslike/desktop/builds/?game={game}",
                json=payload,
                headers={"X-Listener-Key": self._api_key},
                timeout=10,
            )
            if r.ok:
                resp = r.json()
                cloud_id = resp.get("id")
                if cloud_id:
                    _update_build_cloud_id(build.get("name", ""), cloud_id)
                log.info("Cloud save OK id=%s", cloud_id)
            else:
                log.warning("Cloud save → %d %s", r.status_code, r.text[:200])
        except Exception as e:
            log.warning("Cloud save failed: %s", e)

    def _load_build(self, build: dict):
        """Restore a saved build dict into UI state."""
        game = build.get("game", "elden_ring")
        current_game = self._build.get("game", "elden_ring")
        if game != current_game and (self._data is None or self._data.game != game):
            # Switch game — reloads data, then re-applies build via _on_data_ready
            self._build = dict(build)
            self._pending_build_load = True
            idx = self._game_combo.findData(game)
            if idx >= 0:
                self._game_combo.setCurrentIndex(idx)
            return

        self._build = dict(build)
        self._build_name_input.setText(build.get("name", ""))

        # Resolve slot IDs back to full objects if data is loaded
        if self._data:
            _lookup = {
                **{s: self._data.weapons_by_id   for s in WEAPON_SLOTS},
                **{s: self._data.armor_by_id      for s in ARMOR_SLOTS},
                **{s: self._data.talismans_by_id  for s in TALI_SLOTS},
            }
            for slot in WEAPON_SLOTS + ARMOR_SLOTS + TALI_SLOTS:
                stub = self._build["slots"].get(slot)
                if stub and "id" in stub:
                    full = _lookup[slot].get(stub["id"])
                    if full:
                        self._build["slots"][slot] = full

        # Resolve class_base from live data (fixes stale all-1s from cloud-normalised saves)
        if self._data and self._build.get("class_id"):
            cls = next((c for c in self._data.classes if c.get("id") == self._build["class_id"]), None)
            if cls:
                self._build["class_name"] = cls.get("name", "")
                for s in STAT_KEYS:
                    self._build["class_base"][s] = cls.get(s, 1)

        # Ensure affinities dict exists in loaded build
        if "affinities" not in self._build:
            self._build["affinities"] = {s: "Standard" for s in WEAPON_SLOTS}
        if "aow" not in self._build:
            self._build["aow"] = {s: None for s in WEAPON_SLOTS}

        # Sync UI
        for slot, btn in self._slot_buttons.items():
            btn.set_item(self._build["slots"].get(slot))
        # Sync AoW rows for weapon slots
        for ws, aow_row in self._aow_rows.items():
            weapon = self._build["slots"].get(ws)
            aow_row.set_weapon(weapon)
            aow_row.set_aow(self._build["aow"].get(ws))
        # Resolve spirit ash name stub if needed
        ash = self._build.get("spirit_ash")
        if isinstance(ash, str) and self._data:
            ash = next((a for a in self._data.spirit_ashes if a.get("name") == ash), None)
            self._build["spirit_ash"] = ash
        self._ash_btn.set_item(ash)

        # Resolve tear name stubs if needed
        tears = self._build.get("tears", [None, None])
        if self._data:
            def _resolve_tear(t):
                if isinstance(t, str):
                    return next((x for x in self._data.tears if x.get("name") == t), None)
                return t
            tears = [_resolve_tear(t) for t in tears]
            self._build["tears"] = tears
        for i, tb in enumerate(self._tear_btns):
            tb.set_item(tears[i] if i < len(tears) else None)

        self._reset_spell_ui()
        for sp in self._build.get("spells", []):
            if self._data and isinstance(sp, dict) and "id" in sp:
                full = self._data.spells_by_id.get(sp["id"], sp)
                self._add_spell_row(full)
            elif isinstance(sp, dict):
                self._add_spell_row(sp)

        # Stats
        for key in STAT_KEYS:
            self._build["stats"][key] = build.get("stats", {}).get(key, 10)
        self._sync_stat_rows()

        # Class combo
        if self._data and build.get("class_id"):
            for i in range(self._class_combo.count()):
                cls = self._class_combo.itemData(i)
                if cls and cls.get("id") == build["class_id"]:
                    self._class_combo.setCurrentIndex(i)
                    break

        # Scadutree
        scadu = build.get("scadutree", 0)
        self._scadu_slider.setValue(scadu)
        self._scadu_lbl.setText(f"{scadu} / 20")

        # Playstyle
        self._set_tag(build.get("playstyle_tag", "pve"))

        # ERR systems
        if build.get("curioSelections") and self._curios_tab_btn.isVisible():
            self._curio_panel._selections = build["curioSelections"]
            self._curio_panel._rebuild()

        self._recalc()

    def _delete_build(self, name: str):
        # Delete from cloud first (non-blocking) if we have a cloud_id
        if self._api_key:
            for b in _list_saved_builds():
                if b.get("name") == name and b.get("cloud_id"):
                    cloud_id = b["cloud_id"]
                    game = b.get("game", "elden_ring")
                    def _do_cloud_delete(cid=cloud_id, g=game):
                        try:
                            from core.questlog_sync import QuestLogSync, BASE_URL
                            import requests
                            r = requests.delete(
                                f"{BASE_URL}/api/soulslike/desktop/builds/{cid}/",
                                headers={"X-Listener-Key": self._api_key},
                                params={"game": g},
                                timeout=10,
                            )
                            log.info("Cloud delete build %s → %d", cid, r.status_code)
                        except Exception as e:
                            log.warning("Cloud delete failed: %s", e)
                    threading.Thread(target=_do_cloud_delete, daemon=True).start()
                    break
        _delete_build_local(name)
        self._refresh_saved_builds()

    def _refresh_saved_builds(self):
        while self._saved_layout.count() > 1:
            item = self._saved_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        builds = _list_saved_builds()
        if not builds:
            ph = QLabel("No saved builds yet")
            ph.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px; background: transparent;")
            self._saved_layout.insertWidget(0, ph)
            return

        for b in builds:
            card = self._make_saved_card(b)
            self._saved_layout.insertWidget(self._saved_layout.count() - 1, card)

    def _make_saved_card(self, build):
        card = QWidget()
        card.setFixedHeight(48)
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.setStyleSheet(f"""
            QWidget {{ background: {BG_CARD}; border: 1px solid {BORDER_SOLID}; border-radius: 7px; }}
            QWidget:hover {{ border-color: rgba(201,168,76,0.4); }}
        """)
        cl = QHBoxLayout(card)
        cl.setContentsMargins(12, 0, 8, 0)
        cl.setSpacing(8)
        col = QVBoxLayout()
        col.setSpacing(2)
        name_lbl = QLabel(build.get("name", "Build"))
        name_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 12px; font-weight: 600; background: transparent;")
        game = build.get("game", "elden_ring").replace("_", " ").title()
        lvl  = build.get("level", "?")
        sub  = QLabel(f"{game}  ·  Lv {lvl}")
        sub.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; background: transparent;")
        col.addWidget(name_lbl)
        col.addWidget(sub)
        cl.addLayout(col, 1)
        del_btn = QToolButton()
        del_btn.setText("×")
        del_btn.setFixedSize(20, 20)
        del_btn.setStyleSheet(f"QToolButton {{ background: transparent; border: none; color: {TEXT_DIM}; font-size: 14px; }} QToolButton:hover {{ color: {ACCENT_RED2}; }}")
        build_name = build.get("name", "")
        del_btn.clicked.connect(lambda: self._delete_build(build_name))
        cl.addWidget(del_btn)
        card.mousePressEvent = lambda e, b=build: self._load_build(b) if e.button() == Qt.MouseButton.LeftButton else None
        return card

    # ── Start run from build ──────────────────────────────────────────────────

    def _request_start_run(self):
        self.start_run_requested.emit(dict(self._build))

    # ── Public API ────────────────────────────────────────────────────────────

    def set_api_key(self, api_key):
        self._api_key = api_key
