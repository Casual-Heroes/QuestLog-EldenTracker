import os
import time
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QLineEdit, QComboBox, QSizePolicy,
    QMessageBox, QCheckBox, QTabWidget,
)
from PyQt6.QtCore import Qt, pyqtSignal, QUrl
from PyQt6.QtGui import QFont, QPixmap, QDesktopServices, QIcon, QImageReader

from core.paths import assets as _assets_path
LOGO_QL  = _assets_path("QL1.png")
LOGO_CH  = _assets_path("CH.png")
ICO_CH   = _assets_path("CH.ico")


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
SITE_URL   = "https://questlog.casual-heroes.com"
GITHUB_URL = "https://github.com/Casual-Heroes/QuestLog-EldenTracker"
UPDATE_URL = SITE_URL + "/soulslike/"
FEEDBACK_URL = SITE_URL + "/feedback/"

from core.run import list_runs, create_run, delete_run, load_run_meta, update_run_meta
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


def _commit_combo_on_press(combo, callback=None):
    """Make popup item clicks commit immediately on Windows."""
    combo.setEditable(False)

    def _pressed(index):
        combo.setCurrentIndex(index.row())
        combo.hidePopup()
        if callback:
            callback(index.row())

    combo.view().pressed.connect(_pressed)


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
    run_created = pyqtSignal(str)   # slug
    server_run_created = pyqtSignal(dict)
    _builds_fetched = pyqtSignal(str, list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._api = None
        self._build_cache = {}
        self._builds_fetched.connect(self._on_builds_fetched)
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

        run_type_lbl = QLabel("RUN TYPE")
        run_type_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        run_type_lbl.setStyleSheet(f"color: {TEXT_MUTED}; letter-spacing: 2px; background: transparent; border: none;")
        run_type_lbl.setToolTip("This is the run's game/mode. Choosing a live save below can update this automatically.")
        layout.addWidget(run_type_lbl)

        row = QHBoxLayout()
        row.setSpacing(12)

        self.game_combo = QComboBox()
        self._games     = list_games()
        for g in self._games:
            self.game_combo.addItem(g["name"], g["id"])
        self.game_combo.currentIndexChanged.connect(self._on_game_changed)
        _commit_combo_on_press(self.game_combo)

        self.mode_combo = QComboBox()
        self._populate_modes()
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        _commit_combo_on_press(self.mode_combo)

        row.addWidget(self.game_combo, 1)
        row.addWidget(self.mode_combo, 1)
        layout.addLayout(row)

        build_lbl = QLabel("BUILD TO TRACK")
        build_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        build_lbl.setStyleSheet(f"color: {TEXT_MUTED}; letter-spacing: 2px; background: transparent; border: none;")
        build_lbl.setToolTip("Optional. Choose a build so QuestLog seeds the run checklist from its equipment.")
        layout.addWidget(build_lbl)

        self.build_combo = QComboBox()
        self.build_combo.setToolTip("Optional. Seeds the run checklist; it does not choose the save file.")
        _commit_combo_on_press(self.build_combo, self._on_build_selected)
        self.build_combo.activated.connect(self._on_build_selected)
        layout.addWidget(self.build_combo)

        save_lbl = QLabel("LIVE SAVE SCAN")
        save_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        save_lbl.setStyleSheet(f"color: {TEXT_MUTED}; letter-spacing: 2px; background: transparent; border: none;")
        save_lbl.setToolTip("Choose the exact character save EldenTracker scans for automatic item collection.")
        layout.addWidget(save_lbl)

        save_row = QHBoxLayout()
        save_row.setSpacing(12)
        self.save_combo = QComboBox()
        self.save_combo.setToolTip("Pick the exact character slot EldenTracker should scan before starting or connecting a run.")
        _commit_combo_on_press(self.save_combo, self._on_save_selected)
        self.save_combo.currentIndexChanged.connect(self._on_save_selected)
        refresh_save_btn = QPushButton("Reload Saves")
        refresh_save_btn.setToolTip("Reload Elden Ring character slots from your save files.")
        refresh_save_btn.setFixedHeight(34)
        refresh_save_btn.clicked.connect(lambda: self._populate_save_slots(prefer_current=True))
        save_row.addWidget(self.save_combo, 1)
        save_row.addWidget(refresh_save_btn)
        layout.addLayout(save_row)
        save_help = QLabel(
            "Auto-collection scans this exact character save. Pick the character you are about to play before creating or connecting a run, or items from the wrong inventory can be marked collected."
        )
        save_help.setWordWrap(True)
        save_help.setStyleSheet(f"color: {ACCENT_GOLD}; font-size: 10px; background: transparent; border: none;")
        layout.addWidget(save_help)
        self._select_saved_save_mode()
        self._populate_save_slots(prefer_current=False)

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
        self._populate_builds()

    def set_api(self, api):
        self._api = api
        self._populate_builds()

    def _on_game_changed(self):
        self._populate_modes()
        self._populate_builds()

    def _on_mode_changed(self):
        self._populate_builds()

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
        if hasattr(self, "save_combo"):
            self._populate_save_slots(prefer_current=True)

    def _build_api_game(self):
        mode_id = self.mode_combo.currentData()
        return "err" if mode_id == "reforged" else "elden_ring"

    def _populate_builds(self):
        if not hasattr(self, "build_combo"):
            return
        game_id = self.game_combo.currentData()
        mode_id = self.mode_combo.currentData()
        self.build_combo.clear()
        self.build_combo.addItem("No build - blank run", None)
        if game_id != "elden_ring" or mode_id not in ("vanilla", "reforged"):
            self.build_combo.setEnabled(False)
            return
        self.build_combo.setEnabled(True)

        api_game = self._build_api_game()
        local_rows = []
        try:
            from core import local_builds as local_builds_store
            for build in local_builds_store.list_local_builds(api_game):
                build = dict(build)
                build["_is_local"] = True
                build["_api_game"] = api_game
                local_rows.append(build)
        except Exception:
            local_rows = []
        self._on_builds_fetched(api_game, local_rows)

        if not self._api:
            return
        import threading
        def _fetch_cloud_builds():
            cloud_rows = self._api.get_builds(game=api_game) or []
            for build in cloud_rows:
                build["_is_local"] = False
                build["_api_game"] = api_game
            self._builds_fetched.emit(api_game, local_rows + cloud_rows)
        threading.Thread(target=_fetch_cloud_builds, daemon=True).start()

    def _on_builds_fetched(self, api_game, builds):
        if api_game != self._build_api_game() or not hasattr(self, "build_combo"):
            return
        current = self.build_combo.currentData()
        current_key = (current or {}).get("share_token") or (current or {}).get("id")
        self._build_cache[api_game] = builds or []
        self.build_combo.blockSignals(True)
        self.build_combo.clear()
        self.build_combo.addItem("No build - blank run", None)
        selected_index = 0
        for build in builds or []:
            label = build.get("name", "Untitled Build")
            level = build.get("level") or build.get("total_level")
            source = "Local" if build.get("_is_local") else "QuestLog"
            if level:
                label = f"{label}  -  Lv {level}  -  {source}"
            else:
                label = f"{label}  -  {source}"
            row_index = self.build_combo.count()
            self.build_combo.addItem(label, build)
            build_key = build.get("share_token") or build.get("id")
            if current_key and build_key == current_key:
                selected_index = row_index
        self.build_combo.setCurrentIndex(selected_index)
        self.build_combo.blockSignals(False)

    def _on_build_selected(self, _index):
        build = self.build_combo.currentData() if hasattr(self, "build_combo") else None
        if build and not self.name_input.text().strip():
            self.name_input.setText(build.get("name", "Untitled Build"))
        if build:
            target_mode = "reforged" if build.get("_api_game") == "err" else "vanilla"
            mode_index = self.mode_combo.findData(target_mode)
            if mode_index >= 0 and self.mode_combo.currentIndex() != mode_index:
                self.mode_combo.setCurrentIndex(mode_index)

    def _on_save_selected(self, _index=None):
        save_choice = self.save_combo.currentData() if hasattr(self, "save_combo") else None
        if not save_choice:
            return
        save_mode = save_choice.get("mode")
        if save_mode in ("vanilla", "reforged"):
            mode_index = self.mode_combo.findData(save_mode)
            if mode_index >= 0 and self.mode_combo.currentIndex() != mode_index:
                self.mode_combo.setCurrentIndex(mode_index)
        from gui.boss_tracker import _load_settings, _save_settings
        settings = _load_settings()
        settings["save_file_path"] = save_choice["path"]
        settings["save_slot"] = save_choice["slot"]
        settings["save_character_name"] = save_choice["name"]
        _save_settings(settings)

    def _same_save_choice(self, left, right) -> bool:
        if not left or not right:
            return False
        return (
            left.get("path") == right.get("path")
            and left.get("slot") == right.get("slot")
            and (not left.get("mode") or not right.get("mode") or left.get("mode") == right.get("mode"))
        )

    def _populate_save_slots(self, prefer_current=False):
        if not hasattr(self, "save_combo"):
            return
        previous_choice = self.save_combo.currentData() if prefer_current else None
        self.save_combo.blockSignals(True)
        self.save_combo.clear()
        game_id = self.game_combo.currentData()
        if game_id != "elden_ring":
            self.save_combo.addItem("Manual item tracking only", None)
            self.save_combo.setEnabled(False)
            self.save_combo.blockSignals(False)
            return
        self.save_combo.setEnabled(True)
        try:
            from core.save_paths import find_save_files
            from core.save_watcher import SaveWatcher
            from gui.boss_tracker import _load_settings
            settings = _load_settings()
            current_path = settings.get("save_file_path", "")
            current_name = settings.get("save_character_name", "")
            try:
                current_slot = int(settings.get("save_slot"))
            except (TypeError, ValueError):
                current_slot = None
            selected_index = -1
            candidates = [c for c in find_save_files() if c["mode"] in ("vanilla", "reforged")]
            if not candidates:
                self.save_combo.addItem("No Elden Ring save found - configure in Settings", None)
                return
            for c in candidates:
                mode_id = c["mode"]
                watcher = SaveWatcher(c["path"], mode=mode_id)
                slots = watcher.list_slots()
                for slot in slots:
                    label = f"{slot['name']}  -  Slot {slot['index']} / Game Slot {slot['index'] + 1}  -  {mode_id.title()}"
                    row_index = self.save_combo.count()
                    self.save_combo.addItem(label, {
                        "path": c["path"],
                        "slot": slot["index"],
                        "name": slot["name"],
                        "mode": mode_id,
                    })
                    choice = self.save_combo.itemData(row_index)
                    if selected_index < 0 and self._same_save_choice(previous_choice, choice):
                        selected_index = row_index
                    elif selected_index < 0 and current_path == c["path"] and current_slot == slot["index"]:
                        selected_index = row_index
                    elif (
                        selected_index < 0
                        and current_slot is None
                        and current_name
                        and current_name == slot["name"]
                    ):
                        selected_index = row_index
            if selected_index >= 0:
                self.save_combo.setCurrentIndex(selected_index)
        except Exception:
            self.save_combo.addItem("Could not read Elden Ring saves - configure in Settings", None)
        finally:
            self.save_combo.blockSignals(False)

    def _select_saved_save_mode(self):
        try:
            from gui.boss_tracker import _load_settings
            save_path = (_load_settings().get("save_file_path") or "").lower()
        except Exception:
            return
        if save_path.endswith(".err"):
            mode_id = "reforged"
        elif save_path.endswith(".sl2"):
            mode_id = "vanilla"
        else:
            return
        idx = self.mode_combo.findData(mode_id)
        if idx >= 0:
            self.mode_combo.setCurrentIndex(idx)

    def _create(self):
        selected_build = self.build_combo.currentData() if hasattr(self, "build_combo") else None
        name    = self.name_input.text().strip() or ((selected_build or {}).get("name") if selected_build else "")
        game_id = self.game_combo.currentData()
        mode_id = self.mode_combo.currentData()
        if not name or not game_id or not mode_id:
            return
        local_only = self.local_check.isChecked()
        save_choice = self.save_combo.currentData() if hasattr(self, "save_combo") else None
        if save_choice:
            self._on_save_selected()
        if not local_only and self._api:
            self._create_questlog_run_from_build(selected_build, name, game_id, mode_id)
            return
        slug = create_run(name, game_id, mode_id,
                          questlog_token="__local__" if local_only else None,
                          save_file_path=save_choice.get("path") if save_choice else None,
                          save_slot=save_choice.get("slot") if save_choice else None,
                          save_character_name=save_choice.get("name") if save_choice else None)
        self.local_check.setChecked(False)
        self.name_input.clear()
        self.run_created.emit(slug)

    @staticmethod
    def _items_from_build_detail(detail):
        items = []
        for slot in ("rh1", "rh2", "rh3", "lh1", "lh2", "lh3"):
            weapon = (detail.get("weapons") or {}).get(slot)
            if weapon and weapon.get("name"):
                items.append({"name": weapon.get("name"), "type": "weapon", "id": weapon.get("id")})
        for armor in (detail.get("armor") or {}).values():
            if armor and armor.get("name"):
                items.append({"name": armor.get("name"), "type": "armor", "id": armor.get("id")})
        for talisman in detail.get("talismans") or []:
            if talisman and talisman.get("name"):
                items.append({"name": talisman.get("name"), "type": "talisman", "id": talisman.get("id")})
        for key, item_type in (
            ("spirit_ash_name", "spirit_ash"),
            ("tear_1_name", "crystal_tear"),
            ("tear_2_name", "crystal_tear"),
        ):
            name = detail.get(key)
            if name:
                items.append({"name": name, "type": item_type})
        return items

    def _create_questlog_run_from_build(self, build, name, game_id, mode_id):
        api_game = self._build_api_game()
        build_key = (build or {}).get("share_token") or (build or {}).get("id")
        self.setEnabled(False)
        import threading
        def _worker():
            detail = {}
            if build and build.get("_is_local"):
                try:
                    from core import local_builds as local_builds_store
                    detail = local_builds_store.load_local_build(build.get("id"), api_game) or {}
                except Exception:
                    detail = {}
            elif build:
                detail = self._api.get_build_detail(build_key, game=api_game) or {}
            items = self._items_from_build_detail(detail)
            result = self._api.create_session(
                game_id,
                mode_id,
                build_name=name,
                items=items,
            )
            if result:
                result.setdefault("game", game_id)
                result.setdefault("game_mode", mode_id)
                result.setdefault("build_name", name)
                result.setdefault("name", name)
            self.server_run_created.emit(result or {})
        threading.Thread(target=_worker, daemon=True).start()


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
        overlay_btn.setFixedSize(120, 22)
        overlay_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none;
                color: {TEXT_MUTED}; font-size: 9px; letter-spacing: 0px;
                text-align: center;
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
    _remote_delete_finished = pyqtSignal(str, str, dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(QSS)
        self.setAutoFillBackground(True)
        from PyQt6.QtGui import QPalette, QColor
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor(BG_BASE))
        self.setPalette(pal)
        self._server_active  = []  # active runs from last profile fetch
        self._server_history = []  # run history from last profile fetch
        self._deleted_server_tokens = set()
        self._pending_delete_slugs = set()
        self._update_url = UPDATE_URL

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
        logo_lbl.setFixedSize(44, 44)
        pix = _load_pixmap(LOGO_CH, ICO_CH)
        if not pix.isNull():
            logo_lbl.setPixmap(pix.scaled(44, 44, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
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

        self.update_btn = QPushButton("UPDATE AVAILABLE")
        self.update_btn.setToolTip("Download the latest EldenTracker release from QuestLog")
        self.update_btn.setFixedHeight(32)
        self.update_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(201,168,76,0.16); border: 1px solid {ACCENT_GOLD};
                border-radius: 6px; color: {ACCENT_GOLD};
                padding: 6px 14px; font-size: 11px; font-weight: 700;
                letter-spacing: 1px;
            }}
            QPushButton:hover {{ background: rgba(201,168,76,0.26); }}
        """)
        self.update_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self._update_url)))
        self.update_btn.setVisible(False)
        h_layout.addWidget(self.update_btn)

        settings_btn = QPushButton("Settings")
        settings_btn.setToolTip("Settings")
        settings_btn.setFixedHeight(32)
        settings_btn.setStyleSheet(_btn_style)
        settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        settings_btn.clicked.connect(self.settings_requested.emit)
        h_layout.addWidget(settings_btn)

        site_btn = QPushButton("Soulslike Hub")
        site_btn.setStyleSheet(_btn_style)
        site_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        site_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(SITE_URL + "/soulslike/")))
        h_layout.addWidget(site_btn)

        feedback_btn = QPushButton("Feedback")
        feedback_btn.setToolTip("Send EldenTracker feedback")
        feedback_btn.setStyleSheet(_btn_style)
        feedback_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        feedback_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(FEEDBACK_URL)))
        h_layout.addWidget(feedback_btn)

        github_btn = QPushButton("GitHub")
        github_btn.setStyleSheet(_btn_style)
        github_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        github_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(GITHUB_URL)))
        h_layout.addWidget(github_btn)

        root.addWidget(header)

        # ── Body ──────────────────────────────────────────────
        body = QWidget()
        body.setAutoFillBackground(True)
        from PyQt6.QtGui import QPalette as _QPalette, QColor as _QColor
        from PyQt6.QtWidgets import QSizePolicy as _QSP
        _pal = body.palette()
        _pal.setColor(_QPalette.ColorRole.Window, _QColor(BG_BASE))
        body.setPalette(_pal)
        body.setSizePolicy(_QSP.Policy.Expanding, _QSP.Policy.Expanding)
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(32, 32, 32, 32)
        body_layout.setSpacing(32)

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
        from PyQt6.QtWidgets import QSizePolicy as _QSP2
        scroll.setSizePolicy(_QSP2.Policy.Expanding, _QSP2.Policy.Expanding)
        left.addWidget(scroll, 1)

        right = QVBoxLayout()
        right.setSpacing(12)

        new_lbl = QLabel("START SOMETHING NEW")
        new_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        new_lbl.setStyleSheet(f"color: {TEXT_MUTED}; letter-spacing: 2px;")
        right.addWidget(new_lbl)

        self.new_panel = NewRunPanel()
        self.new_panel.run_created.connect(self._on_run_created)
        self.new_panel.server_run_created.connect(self._on_server_run_created_from_panel)
        right.addWidget(self.new_panel)
        right.addStretch()

        body_layout.addLayout(left, 1)
        body_layout.addLayout(right, 1)

        # ── Tabs: RUNS (existing body above) | BUILDS (build planner) ──
        from gui.build_planner import BuildPlannerWidget
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: none; background: {BG_BASE}; }}
            QTabBar {{ background: {BG_SURFACE}; }}
            QTabBar::tab {{
                background: transparent; color: {TEXT_MUTED}; padding: 10px 24px;
                font-size: 11px; font-weight: 700; letter-spacing: 1.5px;
            }}
            QTabBar::tab:selected {{ color: {ACCENT_GOLD}; border-bottom: 2px solid {ACCENT_GOLD}; }}
        """)
        self.tabs.addTab(body, "RUNS")
        self.build_planner_tab = BuildPlannerWidget()
        self.build_planner_tab.start_run_requested.connect(self.server_run_connect.emit)
        self.tabs.addTab(self.build_planner_tab, "BUILDS")
        root.addWidget(self.tabs, 1)

        self.login_btn.clicked.connect(self.login_requested.emit)
        self.refresh_btn.clicked.connect(self.refresh_requested.emit)
        self._remote_delete_finished.connect(self._on_remote_delete_finished)
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

    def set_update_available(self, info):
        version = str((info or {}).get("version") or "").strip()
        self._update_url = (info or {}).get("release_url") or (info or {}).get("download_url") or UPDATE_URL
        label = f"UPDATE {version}" if version else "UPDATE AVAILABLE"
        self.update_btn.setText(label.upper())
        self.update_btn.setToolTip("Download the latest EldenTracker release from QuestLog")
        self.update_btn.setVisible(True)

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
        self._deleted_server_tokens = set()
        self._pending_delete_slugs = set()
        self._populate_runs()

    def _populate_runs(self):
        # Clear existing cards (keep the stretch at end)
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        local_runs = list_runs()

        # Tokens of local stubs that are already linked to a server run
        local_tokens = {
            m.get("questlog_token") for m in local_runs
            if m.get("questlog_token") and m.get("questlog_token") != "__local__"
        }

        # Names of local runs that have NO server token — used to suppress the
        # server card when a same-named local stub exists (avoids duplicate rows
        # when START RUN created the local stub before create_session returned a token)
        _MODE_REMAP = {"reforged": "err", "vanilla": "elden_ring"}
        local_unlinked_names = {
            (m.get("name", "").strip().lower(),
             _MODE_REMAP.get(m.get("mode_id", ""), m.get("game_id", "")))
            for m in local_runs
            if not m.get("questlog_token") or m.get("questlog_token") == "__local__"
        }

        def _server_key(run):
            name = (run.get("build_name") or run.get("name", "")).strip().lower()
            game = run.get("game", "")
            return (name, game)

        # Server active runs first — skip if already represented locally
        i = 0
        for run in self._server_active:
            token = run.get("token")
            if token in self._deleted_server_tokens:
                continue
            if token in local_tokens:
                continue
            if _server_key(run) in local_unlinked_names:
                continue
            card = ServerRunCard(run, is_active=True)
            card.connect_requested.connect(self.server_run_connect.emit)
            self._list_layout.insertWidget(i, card)
            i += 1

        # Local runs
        for meta in local_runs:
            if meta.get("slug") in self._pending_delete_slugs:
                continue
            token = meta.get("questlog_token")
            if token and token in self._deleted_server_tokens:
                continue
            card = RunCard(meta)
            card.selected.connect(self.run_selected.emit)
            card.deleted.connect(self._on_delete)
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

    def _on_server_run_created_from_panel(self, server_run):
        self.new_panel.setEnabled(True)
        if server_run.get("token"):
            self.new_panel.local_check.setChecked(False)
            self.new_panel.name_input.clear()
            self.server_run_connect.emit(server_run)
            return
        QMessageBox.warning(
            self,
            "Create Run Failed",
            str(server_run.get("error") or "QuestLog could not create this run."),
        )

    def _on_delete(self, slug):
        meta = {}
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
        token = meta.get("questlog_token")
        is_questlog_run = bool(token and token != "__local__")
        if is_questlog_run:
            self._deleted_server_tokens.add(token)
            self._server_active = [run for run in self._server_active if run.get("token") != token]
            self._server_history = [run for run in self._server_history if run.get("token") != token]
            self._pending_delete_slugs.add(slug)
            if not self.new_panel._api:
                self._deleted_server_tokens.discard(token)
                self._pending_delete_slugs.discard(slug)
                QMessageBox.warning(
                    self,
                    "Delete Run Failed",
                    "QuestLog runs must be deleted while logged in and online.",
                )
                self._populate_runs()
                return
            self._populate_runs()
            import threading

            def _delete_remote():
                result = self.new_panel._api.delete_session(token)
                self._remote_delete_finished.emit(slug, token, result or {})

            threading.Thread(target=_delete_remote, daemon=True).start()
            return

        self.run_deleted.emit(slug)
        delete_run(slug)
        self._populate_runs()

    def _on_remote_delete_finished(self, slug, token, result):
        if result.get("ok"):
            self.run_deleted.emit(slug)
            delete_run(slug)
            self._pending_delete_slugs.discard(slug)
            self._deleted_server_tokens.add(token)
            self._server_active = [run for run in self._server_active if run.get("token") != token]
            self._server_history = [run for run in self._server_history if run.get("token") != token]
            self._populate_runs()
            return

        self._pending_delete_slugs.discard(slug)
        self._deleted_server_tokens.discard(token)
        self._populate_runs()
        QMessageBox.warning(
            self,
            "Delete Run Failed",
            str(result.get("error") or "QuestLog could not delete this run. It was kept locally."),
        )

    def set_server_runs(self, active_runs, run_history, deleted_runs=None):
        self._reset_refresh_btn()
        self._apply_deleted_runs(deleted_runs or [])
        self._server_active  = [
            run for run in (active_runs or [])
            if run.get("token") not in self._deleted_server_tokens
        ]
        self._server_history = [
            run for run in (run_history or [])
            if run.get("token") not in self._deleted_server_tokens
        ]
        self._sync_linked_local_runs_from_server()
        self._populate_runs()

    def _apply_deleted_runs(self, deleted_runs):
        deleted_tokens = set()
        for run in deleted_runs or []:
            token = run.get("token") or run.get("session_token") or run.get("run_token")
            if token:
                deleted_tokens.add(token)
        if not deleted_tokens:
            return
        self._deleted_server_tokens.update(deleted_tokens)
        for meta in list_runs():
            token = meta.get("questlog_token")
            if token in deleted_tokens:
                try:
                    self.run_deleted.emit(meta["slug"])
                    delete_run(meta["slug"])
                except Exception:
                    pass

    def set_api(self, api):
        self.new_panel.set_api(api)
        self.build_planner_tab.set_api(api)

    def _sync_linked_local_runs_from_server(self):
        """Mirror server-side run display metadata onto linked local stubs."""
        server_by_token = {}
        for run in [*self._server_active, *self._server_history]:
            token = run.get("token")
            if token:
                server_by_token[token] = run
        if not server_by_token:
            return

        for meta in list_runs():
            token = meta.get("questlog_token")
            if not token or token == "__local__":
                continue
            server_run = server_by_token.get(token)
            if not server_run:
                continue

            updates = {}
            server_name = (server_run.get("build_name") or server_run.get("name") or "").strip()
            if server_name and server_name != meta.get("name"):
                updates["name"] = server_name
            if server_run.get("started_at") and server_run.get("started_at") != meta.get("started_at"):
                updates["started_at"] = server_run.get("started_at")
            if updates:
                update_run_meta(meta["slug"], updates)
