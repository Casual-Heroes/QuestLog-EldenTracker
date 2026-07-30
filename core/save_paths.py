"""
Auto-detection for the real Elden Ring save file location.

Confirmed real layout on a live machine:
    %APPDATA%\\EldenRing\\<steamid64>\\ER0000.sl2   (vanilla)
    %APPDATA%\\EldenRing\\<steamid64>\\ER0000.err   (Elden Ring Reforged)
    %APPDATA%\\EldenRing\\<steamid64>\\ER0000.cnv   (Convergence -- not scanned for, out of scope)
    %APPDATA%\\EldenRing\\<steamid64>\\ER0000.err.bak / .old
    %APPDATA%\\EldenRing\\<steamid64>\\ERR Backups\\*.err

No decryption/parsing here -- this module only locates candidate save
files on disk. Vanilla and Reforged only, matching core.save_watcher's
scope (see its module docstring for why Convergence is excluded).
"""

import os
import re

_APPDATA_ELDEN_RING = os.path.join(os.environ.get("APPDATA", ""), "EldenRing")

_STEAM_ID_RE = re.compile(r"^\d+$")

# filename -> mode, in the order we care about them
_CANDIDATE_FILES = {
    "ER0000.sl2": "vanilla",
    "ER0000.err": "reforged",
}


def find_save_files(root: str = None) -> list:
    """
    Scan %APPDATA%\\EldenRing\\* for numeric-named (steam ID) subfolders and
    return every real ER0000.sl2/.err found directly inside one -- never a
    .bak/.old variant, never anything under an "ERR Backups" subfolder.

    Returns a list of dicts: {"path": ..., "steam_id": ..., "mode": "vanilla"
    | "reforged", "mtime": ...}, sorted newest-modified first (the file the
    player most recently played is the most likely one they want tracked,
    useful when multiple Steam accounts exist on one machine).
    """
    root = root or _APPDATA_ELDEN_RING
    found = []
    if not os.path.isdir(root):
        return found

    for entry in os.listdir(root):
        steam_dir = os.path.join(root, entry)
        if not os.path.isdir(steam_dir) or not _STEAM_ID_RE.match(entry):
            continue
        for filename, mode in _CANDIDATE_FILES.items():
            candidate = os.path.join(steam_dir, filename)
            if os.path.isfile(candidate):
                try:
                    mtime = os.path.getmtime(candidate)
                except OSError:
                    continue
                found.append({
                    "path": candidate,
                    "steam_id": entry,
                    "mode": mode,
                    "mtime": mtime,
                })

    found.sort(key=lambda d: d["mtime"], reverse=True)
    return found


def find_save_file_for_mode(mode: str, root: str = None) -> dict | None:
    """
    Returns the single best candidate for the given run mode
    ("vanilla"/"reforged"), or None if zero or multiple candidates exist
    (ambiguous -- caller should surface a manual picker rather than guess).
    """
    matches = [f for f in find_save_files(root) if f["mode"] == mode]
    if len(matches) == 1:
        return matches[0]
    return None
