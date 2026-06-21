# QuestLog Mortality Tracker

**SoulsLike Boss, Item and Death Tracker** — see how well you do, keep track of your 100%, and create new runs for each session you play.

Built by [Casual Heroes](https://questlog.casual-heroes.com) for streamers and players who want to track their suffering properly.

---

## Features

- **Death tracking** — session and total deaths, deaths per hour, session timer
- **Boss checklist** — tick off every boss as you go, organised by area
- **Rage Index** — a tiered fury system that builds as you die and decays as you kill. Go hollow enough times and it shows
- **OBS overlay** — self-contained HTML browser source, no server needed
- **Multiple runs** — create named runs per playthrough, switch between them, everything persists
- **Auto-resume** — reopening the app picks up where you left off
- **OCR death detection** — automatically detects the YOU DIED screen via screen capture (hotkeys available as fallback)
- **Always on top / opacity** — pin the tracker over your game, dial in the transparency

---

## Supported Games

| Game | Modes |
|------|-------|
| Elden Ring | Vanilla (base game + Shadow of the Erdtree DLC) |
| Elden Ring | Elden Ring Reforged (mod) |

More games coming in future releases.

---

## Hotkeys

| Key | Action |
|-----|--------|
| F9 | Manual death |
| F10 | Manual boss kill |
| F8 (hold 3s) | Reset all deaths and rage |

---

## OBS Overlay Setup

1. In OBS, add a **Browser Source**
2. Check **Local file** and point it to `overlay/index.html` in the tracker folder
3. Set width to `300`, height to `420`
4. The overlay polls `stats.json` every second automatically — no config needed

The overlay supports three boss display modes (cycle with the button): recent kills, full list, or count only.

---

## Installation

Requires Python 3.11+

```bash
pip install -r requirements.txt
python main.py
```

> **Note:** On first launch, EasyOCR will download its English model (~100MB). This only happens once. The tracker runs in hotkey-only mode until the download completes.

---

## How Runs Work

Each run is a named profile stored under `data/runs/`. You can have as many as you want — one per playthrough, challenge run, or mod. Boss progress, deaths, and session stats are all saved per run and survive restarts.

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
core/                 — session, death tracking, OCR detection, run management
games/                — game definitions (meta.json + boss lists per mode)
gui/                  — PyQt6 UI (run selector, boss tracker window)
overlay/              — OBS HTML browser source
assets/               — logos and icons
data/                 — runtime data, not committed (runs, logs, settings)
```

---

## License

MIT — free to use, fork, and build on.

---

*QuestLog Mortality Tracker is a Casual Heroes project. Not affiliated with FromSoftware or any game publisher.*
