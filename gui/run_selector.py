import os
import time
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QLineEdit, QComboBox, QSizePolicy,
    QMessageBox,
)
from PyQt6.QtCore import Qt, pyqtSignal, QUrl
from PyQt6.QtGui import QFont, QPixmap, QDesktopServices

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")
LOGO_QL    = os.path.join(ASSETS_DIR, "QL1.png")
LOGO_CH    = os.path.join(ASSETS_DIR, "CH.png")
SITE_URL   = "https://questlog.casual-heroes.com"

from core.run import list_runs, create_run, delete_run, load_run_meta
from games.registry import list_games

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

QSS = f"""
* {{ font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif; font-size: 13px; }}
QWidget {{ background: {BG_BASE}; color: {TEXT_PRIMARY}; }}
QPushButton {{
    background: transparent; border: 1px solid {BORDER_SOLID};
    border-radius: 6px; color: {TEXT_MUTED};
    padding: 8px 20px; font-size: 11px; font-weight: 600; letter-spacing: 1px;
}}
QPushButton:hover {{ border-color: {ACCENT_GOLD}; color: {ACCENT_GOLD}; background: rgba(201,168,76,0.06); }}
QPushButton#primary {{
    background: rgba(201,168,76,0.12); border-color: {ACCENT_GOLD}; color: {ACCENT_GOLD};
}}
QPushButton#primary:hover {{ background: rgba(201,168,76,0.22); }}
QPushButton#danger:hover {{ border-color: {ACCENT_RED}; color: {ACCENT_RED}; background: rgba(192,57,15,0.08); }}
QLineEdit {{
    background: {BG_SURFACE}; border: 1px solid {BORDER_SOLID}; border-radius: 6px;
    color: {TEXT_PRIMARY}; padding: 8px 14px; font-size: 13px;
}}
QLineEdit:focus {{ border-color: {ACCENT_GOLD}; }}
QComboBox {{
    background: {BG_SURFACE}; border: 1px solid {BORDER_SOLID}; border-radius: 6px;
    color: {TEXT_PRIMARY}; padding: 8px 14px; font-size: 13px;
}}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{
    background: {BG_CARD}; border: 1px solid {BORDER_SOLID}; color: {TEXT_PRIMARY};
    selection-background-color: rgba(201,168,76,0.15);
}}
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: {BG_BASE}; width: 4px; border: none; margin: 0; }}
QScrollBar::handle:vertical {{ background: {BORDER_SOLID}; border-radius: 2px; min-height: 30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
"""


def _fmt_date(ts):
    import datetime
    return datetime.datetime.fromtimestamp(ts).strftime("%b %d, %Y")


class RunCard(QWidget):
    selected  = pyqtSignal(str)
    deleted   = pyqtSignal(str)

    def __init__(self, meta, parent=None):
        super().__init__(parent)
        self.slug = meta["slug"]
        self.setFixedHeight(72)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QWidget {{
                background: {BG_CARD};
                border: 1px solid {BORDER_SOLID};
                border-radius: 8px;
            }}
            QWidget:hover {{ border-color: rgba(201,168,76,0.4); }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 12, 0)
        layout.setSpacing(12)

        icon = QLabel("✦")
        icon.setStyleSheet(f"color: {ACCENT_GOLD}; font-size: 16px; background: transparent; border: none;")
        icon.setFixedWidth(24)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        name_lbl = QLabel(meta["name"])
        name_lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        name_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent; border: none;")

        game_id = meta.get("game_id", "")
        mode_id = meta.get("mode_id", "")
        sub_lbl = QLabel(f"{game_id.replace('_', ' ').title()}  ·  {mode_id.replace('_', ' ').title()}  ·  {_fmt_date(meta.get('created', 0))}")
        sub_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; background: transparent; border: none;")

        text_col.addWidget(name_lbl)
        text_col.addWidget(sub_lbl)

        del_btn = QPushButton("✕")
        del_btn.setObjectName("danger")
        del_btn.setFixedSize(32, 32)
        del_btn.setToolTip("Delete run")
        del_btn.clicked.connect(lambda: self.deleted.emit(self.slug))

        layout.addWidget(icon)
        layout.addLayout(text_col, 1)
        layout.addWidget(del_btn)

    def mousePressEvent(self, event):
        self.selected.emit(self.slug)


class NewRunPanel(QWidget):
    run_created = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {BG_CARD}; border: 1px solid {BORDER_SOLID}; border-radius: 8px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("NEW RUN")
        title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {TEXT_MUTED}; letter-spacing: 2px; background: transparent; border: none;")
        layout.addWidget(title)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Run name  (e.g. Vanilla First Clear, Reforged NG+)")
        layout.addWidget(self.name_input)

        row = QHBoxLayout()
        row.setSpacing(12)

        self.game_combo = QComboBox()
        self._games     = list_games()
        for g in self._games:
            self.game_combo.addItem(g["name"], g["id"])
        self.game_combo.currentIndexChanged.connect(self._on_game_changed)

        self.mode_combo = QComboBox()
        self._populate_modes()

        row.addWidget(self.game_combo, 1)
        row.addWidget(self.mode_combo, 1)
        layout.addLayout(row)

        create_btn = QPushButton("CREATE RUN")
        create_btn.setObjectName("primary")
        create_btn.setFixedHeight(38)
        create_btn.clicked.connect(self._create)
        layout.addWidget(create_btn)

    def _on_game_changed(self):
        self._populate_modes()

    def _populate_modes(self):
        self.mode_combo.clear()
        idx = self.game_combo.currentIndex()
        if idx < 0 or idx >= len(self._games):
            return
        for m in self._games[idx]["modes"]:
            self.mode_combo.addItem(m["name"], m["id"])

    def _create(self):
        name    = self.name_input.text().strip()
        game_id = self.game_combo.currentData()
        mode_id = self.mode_combo.currentData()
        if not name or not game_id or not mode_id:
            return
        slug = create_run(name, game_id, mode_id)
        self.name_input.clear()
        self.run_created.emit(slug)


class RunSelectorWidget(QWidget):
    run_selected  = pyqtSignal(str)
    run_deleted   = pyqtSignal(str)   # emitted before rmtree so main.py can close file handles

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(QSS)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ────────────────────────────────────────────
        header = QWidget()
        header.setFixedHeight(72)
        header.setStyleSheet(f"background: {BG_SURFACE}; border-bottom: 1px solid {BORDER_SOLID};")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(20, 0, 20, 0)
        h_layout.setSpacing(14)

        # QL logo
        logo_lbl = QLabel()
        pix = QPixmap(LOGO_QL)
        if not pix.isNull():
            logo_lbl.setPixmap(pix.scaledToHeight(44, Qt.TransformationMode.SmoothTransformation))
        else:
            logo_lbl.setText("QL")
            logo_lbl.setStyleSheet(f"color: {ACCENT_GOLD}; font-size: 22px; font-weight: 700;")
        h_layout.addWidget(logo_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title_col.setContentsMargins(0, 0, 0, 0)

        title_lbl = QLabel("QUESTLOG  MORTALITY  TRACKER")
        title_lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; letter-spacing: 3px;")

        sub_lbl = QLabel("Select or create a run to begin  ·  questlog.casual-heroes.com")
        sub_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")

        title_col.addWidget(title_lbl)
        title_col.addWidget(sub_lbl)
        h_layout.addLayout(title_col)
        h_layout.addStretch()

        logo_r = QLabel()
        pix_r = QPixmap(LOGO_QL)
        if not pix_r.isNull():
            logo_r.setPixmap(pix_r.scaledToHeight(36, Qt.TransformationMode.SmoothTransformation))
        h_layout.addWidget(logo_r)

        site_btn = QPushButton("questlog.casual-heroes.com")
        site_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: 1px solid {BORDER_SOLID};
                border-radius: 6px; color: {TEXT_MUTED};
                padding: 6px 14px; font-size: 11px;
            }}
            QPushButton:hover {{ border-color: {ACCENT_GOLD}; color: {ACCENT_GOLD}; }}
        """)
        site_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        site_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(SITE_URL)))
        h_layout.addWidget(site_btn)

        root.addWidget(header)

        # ── Body ──────────────────────────────────────────────
        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(32, 32, 32, 32)
        body_layout.setSpacing(32)
        body_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        left = QVBoxLayout()
        left.setSpacing(12)

        runs_lbl = QLabel("YOUR RUNS")
        runs_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        runs_lbl.setStyleSheet(f"color: {TEXT_MUTED}; letter-spacing: 2px;")
        left.addWidget(runs_lbl)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list_container = QWidget()
        self._list_layout    = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(8)
        self._list_layout.addStretch()
        scroll.setWidget(self._list_container)
        scroll.setMinimumWidth(340)
        left.addWidget(scroll, 1)

        right = QVBoxLayout()
        right.setSpacing(12)
        right.setAlignment(Qt.AlignmentFlag.AlignTop)

        new_lbl = QLabel("START SOMETHING NEW")
        new_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        new_lbl.setStyleSheet(f"color: {TEXT_MUTED}; letter-spacing: 2px;")
        right.addWidget(new_lbl)

        self.new_panel = NewRunPanel()
        self.new_panel.run_created.connect(self._on_run_created)
        right.addWidget(self.new_panel)
        right.addStretch()

        body_layout.addLayout(left, 1)
        body_layout.addLayout(right, 1)
        root.addWidget(body, 1)

        self._populate_runs()

    def _populate_runs(self):
        # Clear existing cards (keep the stretch at end)
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        runs = list_runs()
        if not runs:
            empty = QLabel("No runs yet — create one on the right.")
            empty.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px;")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._list_layout.insertWidget(0, empty)
        else:
            for i, meta in enumerate(runs):
                card = RunCard(meta)
                card.selected.connect(self.run_selected.emit)
                card.deleted.connect(self._on_delete)
                self._list_layout.insertWidget(i, card)

    def _on_run_created(self, slug):
        self._populate_runs()
        self.run_selected.emit(slug)

    def _on_delete(self, slug):
        try:
            meta = load_run_meta(slug)
            run_name = meta.get("name", slug)
        except Exception:
            run_name = slug

        dlg = QMessageBox(self)
        dlg.setWindowTitle("Delete Run")
        dlg.setText(f"Delete <b>{run_name}</b>?")
        dlg.setInformativeText("This will permanently remove all deaths, boss progress, and stats for this run.")
        dlg.setStandardButtons(QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes)
        dlg.setDefaultButton(QMessageBox.StandardButton.Cancel)
        dlg.setStyleSheet(f"QMessageBox {{ background: {BG_CARD}; color: {TEXT_PRIMARY}; }}")
        if dlg.exec() != QMessageBox.StandardButton.Yes:
            return

        # Signal main.py to stop the run if it's currently active — must happen
        # before rmtree so no file handles are open
        self.run_deleted.emit(slug)
        delete_run(slug)
        self._populate_runs()
