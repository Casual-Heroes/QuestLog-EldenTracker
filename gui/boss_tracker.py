import sys
import json
import os
import time
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QScrollArea, QLabel, QCheckBox, QLineEdit,
    QPushButton, QFrame, QSizePolicy, QGraphicsDropShadowEffect,
    QSlider, QSpacerItem, QDialog, QGridLayout, QInputDialog
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QPropertyAnimation, QEasingCurve, QUrl
from PyQt6.QtGui import QFont, QColor, QPalette, QPixmap, QDesktopServices, QIcon, QImageReader

from core.paths import assets as _assets_path, data as _data_path
LOGO_QL     = _assets_path("QL1.png")
LOGO_QL_ICO = _assets_path("QL1.ico")
LOGO_CH     = _assets_path("CH.png")
LOGO_CH_ICO = _assets_path("CH.ico")


def _load_pixmap(*paths: str) -> QPixmap:
    for path in paths:
        pix = QPixmap(path)
        if not pix.isNull():
            return pix
        reader = QImageReader(path)
        image = reader.read()
        if not image.isNull():
            return QPixmap.fromImage(image)
    return QPixmap()
SITE_URL    = "https://questlog.casual-heroes.com"
GITHUB_URL  = "https://github.com/Casual-Heroes/QuestLog-EldenTracker"
APP_VERSION = "1.1.0"

SETTINGS_FILE = _data_path("settings.json")

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
    # state: 'idle' | 'focusing' | 'defeated'
    tapped = pyqtSignal(str, str, str)   # key, name, new_state
    unfocused = pyqtSignal(str, str)     # key, name -- right-click: back to idle without touching defeated/kill state
    clear_deaths_requested = pyqtSignal(str, str)  # key, name -- death badge clicked
    deaths_cleared = pyqtSignal()        # server confirmed clear -- safe to zero the badge (may fire from a bg thread via Qt's queued connection)

    # Keep toggled as alias so refresh() still works
    toggled = pyqtSignal(str, bool)

    def __init__(self, key, name, location, defeated, parent=None):
        super().__init__(parent)
        self.key      = key
        self._name    = name
        self._state   = "defeated" if defeated else "idle"
        self._defeated = defeated   # kept for compat with refresh()
        self.setFixedHeight(44)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(12)

        self._dot = QLabel()
        self._dot.setFixedSize(14, 14)

        self.name_lbl = QLabel(name)
        self.name_lbl.setFont(QFont("Palatino Linotype", 11))
        self.name_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        # Death-count pill (e.g. "5 💀") -- click to clear mis-attributed
        # deaths for this boss (server's boss/clear-deaths/, does NOT touch
        # Total Deaths). Hidden until set_death_count() reports count > 0.
        self._death_count = 0
        self.death_badge = QPushButton()
        self.death_badge.setCursor(Qt.CursorShape.PointingHandCursor)
        self.death_badge.setFixedHeight(22)
        self.death_badge.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.death_badge.setStyleSheet(
            f"QPushButton {{ background: rgba(239,68,68,0.15); color: {RED_LIVE}; "
            f"border: 1px solid {RED_DIM}; border-radius: 4px; padding: 0 8px; }}"
            f"QPushButton:hover {{ background: rgba(239,68,68,0.3); }}"
        )
        self.death_badge.setVisible(False)
        self.death_badge.setToolTip("Click to clear death attribution for this boss (doesn't affect Total Deaths)")
        self.death_badge.clicked.connect(
            lambda: self.clear_deaths_requested.emit(self.key, self._name)
        )

        self.badge = QLabel()
        self.badge.setFixedWidth(80)
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.badge.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.badge.setFixedHeight(24)

        layout.addWidget(self._dot)
        layout.addWidget(self.name_lbl)
        layout.addWidget(self.death_badge)
        layout.addWidget(self.badge)

        self._apply_state(self._state)

    def set_death_count(self, count):
        self._death_count = count
        if count > 0:
            self.death_badge.setText(f"{count} \U0001F480")
            self.death_badge.setVisible(True)
        else:
            self.death_badge.setVisible(False)

    def _apply_state(self, state):
        if state == "defeated":
            self.setStyleSheet(f"QWidget {{ background: rgba(34,197,94,0.04); border-left: 3px solid {GREEN_DIM}; }}")
            self._dot.setStyleSheet(f"background: {GREEN_LIVE}; border-radius: 7px;")
            self.name_lbl.setStyleSheet(f"color: {GREEN_LIVE};")
            self.badge.setText("DEFEATED")
            self.badge.setStyleSheet(f"background: {GREEN_DIM}44; color: {GREEN_LIVE}; border: 1px solid {GREEN_DIM}; border-radius: 4px; padding: 0 6px; font-size: 9px; font-weight: 700; letter-spacing: 1px;")
        elif state == "focusing":
            self.setStyleSheet(f"QWidget {{ background: rgba(192,57,15,0.08); border-left: 3px solid {ACCENT_RED2}; }}")
            self._dot.setStyleSheet(f"background: {ACCENT_RED2}; border-radius: 7px;")
            self.name_lbl.setStyleSheet(f"color: {ACCENT_RED2};")
            self.badge.setText("FIGHTING")
            self.badge.setStyleSheet(f"background: rgba(192,57,15,0.15); color: {ACCENT_RED2}; border: 1px solid {ACCENT_RED2}; border-radius: 4px; padding: 0 6px; font-size: 9px; font-weight: 700; letter-spacing: 1px;")
        else:  # idle
            self.setStyleSheet(f"QWidget {{ background: transparent; border-left: 3px solid {BORDER_SOLID}; }}")
            self._dot.setStyleSheet(f"background: {TEXT_DIM}; border-radius: 7px;")
            self.name_lbl.setStyleSheet(f"color: {TEXT_PRIMARY};")
            self.badge.setText("ALIVE")
            self.badge.setStyleSheet(f"background: {RED_DIM}44; color: {RED_LIVE}; border: 1px solid {RED_DIM}; border-radius: 4px; padding: 0 6px; font-size: 9px; font-weight: 700; letter-spacing: 1px;")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            # Right-click: instant unfocus, no cycling required to back out
            # of "focusing". Only meaningful while actively focused -- does
            # NOT touch defeated/kill state, unlike the left-click cycle's
            # idle step (which is really "undo defeat").
            if self._state == "focusing":
                self.set_state("idle")
                self.unfocused.emit(self.key, self._name)
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        # 3-state cycle: idle → focusing → defeated → idle
        if self._state == "idle":
            next_state = "focusing"
        elif self._state == "focusing":
            next_state = "defeated"
        else:
            next_state = "idle"
        self.set_state(next_state)
        self.tapped.emit(self.key, self._name, next_state)

    def mouseDoubleClickEvent(self, event):
        pass

    def set_state(self, state):
        self._state   = state
        self._defeated = (state == "defeated")
        self._apply_state(state)

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
    def __init__(self, bosses, boss_tracker, on_kill=None, accent=None, api=None,
                 on_boss_mark=None, ql_sync=None, parent=None):
        super().__init__(parent)
        self.boss_tracker  = boss_tracker
        self.on_kill       = on_kill
        self._api          = api
        self._ql_sync      = ql_sync       # QuestLogSync instance for focus/unmark calls
        self._on_boss_mark = on_boss_mark  # callback(boss_key) → fires mark_boss, returns rage data
        self.rows = []
        self._focused_key = None  # key of the currently-focused BossRow, if any -- lets hotkey-driven focus/unfocus find and restyle the right row without a click event
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

        # Focus banner — shown when a boss is in "focusing" state
        self._focus_banner = QWidget()
        self._focus_banner.setFixedHeight(32)
        self._focus_banner.setStyleSheet(f"background: rgba(192,57,15,0.15); border-bottom: 1px solid {ACCENT_RED2};")
        _fb_layout = QHBoxLayout(self._focus_banner)
        _fb_layout.setContentsMargins(16, 0, 16, 0)
        self._focus_lbl = QLabel("")
        self._focus_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self._focus_lbl.setStyleSheet(f"color: {ACCENT_RED2}; letter-spacing: 1px;")
        _fb_layout.addWidget(self._focus_lbl)
        self._focus_banner.setVisible(False)
        outer.addWidget(self._focus_banner)

        self.prog_track = QWidget()
        self.prog_track.setFixedHeight(3)
        self.prog_track.setStyleSheet(f"background: {BORDER_SOLID};")
        self.prog_fill = QWidget(self.prog_track)
        self.prog_fill.setFixedHeight(3)
        self.prog_fill.setStyleSheet(f"background: {self._accent};")
        self.prog_fill.setFixedWidth(0)
        outer.addWidget(self.prog_track)

        # Internal capped-height QScrollArea, matching the site: Boss
        # Progress is its own scrollable box (not the full boss list flowing
        # into the page), so the outer RunOverviewTab page stays a
        # reasonable length and Items doesn't end up dozens of screens down.
        container = QWidget()
        container.setStyleSheet(f"background: {BG_BASE};")
        self.list_layout = QVBoxLayout(container)
        self.list_layout.setContentsMargins(0, 8, 0, 8)
        self.list_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFixedHeight(360)
        scroll.setWidget(container)

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
                row.tapped.connect(self._on_tapped)
                row.unfocused.connect(self._on_unfocused)
                row.clear_deaths_requested.connect(self._on_clear_deaths_requested)
                row.deaths_cleared.connect(lambda r=row: r.set_death_count(0))
                self.list_layout.addWidget(row)
                self.rows.append(row)
                self.region_headers[location]["rows"].append(row)

            spacer = QWidget()
            spacer.setFixedHeight(8)
            spacer.setStyleSheet(f"background: {BG_BASE};")
            self.list_layout.addWidget(spacer)

        self.list_layout.addStretch()
        outer.addWidget(scroll)

        self._update_progress()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_prog_bar()

    def _on_tapped(self, key, name, new_state):
        import threading
        if new_state == "focusing":
            # Tap 1: set focus — send both boss_name (human label) and boss_key
            # (unique identifier). boss_key matters: several bosses share a
            # boss_name across different locations (e.g. "Erdtree Avatar" in
            # 6 different areas) -- name alone lets death attribution bleed
            # across unrelated fights.
            self._focus_lbl.setText(f"  ⚔ Fighting: {name}")
            self._focus_banner.setVisible(True)
            self._focused_key = key
            if self._ql_sync:
                threading.Thread(target=self._ql_sync.set_focus, args=(name, key), daemon=True).start()

        elif new_state == "defeated":
            # Tap 2: mark defeated — send boss_key ("Name (Location)")
            self._focus_banner.setVisible(False)
            self._focused_key = None
            self.boss_tracker.mark_defeated(key)
            if self.on_kill and not self._ql_sync:
                self.on_kill(tier=self.boss_tracker.get_tier(key))
            if self._on_boss_mark:
                self._on_boss_mark(key)   # handles mark_boss + rage update
            elif self._ql_sync:
                threading.Thread(target=self._ql_sync.mark_boss, args=(key,), daemon=True).start()

        else:  # idle — undo defeat
            # Tap 3: unmark — send boss_key, clear focus
            self._focus_banner.setVisible(False)
            self._focused_key = None
            self.boss_tracker.mark_undefeated(key)
            if self._ql_sync:
                threading.Thread(target=self._ql_sync.unmark_boss, args=(key,), daemon=True).start()
                threading.Thread(target=self._ql_sync.clear_focus, daemon=True).start()

        self._update_progress()

    def _on_unfocused(self, key, name):
        """
        Right-click on a FIGHTING row: back out of focus instantly, no death/
        kill/defeat state touched -- distinct from the left-click idle step
        above (which is "undo defeat"). Matches the doc's "right-click a
        focused boss = instant unfocus" UX.
        """
        self._focus_banner.setVisible(False)
        self._focused_key = None
        if self._ql_sync:
            threading.Thread(target=self._ql_sync.clear_focus, daemon=True).start()

    def _on_clear_deaths_requested(self, key, name):
        """
        Death badge clicked: clear mis-attributed deaths for this boss
        (server's boss/clear-deaths/). Does NOT touch Total Deaths -- the
        deaths still happened, only the boss tag on them was wrong (mis-
        click, testing, wrong boss picked). Confirm first since this can't
        be undone from the UI.
        """
        from PyQt6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, "Clear boss deaths?",
            f"Clear death attribution for \"{name}\"?\n\n"
            "This removes the death count shown on this boss, but does NOT "
            "reduce your Total Deaths -- those deaths still happened, only "
            "the boss tag was wrong.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        if self._ql_sync:
            row = next((r for r in self.rows if r.key == key), None)
            def _on_done(_resp):
                # Runs on the sync's background thread -- emit a signal
                # rather than touching the widget directly (Qt signals
                # crossing threads are queued to the receiving object's
                # thread automatically, unlike a raw method call).
                if row:
                    row.deaths_cleared.emit()
            self._ql_sync.clear_boss_deaths(key, on_done=_on_done)

    def focus_boss(self, key, name):
        """
        Programmatic focus (e.g. from the focus hotkey's picker dialog) --
        same effect as clicking a row into "focusing" state, including
        restyling that row. Unfocuses whatever was previously focused first
        (only one boss can be focused at a time).
        """
        import threading
        if self._focused_key and self._focused_key != key:
            for row in self.rows:
                if row.key == self._focused_key and row._state == "focusing":
                    row.set_state("idle")
        for row in self.rows:
            if row.key == key:
                row.set_state("focusing")
        self._focus_lbl.setText(f"  ⚔ Fighting: {name}")
        self._focus_banner.setVisible(True)
        self._focused_key = key
        if self._ql_sync:
            threading.Thread(target=self._ql_sync.set_focus, args=(name, key), daemon=True).start()

    def unfocus_current(self):
        """Programmatic unfocus (e.g. from the unfocus hotkey) -- no-op if nothing is focused."""
        import threading
        if not self._focused_key:
            return
        for row in self.rows:
            if row.key == self._focused_key and row._state == "focusing":
                row.set_state("idle")
        self._focus_banner.setVisible(False)
        self._focused_key = None
        if self._ql_sync:
            threading.Thread(target=self._ql_sync.clear_focus, daemon=True).start()

    def defeat_current(self):
        """Programmatic kill confirm -- marks the focused boss defeated."""
        if not self._focused_key:
            return False
        for row in self.rows:
            if row.key == self._focused_key:
                row.set_state("defeated")
                self._on_tapped(row.key, row._name, "defeated")
                return True
        return False

    def undefeated_bosses(self):
        """Returns [(key, name), ...] for bosses not yet marked defeated -- feeds the focus picker dialog."""
        return [(row.key, row._name) for row in self.rows if row._state != "defeated"]

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
        lookup = {b["key"]: b for b in boss_list}
        for row in self.rows:
            b = lookup.get(row.key)
            if b is None:
                continue
            defeated = b["defeated"]
            # Don't clobber "focusing" state with a refresh — only sync defeated/idle
            if defeated and row._state != "defeated":
                row.set_state("defeated")
            elif not defeated and row._state == "defeated":
                row.set_state("idle")
            if "deaths" in b:
                row.set_death_count(b["deaths"])
        self._update_progress()


class BossFocusPickerDialog(QDialog):
    """
    Focus hotkey opens this: a searchable list of undefeated bosses to focus
    on, without needing to scroll to the right region tab and click the
    row. Selecting an entry calls BossTab.focus_boss() the same as clicking
    a row would. Only lists undefeated bosses -- a defeated boss isn't
    something you'd need to focus on again.
    """
    def __init__(self, undefeated_bosses, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Focus Boss")
        self.setMinimumSize(420, 480)
        self.setStyleSheet(QSS)
        self._selected = None  # (key, name), set on accept

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title = QLabel("Which boss are you fighting?")
        title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {TEXT_PRIMARY};")
        layout.addWidget(title)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search bosses...")
        self.search.textChanged.connect(self._filter)
        layout.addWidget(self.search)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none;")
        container = QWidget()
        self._list_layout = QVBoxLayout(container)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(0)

        self._buttons = []
        for key, name in undefeated_bosses:
            btn = QPushButton(name)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    text-align: left; padding: 10px 12px; border: none;
                    background: transparent; color: {TEXT_PRIMARY}; font-size: 13px;
                }}
                QPushButton:hover {{ background: {BG_CARD_HOVER}; }}
            """)
            btn.clicked.connect(lambda _, k=key, n=name: self._choose(k, n))
            self._list_layout.addWidget(btn)
            self._buttons.append((btn, name))

        self._list_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll)

        self.search.setFocus()

    def _filter(self, query):
        q = query.lower()
        for btn, name in self._buttons:
            btn.setVisible(q in name.lower())

    def _choose(self, key, name):
        self._selected = (key, name)
        self.accept()

    @staticmethod
    def pick(undefeated_bosses, parent=None):
        """Returns (key, name) if the user picked one, else None."""
        dlg = BossFocusPickerDialog(undefeated_bosses, parent)
        dlg.exec()
        return dlg._selected


class MortalityTab(QWidget):
    sig_add_death      = pyqtSignal()
    sig_subtract_death = pyqtSignal()
    sig_reset_deaths   = pyqtSignal()
    sig_set_total_deaths = pyqtSignal(int)
    sig_set_session_deaths = pyqtSignal(int)
    sig_reset_bosses   = pyqtSignal()
    sig_focus_boss     = pyqtSignal()   # button equivalent of the focus hotkey -- opens the picker
    sig_unfocus_boss   = pyqtSignal()   # button equivalent of the unfocus hotkey
    sig_end_run        = pyqtSignal()   # explicit "End Run" -- ends server-side, keeps app/window open
    sig_submit_leaderboard = pyqtSignal()   # "Submit to Leaderboard" -- only enabled once ended

    def __init__(self, session=None, deaths=None, rage_label="Rage Index", parent=None):
        super().__init__(parent)
        self._session = session
        self._deaths  = deaths
        self._rage_label = rage_label
        self._ended     = False   # run has been explicitly ended (server-side + meta.json)
        self._submitted = False   # run has been submitted to the leaderboard (one-shot)
        self._can_submit = False  # whether Submit is even applicable (cloud-synced run w/ a token)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 28, 24, 24)
        outer.setSpacing(0)

        # ── Stat card grid ────────────────────────────────────────
        # Matches the site's layout exactly: TOTAL DEATHS / THIS SESSION /
        # DEATHS-BOSS, CURRENT BOSS / BOSS DEATHS / EVERYTHING ELSE,
        # DEATHS-HR SESSION / DEATHS-HR RUN, CURRENT STREAK / LONGEST LIFE /
        # ITEMS FOUND, SESSION TIME / RUN DURATION -- 3 cards per row where
        # the site has 3, 2 where the site has 2. CompactStatsBar (the thin
        # strip above the tabs) was removed entirely since the site has no
        # equivalent element -- this grid is the ONLY place these numbers
        # live now, not a duplicate of a second summary bar.
        grid = QGridLayout()
        grid.setSpacing(16)

        self._total_card       = self._make_stat_card("TOTAL DEATHS", "0")
        self._session_card     = self._make_stat_card("THIS SESSION", "0")
        self._dhr_card         = self._make_stat_card("DEATHS / BOSS", "--")
        self._current_boss_card = self._make_stat_card("CURRENT BOSS", "0")
        self._boss_deaths_card = self._make_stat_card("BOSS DEATHS", "0")
        self._non_boss_deaths_card = self._make_stat_card("EVERYTHING ELSE", "0")
        self._session_dph_card = self._make_stat_card("DEATHS / HR (SESSION)", "--")
        self._run_dph_card     = self._make_stat_card("DEATHS / HR (RUN)", "--")
        self._streak_card      = self._make_stat_card("CURRENT STREAK", "00:00:00")
        self._longest_card     = self._make_stat_card("LONGEST LIFE", "00:00")
        self._items_card       = self._make_stat_card("ITEMS FOUND", "0/0")
        self._session_card2    = self._make_stat_card("SESSION TIME", "00:00:00")
        self._survival_card    = self._make_stat_card("RUN DURATION", "--")

        grid.addWidget(self._total_card, 0, 0)
        grid.addWidget(self._session_card, 0, 1)
        grid.addWidget(self._dhr_card, 0, 2)
        grid.addWidget(self._current_boss_card, 1, 0)
        grid.addWidget(self._boss_deaths_card, 1, 1)
        grid.addWidget(self._non_boss_deaths_card, 1, 2)
        grid.addWidget(self._session_dph_card, 2, 0)
        grid.addWidget(self._run_dph_card, 2, 1)
        grid.addWidget(self._streak_card, 3, 0)
        grid.addWidget(self._longest_card, 3, 1)
        grid.addWidget(self._items_card, 3, 2)
        grid.addWidget(self._session_card2, 4, 0)
        grid.addWidget(self._survival_card, 4, 1)
        outer.addLayout(grid)

        outer.addSpacing(20)

        # ── Manual controls ───────────────────────────────────────
        # Matches the site: one primary LOG DEATH button, then a
        # secondary Undo / Full Reset row. Reset Bosses / Focus / Unfocus
        # aren't shown on the site's equivalent page, but the desktop app
        # still needs a UI path to them (mouse users without the hotkeys
        # hotkeys) -- kept as a smaller row below the site-matching buttons
        # rather than dropped, since that functionality has no other home.
        def _action_btn(label, color=None):
            btn = QPushButton(label)
            btn.setFixedHeight(36)
            base = color or BG_SURFACE
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {base};
                    color: {TEXT_PRIMARY};
                    border: 1px solid {BORDER_SOLID};
                    border-radius: 6px;
                    font-size: 11px;
                    font-weight: 700;
                    letter-spacing: 1px;
                }}
                QPushButton:hover {{ background: {BG_CARD_HOVER}; border-color: {ACCENT_GOLD}; }}
                QPushButton:pressed {{ background: {BG_BASE}; }}
            """)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            return btn

        # One row -- LOG DEATH (wide, red) + Undo + Full Reset side by side,
        # matching the site exactly (not LOG DEATH as its own full-width row
        # above a separate Undo/Reset row).
        self.log_death_btn = QPushButton("💀  LOG DEATH")
        self.log_death_btn.setFixedHeight(44)
        self.log_death_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.log_death_btn.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT_RED};
                color: {TEXT_PRIMARY};
                border: 1px solid {ACCENT_RED2};
                border-radius: 6px;
                font-size: 13px;
                font-weight: 700;
                letter-spacing: 1px;
            }}
            QPushButton:hover {{ background: #d94418; }}
            QPushButton:pressed {{ background: {ACCENT_RED2}; }}
            QPushButton:disabled {{ background: {BG_SURFACE}; color: {TEXT_DIM}; border-color: {BORDER_SOLID}; }}
        """)
        self.log_death_btn.clicked.connect(self.sig_add_death)

        self.undo_btn = _action_btn("↺ Undo")
        self.undo_btn.setFixedHeight(44)
        self.full_reset_btn = _action_btn("⟳ Full Reset")
        self.full_reset_btn.setFixedHeight(44)
        self.undo_btn.clicked.connect(self.sig_subtract_death)
        self.full_reset_btn.clicked.connect(self.sig_reset_deaths)

        undo_reset_row = QHBoxLayout()
        undo_reset_row.setSpacing(8)
        undo_reset_row.addWidget(self.log_death_btn, 2)
        undo_reset_row.addWidget(self.undo_btn, 1)
        undo_reset_row.addWidget(self.full_reset_btn, 1)
        outer.addLayout(undo_reset_row)

        outer.addSpacing(8)

        secondary_row = QHBoxLayout()
        secondary_row.setSpacing(8)
        self.reset_bosses_btn = _action_btn("RESET BOSSES")
        self.set_total_btn = _action_btn("SET TOTAL")
        self.set_session_btn = _action_btn("SET SESSION")
        focus_btn   = _action_btn("⚔ FOCUS BOSS")
        unfocus_btn = _action_btn("UNFOCUS")
        self.reset_bosses_btn.clicked.connect(self.sig_reset_bosses)
        self.set_total_btn.clicked.connect(self._prompt_set_total_deaths)
        self.set_session_btn.clicked.connect(self._prompt_set_session_deaths)
        focus_btn.clicked.connect(self.sig_focus_boss)
        unfocus_btn.clicked.connect(self.sig_unfocus_boss)
        secondary_row.addWidget(self.reset_bosses_btn)
        secondary_row.addWidget(self.set_total_btn)
        secondary_row.addWidget(self.set_session_btn)
        secondary_row.addWidget(focus_btn)
        secondary_row.addWidget(unfocus_btn)
        outer.addLayout(secondary_row)

        outer.addSpacing(8)

        # ── End Run / Submit to Leaderboard ────────────────────────
        # Distinct from SWITCH RUN (header button) / closing the window --
        # those already end the run implicitly via App._stop_active(); this
        # is an explicit, separate action that keeps the app/window open.
        end_run_row = QHBoxLayout()
        end_run_row.setSpacing(8)
        self.end_run_btn = _action_btn("⏹ END RUN", color=BG_SURFACE)
        self.end_run_btn.clicked.connect(self.sig_end_run)
        self.submit_leaderboard_btn = _action_btn("🏆 SUBMIT TO LEADERBOARD", color=ACCENT_GOLD)
        self.submit_leaderboard_btn.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT_GOLD};
                color: {BG_BASE};
                border: 1px solid {ACCENT_GOLD2};
                border-radius: 6px;
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 1px;
            }}
            QPushButton:hover {{ background: {ACCENT_GOLD2}; }}
            QPushButton:pressed {{ background: {ACCENT_GOLD}; }}
            QPushButton:disabled {{ background: {BG_SURFACE}; color: {TEXT_DIM}; border-color: {BORDER_SOLID}; }}
        """)
        self.submit_leaderboard_btn.clicked.connect(self.sig_submit_leaderboard)
        self.submit_leaderboard_btn.setVisible(False)   # only shown once ended
        end_run_row.addWidget(self.end_run_btn, 1)
        end_run_row.addWidget(self.submit_leaderboard_btn, 1)
        outer.addLayout(end_run_row)

        outer.addSpacing(12)

        # ── Hotkey reminder ───────────────────────────────────────
        hotkeys = QLabel("Hotkeys configurable in Settings tab")
        hotkeys.setStyleSheet(f"color: {TEXT_DIM}; font-size: 10px;")
        hotkeys.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(hotkeys)

        outer.addSpacing(20)

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

    def _prompt_set_total_deaths(self):
        current = self._session.total_deaths if self._session else 0
        value, ok = QInputDialog.getInt(
            self, "Set Total Deaths", "Total deaths:", int(current), 0, 999999, 1
        )
        if ok:
            self.sig_set_total_deaths.emit(value)

    def _prompt_set_session_deaths(self):
        current = self._session.session_deaths if self._session else 0
        value, ok = QInputDialog.getInt(
            self, "Set Session Deaths", "Session deaths:", int(current), 0, 999999, 1
        )
        if ok:
            self.sig_set_session_deaths.emit(value)

    def set_ended(self, ended: bool):
        """
        Reflects a run's ended state in the UI -- disables death-logging
        controls (an ended run shouldn't accept new deaths) and reveals the
        Submit button. Called both right after the user clicks END RUN and
        when restoring a previously-ended run's state from meta.json on
        load, so it must be idempotent / safe to call redundantly.
        """
        self._ended = ended
        self.log_death_btn.setEnabled(not ended)
        self.undo_btn.setEnabled(not ended)
        self.full_reset_btn.setEnabled(not ended)
        self.reset_bosses_btn.setEnabled(not ended)
        self.set_total_btn.setEnabled(not ended)
        self.set_session_btn.setEnabled(not ended)
        self.end_run_btn.setEnabled(not ended)
        self.end_run_btn.setText("ENDED" if ended else "⏹ END RUN")
        self.submit_leaderboard_btn.setVisible(ended and self._can_submit and not self._submitted)

    def set_can_submit(self, can_submit: bool):
        """Whether Submit is even applicable -- only cloud-synced runs with a questlog_token."""
        self._can_submit = can_submit
        self.submit_leaderboard_btn.setVisible(self._ended and can_submit and not self._submitted)

    def set_submitted(self, submitted: bool):
        self._submitted = submitted
        if submitted:
            self.submit_leaderboard_btn.setVisible(False)
        self.submit_leaderboard_btn.setEnabled(not submitted)

    def _make_stat_card(self, label, value, sub=None):
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
        card._sub_lbl   = None

        if sub is not None:
            sub_lbl = QLabel(sub)
            sub_lbl.setFont(QFont("Segoe UI", 8))
            sub_lbl.setStyleSheet(f"color: {TEXT_MUTED}; background: transparent; border: none;")
            sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(sub_lbl)
            card._sub_lbl = sub_lbl

        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        return card

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_rage_bar_width()

    def _update_rage_bar_width(self, pct_override=None):
        if self._deaths is None:
            return
        pct = (self._deaths._rage_pct if pct_override is None else pct_override) / 100.0
        w   = int(self._rage_bar_track.width() * pct)
        self._rage_bar.setFixedWidth(max(0, w))

    def update_timing(self, streak_sec, longest_sec, started_at=None,
                       lifetime_playtime_sec=None, server_authoritative=False):
        def _fmt(s):
            return f"{s//3600:02}:{(s%3600)//60:02}:{s%60:02}"
        self._streak_card._value_lbl.setText(_fmt(streak_sec))
        self._longest_card._value_lbl.setText(_fmt(longest_sec))
        if server_authoritative:
            # Server is the ONLY source of truth for Run Duration when
            # connected -- it only accumulates while the listener is
            # connected AND the game exe is detected running (see
            # QuestLogSync/_heartbeat). Never fall back to local wall-clock
            # math here: that math has no idea whether the exe is running,
            # so it would silently tick every second the app window is
            # open, exe or no exe -- exactly the bug this replaces. The
            # server's raw seconds value is still the source of truth --
            # only the day-formatting is done client-side (to match the
            # site's "3d 13:35" display), since the server was sending a
            # flat HH:MM:SS string with no day rollover.
            if lifetime_playtime_sec is None:
                self._survival_card._value_lbl.setText("--")
            else:
                self._survival_card._value_lbl.setText(_days_hours_display(lifetime_playtime_sec))
        else:
            self._survival_card._value_lbl.setText(_run_duration_display(started_at))

    def update_stats(self, session, deaths, ql_sync=None, bosses_defeated=0):
        self._session = session
        self._deaths  = deaths

        self._total_card._value_lbl.setText(str(session.total_deaths))
        self._session_card._value_lbl.setText(str(session.session_deaths))
        self._session_card2._value_lbl.setText(session.elapsed_str())

        server_rate = ql_sync.get_true_death_rate() if ql_sync else None
        _dpb = server_rate if server_rate is not None else deaths.deaths_per_boss(bosses_defeated)
        self._dhr_card._value_lbl.setText(str(_dpb))

        if ql_sync:
            boss_deaths, non_boss_deaths = ql_sync.get_death_split()
            self._boss_deaths_card._value_lbl.setText(str(boss_deaths))
            self._non_boss_deaths_card._value_lbl.setText(str(non_boss_deaths))

            session_dph, run_dph = ql_sync.get_deaths_per_hour()
            if session_dph is None:
                session_sec = ql_sync.session_time_sec()
                if session_sec > 0:
                    session_dph = session.session_deaths / (session_sec / 3600)
            self._session_dph_card._value_lbl.setText(
                f"{session_dph:.1f}" if session_dph is not None else "--"
            )
            self._run_dph_card._value_lbl.setText(
                f"{run_dph:.1f}" if run_dph is not None else "--"
            )

            # CURRENT BOSS -- deaths against whichever boss is currently
            # focused, 0 if nothing is focused right now (matches the site:
            # this tile always shows a number, not the boss's name).
            current_key = ql_sync.get_current_boss_key()
            current_boss_deaths = 0
            if current_key:
                for b in ql_sync.get_bosses():
                    if b.get("key") == current_key:
                        current_boss_deaths = b.get("deaths", 0)
                        break
            self._current_boss_card._value_lbl.setText(str(current_boss_deaths))

            items, collected, total = ql_sync.get_items()
            self._items_card._value_lbl.setText(f"{collected}/{total}")
        else:
            session_sec = session.elapsed_seconds()
            session_dph = session.session_deaths / (session_sec / 3600) if session_sec > 0 else None
            self._session_dph_card._value_lbl.setText(
                f"{session_dph:.1f}" if session_dph is not None else "--"
            )
            self._run_dph_card._value_lbl.setText("--")
            self._boss_deaths_card._value_lbl.setText("0")
            self._non_boss_deaths_card._value_lbl.setText(str(session.total_deaths))
            self._current_boss_card._value_lbl.setText("0")

        if ql_sync:
            pct, state, hollow = ql_sync.get_rage_state()
            pct = int(max(0, min(100, pct)))
            if hollow > 0:
                pct = 100
                state = "HOLLOW"
            if str(state).upper() == "HOLLOW" or pct >= 100:
                color = "#FF0000"
                state = "HOLLOW"
            elif pct >= 75:
                color = "#8B0000"
            elif pct >= 50:
                color = "#C0390F"
            elif pct >= 25:
                color = "#E07B00"
            else:
                color = "#C9A84C"
        else:
            pct, state, color = deaths.rage_state()
            hollow = deaths.hollow_streak()

        self._rage_pct_lbl.setText(f"{pct}%")
        # State label now carries its own percentage inline (e.g. "Maiden's
        # Grace · 0%") instead of relying on the reader to separately look at
        # the header row's "0%" on the far right of the bar.
        self._rage_state_lbl.setText(f"{state}  ·  {pct}%")
        self._rage_state_lbl.setStyleSheet(f"color: {color};")

        if ql_sync and hollow > 0:
            hollow += 1
        if hollow > 0:
            self._hollow_lbl.setText(f"Gone Hollow ×{hollow}")
            self._hollow_lbl.setVisible(True)
        else:
            self._hollow_lbl.setVisible(False)

        # Rage bar color
        bar_color = color if pct > 0 else BORDER_SOLID
        self._rage_bar.setStyleSheet(f"background: {bar_color}; border-radius: 4px;")
        self._update_rage_bar_width(pct)


_KEYRING_SERVICE = "QuestLog-EldenTracker"
_KEYRING_USER    = "api_key"

def _keyring_save(api_key: str):
    try:
        import keyring
        keyring.set_password(_KEYRING_SERVICE, _KEYRING_USER, api_key)
        return True
    except Exception:
        return False

def _keyring_load() -> str:
    try:
        import keyring
        val = keyring.get_password(_KEYRING_SERVICE, _KEYRING_USER)
        return val or ""
    except Exception:
        return ""


def _days_hours_display(total_sec):
    """Xd HH:MM past a day, HH:MM:SS under a day -- matches the site's Run
    Duration formatting, which rolls over to days instead of ever-growing
    triple-digit hours."""
    total_sec = max(0, int(total_sec))
    days  = total_sec // 86400
    hours = (total_sec % 86400) // 3600
    mins  = (total_sec % 3600) // 60
    if days > 0:
        return f"{days}d {hours:02d}:{mins:02d}"
    secs = total_sec % 60
    return f"{hours:02d}:{mins:02d}:{secs:02d}"


def _run_duration_display(started_at):
    if not started_at:
        return "--"
    elapsed = int(time.time()) - int(started_at)
    return _days_hours_display(elapsed)


def _load_settings():
    defaults = {
        "opacity":         100,
        "pin":             False,
        "compact":         False,
        "hotkey_death":    "f9",
        "hotkey_subtract": "f10",
        "hotkey_reset":    "f8",
        "hotkey_focus":    "f4",
        "hotkey_unfocus":  "f5",
        "hotkey_defeat":   "f11",
        "save_file_path":  "",
        "api_key":         "",
        "session_token":   "",
        "username":        "",
    }
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE) as f:
                data = {**defaults, **json.load(f)}
        except Exception:
            data = defaults
    else:
        data = defaults

    # Prefer keyring for api_key; fall back to whatever is in settings.json
    kr_key = _keyring_load()
    if kr_key:
        data["api_key"] = kr_key
    return data


def _save_settings(settings):
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    # Persist api_key to keyring; strip it from the JSON file
    api_key = settings.get("api_key", "")
    if api_key:
        saved_to_keyring = _keyring_save(api_key)
    else:
        saved_to_keyring = False
    on_disk = dict(settings)
    if saved_to_keyring:
        on_disk.pop("api_key", None)  # don't duplicate in plaintext
    with open(SETTINGS_FILE, "w") as f:
        json.dump(on_disk, f, indent=2)


class ItemsTab(QWidget):
    """Item collection checklist — loaded from QuestLog status API."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ql_sync   = None
        self._local_run = None
        self._rows      = {}   # item_name → (widget, collected_state)
        # A click optimistically flips a row immediately, but the next few
        # refresh() calls read from ql_sync's status-poll cache, which only
        # updates every ~6s -- for that window, refresh() was clobbering the
        # just-clicked row back to its stale pre-click state (the visible
        # "checks, flickers unchecked, then re-checks" bug), since refresh()
        # trusted the server snapshot unconditionally. Track what the user
        # just set per item and skip overwriting it until either the server
        # snapshot agrees or a timeout passes (in case the POST silently
        # failed and the server genuinely never gets the new state).
        self._pending = {}   # item_name -> (desired_collected_bool, expires_at_monotonic)
        self._PENDING_TIMEOUT_SEC = 10

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header bar ───────────────────────────────────────────────────────
        hdr = QWidget()
        hdr.setFixedHeight(48)
        hdr.setStyleSheet(f"background: {BG_SURFACE}; border-bottom: 1px solid {BORDER_SOLID};")
        hdr_l = QHBoxLayout(hdr)
        hdr_l.setContentsMargins(20, 0, 20, 0)

        self._title_lbl = QLabel("ITEMS")
        self._title_lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self._title_lbl.setStyleSheet(f"color: {ACCENT_GOLD}; letter-spacing: 2px;")

        self._progress_lbl = QLabel("")
        self._progress_lbl.setFont(QFont("Segoe UI", 10))
        self._progress_lbl.setStyleSheet(f"color: {TEXT_MUTED};")

        hdr_l.addWidget(self._title_lbl)
        hdr_l.addStretch()
        hdr_l.addWidget(self._progress_lbl)
        root.addWidget(hdr)

        # ── Progress bar ─────────────────────────────────────────────────────
        self._bar_track = QWidget()
        self._bar_track.setFixedHeight(3)
        self._bar_track.setStyleSheet(f"background: {BORDER_SOLID};")
        self._bar_fill = QWidget(self._bar_track)
        self._bar_fill.setFixedHeight(3)
        self._bar_fill.move(0, 0)
        self._bar_fill.setFixedWidth(0)
        self._bar_fill.setStyleSheet(f"background: {GREEN_LIVE};")
        root.addWidget(self._bar_track)

        # ── No-sync gate ─────────────────────────────────────────────────────
        self._gate = QWidget()
        gate_l = QVBoxLayout(self._gate)
        gate_l.setAlignment(Qt.AlignmentFlag.AlignCenter)
        gate_lbl = QLabel("Connect your QuestLog account and start a\nsynced run to track item collection.")
        gate_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        gate_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 13px;")
        gate_l.addWidget(gate_lbl)
        root.addWidget(self._gate)

        # ── Item list ────────────────────────────────────────────────────────
        # Capped-height internal QScrollArea, matching the site: Items gets
        # its own scrollable box rather than flowing the full item list into
        # RunOverviewTab's outer page (which made the page dozens of screens
        # long with a large item set).
        self._list_widget = QWidget()
        self._list_widget.setStyleSheet("background: transparent;")
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(0)
        self._list_layout.addStretch()

        self._list_scroll = QScrollArea()
        self._list_scroll.setWidgetResizable(True)
        self._list_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._list_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list_scroll.setFixedHeight(360)
        self._list_scroll.setWidget(self._list_widget)
        self._list_scroll.hide()
        root.addWidget(self._list_scroll)

    def set_ql_sync(self, ql_sync):
        self._ql_sync   = ql_sync
        self._local_run = None
        active = bool(ql_sync)
        if active:
            self._gate.hide()
            self._list_scroll.show()
        else:
            self._gate.show()
            self._list_scroll.hide()
            self._rows.clear()
            self._clear_list()

    def set_local_run(self, local_run):
        self._local_run = local_run
        self._ql_sync   = None
        active = bool(local_run)
        if active:
            self._gate.hide()
            self._list_scroll.show()
        else:
            self._gate.show()
            self._list_scroll.hide()
            self._rows.clear()
            self._clear_list()

    def refresh(self, items, collected, total):
        import time as _time
        now = _time.monotonic()

        # Reconcile pending optimistic clicks against this server snapshot:
        # if the server now agrees, the pending override isn't needed
        # anymore; if it's been pending too long (POST likely failed
        # silently), give up on it rather than hold a wrong state forever.
        by_name = {it["name"]: it for it in items}
        for name in list(self._pending.keys()):
            desired, expires_at = self._pending[name]
            server_it = by_name.get(name)
            if (server_it and server_it["collected"] == desired) or now >= expires_at:
                del self._pending[name]

        self._progress_lbl.setText(f"{collected} / {total}")
        if total > 0:
            pct = collected / total
            fill = int(self._bar_track.width() * pct)
            self._bar_fill.setFixedWidth(max(0, fill))

        # Rebuild list if item set changed
        current_names = set(self._rows.keys())
        new_names     = {it["name"] for it in items}
        if current_names != new_names:
            self._rebuild(items)
        else:
            # Just update collected states -- but a name with an unresolved
            # pending click keeps showing what the user just set, not this
            # (possibly stale) server snapshot's value for it.
            for it in items:
                name = it["name"]
                if name in self._pending:
                    continue
                if name in self._rows:
                    row_w, _ = self._rows[name]
                    self._rows[name] = (row_w, it["collected"])
                    self._update_row_style(row_w, it["collected"])

    def _rebuild(self, items):
        self._clear_list()
        self._rows.clear()

        TYPE_ORDER  = ["weapon", "armor", "talisman", "spell", "spirit_ash", "crystal_tear"]
        TYPE_LABELS = {
            "weapon": "WEAPONS", "armor": "ARMOR", "talisman": "TALISMANS",
            "spell": "SPELLS", "spirit_ash": "SPIRIT ASHES", "crystal_tear": "CRYSTAL TEARS",
        }
        grouped = {}
        for it in items:
            t = it.get("type", "weapon")
            grouped.setdefault(t, []).append(it)

        layout = self._list_layout
        # Remove stretch, add items, re-add stretch
        stretch = layout.takeAt(layout.count() - 1)

        for t in TYPE_ORDER:
            if t not in grouped:
                continue
            # Section header
            sec = QLabel(TYPE_LABELS.get(t, t.upper()))
            sec.setFixedHeight(28)
            sec.setStyleSheet(
                f"color: {TEXT_MUTED}; font-size: 9px; font-weight: 700; "
                f"letter-spacing: 1.5px; padding-left: 20px; "
                f"background: {BG_SURFACE}; border-bottom: 1px solid {BORDER_SOLID};"
            )
            layout.addWidget(sec)
            for it in sorted(grouped[t], key=lambda x: x["name"]):
                row_w = self._make_row(it)
                layout.addWidget(row_w)
                self._rows[it["name"]] = (row_w, it["collected"])

        layout.addStretch()

    def _make_row(self, item):
        row = QWidget()
        row.setFixedHeight(44)
        row.setCursor(Qt.CursorShape.PointingHandCursor)
        row._item_name      = item["name"]
        row._item_collected = item["collected"]

        rl = QHBoxLayout(row)
        rl.setContentsMargins(20, 0, 20, 0)
        rl.setSpacing(12)

        check = QLabel("✓" if item["collected"] else "○")
        check.setFixedWidth(18)
        check.setAlignment(Qt.AlignmentFlag.AlignCenter)
        check.setFont(QFont("Segoe UI", 13))
        row._check_lbl = check

        name_lbl = QLabel(item["name"])
        name_lbl.setFont(QFont("Segoe UI", 12))
        row._name_lbl = name_lbl

        hint = item.get("hint") or ""
        hint_lbl = QLabel(hint)
        hint_lbl.setFont(QFont("Segoe UI", 10))
        hint_lbl.setStyleSheet(f"color: {TEXT_MUTED};")
        hint_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        rl.addWidget(check)
        rl.addWidget(name_lbl, 1)
        rl.addWidget(hint_lbl)

        self._update_row_style(row, item["collected"])

        row.mousePressEvent = lambda e, r=row: self._on_row_click(r)
        return row

    def _update_row_style(self, row, collected):
        row._item_collected = collected
        if collected:
            row.setStyleSheet(f"background: rgba(34,197,94,0.06); border-bottom: 1px solid {BORDER_SOLID};")
            row._check_lbl.setText("✓")
            row._check_lbl.setStyleSheet(f"color: {GREEN_LIVE};")
            row._name_lbl.setStyleSheet(f"color: {TEXT_MUTED}; text-decoration: line-through;")
        else:
            row.setStyleSheet(f"background: transparent; border-bottom: 1px solid {BORDER_SOLID};")
            row._check_lbl.setText("○")
            row._check_lbl.setStyleSheet(f"color: {TEXT_DIM};")
            row._name_lbl.setStyleSheet(f"color: {TEXT_PRIMARY};")

    def _on_row_click(self, row):
        backend = self._ql_sync or self._local_run
        if not backend:
            return
        import time as _time
        name      = row._item_name
        collected = row._item_collected
        if collected:
            backend.uncollect_item(name)
            self._update_row_style(row, False)
            self._rows[name] = (row, False)
            self._pending[name] = (False, _time.monotonic() + self._PENDING_TIMEOUT_SEC)
        else:
            backend.collect_item(name)
            self._update_row_style(row, True)
            self._rows[name] = (row, True)
            self._pending[name] = (True, _time.monotonic() + self._PENDING_TIMEOUT_SEC)
        # Update progress immediately without waiting for next tick
        new_collected = sum(1 for _, c in self._rows.values() if c)
        total = len(self._rows)
        self._progress_lbl.setText(f"{new_collected} / {total}")
        if total > 0:
            fill = int(self._bar_track.width() * new_collected / total)
            self._bar_fill.setFixedWidth(max(0, fill))

    def _clear_list(self):
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Recompute progress bar width on resize
        if hasattr(self, '_bar_track'):
            self._bar_track.update()


# ─────────────────────────────────────────────────────────────────────────────

class DeathLogTab(QWidget):
    """Recent death log — local append on death, refreshed from status poll."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries = []   # list of dicts: {boss, at, life, session_deaths, total_deaths}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ───────────────────────────────────────────────────────────
        hdr = QWidget()
        hdr.setFixedHeight(48)
        hdr.setStyleSheet(f"background: {BG_SURFACE}; border-bottom: 1px solid {BORDER_SOLID};")
        hdr_l = QHBoxLayout(hdr)
        hdr_l.setContentsMargins(20, 0, 20, 0)

        self._title_lbl = QLabel("DEATH LOG")
        self._title_lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self._title_lbl.setStyleSheet(f"color: {ACCENT_GOLD}; letter-spacing: 2px;")

        self._count_lbl = QLabel("")
        self._count_lbl.setFont(QFont("Segoe UI", 10))
        self._count_lbl.setStyleSheet(f"color: {TEXT_MUTED};")

        hdr_l.addWidget(self._title_lbl)
        hdr_l.addStretch()
        hdr_l.addWidget(self._count_lbl)
        root.addWidget(hdr)

        # ── No-sync gate ─────────────────────────────────────────────────────
        self._gate = QWidget()
        gate_l = QVBoxLayout(self._gate)
        gate_l.setAlignment(Qt.AlignmentFlag.AlignCenter)
        gate_lbl = QLabel("Connect your QuestLog account and start a\nsynced run to see your death log.")
        gate_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        gate_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 13px;")
        gate_l.addWidget(gate_lbl)
        root.addWidget(self._gate)

        # ── Scroll area ──────────────────────────────────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet("background: transparent;")
        self._scroll.hide()

        self._list_widget = QWidget()
        self._list_widget.setStyleSheet("background: transparent;")
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(0)
        self._list_layout.addStretch()
        self._scroll.setWidget(self._list_widget)
        root.addWidget(self._scroll)

    def set_active(self, active: bool):
        if active:
            self._gate.hide()
            self._scroll.show()
        else:
            self._gate.show()
            self._scroll.hide()
            self._entries.clear()
            self._rebuild()

    def append_death(self, boss, life_sec, session_deaths, total_deaths):
        """Called immediately on death event (main thread via signal)."""
        import time as _time
        self._entries.insert(0, {
            "boss":           boss or "",
            "at":             int(_time.time()),
            "life":           life_sec,
            "session_deaths": session_deaths,
            "total_deaths":   total_deaths,
        })
        self._entries = self._entries[:10]
        self._rebuild()

    def load_from_status(self, recent_deaths, session_deaths, total_deaths):
        """Refresh from status poll — replaces entries list."""
        new_entries = list(recent_deaths[:10])
        self._count_lbl.setText(f"{total_deaths} total  |  {session_deaths} this session")
        # Only rebuild widgets when the entry list actually changed
        if new_entries != self._entries:
            self._entries = new_entries
            self._rebuild()

    def update_counts(self, session_deaths, total_deaths):
        """Update header counts without rebuilding the list (for local runs)."""
        self._count_lbl.setText(f"{total_deaths} total  |  {session_deaths} this session")

    def _rebuild(self):
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        import time as _time
        now = int(_time.time())

        for i, e in enumerate(self._entries):
            row = self._make_row(e, i + 1, now)
            self._list_layout.insertWidget(self._list_layout.count() - 1, row)

    def _make_row(self, entry, num, now):
        row = QWidget()
        row.setFixedHeight(56)
        row.setStyleSheet(f"background: transparent; border-bottom: 1px solid {BORDER_SOLID};")

        rl = QHBoxLayout(row)
        rl.setContentsMargins(20, 8, 20, 8)
        rl.setSpacing(12)

        # Death number
        num_lbl = QLabel(f"#{entry.get('total_deaths', num)}" if entry.get('total_deaths') else f"#{num}")
        num_lbl.setFixedWidth(42)
        num_lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        num_lbl.setStyleSheet(f"color: {ACCENT_GOLD};")

        # Boss / location
        boss = entry.get("boss") or ""
        boss_lbl = QLabel(boss if boss else "[Unknown]")
        boss_lbl.setFont(QFont("Segoe UI", 12))
        boss_lbl.setStyleSheet(f"color: {TEXT_PRIMARY if boss else TEXT_MUTED};")

        # Right column: survived time + ago
        right = QVBoxLayout()
        right.setSpacing(2)
        right.setContentsMargins(0, 0, 0, 0)

        life_sec = entry.get("life", 0)
        if life_sec:
            m, s = divmod(life_sec, 60)
            survived = f"survived  {m}m {s:02d}s"
        else:
            survived = "survived  —"
        surv_lbl = QLabel(survived)
        surv_lbl.setFont(QFont("Segoe UI", 10))
        surv_lbl.setStyleSheet(f"color: {TEXT_MUTED};")
        surv_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)

        at = entry.get("at", 0)
        ago = ""
        if at:
            delta = now - at
            if delta < 60:
                ago = "just now"
            elif delta < 3600:
                ago = f"{delta // 60}m ago"
            else:
                ago = f"{delta // 3600}h ago"
        ago_lbl = QLabel(ago)
        ago_lbl.setFont(QFont("Segoe UI", 9))
        ago_lbl.setStyleSheet(f"color: {TEXT_DIM};")
        ago_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)

        right.addWidget(surv_lbl)
        right.addWidget(ago_lbl)

        rl.addWidget(num_lbl)
        rl.addWidget(boss_lbl, 1)
        rl.addLayout(right)
        return row


# ─────────────────────────────────────────────────────────────────────────────

class SettingsTab(QWidget):
    opacity_changed  = pyqtSignal(int)
    pin_changed      = pyqtSignal(bool)
    compact_changed  = pyqtSignal(bool)
    hotkeys_changed  = pyqtSignal(dict)
    save_path_changed = pyqtSignal(str)   # new save_file_path, live-applied (no restart needed)
    login_requested  = pyqtSignal()
    logout_requested = pyqtSignal()
    reset_stats      = pyqtSignal()     # reset deaths + session timers (app + site)
    # emitted from worker thread via App — connected in main.py
    login_succeeded  = pyqtSignal(str, str, list)   # api_key, username, runs
    login_failed     = pyqtSignal(str)               # error message

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self._settings = settings

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        outer = QVBoxLayout(inner)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(0)
        scroll.setWidget(inner)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

        def section(title):
            lbl = QLabel(title.upper())
            lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            lbl.setStyleSheet(f"color: {TEXT_MUTED}; letter-spacing: 2px; margin-top: 20px; margin-bottom: 8px;")
            outer.addWidget(lbl)
            line = QFrame()
            line.setFrameShape(QFrame.Shape.HLine)
            line.setStyleSheet(f"color: {BORDER_SOLID}; margin-bottom: 16px;")
            outer.addWidget(line)

        # ── Appearance ────────────────────────────────────────────────────────
        section("Appearance")

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
        outer.addSpacing(8)

        self.compact_btn = QPushButton("COMPACT MODE")
        self.compact_btn.setCheckable(True)
        self.compact_btn.setChecked(settings.get("compact", False))
        self.compact_btn.setFixedHeight(36)
        self.compact_btn.clicked.connect(self._on_compact)
        outer.addWidget(self.compact_btn)

        # ── Window ────────────────────────────────────────────────────────────
        section("Window")

        self.pin_btn = QPushButton("ALWAYS ON TOP")
        self.pin_btn.setCheckable(True)
        self.pin_btn.setChecked(settings.get("pin", False))
        self.pin_btn.setFixedHeight(36)
        self.pin_btn.clicked.connect(self._on_pin)
        pin_hint = QLabel("Keep the tracker above all other windows.")
        pin_hint.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; margin-top: 6px;")
        outer.addWidget(self.pin_btn)
        outer.addWidget(pin_hint)

        # ── Hotkeys ───────────────────────────────────────────────────────────
        section("Hotkeys")

        hk_info = QLabel("Click a box and press any key to remap. Takes effect immediately.")
        hk_info.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        hk_info.setWordWrap(True)
        outer.addWidget(hk_info)
        outer.addSpacing(10)

        self._hk_fields = {}
        for key, label, default in [
            ("hotkey_death",    "Add Death",              "f9"),
            ("hotkey_subtract", "Subtract Death",         "f10"),
            ("hotkey_reset",    "Reset All (hold 3s)",    "f8"),
            ("hotkey_focus",    "Focus Boss",             "f4"),
            ("hotkey_unfocus",  "Unfocus Boss",           "f5"),
            ("hotkey_defeat",   "Defeat Focused Boss",    "f11"),
        ]:
            self._hk_fields[key] = self._make_hotkey_row(outer, label, settings.get(key, default))

        # ── Save File Tracking ───────────────────────────────────────────────
        section("Save File Tracking")

        save_info = QLabel(
            "Auto-checks off items in your Items list the moment your Elden "
            "Ring save file shows them as owned — no manual clicking needed. "
            "Vanilla and Elden Ring Reforged only, for now."
        )
        save_info.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        save_info.setWordWrap(True)
        outer.addWidget(save_info)
        outer.addSpacing(10)

        self._save_path_lbl = QLabel()
        self._save_path_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 11px;")
        self._save_path_lbl.setWordWrap(True)
        outer.addWidget(self._save_path_lbl)
        outer.addSpacing(8)

        save_btn_row = QHBoxLayout()
        save_btn_row.setSpacing(8)
        auto_detect_btn = QPushButton("AUTO-DETECT")
        auto_detect_btn.setFixedHeight(34)
        auto_detect_btn.clicked.connect(self._on_auto_detect_save)
        browse_btn = QPushButton("BROWSE...")
        browse_btn.setFixedHeight(34)
        browse_btn.clicked.connect(self._on_browse_save)
        save_btn_row.addWidget(auto_detect_btn)
        save_btn_row.addWidget(browse_btn)
        outer.addLayout(save_btn_row)

        self._update_save_path_label(settings.get("save_file_path", ""))

        # ── Run Stats ─────────────────────────────────────────────────────────
        section("Run Stats")

        reset_info = QLabel(
            "Resets all session deaths, total deaths, rage index, and streak timers "
            "to zero — both in the app and on QuestLog."
        )
        reset_info.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        reset_info.setWordWrap(True)
        outer.addWidget(reset_info)
        outer.addSpacing(10)

        reset_stats_btn = QPushButton("RESET ALL STATS")
        reset_stats_btn.setFixedHeight(38)
        reset_stats_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(192,57,15,0.10);
                border: 1px solid {ACCENT_RED2};
                border-radius: 6px;
                color: {ACCENT_RED2};
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 1px;
            }}
            QPushButton:hover {{
                background: rgba(192,57,15,0.22);
                border-color: #e04010;
                color: #e04010;
            }}
        """)
        reset_stats_btn.clicked.connect(self.reset_stats.emit)
        outer.addWidget(reset_stats_btn)

        # ── QuestLog Account ──────────────────────────────────────────────────
        section("QuestLog Account")

        account_info = QLabel(
            "Optional — connect your QuestLog account to sync deaths and "
            "boss progress to the web tracker and leaderboards."
        )
        account_info.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        account_info.setWordWrap(True)
        outer.addWidget(account_info)
        outer.addSpacing(12)

        self._username_lbl = QLabel("")
        self._username_lbl.setStyleSheet(f"color: {ACCENT_GOLD}; font-weight: 700; font-size: 12px;")
        self._username_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._username_lbl.setVisible(False)
        outer.addWidget(self._username_lbl)

        self._login_status = QLabel("")
        self._login_status.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        self._login_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._login_status.setWordWrap(True)
        outer.addWidget(self._login_status)
        outer.addSpacing(8)

        self._login_btn = QPushButton("LOGIN WITH QUESTLOG")
        self._login_btn.setFixedHeight(40)
        self._login_btn.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT_GOLD};
                color: {BG_BASE};
                border: none;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 700;
                letter-spacing: 1px;
            }}
            QPushButton:hover {{ background: {ACCENT_GOLD2}; }}
            QPushButton:pressed {{ background: {ACCENT_GOLD}; }}
            QPushButton:disabled {{ background: {BG_SURFACE}; color: {TEXT_DIM}; }}
        """)
        self._login_btn.clicked.connect(self._on_login_clicked)
        outer.addWidget(self._login_btn)

        self._logout_btn = QPushButton("LOGOUT")
        self._logout_btn.setFixedHeight(36)
        self._logout_btn.setVisible(False)
        self._logout_btn.clicked.connect(self._on_logout_clicked)
        outer.addWidget(self._logout_btn)

        outer.addSpacing(8)

        web_btn = QPushButton("Open Web Tracker →")
        web_btn.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; border: none; background: transparent;")
        web_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        web_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(SITE_URL)))
        outer.addWidget(web_btn)

        outer.addStretch()

        # ── Footer ────────────────────────────────────────────────────────────
        footer_row = QHBoxLayout()
        footer_row.setSpacing(10)
        footer_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        ql_lbl = QLabel()
        ql_lbl.setFixedSize(24, 24)
        ql_pix = _load_pixmap(LOGO_QL, LOGO_QL_ICO)
        if not ql_pix.isNull():
            ql_lbl.setPixmap(ql_pix.scaled(24, 24, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            ql_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer_row.addWidget(ql_lbl)

        ver = QLabel(f"EldenTracker  v{APP_VERSION}  ·  Powered by QuestLog  ·  by Casual Heroes")
        ver.setStyleSheet(f"color: {TEXT_DIM}; font-size: 10px;")
        footer_row.addWidget(ver)

        ch_lbl = QLabel()
        ch_lbl.setFixedSize(24, 24)
        ch_pix = _load_pixmap(LOGO_CH, LOGO_CH_ICO)
        if not ch_pix.isNull():
            ch_lbl.setPixmap(ch_pix.scaled(24, 24, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            ch_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer_row.addWidget(ch_lbl)

        outer.addLayout(footer_row)

        site_btn = QPushButton("questlog.casual-heroes.com")
        site_btn.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; border: none; background: transparent;")
        site_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        site_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(SITE_URL)))
        outer.addWidget(site_btn)

        # Connect login signals (emitted from App worker thread)
        self.login_succeeded.connect(self._on_login_success)
        self.login_failed.connect(self._on_login_error)

        # Restore logged-in state if we have saved credentials
        if settings.get("api_key") and settings.get("username"):
            self._set_logged_in(settings["username"])

    # ── Save file tracking ───────────────────────────────────────────────────

    def _update_save_path_label(self, path):
        if path:
            self._save_path_lbl.setText(f"Tracking: {path}")
        else:
            self._save_path_lbl.setText("Not configured — items must be checked off manually.")

    def _on_auto_detect_save(self):
        from core.save_paths import find_save_files
        candidates = find_save_files()
        if not candidates:
            self._save_path_lbl.setText(
                "No save file found under %APPDATA%\\EldenRing\\ — use Browse to select one manually."
            )
            return
        if len(candidates) == 1:
            self._apply_save_path(candidates[0]["path"])
            return

        from PyQt6.QtWidgets import QInputDialog
        labels = [f"{c['mode'].title()} — {c['path']}" for c in candidates]
        choice, ok = QInputDialog.getItem(
            self, "Multiple Save Files Found",
            "Select which save file to track:", labels, editable=False,
        )
        if ok and choice:
            idx = labels.index(choice)
            self._apply_save_path(candidates[idx]["path"])

    def _on_browse_save(self):
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Elden Ring Save File", "",
            "Elden Ring Saves (*.sl2 *.err);;All Files (*)",
        )
        if path:
            self._apply_save_path(path)

    def _apply_save_path(self, path):
        self._update_save_path_label(path)
        settings = _load_settings()
        settings["save_file_path"] = path
        _save_settings(settings)
        self.save_path_changed.emit(path)

    # ── Hotkey row ────────────────────────────────────────────────────────────

    def _make_hotkey_row(self, layout, label, current_key):
        row = QHBoxLayout()
        row.setSpacing(12)

        lbl = QLabel(label)
        lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; min-width: 140px;")
        lbl.setFixedWidth(140)

        field = QLineEdit(current_key.upper())
        field.setFixedHeight(34)
        field.setReadOnly(True)
        field.setAlignment(Qt.AlignmentFlag.AlignCenter)
        field.setCursor(Qt.CursorShape.PointingHandCursor)
        field.setStyleSheet(f"""
            QLineEdit {{
                background: {BG_SURFACE};
                border: 1px solid {BORDER_SOLID};
                border-radius: 6px;
                color: {ACCENT_GOLD};
                font-weight: 700;
                font-size: 12px;
                padding: 0 8px;
            }}
            QLineEdit:focus {{
                border-color: {ACCENT_GOLD};
                background: {BG_CARD};
                color: {TEXT_PRIMARY};
            }}
        """)

        def on_focus_in(event):
            field.setText("Press a key...")
            field.setStyleSheet(field.styleSheet())
            QLineEdit.focusInEvent(field, event)

        def on_key_press(event):
            from PyQt6.QtCore import Qt as _Qt
            key = event.key()
            # Ignore modifier-only presses
            if key in (
                _Qt.Key.Key_Control, _Qt.Key.Key_Shift,
                _Qt.Key.Key_Alt, _Qt.Key.Key_Meta,
            ):
                return
            # Map Qt key to keyboard-lib name
            name = self._qt_key_to_name(key, event.text())
            if name:
                field.setText(name.upper())
                field.clearFocus()
                self._save_hotkeys()

        field.focusInEvent  = on_focus_in
        field.keyPressEvent = on_key_press

        row.addWidget(lbl)
        row.addWidget(field, 1)
        layout.addLayout(row)
        layout.addSpacing(6)
        return field

    @staticmethod
    def _qt_key_to_name(qt_key, text):
        from PyQt6.QtCore import Qt as _Qt
        _MAP = {
            _Qt.Key.Key_F1:  "f1",  _Qt.Key.Key_F2:  "f2",  _Qt.Key.Key_F3:  "f3",
            _Qt.Key.Key_F4:  "f4",  _Qt.Key.Key_F5:  "f5",  _Qt.Key.Key_F6:  "f6",
            _Qt.Key.Key_F7:  "f7",  _Qt.Key.Key_F8:  "f8",  _Qt.Key.Key_F9:  "f9",
            _Qt.Key.Key_F10: "f10", _Qt.Key.Key_F11: "f11", _Qt.Key.Key_F12: "f12",
            _Qt.Key.Key_Insert:    "insert",   _Qt.Key.Key_Delete:    "delete",
            _Qt.Key.Key_Home:      "home",     _Qt.Key.Key_End:       "end",
            _Qt.Key.Key_PageUp:    "page up",  _Qt.Key.Key_PageDown:  "page down",
            _Qt.Key.Key_Up:        "up",       _Qt.Key.Key_Down:      "down",
            _Qt.Key.Key_Left:      "left",     _Qt.Key.Key_Right:     "right",
            _Qt.Key.Key_Tab:       "tab",      _Qt.Key.Key_Escape:    "esc",
            _Qt.Key.Key_Return:    "enter",    _Qt.Key.Key_Space:     "space",
        }
        if qt_key in _MAP:
            return _MAP[qt_key]
        if text and text.isprintable() and len(text) == 1:
            return text.lower()
        return None

    def _save_hotkeys(self):
        mapping = {
            "hotkey_death":    "f9",
            "hotkey_subtract": "f10",
            "hotkey_reset":    "f8",
            "hotkey_focus":    "f4",
            "hotkey_unfocus":  "f5",
            "hotkey_defeat":   "f11",
        }
        changed = False
        for key, default in mapping.items():
            field = self._hk_fields[key]
            val = field.text().lower()
            if val and val != "press a key...":
                if self._settings.get(key) != val:
                    self._settings[key] = val
                    changed = True
        if changed:
            _save_settings(self._settings)
            self.hotkeys_changed.emit({
                "death":    self._settings.get("hotkey_death",    "f9"),
                "subtract": self._settings.get("hotkey_subtract", "f10"),
                "reset":    self._settings.get("hotkey_reset",    "f8"),
                "focus":    self._settings.get("hotkey_focus",    "f4"),
                "unfocus":  self._settings.get("hotkey_unfocus",  "f5"),
                "defeat":   self._settings.get("hotkey_defeat",   "f11"),
            })

    # ── Login UI ──────────────────────────────────────────────────────────────

    def _on_login_clicked(self):
        self._login_btn.setEnabled(False)
        self._login_status.setText("Opening browser — waiting for login...")
        self._login_status.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        self.login_requested.emit()

    def _on_login_success(self, api_key, username, runs):
        self._settings["api_key"]  = api_key
        self._settings["username"] = username
        _save_settings(self._settings)
        self._set_logged_in(username)

    def _on_login_error(self, msg):
        self._login_btn.setEnabled(True)
        self._login_status.setText(f"Login failed: {msg}")
        self._login_status.setStyleSheet(f"color: {RED_LIVE}; font-size: 11px;")

    def _on_logout_clicked(self):
        self._set_logged_out()
        self.logout_requested.emit()  # App._do_logout handles clearing disk

    def _set_logged_in(self, username):
        self._username_lbl.setText(f"Logged in as  {username}")
        self._username_lbl.setVisible(True)
        self._login_status.setText("Deaths and boss progress sync to QuestLog.")
        self._login_status.setStyleSheet(f"color: {GREEN_LIVE}; font-size: 11px;")
        self._login_btn.setVisible(False)
        self._logout_btn.setVisible(True)

    def _set_logged_out(self):
        self._username_lbl.setVisible(False)
        self._login_status.setText("Not connected — running offline.")
        self._login_status.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        self._login_btn.setVisible(True)
        self._login_btn.setEnabled(True)
        self._logout_btn.setVisible(False)

    # ── Other settings ────────────────────────────────────────────────────────

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


class RunOverviewTab(QWidget):
    """
    Composite "everything on one page" tab matching the site's layout:
    stat tiles / Fury / Log Death-Undo-Reset (MortalityTab) -> Boss Progress
    (region-tabbed boss lists) -> Items, all under ONE outer scroll area
    instead of separate sibling tabs the user has to switch between. Owns no
    logic of its own -- mortality_tab/boss_progress_tabs/items_tab are built
    and wired exactly as before by BossTrackerWindow, this just changes where
    they're parented in the layout.
    """

    def __init__(self, mortality_tab, boss_progress_tabs, items_tab, parent=None):
        super().__init__(parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background: transparent;")

        page = QWidget()
        page.setStyleSheet(f"background: {BG_BASE};")
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)

        page_layout.addWidget(mortality_tab)

        page_layout.addSpacing(8)
        boss_section_lbl = QLabel("BOSS PROGRESS")
        boss_section_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        boss_section_lbl.setStyleSheet(f"color: {ACCENT_GOLD}; letter-spacing: 2px; padding: 0 24px;")
        page_layout.addWidget(boss_section_lbl)
        page_layout.addSpacing(8)

        # Nested QTabWidget for the boss regions (LIMGRAVE / STORMVEIL / ...)
        # -- picks up the same global QSS tab styling as the top-level
        # self.tabs (gold underline, uppercase, letter-spaced) automatically,
        # since QSS applies window-wide. Fixed-ish height since it's inside
        # a bigger scroll now, not the sole content of its own tab -- let it
        # size to its content (each BossTab no longer scrolls internally).
        boss_progress_tabs.setDocumentMode(True)
        page_layout.addWidget(boss_progress_tabs)

        page_layout.addSpacing(16)
        page_layout.addWidget(items_tab)

        scroll.setWidget(page)
        outer.addWidget(scroll)


class BossTrackerWindow(QMainWindow):
    switch_run = pyqtSignal()

    def __init__(self, boss_tracker, run_meta, session=None, deaths=None, on_kill=None,
                 rage_label="Rage Index", api=None, on_boss_mark=None, ql_sync=None):
        super().__init__()
        self._rage_label  = rage_label
        self.boss_tracker = boss_tracker
        self._run_meta    = run_meta
        self._session     = session
        self._deaths      = deaths
        self.on_kill      = on_kill
        self._api         = api
        self._ql_sync     = ql_sync
        self._on_boss_mark = on_boss_mark
        self._settings    = _load_settings()
        self._closing     = False

        game  = run_meta.get("game_id", "").replace("_", " ").title()
        mode  = run_meta.get("mode_id", "").replace("_", " ").title()
        rname = run_meta.get("name", "")
        self.setWindowTitle(f"EldenTracker — {rname}")
        self.setWindowIcon(QIcon(LOGO_CH_ICO))
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
        logo_lbl.setFixedSize(38, 38)
        pix = _load_pixmap(LOGO_QL, LOGO_QL_ICO)
        if not pix.isNull():
            logo_lbl.setPixmap(pix.scaled(38, 38, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
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

        mode_lbl = QLabel(f"QuestLog Elden Ring Tracker  ·  {game}  ·  {mode}")
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

        github_btn = QPushButton("⌥ Source Code")
        github_btn.setFixedHeight(30)
        github_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        github_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: 1px solid {BORDER_SOLID};
                border-radius: 6px; color: {TEXT_DIM};
                padding: 0 12px; font-size: 10px; letter-spacing: 0.5px;
            }}
            QPushButton:hover {{ border-color: {ACCENT_GOLD}; color: {ACCENT_GOLD}; }}
        """)
        github_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(GITHUB_URL)))

        settings_btn = QPushButton("Settings")
        settings_btn.setFixedHeight(30)
        settings_btn.setToolTip("Settings")
        settings_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: 1px solid {BORDER_SOLID};
                border-radius: 6px; color: {TEXT_DIM};
                padding: 0 12px; font-size: 10px; letter-spacing: 0.5px;
            }}
            QPushButton:hover {{ border-color: {ACCENT_GOLD}; color: {ACCENT_GOLD}; }}
        """)
        settings_btn.clicked.connect(self._open_settings_dialog)

        h_layout.addWidget(self.switch_btn)
        h_layout.addSpacing(4)
        h_layout.addWidget(self.pin_btn)
        h_layout.addSpacing(4)
        h_layout.addWidget(settings_btn)
        h_layout.addSpacing(8)
        h_layout.addWidget(site_btn)
        h_layout.addSpacing(4)
        h_layout.addWidget(github_btn)
        root.addWidget(header)

        # ── Tabs ──
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        root.addWidget(self.tabs)

        # Nested tab widget for boss regions (LIMGRAVE, STORMVEIL CASTLE,
        # ...) -- lives INSIDE the OVERVIEW tab's scrolling page (built
        # below), not as top-level siblings of OVERVIEW/DEATHS/BUILD. Built
        # before _build_boss_tabs() populates it.
        self._boss_progress_tabs = QTabWidget()
        self._boss_tabs = {}   # group_label → BossTab
        self._build_boss_tabs(boss_tracker, on_kill, self._api, self._on_boss_mark, self._ql_sync)

        self.mortality_tab = MortalityTab(session=session, deaths=deaths, rage_label=rage_label)
        # sig_add_death / sig_subtract_death / sig_reset_deaths are connected
        # by main.py (App), not here -- they route through the same
        # on_death/on_subtract/on_reset handlers the F8/F9/F10 hotkeys use,
        # so there's exactly one code path per action instead of two (this
        # used to have its own separate _on_add_death/_on_subtract_death/
        # _on_reset_deaths here, which only called self._api and skipped
        # the _local_run / boss_key / in-flight-guard logic main.py's
        # versions have).
        self.mortality_tab.sig_reset_bosses.connect(self._on_reset_bosses)

        self.settings_tab  = SettingsTab(self._settings)
        self.settings_tab.opacity_changed.connect(self._on_opacity)
        self.settings_tab.pin_changed.connect(self._apply_pin)
        self.settings_tab.compact_changed.connect(self._on_compact)

        self.items_tab     = ItemsTab()
        self.death_log_tab = DeathLogTab()

        self.items_tab.set_ql_sync(ql_sync)
        self.death_log_tab.set_active(bool(ql_sync))

        from gui.build_planner import BuildPlannerWidget
        self.build_planner_tab = BuildPlannerWidget(api=self._api)

        # Stats/Fury/Log-Death (mortality_tab) + Boss Progress
        # (boss_progress_tabs) + Items (items_tab) merged into one
        # continuously-scrolling page, matching the site's layout, instead
        # of separate sibling tabs the user had to switch between.
        # DEATHS and BUILD stay as their own tabs -- the site treats those
        # as distinct sections too.
        self.run_overview_tab = RunOverviewTab(self.mortality_tab, self._boss_progress_tabs, self.items_tab)

        self.tabs.addTab(self.run_overview_tab, "OVERVIEW")
        self.tabs.addTab(self.death_log_tab, "DEATHS")
        self.tabs.addTab(self.build_planner_tab, "BUILD")

        if self._settings.get("pin", False):
            self._apply_pin(True)
        if self._settings.get("compact", False):
            self._on_compact(True)

    def _open_settings_dialog(self):
        from PyQt6.QtWidgets import QDialog, QVBoxLayout
        dlg = QDialog(self)
        dlg.setWindowTitle("Settings")
        dlg.setMinimumSize(520, 640)
        dlg.setStyleSheet(QSS)
        root = QVBoxLayout(dlg)
        root.setContentsMargins(0, 0, 0, 0)

        # Fresh tab owned by the dialog — avoids reparent/signal-breakage issues.
        # Forward signals up so App can handle them.
        dlg_settings = SettingsTab(self._settings)
        dlg_settings.opacity_changed.connect(self._on_opacity)
        dlg_settings.pin_changed.connect(self._apply_pin)
        dlg_settings.compact_changed.connect(self._on_compact)
        dlg_settings.hotkeys_changed.connect(
            lambda hk: self.settings_tab.hotkeys_changed.emit(hk)
        )
        dlg_settings.login_requested.connect(
            lambda: self.settings_tab.login_requested.emit()
        )
        dlg_settings.logout_requested.connect(
            lambda: self.settings_tab.logout_requested.emit()
        )
        dlg_settings.reset_stats.connect(
            lambda: self.settings_tab.reset_stats.emit()
        )
        root.addWidget(dlg_settings)

        # Stream overlays at the bottom if this run has a server token
        token = self._run_meta.get("questlog_token", "") if self._run_meta else ""
        if token and token != "__local__":
            stream_widget = self._make_stream_info(token)
            root.addWidget(stream_widget)

        dlg.exec()

    def _make_stream_info(self, token):
        from PyQt6.QtWidgets import QApplication
        widget = QWidget()
        widget.setStyleSheet(f"background: {BG_SURFACE}; border-top: 1px solid {BORDER_SOLID};")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 12, 20, 12)
        layout.setSpacing(4)

        hdr = QLabel("STREAM OVERLAYS")
        hdr.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {TEXT_MUTED}; letter-spacing: 2px;")
        layout.addWidget(hdr)
        layout.addSpacing(4)

        base = "https://questlog.casual-heroes.com/soulslike"
        urls = [
            ("Web Tracker",        f"{base}/runs/{token}/"),
            ("Combined Overlay",   f"{base}/overlay/{token}/combined/"),
            ("Mortality Overlay",  f"{base}/overlay/{token}/mortality/"),
            ("Deaths Overlay",     f"{base}/overlay/{token}/deaths/"),
            ("Hollow Overlay",     f"{base}/overlay/{token}/hollow/"),
            ("Collection Overlay", f"{base}/overlay/{token}/collection/"),
        ]

        copy_style = f"""
            QPushButton {{
                background: rgba(201,168,76,0.1); border: 1px solid {ACCENT_GOLD};
                border-radius: 4px; color: {ACCENT_GOLD}; font-size: 9px; font-weight: 700;
                padding: 0;
            }}
            QPushButton:hover {{ background: rgba(201,168,76,0.22); }}
        """

        for label, url in urls:
            row = QHBoxLayout()
            row.setSpacing(8)
            row.setContentsMargins(0, 0, 0, 0)

            lbl = QLabel(f"<b>{label}</b>")
            lbl.setFixedWidth(130)
            lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 11px;")

            url_lbl = QLabel(url)
            url_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 9px;")
            url_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

            copy_btn = QPushButton("Copy")
            copy_btn.setFixedSize(44, 20)
            copy_btn.setStyleSheet(copy_style)
            _url = url
            copy_btn.clicked.connect(lambda _, u=_url: QApplication.clipboard().setText(u))

            row.addWidget(lbl)
            row.addWidget(url_lbl, 1)
            row.addWidget(copy_btn)
            layout.addLayout(row)

        return widget

    # Short display labels for groups whose full names overflow the tab bar
    _TAB_LABELS = {
        "Mountaintops of the Giants":  "MOUNTAINTOPS",
        "Consecrated Snowfield":        "SNOWFIELD",
        "Miquella's Haligtree":         "HALIGTREE",
        "Crumbling Farum Azula":        "FARUM AZULA",
        "Liurnia of the Lakes":         "LIURNIA",
        "Shadow of the Erdtree":        "SOTE",
    }

    def _build_boss_tabs(self, boss_tracker, on_kill, api=None, on_boss_mark=None, ql_sync=None):
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
            tab = BossTab(by_group[group], boss_tracker, on_kill=on_kill,
                          api=api, on_boss_mark=on_boss_mark, ql_sync=ql_sync)
            label = self._TAB_LABELS.get(group, group.upper())
            self._boss_tabs[group] = tab
            # Region tabs (LIMGRAVE, STORMVEIL CASTLE, ...) now live in their
            # own nested QTabWidget (self._boss_progress_tabs) inside
            # RunOverviewTab's single scrolling page, matching the site's
            # "Boss Progress" section -- not top-level siblings of
            # MORTALITY/ITEMS/DEATHS/BUILD anymore.
            self._boss_progress_tabs.addTab(tab, label)

    def _toggle_pin(self, checked):
        self._settings["pin"] = checked
        _save_settings(self._settings)
        self._apply_pin(checked)
        self.settings_tab.sync_pin(checked)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, lambda: self._apply_opacity(self._settings.get("opacity", 100)))

    def closeEvent(self, event):
        if not self._closing:
            self._closing = True
            self.switch_run.emit()
        event.accept()

    def _apply_opacity(self, pct):
        self.setWindowOpacity(max(0.20, min(1.0, pct / 100.0)))

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
        QTimer.singleShot(50, lambda: self._apply_opacity(self._settings.get("opacity", 100)))

    def _on_opacity(self, val):
        self._settings["opacity"] = val
        _save_settings(self._settings)
        self._apply_opacity(val)

    def _on_compact(self, checked):
        height = 32 if checked else 44
        for tab in self._boss_tabs.values():
            for row in tab.rows:
                row.setFixedHeight(height)

    def _on_reset_bosses(self):
        if self.boss_tracker:
            self.boss_tracker.reset_all()
            if self._api:
                self._api.post_boss_reset()

    def open_focus_picker(self):
        """
        Focus hotkey: show a searchable picker of every undefeated boss across
        ALL region tabs (not just whichever tab happens to be visible), and
        focus whichever one is chosen. This is the app-side equivalent of
        the web's "Where did you die?" boss picker, but for setting focus
        rather than attributing a death.
        """
        undefeated = []
        for tab in self._boss_tabs.values():
            undefeated.extend(tab.undefeated_bosses())
        if not undefeated:
            return
        picked = BossFocusPickerDialog.pick(undefeated, parent=self)
        if not picked:
            return
        key, name = picked
        for tab in self._boss_tabs.values():
            if any(row.key == key for row in tab.rows):
                tab.focus_boss(key, name)
                break

    def unfocus_current_boss(self):
        """Unfocus hotkey: clear whatever boss is currently focused, on whichever tab has it."""
        for tab in self._boss_tabs.values():
            if tab._focused_key:
                tab.unfocus_current()

    def defeat_focused_boss(self):
        """Hotkey action: mark the currently focused boss defeated."""
        for tab in self._boss_tabs.values():
            if tab._focused_key:
                return tab.defeat_current()
        return False

    def refresh(self, boss_list, session=None, deaths=None, ql_sync=None, local_run=None, started_at=None):
        by_group = {}
        for b in boss_list:
            by_group.setdefault(b["group"], []).append(b)

        for group, tab in self._boss_tabs.items():
            tab.refresh(by_group.get(group, []))

        s = session or self._session
        d = deaths  or self._deaths
        bosses_defeated = sum(1 for b in boss_list if b.get("defeated"))
        if s and d:
            self.mortality_tab.update_stats(s, d, ql_sync=ql_sync, bosses_defeated=bosses_defeated)

        if ql_sync and ql_sync.running:
            streak  = ql_sync.current_streak_sec()
            longest = ql_sync.longest_life_sec()
            # Run Duration = true lifetime PLAYED time: server-tracked,
            # accumulates ONLY while the listener is connected AND the game
            # exe is detected running (see QuestLogSync/_heartbeat), never
            # reset by Full Reset/Stop Session. The server is the sole
            # source of truth here -- server_authoritative=True means we
            # show exactly what it reports (or "--" if it hasn't sent a
            # value yet), and deliberately do NOT fall back to local
            # wall-clock math, which has no concept of exe state and would
            # silently tick every second regardless of whether the game is
            # even running.
            playtime_sec, _playtime_fmt = ql_sync.get_lifetime_playtime()
            self.mortality_tab.update_timing(streak, longest, started_at=started_at,
                                              lifetime_playtime_sec=playtime_sec,
                                              server_authoritative=True)

            items, collected, total = ql_sync.get_items()
            if items:
                self.items_tab.refresh(items, collected, total)

            recent_deaths = ql_sync.get_recent_deaths()
            if recent_deaths:
                self.death_log_tab.load_from_status(
                    recent_deaths,
                    s.session_deaths if s else 0,
                    s.total_deaths   if s else 0,
                )

        elif local_run:
            self.mortality_tab.update_timing(0, 0, started_at=started_at)
            items, collected, total = local_run.get_items()
            self.items_tab.refresh(items, collected, total)
            recent = local_run.get_recent_deaths()
            self.death_log_tab.load_from_status(
                recent,
                s.session_deaths if s else 0,
                s.total_deaths   if s else 0,
            )


def launch_boss_tracker(boss_tracker):
    app = QApplication.instance() or QApplication(sys.argv)
    window = BossTrackerWindow(boss_tracker)
    window.show()
    return app, window
