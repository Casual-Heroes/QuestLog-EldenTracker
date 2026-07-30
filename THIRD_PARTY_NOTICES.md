# Third-Party Notices

QuestLog EldenTracker is an unofficial companion app for tracking Elden Ring and
Elden Ring Reforged runs, deaths, builds, and local save-file item progress.

This project is built to support players and streamers. It does not modify game
files, does not modify Elden Ring Reforged, does not include FromSoftware game
assets, and does not include paid features. The desktop app contains no Ko-fi,
donation, affiliate, or purchase links.

QuestLog EldenTracker is not affiliated with, endorsed by, sponsored by, or
approved by FromSoftware, Bandai Namco, the Elden Ring Reforged team, the Elden
Ring Debug Tool team, Nexus Mods, or any other third-party project referenced
below.

## Elden Ring

Elden Ring and Shadow of the Erdtree are works of FromSoftware and Bandai Namco.
QuestLog EldenTracker uses player-facing names and gameplay reference data only
to identify bosses, items, builds, and run progress inside this companion tool.

No Elden Ring game files, textures, models, audio, maps, executable code, or
other proprietary game assets are included in this repository or desktop app.

## Elden Ring Reforged

Elden Ring Reforged is a community mod for Elden Ring.

Official Nexus page:
https://www.nexusmods.com/eldenring/mods/541

Official wiki:
https://err.fandom.com/wiki/ERR_-_Elden_Ring_Reforged

QuestLog EldenTracker supports Elden Ring Reforged as a compatibility target.
Support is limited to tracking runs, displaying build/planner data, and resolving
local save-file item IDs into readable names. QuestLog EldenTracker does not
modify, package, replace, or redistribute the Elden Ring Reforged mod itself.

All credit for Elden Ring Reforged belongs to its creators and contributors.

## ERR Debug Tool Resources

This repository may include resource text files from the public
`reforged-team/ERR-Debug-Tool-Resources` repository.

Source:
https://github.com/reforged-team/ERR-Debug-Tool-Resources

That project describes itself as Erd-Tools / Elden Ring Debug Tool resources to
support Elden Ring Reforged, and provides item lists for Elden Ring Debug Tool.

QuestLog EldenTracker uses these text resources only as a local item ID to item
name lookup layer for Elden Ring Reforged live save tracking. The app does not
use them to spawn items, edit memory, modify saves, bypass progression, or alter
Elden Ring Reforged behavior. They are used so that a locally owned save-file
item ID can be shown to the player as a readable item name.

All credit for ERR Debug Tool Resources belongs to the reforged-team project and
its contributors.

## Elden Ring Debug Tool / Erd-Tools

Elden Ring Debug Tool is a separate community tool for Elden Ring modding.

Source:
https://github.com/Nordgaren/Elden-Ring-Debug-Tool

QuestLog EldenTracker does not bundle or launch Elden Ring Debug Tool. It uses
the compatible public resource-file format described by that ecosystem for item
lookup data.

All credit for Elden Ring Debug Tool and Erd-Tools belongs to their creators and
contributors.

## Public Catalog And Reference Data

QuestLog EldenTracker includes local JSON catalog snapshots under
`resources/catalog/` so the build planner and tracker can run offline after
installation. These snapshots are generated from QuestLog/Casual Heroes server
catalog APIs and public/reference gameplay data maintained for the companion
tracker.

The app checks for catalog updates when online and falls back to the bundled
snapshot when offline.

## Python And Open Source Dependencies

QuestLog EldenTracker is written in Python and uses open source packages,
including PyQt6, requests, keyboard, psutil, pyinstaller, and their transitive
dependencies.

Dependency versions are managed by `requirements.txt` and the active Python
environment used to build the release package.

## Noncommercial App Intent

QuestLog EldenTracker is released as a free companion app. Casual Heroes may
accept voluntary support for the broader QuestLog website or community work, but
the desktop app itself is not sold, does not include donation prompts, and does
not gate features behind payment.

## Attribution Requests

If you are a creator or maintainer of one of the referenced projects and want an
attribution changed, clarified, or removed, please contact Casual Heroes through
the QuestLog/Casual Heroes project channels. The goal is compatibility,
transparency, and credit, not misrepresentation or appropriation.
