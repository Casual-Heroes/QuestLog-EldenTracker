import json
import os
import secrets
import sys


KEYRING_SERVICE = "QuestLog.EldenTracker"
KEYRING_ACCOUNT = "listener_api_key"
LEGACY_KEYRING_SERVICE = "QuestLog-EldenTracker"
LEGACY_KEYRING_ACCOUNT = "api_key"

LEGACY_SECRET_FIELDS = {
    "api_key",
    "listener_api_key",
    "access_token",
    "refresh_token",
    "authorization",
    "authorization_header",
    "code",
    "oauth_code",
    "state",
    "oauth_state",
}


class CredentialStorageError(Exception):
    pass


def _require_windows_keyring():
    if sys.platform != "win32":
        raise CredentialStorageError("Windows Credential Manager is required for persistent QuestLog login.")
    try:
        import keyring
    except Exception as exc:
        raise CredentialStorageError("The keyring package is not available.") from exc

    backend = keyring.get_keyring()
    module = backend.__class__.__module__
    name = backend.__class__.__name__.lower()
    if not module.startswith("keyring.backends.Windows") and "winvault" not in name:
        raise CredentialStorageError("Windows Credential Manager is not the active keyring backend.")
    return keyring


def load_api_key() -> str:
    keyring = _require_windows_keyring()
    try:
        api_key = keyring.get_password(KEYRING_SERVICE, KEYRING_ACCOUNT) or ""
        if api_key:
            return api_key
        legacy_key = keyring.get_password(LEGACY_KEYRING_SERVICE, LEGACY_KEYRING_ACCOUNT) or ""
        if legacy_key:
            save_api_key(legacy_key)
            try:
                keyring.delete_password(LEGACY_KEYRING_SERVICE, LEGACY_KEYRING_ACCOUNT)
            except Exception:
                pass
            return legacy_key
        return ""
    except Exception as exc:
        raise CredentialStorageError("Windows Credential Manager could not be read.") from exc


def save_api_key(api_key: str):
    if not api_key:
        raise CredentialStorageError("QuestLog login returned an empty credential.")
    keyring = _require_windows_keyring()
    try:
        keyring.set_password(KEYRING_SERVICE, KEYRING_ACCOUNT, api_key)
        stored_key = keyring.get_password(KEYRING_SERVICE, KEYRING_ACCOUNT)
        if not stored_key or not secrets.compare_digest(stored_key, api_key):
            raise CredentialStorageError("QuestLog login could not be stored securely.")
    except CredentialStorageError:
        raise
    except Exception as exc:
        raise CredentialStorageError("QuestLog login could not be stored securely.") from exc


def delete_api_key():
    try:
        keyring = _require_windows_keyring()
    except Exception:
        return
    for service, account in (
        (KEYRING_SERVICE, KEYRING_ACCOUNT),
        (LEGACY_KEYRING_SERVICE, LEGACY_KEYRING_ACCOUNT),
    ):
        try:
            keyring.delete_password(service, account)
        except Exception:
            pass


def sanitize_settings(settings: dict) -> dict:
    clean = dict(settings or {})
    for field in LEGACY_SECRET_FIELDS:
        clean.pop(field, None)
    return clean


def find_legacy_secret(settings: dict) -> str:
    for field in ("api_key", "listener_api_key", "access_token", "refresh_token"):
        value = (settings or {}).get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def atomic_write_json(path: str, payload: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)
