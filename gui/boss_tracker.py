import sys
import json
import os
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QScrollArea, QLabel, QCheckBox, QLineEdit,
    QPushButton, QFrame, QSizePolicy, QGraphicsDropShadowEffect,
    QSlider, QSpacerItem
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QPropertyAnimation, QEasingCurve, QUrl
from PyQt6.QtGui import QFont, QColor, QPalette, QPixmap, QDesktopServices, QIcon

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")
LOGO_QL     = os.path.join(ASSETS_DIR, "QL1.png")
LOGO_QL_ICO = os.path.join(ASSETS_DIR, "QL1.ico")
LOGO_CH    = os.path.join(ASSETS_DIR, "CH.png")
SITE_URL   = "https://questlog.casual-heroes.com"

SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "settings.json")

# ── Palette ────────────────────────────────────────────────────────────────
BG_BASE      = "#09090f"
BG_SURFACE   = "#0f1018"
BG_CARD      = "#13141f"
BG_CARD_HOVER= "#181926"
BORDER       = "rgba(255,255,255,0.06)"
BORDER_SOLID = "#1e1f2e"
ACCENT_GOLD  = "#c9a84c"
ACCENT_GOLD2 = "#e8c45a"
ACCENT_RED   = "#8B0000"
ACCENT_RED2  = "#c0390f"
GREEN_LIVE   = "#22c55e"
GREEN_DIM    = "#166534"
RED_LIVE     = "#ef4444"
RED_DIM      = "#7f1d1d"
TEXT_PRIMARY = "#f1f0f5"
TEXT_MUTED   = "#6b7280"
TEXT_DIM     = "#374151"
PURPLE       = "#6c5ce7"   # QuestLog brand — used sparingly as a nod

QSS = f"""
* {{
    font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
    font-size: 13px;
}}
QMainWindow, QWidget {{
    background-color: {BG_BASE};
    color: {TEXT_PRIMARY};
}}
/* ── Tabs ── */
QTabWidget::pane {{
    border: none;
    background: {BG_BASE};
}}
QTabBar {{
    background: {BG_SURFACE};
    border-bottom: 1px solid {BORDER_SOLID};
}}
QTabBar::tab {{
    background: transparent;
    color: {TEXT_MUTED};
    border: none;
    border-bottom: 2px solid transparent;
    padding: 10px 24px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1.5px;
    text-transform: uppercase;
}}
QTabBar::tab:selected {{
    color: {ACCENT_GOLD};
    border-bottom: 2px solid {ACCENT_GOLD};
}}
QTabBar::tab:hover:!selected {{
    color: {TEXT_PRIMARY};
}}
/* ── Search ── */
QLineEdit {{
    background: {BG_SURFACE};
    border: 1px solid {BORDER_SOLID};
    border-radius: 6px;
    color: {TEXT_PRIMARY};
    padding: 8px 14px;
    font-size: 13px;
    selection-background-color: {ACCENT_GOLD};
}}
QLineEdit:focus {{
    border-color: {ACCENT_GOLD};
    background: {BG_CARD};
}}
QLineEdit::placeholder {{
    color: {TEXT_DIM};
}}
/* ── Buttons ── */
QPushButton {{
    background: transparent;
    border: 1px solid {BORDER_SOLID};
    border-radius: 6px;
    color: {TEXT_MUTED};
    padding: 6px 16px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1px;
}}
QPushButton:hover {{
    border-color: {ACCENT_GOLD};
    color: {ACCENT_GOLD};
    background: rgba(201,168,76,0.06);
}}
QPushButton:checked {{
    border-color: {ACCENT_GOLD};
    color: {ACCENT_GOLD};
    background: rgba(201,168,76,0.12);
}}
/* ── Scrollbar ── */
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{
    background: {BG_BASE};
    width: 4px;
    border: none;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BORDER_SOLID};
    border-radius: 2px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: {TEXT_DIM}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
/* ── Slider ── */
QSlider::groove:horizontal {{
    background: {BORDER_SOLID};
    height: 4px;
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {ACCENT_GOLD};
    border: none;
    width: 14px;
    height: 14px;
    border-radius: 7px;
    margin: -5px 0;
}}
QSlider::sub-page:horizontal {{
    background: {ACCENT_GOLD};
    border-radius: 2px;
}}
"""


class BossRow(QWidget):
    toggled = pyqtSignal(str, bool)

    def __init__(self, key, name, location, defeated, parent=None):
        super().__init__(parent)
        self.key = key
        self._defeated = defeated
        self.setFixedHeight(44)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply_bg(defeated)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(12)

        self.check = QCheckBox()
        self.check.setChecked(defeated)
        self.check.setFixedSize(20, 20)
        self.check.setStyleSheet(f"""
            QCheckBox {{ spacing: 0; }}
            QCheckBox::indicator {{
                width: 18px; height: 18px;
                border-radius: 4px;
                border: 1.5px solid {BORDER_SOLID};
                background: {BG_BASE};
            }}
            QCheckBox::indicator:checked {{
                background: {GREEN_DIM};
                border-color: {GREEN_LIVE};
            }}
            QCheckBox::indicator:hover {{
                border-color: {ACCENT_GOLD};
            }}
        """)
        self.check.stateChanged.connect(self._on_toggle)

        self.name_lbl = QLabel(name)
        self.name_lbl.setFont(QFont("Palatino Linotype", 11))
        self.name_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self.badge = QLabel()
        self.badge.setFixedWidth(80)
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.badge.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.badge.setFixedHeight(24)
        self.badge.setStyleSheet("border-radius: 4px;")

        layout.addWidget(self.check)
        layout.addWidget(self.name_lbl)
        layout.addWidget(self.badge)

        self._apply_style(defeated)

    def _on_toggle(self, state):
        defeated = bool(state)
        self._defeated = defeated
        self._apply_style(defeated)
        self._apply_bg(defeated)
        self.toggled.emit(self.key, defeated)

    def _apply_style(self, defeated):
        if defeated:
            self.name_lbl.setStyleSheet(f"color: {GREEN_LIVE};")
            self.badge.setText("DEFEATED")
            self.badge.setStyleSheet(f"background: {GREEN_DIM}44; color: {GREEN_LIVE}; border: 1px solid {GREEN_DIM}; border-radius: 4px; padding: 0 6px; font-size: 9px; font-weight: 700; letter-spacing: 1px;")
        else:
            self.name_lbl.setStyleSheet(f"color: {TEXT_PRIMARY};")
            self.badge.setText("ALIVE")
            self.badge.setStyleSheet(f"background: {RED_DIM}44; color: {RED_LIVE}; border: 1px solid {RED_DIM}; border-radius: 4px; padding: 0 6px; font-size: 9px; font-weight: 700; letter-spacing: 1px;")

    def _apply_bg(self, defeated):
        if defeated:
            self.setStyleSheet(f"QWidget {{ background: rgba(34,197,94,0.04); border-left: 3px solid {GREEN_DIM}; }}")
        else:
            self.setStyleSheet(f"QWidget {{ background: transparent; border-left: 3px solid {RED_DIM}44; }}")

    def mousePressEvent(self, event):
        self.check.setChecked(not self.check.isChecked())

    def matches(self, query):
        return query.lower() in self.name_lbl.text().lower()

    def set_visible_by_filter(self, query):
        self.setVisible(self.matches(query) if query else True)


class RegionHeader(QWidget):
    def __init__(self, title, count, parent=None):
        super().__init__(parent)
        self.setFixedHeight(36)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)

        lbl = QLabel(title.upper())
        lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color: {TEXT_MUTED}; letter-spacing: 2px;")

        self.count_lbl = QLabel(f"0 / {count}")
        self.count_lbl.setFont(QFont("Segoe UI", 9))
        self.count_lbl.setStyleSheet(f"color: {TEXT_DIM};")

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"color: {BORDER_SOLID};")

        layout.addWidget(lbl)
        layout.addWidget(line, 1)
        layout.addWidget(self.count_lbl)
        self.setStyleSheet(f"background: {BG_BASE};")


class BossTab(QWidget):
    def __init__(self, bosses, boss_tracker, on_kill=None, accent=None, parent=None):
        super().__init__(parent)
        self.boss_tracker = boss_tracker
        self.on_kill = on_kill
        self.rows = []
        self.region_headers = {}
        self._accent = accent or ACCENT_GOLD

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        top_bar = QWidget()
        top_bar.setFixedHeight(60)
        top_bar.setStyleSheet(f"background: {BG_SURFACE}; border-bottom: 1px solid {BORDER_SOLID};")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(16, 0, 16, 0)
        top_layout.setSpacing(12)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search bosses...")
        self.search.textChanged.connect(self._filter)

        self.progress_lbl = QLabel("0 / 0")
        self.progress_lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.progress_lbl.setStyleSheet(f"color: {self._accent}; min-width: 80px;")
        self.progress_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        top_layout.addWidget(self.search)
        top_layout.addWidget(self.progress_lbl)
        outer.addWidget(top_bar)

        self.prog_track = QWidget()
        self.prog_track.setFixedHeight(3)
        self.prog_track.setStyleSheet(f"background: {BORDER_SOLID};")
        self.prog_fill = QWidget(self.prog_track)
        self.prog_fill.setFixedHeight(3)
        self.prog_fill.setStyleSheet(f"background: {self._accent};")
        self.prog_fill.setFixedWidth(0)
        outer.addWidget(self.prog_track)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        container = QWidget()
        container.setStyleSheet(f"background: {BG_BASE};")
        self.list_layout = QVBoxLayout(container)
        self.list_layout.setContentsMargins(0, 8, 0, 8)
        self.list_layout.setSpacing(0)

        from collections import OrderedDict
        by_location = OrderedDict()
        for b in bosses:
            by_location.setdefault(b["location"], []).append(b)

        for location, loc_bosses in by_location.items():
            hdr = RegionHeader(location, len(loc_bosses))
            self.region_headers[location] = {"widget": hdr, "rows": []}
            self.list_layout.addWidget(hdr)

            for b in loc_bosses:
                row = BossRow(b["key"], b["name"], b["location"], b["defeated"])
                row.toggled.connect(self._on_toggled)
                self.list_layout.addWidget(row)
                self.rows.append(row)
                self.region_headers[location]["rows"].append(row)

            spacer = QWidget()
            spacer.setFixedHeight(8)
            spacer.setStyleSheet(f"background: {BG_BASE};")
            self.list_layout.addWidget(spacer)

        self.list_layout.addStretch()
        scroll.setWidget(container)
        outer.addWidget(scroll)

        self._update_progress()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_prog_bar()

    def _on_toggled(self, key, defeated):
        if defeated:
            self.boss_tracker.mark_defeated(key)
            if self.on_kill:
                tier = self.boss_tracker.get_tier(key)
                self.on_kill(tier=tier)
        else:
            self.boss_tracker.mark_undefeated(key)
        self._update_progress()

    def _filter(self, query):
        for row in self.rows:
            row.set_visible_by_filter(query)

    def _update_progress(self):
        total    = len(self.rows)
        defeated = sum(1 for r in self.rows if r._defeated)
        self.progress_lbl.setText(f"{defeated} / {total}")
        self._update_prog_bar()
        # Update region counters
        for loc, data in self.region_headers.items():
            d = sum(1 for r in data["rows"] if r._defeated)
            t = len(data["rows"])
            data["widget"].count_lbl.setText(f"{d} / {t}")
            data["widget"].count_lbl.setStyleSheet(
                f"color: {ACCENT_GOLD};" if d == t and t > 0 else f"color: {TEXT_DIM};"
            )

    def _update_prog_bar(self):
        total    = len(self.rows)
        defeated = sum(1 for r in self.rows if r._defeated)
        pct = defeated / total if total else 0
        self.prog_fill.setFixedWidth(int(self.prog_track.width() * pct))

    def refresh(self, boss_list):
        lookup = {b["key"]: b["defeated"] for b in boss_list}
        for row in self.rows:
            if row.key in lookup:
                row.check.blockSignals(True)
                row.check.setChecked(lookup[row.key])
                row._defeated = lookup[row.key]
                row._apply_style(lookup[row.key])
                row._apply_bg(lookup[row.key])
                row.check.blockSignals(False)
        self._update_progress()


class MortalityTab(QWidget):
    def __init__(self, session=None, deaths=None, rage_label="Rage Index", parent=None):
        super().__init__(parent)
        self._session = session
        self._deaths  = deaths
        self._rage_label = rage_label

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 28, 24, 24)
        outer.setSpacing(0)

        # ── Deaths row ────────────────────────────────────────────
        deaths_row = QHBoxLayout()
        deaths_row.setSpacing(0)

        self._session_card = self._make_stat_card("SESSION DEATHS", "0")
        self._total_card   = self._make_stat_card("TOTAL DEATHS", "0")
        deaths_row.addWidget(self._session_card)
        deaths_row.addSpacing(16)
        deaths_row.addWidget(self._total_card)
        outer.addLayout(deaths_row)

        outer.addSpacing(24)

        # ── Rage bar ──────────────────────────────────────────────
        rage_label_row = QHBoxLayout()
        rage_lbl = QLabel(self._rage_label.upper())
        rage_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        rage_lbl.setStyleSheet(f"color: {TEXT_MUTED}; letter-spacing: 2px;")
        self._rage_pct_lbl = QLabel("0%")
        self._rage_pct_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self._rage_pct_lbl.setStyleSheet(f"color: {ACCENT_GOLD};")
        self._rage_pct_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        rage_label_row.addWidget(rage_lbl)
        rage_label_row.addWidget(self._rage_pct_lbl)
        outer.addLayout(rage_label_row)

        outer.addSpacing(8)

        # Bar track
        bar_track = QWidget()
        bar_track.setFixedHeight(8)
        bar_track.setStyleSheet(f"background: {BORDER_SOLID}; border-radius: 4px;")
        self._rage_bar = QWidget(bar_track)
        self._rage_bar.setFixedHeight(8)
        self._rage_bar.setStyleSheet(f"background: {ACCENT_GOLD}; border-radius: 4px;")
        self._rage_bar.setFixedWidth(0)
        self._rage_bar_track = bar_track
        outer.addWidget(bar_track)

        outer.addSpacing(12)

        # Rage state label
        self._rage_state_lbl = QLabel("Maiden's Grace")
        self._rage_state_lbl.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self._rage_state_lbl.setStyleSheet(f"color: {ACCENT_GOLD};")
        self._rage_state_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self._rage_state_lbl)

        # Hollow streak label (hidden when not hollow)
        self._hollow_lbl = QLabel("")
        self._hollow_lbl.setFont(QFont("Segoe UI", 11))
        self._hollow_lbl.setStyleSheet(f"color: {RED_LIVE}; letter-spacing: 1px;")
        self._hollow_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self._hollow_lbl)

        outer.addSpacing(28)

        # ── Secondary stats row ───────────────────────────────────
        secondary = QHBoxLayout()
        secondary.setSpacing(0)

        self._dhr_card     = self._make_stat_card("DEATHS / HR", "0.0")
        self._session_card2 = self._make_stat_card("SESSION TIME", "00:00:00")
        secondary.addWidget(self._dhr_card)
        secondary.addSpacing(16)
        secondary.addWidget(self._session_card2)
        outer.addLayout(secondary)

        outer.addStretch()

        # ── Hotkey reminder ───────────────────────────────────────
        hotkeys = QLabel("F9 = Death   ·   F10 = Kill   ·   F8 hold 3s = Reset all")
        hotkeys.setStyleSheet(f"color: {TEXT_DIM}; font-size: 10px;")
        hotkeys.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(hotkeys)

    def _make_stat_card(self, label, value):
        card = QWidget()
        card.setStyleSheet(f"""
            QWidget {{
                background: {BG_CARD};
                border: 1px solid {BORDER_SOLID};
                border-radius: 8px;
            }}
        """)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(4)

        lbl = QLabel(label)
        lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color: {TEXT_MUTED}; letter-spacing: 1.5px; background: transparent; border: none;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        val = QLabel(value)
        val.setFont(QFont("Segoe UI", 36, QFont.Weight.Bold))
        val.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent; border: none;")
        val.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(lbl)
        layout.addWidget(val)

        card._value_lbl = val
        card._label_lbl = lbl
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        return card

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_rage_bar_width()

    def _update_rage_bar_width(self):
        if self._deaths is None:
            return
        pct = self._deaths._rage_pct / 100.0
        w   = int(self._rage_bar_track.width() * pct)
        self._rage_bar.setFixedWidth(max(0, w))

    def update_stats(self, session, deaths):
        self._session = session
        self._deaths  = deaths

        self._session_card._value_lbl.setText(str(session.session_deaths))
        self._total_card._value_lbl.setText(str(session.total_deaths))
        self._session_card2._value_lbl.setText(session.elapsed_str())
        self._dhr_card._value_lbl.setText(str(deaths.deaths_per_hour()))

        pct, state, color = deaths.rage_state()
        hollow = deaths.hollow_streak()

        self._rage_pct_lbl.setText(f"{pct}%")
        self._rage_state_lbl.setText(state)
        self._rage_state_lbl.setStyleSheet(f"color: {color};")

        if hollow > 0:
            self._hollow_lbl.setText(f"Gone Hollow ×{hollow}")
            self._hollow_lbl.setVisible(True)
        else:
            self._hollow_lbl.setVisible(False)

        # Rage bar color
        bar_color = color if pct > 0 else BORDER_SOLID
        self._rage_bar.setStyleSheet(f"background: {bar_color}; border-radius: 4px;")
        self._update_rage_bar_width()


def _load_settings():
    defaults = {"opacity": 100, "pin": False, "compact": False}
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE) as f:
                return {**defaults, **json.load(f)}
        except Exception:
            pass
    return defaults

def _save_settings(settings):
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=2)


class SettingsTab(QWidget):
    opacity_changed = pyqtSignal(int)
    pin_changed     = pyqtSignal(bool)
    compact_changed = pyqtSignal(bool)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self._settings = settings

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(0)

        def section(title):
            lbl = QLabel(title.upper())
            lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            lbl.setStyleSheet(f"color: {TEXT_MUTED}; letter-spacing: 2px; margin-top: 20px; margin-bottom: 8px;")
            outer.addWidget(lbl)
            line = QFrame()
            line.setFrameShape(QFrame.Shape.HLine)
            line.setStyleSheet(f"color: {BORDER_SOLID}; margin-bottom: 16px;")
            outer.addWidget(line)

        # ── Appearance ──────────────────────────────────────────
        section("Appearance")

        # Opacity
        row = QHBoxLayout()
        row.setSpacing(16)
        opacity_lbl = QLabel("Window Opacity")
        opacity_lbl.setStyleSheet(f"color: {TEXT_PRIMARY};")
        self.opacity_val = QLabel(f"{settings['opacity']}%")
        self.opacity_val.setFixedWidth(40)
        self.opacity_val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.opacity_val.setStyleSheet(f"color: {ACCENT_GOLD}; font-weight: 700;")

        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(20, 100)
        self.opacity_slider.setValue(settings["opacity"])
        self.opacity_slider.setFixedHeight(24)
        self.opacity_slider.valueChanged.connect(self._on_opacity)

        row.addWidget(opacity_lbl)
        row.addWidget(self.opacity_slider, 1)
        row.addWidget(self.opacity_val)
        outer.addLayout(row)

        outer.addSpacing(12)

        # Hint text
        hint = QLabel("Drag to adjust transparency when pinned over the game.")
        hint.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        hint.setWordWrap(True)
        outer.addWidget(hint)

        outer.addSpacing(8)

        # Compact mode toggle
        self.compact_btn = QPushButton("COMPACT MODE")
        self.compact_btn.setCheckable(True)
        self.compact_btn.setChecked(settings.get("compact", False))
        self.compact_btn.setFixedHeight(36)
        self.compact_btn.clicked.connect(self._on_compact)
        compact_hint = QLabel("Shrinks boss rows to show more on screen.")
        compact_hint.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; margin-top: 6px;")
        outer.addWidget(self.compact_btn)
        outer.addWidget(compact_hint)

        # ── Window ──────────────────────────────────────────────
        section("Window")

        self.pin_btn = QPushButton("ALWAYS ON TOP")
        self.pin_btn.setCheckable(True)
        self.pin_btn.setChecked(settings.get("pin", False))
        self.pin_btn.setFixedHeight(36)
        self.pin_btn.clicked.connect(self._on_pin)
        pin_hint = QLabel("Keep the tracker above all other windows. Same as the PIN button in the header.")
        pin_hint.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; margin-top: 6px;")
        pin_hint.setWordWrap(True)
        outer.addWidget(self.pin_btn)
        outer.addWidget(pin_hint)

        outer.addStretch()

        # ── Footer branding ──────────────────────────────────────
        footer_row = QHBoxLayout()
        footer_row.setSpacing(10)
        footer_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        ch_lbl = QLabel()
        ch_pix = QPixmap(LOGO_CH)
        if not ch_pix.isNull():
            ch_lbl.setPixmap(ch_pix.scaledToHeight(24, Qt.TransformationMode.SmoothTransformation))
        footer_row.addWidget(ch_lbl)

        ver = QLabel("QuestLog Mortality Tracker  v1.0  ·  by Casual Heroes")
        ver.setStyleSheet(f"color: {TEXT_DIM}; font-size: 10px;")
        footer_row.addWidget(ver)

        ql_lbl = QLabel()
        ql_pix = QPixmap(LOGO_QL)
        if not ql_pix.isNull():
            ql_lbl.setPixmap(ql_pix.scaledToHeight(24, Qt.TransformationMode.SmoothTransformation))
        footer_row.addWidget(ql_lbl)

        outer.addLayout(footer_row)

        site_btn = QPushButton("questlog.casual-heroes.com")
        site_btn.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; border: none; background: transparent;")
        site_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        site_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(SITE_URL)))
        outer.addWidget(site_btn)

    def _on_opacity(self, val):
        self._settings["opacity"] = val
        self.opacity_val.setText(f"{val}%")
        _save_settings(self._settings)
        self.opacity_changed.emit(val)

    def _on_pin(self, checked):
        self._settings["pin"] = checked
        _save_settings(self._settings)
        self.pin_changed.emit(checked)

    def _on_compact(self, checked):
        self._settings["compact"] = checked
        _save_settings(self._settings)
        self.compact_changed.emit(checked)

    def sync_pin(self, checked):
        self.pin_btn.blockSignals(True)
        self.pin_btn.setChecked(checked)
        self.pin_btn.blockSignals(False)


class CompactStatsBar(QWidget):
    """Slim always-visible strip showing key mortality stats above the tabs."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(52)
        self.setStyleSheet(f"background: {BG_SURFACE}; border-bottom: 1px solid {BORDER_SOLID};")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(0)

        def stat(label, default="—"):
            col = QVBoxLayout()
            col.setSpacing(2)
            col.setContentsMargins(0, 0, 0, 0)
            lbl = QLabel(label)
            lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            lbl.setStyleSheet(f"color: {TEXT_DIM}; letter-spacing: 1.5px;")
            val = QLabel(default)
            val.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
            val.setStyleSheet(f"color: {TEXT_PRIMARY};")
            col.addWidget(lbl)
            col.addWidget(val)
            return col, val

        session_col, self._session_val = stat("SESSION DEATHS", "0")
        total_col,   self._total_val   = stat("TOTAL DEATHS",   "0")
        dhr_col,     self._dhr_val     = stat("DEATHS / HR",    "0.0")
        time_col,    self._time_val    = stat("SESSION TIME",   "00:00:00")
        rage_col,    self._rage_val    = stat("FURY",           "Calm")

        def sep():
            layout.addSpacing(20)
            line = QFrame()
            line.setFrameShape(QFrame.Shape.VLine)
            line.setFixedWidth(1)
            line.setFixedHeight(32)
            line.setStyleSheet(f"color: {BORDER_SOLID};")
            layout.addWidget(line, 0, Qt.AlignmentFlag.AlignVCenter)
            layout.addSpacing(20)

        layout.addLayout(session_col)
        sep()
        layout.addLayout(total_col)
        sep()
        layout.addLayout(dhr_col)
        sep()
        layout.addLayout(time_col)
        sep()
        layout.addLayout(rage_col)
        layout.addStretch()

    def _make_sep(self):
        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        line.setFixedWidth(1)
        line.setStyleSheet(f"color: {BORDER_SOLID};")
        return line

    def update_stats(self, session, deaths):
        self._session_val.setText(str(session.session_deaths))
        self._total_val.setText(str(session.total_deaths))
        self._dhr_val.setText(str(deaths.deaths_per_hour()))
        self._time_val.setText(session.elapsed_str())

        pct, state, color = deaths.rage_state()
        hollow = deaths.hollow_streak()
        if hollow > 0:
            self._rage_val.setText(f"HOLLOW ×{hollow}")
            self._rage_val.setStyleSheet(f"color: {RED_LIVE}; font-size: 13px; font-weight: 700;")
        else:
            label = f"{pct}% {state}" if pct > 0 else "Calm"
            self._rage_val.setText(label)
            self._rage_val.setStyleSheet(f"color: {color}; font-size: 13px; font-weight: 700;")


class BossTrackerWindow(QMainWindow):
    switch_run = pyqtSignal()

    def __init__(self, boss_tracker, run_meta, session=None, deaths=None, on_kill=None, rage_label="Rage Index"):
        super().__init__()
        self._rage_label = rage_label
        self.boss_tracker = boss_tracker
        self._run_meta = run_meta
        self._session  = session
        self._deaths   = deaths
        self.on_kill   = on_kill
        self._settings = _load_settings()

        game  = run_meta.get("game_id", "").replace("_", " ").title()
        mode  = run_meta.get("mode_id", "").replace("_", " ").title()
        rname = run_meta.get("name", "")
        self.setWindowTitle(f"{game} — {rname}")
        self.setWindowIcon(QIcon(LOGO_QL_ICO))
        self.setMinimumSize(560, 720)
        self.resize(600, 820)
        self.setStyleSheet(QSS)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ──
        header = QWidget()
        header.setFixedHeight(64)
        header.setStyleSheet(f"background: {BG_SURFACE}; border-bottom: 1px solid {BORDER_SOLID};")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(16, 0, 16, 0)
        h_layout.setSpacing(12)

        logo_lbl = QLabel()
        pix = QPixmap(LOGO_QL)
        if not pix.isNull():
            logo_lbl.setPixmap(pix.scaledToHeight(38, Qt.TransformationMode.SmoothTransformation))
        else:
            logo_lbl.setText("QL")
            logo_lbl.setStyleSheet(f"color: {ACCENT_GOLD}; font-size: 18px; font-weight: 700;")
        h_layout.addWidget(logo_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(1)
        title_col.setContentsMargins(0, 0, 0, 0)

        title_lbl = QLabel(rname.upper())
        title_lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        title_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; letter-spacing: 2px;")

        mode_lbl = QLabel(f"QuestLog Mortality Tracker  ·  {game}  ·  {mode}")
        mode_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px;")

        title_col.addWidget(title_lbl)
        title_col.addWidget(mode_lbl)
        h_layout.addLayout(title_col)
        h_layout.addStretch()

        self.switch_btn = QPushButton("SWITCH RUN")
        self.switch_btn.setFixedHeight(30)
        self.switch_btn.clicked.connect(self.switch_run.emit)

        self.pin_btn = QPushButton("PIN")
        self.pin_btn.setCheckable(True)
        self.pin_btn.setChecked(self._settings.get("pin", False))
        self.pin_btn.setFixedSize(56, 30)
        self.pin_btn.clicked.connect(self._toggle_pin)

        site_btn = QPushButton("questlog.casual-heroes.com")
        site_btn.setFixedHeight(30)
        site_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        site_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: 1px solid {BORDER_SOLID};
                border-radius: 6px; color: {TEXT_DIM};
                padding: 0 12px; font-size: 10px; letter-spacing: 0.5px;
            }}
            QPushButton:hover {{ border-color: {ACCENT_GOLD}; color: {ACCENT_GOLD}; }}
        """)
        site_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(SITE_URL)))

        h_layout.addWidget(self.switch_btn)
        h_layout.addSpacing(4)
        h_layout.addWidget(self.pin_btn)
        h_layout.addSpacing(8)
        h_layout.addWidget(site_btn)
        root.addWidget(header)

        # ── Compact stats bar ──
        self.stats_bar = CompactStatsBar()
        root.addWidget(self.stats_bar)

        # ── Tabs — built dynamically from boss groups ──
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        root.addWidget(self.tabs)

        self._boss_tabs = {}   # group_label → BossTab
        self._build_boss_tabs(boss_tracker, on_kill)

        self.mortality_tab = MortalityTab(session=session, deaths=deaths, rage_label=rage_label)
        self.settings_tab  = SettingsTab(self._settings)
        self.settings_tab.opacity_changed.connect(self._on_opacity)
        self.settings_tab.pin_changed.connect(self._apply_pin)
        self.settings_tab.compact_changed.connect(self._on_compact)

        self.tabs.addTab(self.mortality_tab, "MORTALITY")
        self.tabs.addTab(self.settings_tab,  "SETTINGS")

        self.setWindowOpacity(self._settings.get("opacity", 100) / 100.0)
        if self._settings.get("pin", False):
            self._apply_pin(True)
        if self._settings.get("compact", False):
            self._on_compact(True)

    # Short display labels for groups whose full names overflow the tab bar
    _TAB_LABELS = {
        "Mountaintops of the Giants":  "MOUNTAINTOPS",
        "Consecrated Snowfield":        "SNOWFIELD",
        "Miquella's Haligtree":         "HALIGTREE",
        "Crumbling Farum Azula":        "FARUM AZULA",
        "Liurnia of the Lakes":         "LIURNIA",
        "Shadow of the Erdtree":        "SOTE",
    }

    def _build_boss_tabs(self, boss_tracker, on_kill):
        all_bosses = boss_tracker.export()
        seen_groups = []
        by_group = {}
        for b in all_bosses:
            g = b["group"]
            if g not in by_group:
                by_group[g] = []
                seen_groups.append(g)
            by_group[g].append(b)

        for group in seen_groups:
            tab = BossTab(by_group[group], boss_tracker, on_kill=on_kill)
            label = self._TAB_LABELS.get(group, group.upper())
            self._boss_tabs[group] = tab
            self.tabs.insertTab(self.tabs.count() - 0, tab, label)

    def _toggle_pin(self, checked):
        self._settings["pin"] = checked
        _save_settings(self._settings)
        self._apply_pin(checked)
        self.settings_tab.sync_pin(checked)

    def _apply_pin(self, checked):
        flags = self.windowFlags()
        if checked:
            self.setWindowFlags(flags | Qt.WindowType.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(flags & ~Qt.WindowType.WindowStaysOnTopHint)
        self.pin_btn.blockSignals(True)
        self.pin_btn.setChecked(checked)
        self.pin_btn.blockSignals(False)
        self.show()
        # setWindowFlags recreates the native window — re-apply opacity
        self.setWindowOpacity(self._settings.get("opacity", 100) / 100.0)

    def _on_opacity(self, val):
        self._settings["opacity"] = val
        _save_settings(self._settings)
        self.setWindowOpacity(val / 100.0)

    def _on_compact(self, checked):
        height = 32 if checked else 44
        for tab in self._boss_tabs.values():
            for row in tab.rows:
                row.setFixedHeight(height)

    def refresh(self, boss_list, session=None, deaths=None):
        by_group = {}
        for b in boss_list:
            by_group.setdefault(b["group"], []).append(b)

        for group, tab in self._boss_tabs.items():
            tab.refresh(by_group.get(group, []))

        s = session or self._session
        d = deaths  or self._deaths
        if s and d:
            self.stats_bar.update_stats(s, d)
            self.mortality_tab.update_stats(s, d)


def launch_boss_tracker(boss_tracker):
    app = QApplication.instance() or QApplication(sys.argv)
    window = BossTrackerWindow(boss_tracker)
    window.show()
    return app, window
