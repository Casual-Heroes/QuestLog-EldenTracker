import json
import os
import re
import time

RUNS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "runs")


def _slug(name):
    s = name.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    return s[:48]


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


def create_run(name, game_id, mode_id):
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
    with open(os.path.join(run_dir, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2)

    return slug


def get_run_dir(slug):
    return os.path.join(RUNS_DIR, slug)


def load_run_meta(slug):
    with open(os.path.join(RUNS_DIR, slug, "meta.json")) as f:
        return json.load(f)


def delete_run(slug):
    import shutil
    import time
    import tempfile

    run_dir = os.path.join(RUNS_DIR, slug)
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
