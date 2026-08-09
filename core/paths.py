import os
import shutil
import sys

# When frozen by PyInstaller, all paths resolve relative to the exe.
# When running from source, resolve relative to the project root.
if getattr(sys, "frozen", False):
    ROOT = os.path.dirname(sys.executable)
else:
    ROOT = os.path.join(os.path.dirname(__file__), "..")

ROOT = os.path.abspath(ROOT)
LEGACY_DATA_ROOT = os.path.join(ROOT, "data")


def _default_user_data_root():
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return os.path.join(local, "QuestLog", "EldenTracker")
    return LEGACY_DATA_ROOT


USER_DATA_ROOT = os.path.abspath(
    os.environ.get("ELDENTRACKER_DATA_DIR") or _default_user_data_root()
)


def _copy_missing(src, dst):
    if os.path.isdir(src):
        os.makedirs(dst, exist_ok=True)
        for name in os.listdir(src):
            _copy_missing(os.path.join(src, name), os.path.join(dst, name))
        return
    if os.path.isfile(src) and not os.path.exists(dst):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)


def _migrate_legacy_data():
    """
    One-time best-effort migration from pre-1.1.2 app-folder data into
    %LOCALAPPDATA% so ZIP upgrades can replace the app folder safely.

    This copies missing files only. It never deletes or overwrites legacy
    data, and it intentionally runs before logging is configured.
    """
    if os.path.abspath(USER_DATA_ROOT) == os.path.abspath(LEGACY_DATA_ROOT):
        return
    if not os.path.isdir(LEGACY_DATA_ROOT):
        os.makedirs(USER_DATA_ROOT, exist_ok=True)
        return
    try:
        os.makedirs(USER_DATA_ROOT, exist_ok=True)
        for name in os.listdir(LEGACY_DATA_ROOT):
            _copy_missing(os.path.join(LEGACY_DATA_ROOT, name), os.path.join(USER_DATA_ROOT, name))
        marker = os.path.join(USER_DATA_ROOT, ".migrated_from_app_data")
        if not os.path.exists(marker):
            with open(marker, "w", encoding="utf-8") as f:
                f.write(LEGACY_DATA_ROOT)
    except Exception:
        # Failing closed here would make the app unusable for users with a
        # locked OneDrive/app folder. Continue with the AppData location.
        os.makedirs(USER_DATA_ROOT, exist_ok=True)


_migrate_legacy_data()

def data(*parts):
    return os.path.join(USER_DATA_ROOT, *parts)

def assets(*parts):
    return os.path.join(ROOT, "assets", *parts)

def overlay(*parts):
    return os.path.join(ROOT, "overlay", *parts)

def games(*parts):
    return os.path.join(ROOT, "games", *parts)
