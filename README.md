# QuestLog EldenTracker

**SoulsLike Boss, Death, and Build Tracker** — track your suffering, plan your build, compete on community leaderboards, and keep every run organised.

Built by [Casual Heroes](https://questlog.casual-heroes.com) for streamers and players who take their deaths seriously.

---

## Features

- **Death tracking** — session and total deaths, deaths per hour, session timer
- **Boss checklist** — tick off every boss as you go, organised by area
- **Rage Index** — a tiered fury system that builds as you die and decays as you kill. Go hollow enough times and it shows
- **OBS overlay** — self-contained HTML browser source, runs a local server automatically, no external dependencies
- **Multiple runs** — create named runs per playthrough, challenge run, or mod. Everything persists per run
- **Build Planner** — plan your full build: weapons, armor, talismans, spells, spirit ashes, crystal tears, Ashes of War, and affinity. Live AR (Attack Rating) breakdown per weapon slot
- **COMPETE tab** — browse active community tournaments, join or leave with one click. Your runs auto-submit to every tournament you've joined when you end a run
- **QuestLog cloud sync** *(optional)* — connect a free QuestLog account to sync runs and builds across sessions, appear on leaderboards, and access your data from the web
- **Always on top / opacity** — pin the tracker over your game, dial in the transparency

---

## Supported Games

| Game | Modes |
|------|-------|
| Elden Ring | Vanilla (base game + Shadow of the Erdtree DLC) |
| Elden Ring | Elden Ring Reforged + DLC (mod) |

More games coming in future releases.

---

## Hotkeys

| Key | Action |
|-----|--------|
| F9 | Manual death |
| F10 | Manual boss kill |
| F8 (hold 3s) | Reset all deaths and rage |

Hotkeys are configurable in the Settings tab.

---

## OBS Overlay Setup

1. In OBS, add a **Browser Source**
2. Set the URL to `http://localhost:8765/index.html` — the tracker starts a local server automatically when it runs
3. Set width to `300`, height to `420`
4. The overlay updates every second while the tracker is open — no additional config needed

The overlay supports three boss display modes (cycle with the button): recent kills, full list, or count only.

---

## Installation

### Option A — Executable (Windows, recommended)

Download the latest release from the [Releases page](https://github.com/Casual-Heroes/QuestLog-EldenTracker/releases), extract the zip anywhere, and run `QuestLog.exe`. No Python or dependencies required.

### Option B — From source

Requires Python 3.11+

```bash
pip install -r requirements.txt
python main.py
```

---

## QuestLog Cloud Sync (optional)

Log in with a free [QuestLog account](https://questlog.casual-heroes.com) to unlock:

- **Run sync** — deaths, boss kills, and session stats backed up to the cloud
- **Build sync** — your builds saved to your account, accessible from any device
- **Leaderboards** — appear on community leaderboards at [questlog.casual-heroes.com/soulslike/leaderboards](https://questlog.casual-heroes.com/soulslike/leaderboards/)
- **Tournaments** — join and leave active community tournaments from the COMPETE tab. When you end a run, it auto-submits to every tournament you've joined

Cloud sync is entirely optional — the tracker works fully offline without an account.

---

## How Runs Work

Each run is a named profile stored under `data/runs/`. You can have as many as you want — one per playthrough, challenge run, or mod. Boss progress, deaths, and session stats are all saved per run and survive restarts.

If you're logged in to QuestLog, runs created here can be connected to a server-side run for cloud sync and leaderboard submission.

---

## Build Planner

The BUILDS tab lets you plan a complete character build before or during a run:

- **Armament** — six weapon slots (RH1/2/3, LH1/2/3) with Ash of War and affinity selection per slot. Live AR panel shows Attack Rating breakdown by damage type
- **Armor** — helm, chest, gauntlets, legs
- **Talismans** — all four talisman slots
- **Spells** — sorceries and incantations
- **Spirit Ash** — with upgrade level
- **Flask** — crystal tear loadout

Supports both Vanilla Elden Ring and Elden Ring Reforged with separate item databases.

Use **START RUN** in the build planner to launch a new tracked run with your build attached.

---

## Rage Index

The Rage Index (called **Tarnished Fury** in Elden Ring) tracks how tilted you are:

| State | Threshold |
|-------|-----------|
| Maiden's Grace | 0% |
| Staggered | 25% |
| Frenzied | 50% |
| Cursed | 75% |
| HOLLOW | 100% |

Rage builds with each death and decays over time or when you kill bosses. Higher-tier kills decay more rage. Going hollow enough times stacks a hollow streak that takes serious boss kills to clear.

---

## Project Structure

```
main.py               — app entry point
core/                 — death tracking, run management, cloud sync, AR calculator
games/                — game definitions (meta.json + boss lists per mode)
gui/                  — PyQt6 UI (run selector, boss tracker, build planner, tournaments)
overlay/              — OBS HTML browser source
assets/               — logos and icons
data/                 — runtime data, not committed (runs, logs, settings, builds)
```

---

## License

GNU General Public License v3.0 — free to use and modify, but any derivative work must also be open source under the same license.

---

*QuestLog EldenTracker is a [Casual Heroes](https://questlog.casual-heroes.com) project. Not affiliated with FromSoftware or any game publisher.*
