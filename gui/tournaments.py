"""
Tournament browser + join/leave widget for the COMPETE tab.

Flow:
  - On tab open / refresh: GET /api/soulslike/tournaments/?status=active
  - User clicks JOIN / LEAVE: POST …/join/ or …/leave/
  - User clicks VIEW LEADERBOARD: opens site URL in default browser
  - No leaderboard is rendered in-app — that lives on the site.
    Runs auto-enter joined tournaments when submitted via END RUN.
"""

import threading
import webbrowser

import requests

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QStackedWidget,
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject
from PyQt6.QtGui import QFont

from core.crash_logger import get_logger

log = get_logger("questlog.tournaments")

BASE_URL        = "https://questlog.casual-heroes.com"
SITE_TOURNEY_URL = "https://questlog.casual-heroes.com/soulslike/leaderboards/"

# ── Palette (mirrors build_planner.py) ────────────────────────────────────────
BG_BASE      = "#09090f"
BG_SURFACE   = "#0f1018"
BG_CARD      = "#13141f"
BG_CARD_HOV  = "#181926"
BORDER_SOLID = "#2e3048"
ACCENT_GOLD  = "#c9a84c"
TEXT_PRIMARY = "#f1f0f5"
TEXT_MUTED   = "#6b7280"
TEXT_DIM     = "#8892a4"
GREEN_LIVE   = "#22c55e"
HC_COLOR     = "#ef4444"


# ── Signal bridges (Qt signals must live on QObject) ─────────────────────────
class _TourneysReady(QObject):
    ready = pyqtSignal(list)

class _ActionDone(QObject):
    done = pyqtSignal(bool, int)   # joined, tournament_id


# ── Helpers ───────────────────────────────────────────────────────────────────
def _headers(api_key: str) -> dict:
    return {"X-Listener-Key": api_key, "Content-Type": "application/json"}


def _cat_label(category: str) -> str:
    if category.startswith("custom:"):
        return category[7:]
    return {
        "longest_life":       "Iron Tarnished",
        "true_grit":          "True Grit",
        "death_machine":      "Death Machine",
        "hollow_lord":        "Hollow Lord",
        "hollow_depth":       "Hollow Depth",
        "boss_slayer":        "Boss Slayer",
        "glass_cannon":       "Glass Cannon",
        "from_hollow_rising": "From Hollow, Rising",
        "tarnished_legend":   "Tarnished Legend",
        "undying":            "Undying",
        "veteran":            "Veteran",
        "the_grind":          "The Grind",
        "sisyphus":           "Sisyphus",
        "hc_score":           "HC Score",
        "hc_completions":     "HC Completions",
        "hc_perma":           "Perma Deaths",
    }.get(category, category.replace("_", " ").title())


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
    lbl.setStyleSheet(
        f"color: {TEXT_MUTED}; letter-spacing: 2.5px; "
        f"background: transparent; padding-top: 4px;"
    )
    return lbl


# ── Tournament card ────────────────────────────────────────────────────────────
class TournamentCard(QWidget):
    join_requested  = pyqtSignal(dict)
    leave_requested = pyqtSignal(dict)

    def __init__(self, data: dict, parent=None):
        super().__init__(parent)
        self._data   = data
        self._joined = data.get("is_joined", False)
        self.setObjectName("TCard")
        self._apply_style(hover=False)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(6)

        # Row 1: name + HC badge + time badge
        top = QHBoxLayout()
        top.setSpacing(8)

        name_lbl = QLabel(data.get("name", "Tournament"))
        name_lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        name_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")
        top.addWidget(name_lbl, 1)

        if data.get("is_hardcore") or "hc" in data.get("category", "").lower():
            hc = QLabel("HC")
            hc.setStyleSheet(
                f"color: {HC_COLOR}; background: rgba(239,68,68,0.12); "
                f"border: 1px solid rgba(239,68,68,0.35); border-radius: 4px; "
                f"font-size: 9px; font-weight: 700; letter-spacing: 1.5px; padding: 2px 6px;"
            )
            top.addWidget(hc)

        time_str = data.get("time_str", "")
        if time_str:
            tb = QLabel(time_str)
            tb.setStyleSheet(
                f"color: {ACCENT_GOLD}; font-size: 10px; font-weight: 600; background: transparent;"
            )
            top.addWidget(tb)

        root.addLayout(top)

        # Row 2: chips + participant count
        mid = QHBoxLayout()
        mid.setSpacing(6)

        chip_style = (
            f"color: {TEXT_DIM}; background: rgba(255,255,255,0.05); "
            f"border: 1px solid {BORDER_SOLID}; border-radius: 4px; "
            f"font-size: 9px; font-weight: 600; letter-spacing: 1px; padding: 2px 8px;"
        )

        cat_chip = QLabel(_cat_label(data.get("category", "")))
        cat_chip.setStyleSheet(chip_style)
        mid.addWidget(cat_chip)

        game_str = data.get("game", "elden_ring").replace("_", " ").title()
        if data.get("game_mode") == "err":
            game_str = "Elden Ring Reforged"
        game_chip = QLabel(game_str)
        game_chip.setStyleSheet(chip_style)
        mid.addWidget(game_chip)

        mid.addStretch()

        pcount = data.get("participant_count", 0)
        pc_lbl = QLabel(f"{pcount} player{'s' if pcount != 1 else ''}")
        pc_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; background: transparent;")
        mid.addWidget(pc_lbl)

        root.addLayout(mid)

        # Optional description
        desc = data.get("description", "")
        if desc:
            d_lbl = QLabel(desc[:140] + ("…" if len(desc) > 140 else ""))
            d_lbl.setWordWrap(True)
            d_lbl.setStyleSheet(f"color: {TEXT_DIM}; font-size: 10px; background: transparent;")
            root.addWidget(d_lbl)

        # Personal rank (only shown when joined and data is available)
        personal = data.get("personal")
        if personal:
            rank_lbl = QLabel(
                f"Your rank: #{personal['rank']}  {personal.get('score_fmt', '')}"
            )
            rank_lbl.setStyleSheet(
                f"color: {ACCENT_GOLD}; font-size: 11px; font-weight: 600; background: transparent;"
            )
            root.addWidget(rank_lbl)

        # Row 3: VIEW ON SITE + JOIN/LEAVE
        bot = QHBoxLayout()
        bot.setSpacing(8)
        bot.addStretch()

        site_url = data.get("leaderboard_url") or SITE_TOURNEY_URL
        view_btn = QPushButton("VIEW LEADERBOARD ↗")
        view_btn.setFixedHeight(28)
        view_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: 1px solid {BORDER_SOLID};
                border-radius: 5px; color: {TEXT_DIM}; font-size: 9px;
                font-weight: 700; letter-spacing: 1px; padding: 0 12px; min-height: 0;
            }}
            QPushButton:hover {{ border-color: {ACCENT_GOLD}; color: {ACCENT_GOLD}; }}
        """)
        view_btn.setToolTip("Opens full leaderboard on QuestLog site")
        view_btn.clicked.connect(lambda: webbrowser.open(site_url))
        bot.addWidget(view_btn)

        self._join_btn = QPushButton()
        self._join_btn.setFixedHeight(28)
        self._join_btn.clicked.connect(self._on_join_click)
        self._update_join_btn()
        bot.addWidget(self._join_btn)

        root.addLayout(bot)

    # ── Style helpers ─────────────────────────────────────────────────────────

    def _apply_style(self, hover=False):
        bg = BG_CARD_HOV if hover else BG_CARD
        self.setStyleSheet(f"""
            QWidget#TCard {{
                background: {bg}; border: 1px solid {BORDER_SOLID}; border-radius: 10px;
            }}
        """)

    def _update_join_btn(self):
        if self._joined:
            self._join_btn.setText("✓ JOINED")
            self._join_btn.setStyleSheet(f"""
                QPushButton {{
                    background: rgba(34,197,94,0.12); border: 1px solid rgba(34,197,94,0.4);
                    border-radius: 5px; color: {GREEN_LIVE}; font-size: 9px;
                    font-weight: 700; letter-spacing: 1px; padding: 0 12px; min-height: 0;
                }}
                QPushButton:hover {{
                    background: rgba(239,68,68,0.12); border-color: rgba(239,68,68,0.4);
                    color: {HC_COLOR};
                }}
            """)
            self._join_btn.setToolTip("Click to leave this tournament")
        else:
            self._join_btn.setText("JOIN")
            self._join_btn.setStyleSheet(f"""
                QPushButton {{
                    background: rgba(201,168,76,0.15); border: 1px solid rgba(201,168,76,0.45);
                    border-radius: 5px; color: {ACCENT_GOLD}; font-size: 9px;
                    font-weight: 700; letter-spacing: 1px; padding: 0 12px; min-height: 0;
                }}
                QPushButton:hover {{ background: rgba(201,168,76,0.28); }}
            """)
            self._join_btn.setToolTip("Join this tournament — your runs will auto-enter")

    def set_joined(self, joined: bool):
        self._joined = joined
        self._data["is_joined"] = joined
        self._update_join_btn()

    def _on_join_click(self):
        if self._joined:
            self.leave_requested.emit(self._data)
        else:
            self.join_requested.emit(self._data)

    def enterEvent(self, e):
        self._apply_style(hover=True)

    def leaveEvent(self, e):
        self._apply_style(hover=False)


# ── Main widget ────────────────────────────────────────────────────────────────
class TournamentWidget(QWidget):
    """
    COMPETE tab.
    - Lists active / upcoming tournaments.
    - Per-card JOIN / LEAVE toggle (API call in background thread).
    - VIEW LEADERBOARD opens the QuestLog site in the default browser.
    - Shows a "log in to compete" gate when no API key is set.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._api_key  = ""
        self._tourneys: list[dict] = []
        self._cards:    dict[int, TournamentCard] = {}

        self.setStyleSheet(f"background: {BG_BASE};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._stack = QStackedWidget()
        root.addWidget(self._stack)

        # ── Page 0: not logged in ─────────────────────────────────────────────
        gate = QWidget()
        gate.setStyleSheet(f"background: {BG_BASE};")
        gl = QVBoxLayout(gate)
        gl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        gl.setSpacing(10)

        icon = QLabel("🏆")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("font-size: 48px; background: transparent;")
        gl.addWidget(icon)

        gt = QLabel("Log in to compete")
        gt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        gt.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        gt.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")
        gl.addWidget(gt)

        gs = QLabel(
            "Connect your QuestLog account to join tournaments.\n"
            "When you end a run, it auto-submits to every tournament you've joined."
        )
        gs.setAlignment(Qt.AlignmentFlag.AlignCenter)
        gs.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; background: transparent;")
        gl.addWidget(gs)

        self._stack.addWidget(gate)

        # ── Page 1: tournament list ───────────────────────────────────────────
        list_page = QWidget()
        list_page.setStyleSheet(f"background: {BG_BASE};")
        lp = QVBoxLayout(list_page)
        lp.setContentsMargins(0, 0, 0, 0)
        lp.setSpacing(0)

        # Header bar
        hdr = QWidget()
        hdr.setFixedHeight(56)
        hdr.setStyleSheet(f"background: {BG_SURFACE}; border-bottom: 1px solid {BORDER_SOLID};")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(24, 0, 24, 0)
        hl.setSpacing(12)

        h_title = QLabel("TOURNAMENTS")
        h_title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        h_title.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")
        hl.addWidget(h_title, 1)

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 10px; background: transparent;"
        )
        hl.addWidget(self._status_lbl)

        refresh_btn = QPushButton("↻ REFRESH")
        refresh_btn.setFixedHeight(30)
        refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: 1px solid {BORDER_SOLID};
                border-radius: 5px; color: {TEXT_DIM}; font-size: 9px;
                font-weight: 700; letter-spacing: 1px; padding: 0 12px; min-height: 0;
            }}
            QPushButton:hover {{ border-color: {ACCENT_GOLD}; color: {ACCENT_GOLD}; }}
        """)
        refresh_btn.clicked.connect(self.refresh)
        hl.addWidget(refresh_btn)

        lp.addWidget(hdr)

        # Info banner
        info_bar = QWidget()
        info_bar.setStyleSheet(
            f"background: rgba(201,168,76,0.06); border-bottom: 1px solid {BORDER_SOLID};"
        )
        il = QHBoxLayout(info_bar)
        il.setContentsMargins(24, 10, 24, 10)
        info_lbl = QLabel(
            "Join a tournament before you start your run. "
            "QuestLog auto-submits your run to all tournaments you've joined when you end it."
        )
        info_lbl.setWordWrap(True)
        info_lbl.setStyleSheet(f"color: {TEXT_DIM}; font-size: 10px; background: transparent;")
        il.addWidget(info_lbl)
        lp.addWidget(info_bar)

        # Scroll area for cards
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"background: {BG_BASE}; border: none;")

        self._list_inner = QWidget()
        self._list_inner.setStyleSheet(f"background: {BG_BASE};")
        self._list_layout = QVBoxLayout(self._list_inner)
        self._list_layout.setContentsMargins(24, 20, 24, 20)
        self._list_layout.setSpacing(10)

        self._empty_lbl = QLabel("No active tournaments right now — check back soon.")
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_lbl.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 12px; background: transparent;"
        )
        self._empty_lbl.setVisible(False)
        self._list_layout.addWidget(self._empty_lbl)
        self._list_layout.addStretch()

        scroll.setWidget(self._list_inner)
        lp.addWidget(scroll, 1)

        self._stack.addWidget(list_page)

        # Signal bridges
        self._list_bridge   = _TourneysReady()
        self._list_bridge.ready.connect(self._on_list_ready)
        self._action_bridge = _ActionDone()
        self._action_bridge.done.connect(self._on_action_done)

        self._stack.setCurrentIndex(0)

    # ── Public API ────────────────────────────────────────────────────────────

    def set_api_key(self, key: str):
        self._api_key = key
        if key:
            self._stack.setCurrentIndex(1)
            self.refresh()
        else:
            self._stack.setCurrentIndex(0)

    def refresh(self):
        if not self._api_key:
            return
        self._status_lbl.setText("Loading…")
        def _fetch():
            try:
                r = requests.get(
                    f"{BASE_URL}/api/soulslike/tournaments/",
                    headers=_headers(self._api_key),
                    params={"status": "active", "game": "elden_ring"},
                    timeout=10,
                )
                data = r.json() if r.ok else {}
                self._list_bridge.ready.emit(data.get("tournaments", []))
            except Exception as e:
                log.warning("Tournament fetch failed: %s", e)
                self._list_bridge.ready.emit([])
        threading.Thread(target=_fetch, daemon=True).start()

    # ── Internal slots ────────────────────────────────────────────────────────

    def _on_list_ready(self, tourneys: list):
        self._tourneys = tourneys
        self._status_lbl.setText(f"{len(tourneys)} active" if tourneys else "")
        self._rebuild_list(tourneys)

    def _rebuild_list(self, tourneys: list):
        # Clear all card rows; keep _empty_lbl and trailing stretch
        while self._list_layout.count() > 2:
            item = self._list_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self._cards.clear()

        if not tourneys:
            self._empty_lbl.setVisible(True)
            return

        self._empty_lbl.setVisible(False)

        joined     = [t for t in tourneys if t.get("is_joined")]
        not_joined = [t for t in tourneys if not t.get("is_joined")]

        insert_at = 0
        if joined:
            self._list_layout.insertWidget(insert_at, _section_label("YOUR TOURNAMENTS"))
            insert_at += 1
            for t in joined:
                self._list_layout.insertWidget(insert_at, self._make_card(t))
                insert_at += 1

        if not_joined:
            self._list_layout.insertWidget(insert_at, _section_label("OPEN TOURNAMENTS"))
            insert_at += 1
            for t in not_joined:
                self._list_layout.insertWidget(insert_at, self._make_card(t))
                insert_at += 1

    def _make_card(self, t: dict) -> TournamentCard:
        card = TournamentCard(t)
        card.join_requested.connect(self._do_join)
        card.leave_requested.connect(self._do_leave)
        tid = t.get("id")
        if tid:
            self._cards[tid] = card
        return card

    def _do_join(self, t: dict):
        tid = t.get("id")
        self._status_lbl.setText("Joining…")
        def _post():
            try:
                r = requests.post(
                    f"{BASE_URL}/api/soulslike/tournaments/{tid}/join/",
                    headers=_headers(self._api_key),
                    timeout=10,
                )
                joined = r.json().get("joined", False) if r.ok else False
                self._action_bridge.done.emit(joined, tid)
            except Exception as e:
                log.warning("Tournament join failed: %s", e)
                self._action_bridge.done.emit(False, tid)
        threading.Thread(target=_post, daemon=True).start()

    def _do_leave(self, t: dict):
        tid = t.get("id")
        self._status_lbl.setText("Leaving…")
        def _post():
            try:
                r = requests.post(
                    f"{BASE_URL}/api/soulslike/tournaments/{tid}/leave/",
                    headers=_headers(self._api_key),
                    timeout=10,
                )
                still_joined = r.json().get("joined", True) if r.ok else True
                self._action_bridge.done.emit(not still_joined, tid)
            except Exception as e:
                log.warning("Tournament leave failed: %s", e)
                self._action_bridge.done.emit(True, tid)
        threading.Thread(target=_post, daemon=True).start()

    def _on_action_done(self, joined: bool, tid: int):
        self._status_lbl.setText("")
        for t in self._tourneys:
            if t.get("id") == tid:
                t["is_joined"] = joined
                break
        self._rebuild_list(self._tourneys)
        log.info("Tournament %d joined=%s", tid, joined)
