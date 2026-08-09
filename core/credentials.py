import base64
import ctypes
import ctypes.wintypes
import json
import os
import secrets
import sys

from core.paths import data as _data_path


KEYRING_SERVICE = "QuestLog.EldenTracker"
KEYRING_ACCOUNT = "listener_api_key"
LEGACY_KEYRING_SERVICE = "QuestLog-EldenTracker"
LEGACY_KEYRING_ACCOUNT = "api_key"
DPAPI_TOKEN_FILE = _data_path("auth", "questlog_token.dpapi")
DPAPI_ENTROPY = b"QuestLog.EldenTracker.listener.v1"

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


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def _blob_from_bytes(payload: bytes):
    buffer = ctypes.create_string_buffer(payload)
    return _DATA_BLOB(len(payload), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer


def _bytes_from_blob(blob):
    try:
        return ctypes.string_at(blob.pbData, blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob.pbData)


def _dpapi_protect(text: str) -> str:
    if sys.platform != "win32":
        raise CredentialStorageError("Remember-me login is only available on Windows.")
    data_blob, data_buffer = _blob_from_bytes(text.encode("utf-8"))
    entropy_blob, entropy_buffer = _blob_from_bytes(DPAPI_ENTROPY)
    out_blob = _DATA_BLOB()
    ok = ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(data_blob),
        "QuestLog EldenTracker login",
        ctypes.byref(entropy_blob),
        None,
        None,
        0,
        ctypes.byref(out_blob),
    )
    _ = (data_buffer, entropy_buffer)
    if not ok:
        raise ctypes.WinError()
    return base64.b64encode(_bytes_from_blob(out_blob)).decode("ascii")


def _dpapi_unprotect(encoded: str) -> str:
    if sys.platform != "win32":
        raise CredentialStorageError("Remember-me login is only available on Windows.")
    encrypted = base64.b64decode(encoded.encode("ascii"))
    data_blob, data_buffer = _blob_from_bytes(encrypted)
    entropy_blob, entropy_buffer = _blob_from_bytes(DPAPI_ENTROPY)
    out_blob = _DATA_BLOB()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(data_blob),
        None,
        ctypes.byref(entropy_blob),
        None,
        None,
        0,
        ctypes.byref(out_blob),
    )
    _ = (data_buffer, entropy_buffer)
    if not ok:
        raise ctypes.WinError()
    return _bytes_from_blob(out_blob).decode("utf-8")


def _load_dpapi_key() -> str:
    if not os.path.isfile(DPAPI_TOKEN_FILE):
        return ""
    try:
        with open(DPAPI_TOKEN_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
        encrypted = payload.get("token")
        if not encrypted:
            return ""
        return _dpapi_unprotect(encrypted)
    except Exception as exc:
        raise CredentialStorageError("QuestLog login could not be restored.") from exc


def _save_dpapi_key(api_key: str):
    try:
        os.makedirs(os.path.dirname(DPAPI_TOKEN_FILE), exist_ok=True)
        encrypted = _dpapi_protect(api_key)
        atomic_write_json(DPAPI_TOKEN_FILE, {"token": encrypted, "storage": "windows_dpapi"})
        loaded = _load_dpapi_key()
        if not loaded or not secrets.compare_digest(loaded, api_key):
            raise CredentialStorageError("QuestLog login could not be saved.")
    except CredentialStorageError:
        raise
    except Exception as exc:
        raise CredentialStorageError("QuestLog login could not be saved.") from exc


def _load_legacy_keyring_key() -> str:
    if sys.platform != "win32":
        return ""
    try:
        import keyring
    except Exception:
        return ""
    try:
        for service, account in (
            (KEYRING_SERVICE, KEYRING_ACCOUNT),
            (LEGACY_KEYRING_SERVICE, LEGACY_KEYRING_ACCOUNT),
        ):
            api_key = keyring.get_password(service, account) or ""
            if api_key:
                return api_key
    except Exception:
        return ""
    return ""


def _delete_legacy_keyring_keys():
    if sys.platform != "win32":
        return
    try:
        import keyring
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


def load_api_key() -> str:
    api_key = _load_dpapi_key()
    if api_key:
        return api_key

    legacy_key = _load_legacy_keyring_key()
    if legacy_key:
        save_api_key(legacy_key)
        _delete_legacy_keyring_keys()
        return legacy_key
    return ""


def save_api_key(api_key: str):
    if not api_key:
        raise CredentialStorageError("QuestLog login returned an empty credential.")
    _save_dpapi_key(api_key)


def delete_api_key():
    try:
        if os.path.isfile(DPAPI_TOKEN_FILE):
            os.remove(DPAPI_TOKEN_FILE)
    except Exception:
        pass
    _delete_legacy_keyring_keys()


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
