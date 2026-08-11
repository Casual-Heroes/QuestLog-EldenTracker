# QuestLog EldenTracker

**Elden Ring and Elden Ring Reforged desktop tracker** for runs, deaths, bosses, live save item checks, OBS overlays, and build planning.

EldenTracker is built by [Casual Heroes](https://questlog.casual-heroes.com) for players and streamers who want a focused companion app while they play. It works locally without a QuestLog account, and it can optionally connect to QuestLog for cloud synced runs, builds, profile restore, and web overlays.

---

## What It Does

- **Run and death tracking** - total deaths, this session, boss deaths, everything else, current boss deaths, deaths per boss, deaths per hour, current streak, longest life, session time, and run duration.
- **Boss tracking** - focus a current boss, log deaths against it, mark the focused boss defeated, reset boss progress, or keep non-boss deaths separate.
- **Manual correction tools** - set exact total deaths or exact session deaths when a run needs to be repaired.
- **Live save tracking** - choose the save slot/character to track, then let the app scan Elden Ring or Elden Ring Reforged saves for supported inventory items.
- **Item collection checklist** - automatically marks supported weapons, armor, spells, talismans, crystal tears, ashes, key items, and other catalog entries when they exist in the selected save.
- **Tarnished Fury** - the app's tilt meter, including Maiden's Grace through HOLLOW states and Gone Hollow counts.
- **OBS/local overlay** - local browser overlay for stream layouts, including death stats, boss progress, item progress, and Fury status.
- **Build planner** - plan local or QuestLog builds with stats, weapons, armor, talismans, spells, spirit ash, physick, curios, fortunes, binding runes, Ashes of War, affinities, enkindling, runeforging, and attack rating summaries.
- **Catalog updates** - checks QuestLog's public catalog manifest on launch, downloads changed data, verifies it, and falls back to the bundled snapshot when offline.
- **Optional QuestLog sync** - cloud sync for runs, deaths, builds, and profile data when you log in.

---

## Supported Games

| Game | Support |
|------|---------|
| Elden Ring | Base game and Shadow of the Erdtree |
| Elden Ring Reforged | ERR and Shadow of the Erdtree |

More Soulslike games may be added later, but the current app is focused on Elden Ring and Elden Ring Reforged.

---

## Local First, Cloud Optional

You do **not** need a QuestLog account to use EldenTracker.

Local-only runs, builds, settings, logs, builder cache, and catalog cache are stored in:

```text
%LOCALAPPDATA%\QuestLog\EldenTracker
```

Older ZIP builds stored runtime data beside the app in `data\`. On first launch, modern versions copy missing legacy data into `%LOCALAPPDATA%` and leave the old folder untouched as a safety backup.

Logging in with QuestLog adds:

- Cloud run sync
- Cloud build sync
- Profile restore across installs
- Web/OBS overlay status from QuestLog
- QuestLog leaderboards and web build pages

If the internet is unavailable, the app keeps working with local data and the last verified or bundled catalog snapshot.

---

## Live Save Tracking

When creating a run, choose the game mode and the character/save slot you want EldenTracker to follow. Use **Reload Saves** if the save list changes while the app is open.

Live save tracking reads the selected save and marks supported inventory items found in that save. It can catch items you picked up while the tracker was closed, as long as the item can be identified from the save data.

The app does not modify your game files or save files.

Some entries may still require manual tracking when the save data does not expose a clean unique item signal. Known manual cases include:

- Furled Finger's Trick-Mirror
- Perfume Bottle in crystal tear form

---

## Default Hotkeys

| Key | Action |
|-----|--------|
| F9 | Add death |
| F10 | Subtract/undo death |
| F8 hold 3s | Full reset |
| F4 | Focus boss |
| F5 | Unfocus boss |
| F11 | Mark focused boss defeated |

Hotkeys are configurable in the Settings tab.

---

## Death and Boss Controls

The tracker can operate as a local-only counter or as a QuestLog-connected run.

For connected runs, QuestLog is the source of truth after each sync response. The app replaces local counters with the authoritative breakdown from the server:

- Total deaths
- This session
- Boss deaths
- Everything else
- Current boss deaths
- Current streak
- Tarnished Fury state

For local-only runs, the app stores the same run data locally.

---

## Build Planner

The BUILDS tab supports both local and QuestLog builds.

Build planning includes:

- Class and attributes with current rune level preserved
- Six weapon slots with upgrades, Ashes of War, affinities, enkindling, and runeforging
- Armor, talismans, spells, spirit ash, physick tears, curios, fortunes, and binding runes
- Attack Rating summaries for equipped weapons
- ERR-specific data and calculations where available
- Cached catalog data from QuestLog with bundled offline fallback

Elden Ring Reforged support includes ERR-only build systems such as enkindling, runeforging, fortunes, binding runes, and ERR affinity data. Downloaded catalog JSON is data only; executable calculation or UI changes still require an app update.

---

## OBS Overlay

1. Open EldenTracker.
2. In OBS, add a **Browser Source**.
3. Set the URL to:

```text
http://localhost:8765/index.html
```

The tracker starts the local overlay server automatically while the app is running. Size and crop the browser source to fit the overlay layout you want to show.

---

## Installation

### Windows ZIP

Download the latest release from:

- [QuestLog EldenTracker releases](https://github.com/Casual-Heroes/QuestLog-EldenTracker/releases)
- [QuestLog EldenTracker](https://questlog.casual-heroes.com/soulslike/tracker/)

Extract the ZIP and run:

```text
EldenTracker.exe
```

No Python install is required for the packaged build.

### From Source

Python 3.12 is recommended.

```bash
pip install -r requirements.txt
python main.py
```

---

## Data and Catalogs

The app ships with a bundled catalog snapshot so it can work offline after install.

On launch, EldenTracker checks QuestLog's public catalog manifest. If the revision changed, it downloads the updated datasets, verifies byte length and SHA-256, installs them atomically, and uses them for future sessions.

Catalog data covers the app's item, boss, build planner, and regulation-backed calculations where supported. If the public catalog cannot be reached, the app uses the previous verified cache or the bundled snapshot.

---

## Project Structure

```text
main.py                    App entry point
core/                      Sync, paths, save parsing, catalog sync, calculations
games/                     Game definitions and boss data
gui/                       PyQt6 UI for runs, tracker, settings, and builds
overlay/                   Local OBS/browser overlay
assets/                    Logos and icons
resources/catalog/         Bundled offline catalog snapshot
ERR-Debug-Tool-Resources/  ERR reference resources used for supported live data
tools/                     Export, package, validation, and data tooling
```

Runtime user data lives in `%LOCALAPPDATA%\QuestLog\EldenTracker`, not in the release ZIP.

---

## Notices

EldenTracker is a community tool. It is not affiliated with FromSoftware, Bandai Namco, Elden Ring Reforged, or any game publisher or mod team.

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for credits, compatibility notes, and third-party resource attribution for Elden Ring, Elden Ring Reforged, ERR Debug Tool Resources, Elden Ring Debug Tool, and bundled offline catalog data.

---

## License

GNU General Public License v3.0. You are free to use, study, modify, and redistribute the project under the terms of the GPL.
