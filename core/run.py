import json
import os
import re
import time

from core.paths import data as _data_path
RUNS_DIR  = _data_path("runs")
SAVES_DIR = _data_path("builds")  # expected parent for all build_path values


def _safe_run_dir(slug: str) -> str | None:
    """Return the run directory only if slug resolves inside RUNS_DIR."""
    if not slug:
        return None
    real = os.path.realpath(os.path.join(RUNS_DIR, str(slug)))
    allowed = os.path.realpath(RUNS_DIR)
    if real == allowed:
        return None
    if real.startswith(allowed + os.sep):
        return real
    return None


def _safe_build_path(build_path: str) -> str | None:
    """Return realpath of build_path only if it lives inside SAVES_DIR, else None."""
    if not build_path:
        return None
    real = os.path.realpath(build_path)
    allowed = os.path.realpath(SAVES_DIR)
    if real.startswith(allowed + os.sep) or real == allowed:
        return real
    return None


_WIN_RESERVED = {
    "con", "prn", "aux", "nul",
    *[f"com{i}" for i in range(1, 10)],
    *[f"lpt{i}" for i in range(1, 10)],
}

def _slug(name):
    s = name.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    s = s[:48]
    if s in _WIN_RESERVED:
        s = f"run-{s}"
    return s or "run"


def list_runs():
    """Return list of run meta dicts, newest first."""
    runs = []
    if not os.path.isdir(RUNS_DIR):
        return runs
    for entry in os.listdir(RUNS_DIR):
        meta_path = os.path.join(RUNS_DIR, entry, "meta.json")
        if os.path.isfile(meta_path):
            try:
                with open(meta_path) as f:
                    runs.append(json.load(f))
            except Exception:
                pass
    runs.sort(key=lambda r: r.get("created", 0), reverse=True)
    return runs


def create_run(
    name,
    game_id,
    mode_id,
    questlog_token=None,
    build_path=None,
    started_at=None,
    save_file_path=None,
    save_slot=None,
    save_character_name=None,
):
    """Create a new run directory and meta.json. Returns the run slug."""
    base = _slug(name)
    slug = base
    idx  = 1
    while os.path.exists(os.path.join(RUNS_DIR, slug)):
        slug = f"{base}-{idx}"
        idx += 1

    run_dir = os.path.join(RUNS_DIR, slug)
    os.makedirs(run_dir, exist_ok=True)

    meta = {
        "slug":     slug,
        "name":     name,
        "game_id":  game_id,
        "mode_id":  mode_id,
        "created":  time.time(),
    }
    if questlog_token:
        meta["questlog_token"] = questlog_token
    if started_at:
        meta["started_at"] = started_at
    if save_file_path:
        meta["save_file_path"] = save_file_path
    if save_slot is not None:
        meta["save_slot"] = save_slot
    if save_character_name:
        meta["save_character_name"] = save_character_name
    if build_path:
        safe = _safe_build_path(build_path)
        if safe:
            meta["build_path"] = safe
        else:
            from core.crash_logger import get_logger as _gl
            _gl("questlog.run").warning("build_path outside allowed dir — not stored: %r", build_path)
    with open(os.path.join(run_dir, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2)

    return slug


def update_run_meta(slug, updates: dict):
    """Merge updates into an existing run's meta.json."""
    run_dir = _safe_run_dir(slug)
    if not run_dir:
        return
    path = os.path.join(run_dir, "meta.json")
    try:
        with open(path) as f:
            meta = json.load(f)
    except Exception:
        meta = {}
    meta.update(updates)
    with open(path, "w") as f:
        json.dump(meta, f, indent=2)


def get_run_dir(slug):
    return _safe_run_dir(slug) or os.path.join(RUNS_DIR, "_invalid")


def load_run_meta(slug):
    run_dir = _safe_run_dir(slug)
    if not run_dir:
        raise FileNotFoundError("invalid run slug")
    with open(os.path.join(run_dir, "meta.json")) as f:
        return json.load(f)


def delete_run(slug):
    import shutil
    import time
    import tempfile

    run_dir = _safe_run_dir(slug)
    if not run_dir:
        return
    if not os.path.isdir(run_dir):
        return

    # First try a direct rmtree (fast path)
    try:
        shutil.rmtree(run_dir)
        return
    except PermissionError:
        pass

    # OneDrive (or antivirus) may hold the directory open briefly.
    # Rename the folder out of the runs dir first — that always works even
    # while a sync lock is held — then delete the renamed copy.
    try:
        tmp = os.path.join(tempfile.gettempdir(), f"ql_deleted_{slug}_{int(time.time())}")
        os.rename(run_dir, tmp)
        shutil.rmtree(tmp, ignore_errors=True)
    except Exception:
        # Last-ditch: wait 500ms and try one more time
        time.sleep(0.5)
        shutil.rmtree(run_dir, ignore_errors=True)


def save_active_slug(slug):
    path = os.path.join(os.path.dirname(RUNS_DIR), "active_run.json")
    with open(path, "w") as f:
        json.dump({"slug": slug}, f)


def load_active_slug():
    path = os.path.join(os.path.dirname(RUNS_DIR), "active_run.json")
    if os.path.isfile(path):
        try:
            with open(path) as f:
                return json.load(f).get("slug")
        except Exception:
            pass
    return None
