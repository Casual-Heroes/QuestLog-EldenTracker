import json
import re
from urllib.error import URLError
from urllib.request import Request, urlopen

from core.crash_logger import get_logger

log = get_logger("questlog.update")

LATEST_RELEASE_API = "https://api.github.com/repos/Casual-Heroes/QuestLog-EldenTracker/releases/latest"
DOWNLOAD_PAGE = "https://questlog.casual-heroes.com/soulslike/"


def _version_key(version):
    raw = str(version or "").strip().lower().lstrip("v")
    match = re.match(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?([a-z]\d*)?$", raw)
    if not match:
        return (0, 0, 0, "")
    major, minor, patch, suffix = match.groups()
    return (
        int(major or 0),
        int(minor or 0),
        int(patch or 0),
        suffix or "",
    )


def is_newer_version(latest, current):
    latest_key = _version_key(latest)
    current_key = _version_key(current)
    if latest_key[:3] != current_key[:3]:
        return latest_key[:3] > current_key[:3]
    return latest_key[3] > current_key[3]


def check_for_update(current_version, timeout=4):
    """Return update info dict or None.

    Best-effort only: network errors, malformed responses, and missing release
    metadata are logged and treated as "no visible update" so offline/local use
    keeps working.
    """
    try:
        request = Request(
            LATEST_RELEASE_API,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": f"QuestLog-EldenTracker/{current_version}",
            },
        )
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, ValueError) as exc:
        log.info("Update check skipped: %s", exc)
        return None

    tag = str(payload.get("tag_name") or "").strip()
    if not tag or not is_newer_version(tag, current_version):
        return None

    return {
        "version": tag.lstrip("v"),
        "tag": tag,
        "release_url": DOWNLOAD_PAGE,
        "download_url": DOWNLOAD_PAGE,
    }
