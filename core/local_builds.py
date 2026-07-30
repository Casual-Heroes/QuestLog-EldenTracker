"""
Local (offline) Build Planner storage -- saved as JSON on disk, in the same
"build detail response" shape gui/build_planner.py already renders (stats,
class_id, weapons, armor, talismans, etc. -- see
CHARACTER_BUILDER_APP_HANDOFF.md section 3), NOT the older BUILD.slots/
class_base prototype schema used by data/builds/*.json (core/local_run_data.py's
run-item-seeding feature owns that directory/schema; this is a separate,
unrelated feature and deliberately lives in its own directory to avoid any
schema collision).

Local builds never touch the QuestLog server -- no auth, no upload, purely
offline. Distinguishing "local" from "cloud" builds in the UI is done via
the synthetic id prefix "local-" (see new_local_id()).
"""

import json
import os
import re
import time
import uuid

from core.paths import data as _data_path

LOCAL_BUILDS_DIR = _data_path("local_builds")

LOCAL_ID_PREFIX = "local-"


def is_local_id(build_id) -> bool:
    return isinstance(build_id, str) and build_id.startswith(LOCAL_ID_PREFIX)


def new_local_id() -> str:
    return f"{LOCAL_ID_PREFIX}{uuid.uuid4().hex[:12]}"


def _game_dir(game: str) -> str:
    path = os.path.join(LOCAL_BUILDS_DIR, game)
    os.makedirs(path, exist_ok=True)
    return path


def _safe_filename(build_id: str) -> str:
    # build_id is always our own uuid-based new_local_id() output, but sanitize
    # anyway rather than trust it blindly as a path component.
    return re.sub(r'[^a-zA-Z0-9_-]', '_', build_id) + ".json"


def list_local_builds(game: str) -> list:
    """
    Summary list matching the shape of QuestLogClient.get_builds() --
    [{id, name, level, tag, is_public, created_at, updated_at}] -- so the
    sidebar can render local and cloud rows identically.
    """
    game_dir = _game_dir(game)
    results = []
    for fn in sorted(os.listdir(game_dir)):
        if not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(game_dir, fn), encoding="utf-8") as f:
                b = json.load(f)
        except Exception:
            continue
        results.append({
            "id": b.get("id"),
            "name": b.get("name", "Untitled Build"),
            "level": b.get("level", "?"),
            "tag": b.get("tag", "pve"),
            "is_public": False,
            "created_at": b.get("created_at"),
            "updated_at": b.get("updated_at"),
            "is_local": True,
        })
    return results


def load_local_build(build_id: str, game: str):
    path = os.path.join(_game_dir(game), _safe_filename(build_id))
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_local_build(build: dict, game: str) -> dict:
    """
    build must already have an "id" (new_local_id() if this is a brand new
    build -- caller's responsibility, same as the cloud save_build() upsert
    pattern where an existing id updates in place). Returns the saved dict
    (with created_at/updated_at stamped).
    """
    build = dict(build)
    now = time.time()
    if not build.get("created_at"):
        build["created_at"] = now
    build["updated_at"] = now

    path = os.path.join(_game_dir(game), _safe_filename(build["id"]))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(build, f, indent=2, ensure_ascii=False)
    return build


def delete_local_build(build_id: str, game: str) -> bool:
    path = os.path.join(_game_dir(game), _safe_filename(build_id))
    if os.path.isfile(path):
        os.remove(path)
        return True
    return False
