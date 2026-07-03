import os
import time
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QLineEdit, QComboBox, QSizePolicy,
    QMessageBox, QCheckBox,
)
from PyQt6.QtCore import Qt, pyqtSignal, QUrl
from PyQt6.QtGui import QFont, QPixmap, QDesktopServices, QIcon

from core.paths import assets as _assets_path
LOGO_QL  = _assets_path("QL1.png")
LOGO_CH  = _assets_path("CH.png")
ICO_CH   = _assets_path("CH.ico")
SITE_URL   = "https://questlog.casual-heroes.com"
GITHUB_URL = "https://github.com/Casual-Heroes/QuestLog-MortalityTracker"

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
        self.setObjectName("RunCard")
        self.setFixedHeight(72)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QWidget#RunCard {{
                background: {BG_CARD};
                border: 1px solid {BORDER_SOLID};
                border-radius: 8px;
            }}
            QWidget#RunCard:hover {{ border-color: rgba(201,168,76,0.4); }}
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

        del_btn = QPushButton("Delete")
        del_btn.setFixedSize(68, 28)
        del_btn.setToolTip("Delete run")
        del_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {BORDER_SOLID};
                border-radius: 5px;
                color: {TEXT_MUTED};
                font-size: 11px;
                padding: 0;
            }}
            QPushButton:hover {{
                border-color: {ACCENT_RED};
                color: {ACCENT_RED};
                background: rgba(192,57,15,0.08);
            }}
        """)
        del_btn.clicked.connect(lambda: self.deleted.emit(self.slug))

        layout.addWidget(icon)
        layout.addLayout(text_col, 1)
        layout.addWidget(del_btn)

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        child = self.childAt(event.pos())
        if child is None or not isinstance(child, QPushButton):
            self.selected.emit(self.slug)

    def mouseDoubleClickEvent(self, event):
        pass


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

        local_row = QHBoxLayout()
        local_row.setSpacing(8)
        self.local_check = QCheckBox()
        self.local_check.setStyleSheet(f"""
            QCheckBox {{ spacing: 0; }}
            QCheckBox::indicator {{
                width: 16px; height: 16px;
                border-radius: 4px;
                border: 1.5px solid {BORDER_SOLID};
                background: {BG_BASE};
            }}
            QCheckBox::indicator:checked {{
                background: rgba(201,168,76,0.2);
                border-color: {ACCENT_GOLD};
            }}
            QCheckBox::indicator:hover {{ border-color: {ACCENT_GOLD}; }}
        """)
        self._local_hint = QLabel("Local run only — no QuestLog sync")
        self._local_hint.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; background: transparent; border: none;")
        self.local_check.stateChanged.connect(self._on_local_changed)
        local_row.addWidget(self.local_check)
        local_row.addWidget(self._local_hint)
        local_row.addStretch()
        layout.addLayout(local_row)

        create_btn = QPushButton("CREATE RUN")
        create_btn.setObjectName("primary")
        create_btn.setFixedHeight(38)
        create_btn.clicked.connect(self._create)
        layout.addWidget(create_btn)

    def _on_game_changed(self):
        self._populate_modes()

    def _on_local_changed(self, state):
        if state:
            self._local_hint.setText("Local only — won't sync to QuestLog")
            self._local_hint.setStyleSheet(f"color: {ACCENT_GOLD}; font-size: 11px; background: transparent; border: none;")
        else:
            self._local_hint.setText("Local run only — no QuestLog sync")
            self._local_hint.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; background: transparent; border: none;")

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
        # local_only=True: store a marker so the run is never matched to a server run
        local_only = self.local_check.isChecked()
        slug = create_run(name, game_id, mode_id, questlog_token="__local__" if local_only else None)
        self.local_check.setChecked(False)
        self.name_input.clear()
        self.run_created.emit(slug)


class ServerRunCard(QWidget):
    """Card showing a QuestLog server run — clicking connects to it."""
    connect_requested = pyqtSignal(dict)   # emits the full server run dict

    def __init__(self, run, is_active=True, parent=None):
        super().__init__(parent)
        self._run = run
        self.setFixedHeight(76)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        border = "#22c55e" if is_active else BORDER_SOLID
        self.setStyleSheet(f"""
            QWidget {{
                background: {BG_CARD};
                border: 1px solid {border};
                border-radius: 8px;
            }}
            QWidget:hover {{ border-color: rgba(201,168,76,0.4); }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 12, 0)
        layout.setSpacing(12)

        dot = QLabel("●" if is_active else "○")
        dot.setStyleSheet(f"color: {'#22c55e' if is_active else TEXT_DIM}; font-size: 10px; background: transparent; border: none;")
        dot.setFixedWidth(16)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        build_name = run.get("build_name") or run.get("name", "")
        game  = run.get("game", "").replace("_", " ").title()
        mode  = run.get("game_mode", "").replace("_", " ").title()
        token = run.get("token", "")
        deaths = run.get("deaths", 0)

        name_lbl = QLabel(build_name or f"{game}  ·  {mode}")
        name_lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        name_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent; border: none;")

        status = "ACTIVE" if is_active else "RECENT"
        sub_lbl = QLabel(f"{game}  ·  {mode}  ·  {deaths} deaths  ·  {status}")
        sub_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; background: transparent; border: none;")

        text_col.addWidget(name_lbl)
        text_col.addWidget(sub_lbl)

        btn_col = QVBoxLayout()
        btn_col.setSpacing(4)

        connect_btn = QPushButton("CONNECT")
        connect_btn.setFixedSize(100, 26)
        connect_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(201,168,76,0.12); border: 1px solid {ACCENT_GOLD};
                border-radius: 5px; color: {ACCENT_GOLD};
                font-size: 10px; font-weight: 700; letter-spacing: 1px;
            }}
            QPushButton:hover {{ background: rgba(201,168,76,0.22); }}
        """)
        connect_btn.clicked.connect(lambda: self.connect_requested.emit(self._run))
        btn_col.addWidget(connect_btn)

        manage_url = run.get("manage_url") or f"https://questlog.casual-heroes.com/soulslike/runs/{token}/"
        overlay_btn = QPushButton("OVERLAYS [web]")
        overlay_btn.setFixedSize(100, 22)
        overlay_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none;
                color: {TEXT_MUTED}; font-size: 9px; letter-spacing: 0.5px;
            }}
            QPushButton:hover {{ color: {ACCENT_GOLD}; }}
        """)
        overlay_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(manage_url)))
        btn_col.addWidget(overlay_btn)

        layout.addWidget(dot)
        layout.addLayout(text_col, 1)
        layout.addLayout(btn_col)

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        child = self.childAt(event.pos())
        if child is None or not isinstance(child, QPushButton):
            self.connect_requested.emit(self._run)

    def mouseDoubleClickEvent(self, event):
        pass


class RunSelectorWidget(QWidget):
    run_selected       = pyqtSignal(str)
    run_deleted        = pyqtSignal(str)
    login_requested    = pyqtSignal()
    server_run_connect = pyqtSignal(dict)
    refresh_requested  = pyqtSignal()
    settings_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(QSS)
        self._server_active  = []  # active_runs from last profile fetch
        self._server_history = []  # run_history from last profile fetch

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ────────────────────────────────────────────
        header = QWidget()
        header.setFixedHeight(76)
        header.setStyleSheet(f"background: {BG_SURFACE}; border-bottom: 1px solid {BORDER_SOLID};")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(20, 0, 20, 0)
        h_layout.setSpacing(14)

        # CH logo (single logo, left side)
        logo_lbl = QLabel()
        pix = QPixmap(LOGO_CH)
        if not pix.isNull():
            logo_lbl.setPixmap(pix.scaledToHeight(44, Qt.TransformationMode.SmoothTransformation))
        else:
            logo_lbl.setText("CH")
            logo_lbl.setStyleSheet(f"color: {ACCENT_GOLD}; font-size: 22px; font-weight: 700;")
        h_layout.addWidget(logo_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title_col.setContentsMargins(0, 0, 0, 0)

        title_lbl = QLabel("ELDENTRACKER")
        title_lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; letter-spacing: 3px;")

        sub_lbl = QLabel("Powered by QuestLog  ·  Developed by Casual Heroes")
        sub_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")

        title_col.addWidget(title_lbl)
        title_col.addWidget(sub_lbl)
        h_layout.addLayout(title_col)
        h_layout.addStretch()

        _btn_style = f"""
            QPushButton {{
                background: transparent; border: 1px solid {BORDER_SOLID};
                border-radius: 6px; color: {TEXT_MUTED};
                padding: 6px 14px; font-size: 11px;
            }}
            QPushButton:hover {{ border-color: {ACCENT_GOLD}; color: {ACCENT_GOLD}; background: rgba(201,168,76,0.06); }}
        """

        self.login_btn = QPushButton("LOGIN WITH QUESTLOG")
        self.login_btn.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT_GOLD}; border: none; border-radius: 6px;
                color: {BG_BASE}; padding: 6px 16px; font-size: 11px; font-weight: 700;
                letter-spacing: 1px;
            }}
            QPushButton:hover {{ background: {ACCENT_GOLD2}; }}
            QPushButton:disabled {{ background: {BG_SURFACE}; color: {TEXT_DIM}; border: 1px solid {BORDER_SOLID}; }}
        """)
        self.login_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        h_layout.addWidget(self.login_btn)

        _icon_btn_style = f"""
            QPushButton {{
                background: transparent; border: 1px solid {BORDER_SOLID};
                border-radius: 6px; color: {TEXT_MUTED}; font-size: 15px;
            }}
            QPushButton:hover {{ border-color: {ACCENT_GOLD}; color: {ACCENT_GOLD}; background: rgba(201,168,76,0.06); }}
            QPushButton:disabled {{ color: {TEXT_DIM}; border-color: {TEXT_DIM}; }}
        """

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setToolTip("Refresh QuestLog runs")
        self.refresh_btn.setFixedHeight(32)
        self.refresh_btn.setStyleSheet(_btn_style)
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.setVisible(False)
        h_layout.addWidget(self.refresh_btn)

        settings_btn = QPushButton("Settings")
        settings_btn.setToolTip("Settings")
        settings_btn.setFixedHeight(32)
        settings_btn.setStyleSheet(_btn_style)
        settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        settings_btn.clicked.connect(self.settings_requested.emit)
        h_layout.addWidget(settings_btn)

        site_btn = QPushButton("QL Site")
        site_btn.setStyleSheet(_btn_style)
        site_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        site_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(SITE_URL)))
        h_layout.addWidget(site_btn)

        github_btn = QPushButton("GitHub")
        github_btn.setStyleSheet(_btn_style)
        github_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        github_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(GITHUB_URL)))
        h_layout.addWidget(github_btn)

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

        self.login_btn.clicked.connect(self.login_requested.emit)
        self.refresh_btn.clicked.connect(self.refresh_requested.emit)
        self._populate_runs()

    def set_logged_in(self, username):
        self.login_btn.setText(f"✓  {username}")
        self.login_btn.setEnabled(False)
        self.login_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: 1px solid #22c55e;
                border-radius: 6px; color: #22c55e;
                padding: 6px 16px; font-size: 11px; font-weight: 700;
            }}
        """)
        self.refresh_btn.setVisible(True)

    def set_server_runs_loading(self):
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText("…")
        # Re-enable after 5s max in case fetch never calls set_server_runs
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(5000, self._reset_refresh_btn)

    def _reset_refresh_btn(self):
        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText("Refresh")

    def set_logged_out(self):
        self.login_btn.setText("LOGIN WITH QUESTLOG")
        self.login_btn.setEnabled(True)
        self.login_btn.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT_GOLD}; border: none; border-radius: 6px;
                color: {BG_BASE}; padding: 6px 16px; font-size: 11px; font-weight: 700;
                letter-spacing: 1px;
            }}
            QPushButton:hover {{ background: {ACCENT_GOLD2}; }}
        """)
        self.refresh_btn.setVisible(False)
        self._server_active  = []
        self._server_history = []
        self._populate_runs()

    def _populate_runs(self):
        # Clear existing cards (keep the stretch at end)
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        local_runs = list_runs()
        # Build set of tokens already represented by local stubs so we don't double-show
        local_tokens = {m.get("questlog_token") for m in local_runs if m.get("questlog_token")}

        # Server active runs first (not already a local stub)
        i = 0
        for run in self._server_active:
            if run.get("token") in local_tokens:
                continue
            card = ServerRunCard(run, is_active=True)
            card.connect_requested.connect(self.server_run_connect.emit)
            self._list_layout.insertWidget(i, card)
            i += 1

        # Local runs
        for meta in local_runs:
            card = RunCard(meta)
            card.selected.connect(self.run_selected.emit)
            card.deleted.connect(self._on_delete)
            self._list_layout.insertWidget(i, card)
            i += 1

        # Server history runs (not already local)
        for run in self._server_history:
            if run.get("token") in local_tokens:
                continue
            card = ServerRunCard(run, is_active=False)
            card.connect_requested.connect(self.server_run_connect.emit)
            self._list_layout.insertWidget(i, card)
            i += 1

        if i == 0:
            empty = QLabel("No runs yet — create one on the right.")
            empty.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px;")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._list_layout.insertWidget(0, empty)

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

    def set_server_runs(self, active_runs, run_history):
        self._reset_refresh_btn()
        self._server_active  = active_runs  or []
        self._server_history = run_history or []
        self._populate_runs()
