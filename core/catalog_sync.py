"""QuestLog public catalog updater and verified local cache.

This sync is independent from the listener-key/Profile API. It only downloads
JSON reference data and keeps the previous verified cache on every failure.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from core.paths import ROOT, data as _data_path


BASE_URL = "https://questlog.casual-heroes.com"
APP_VERSION = "1.1.0"
SUPPORTED_API_VERSION = 1
SUPPORTED_SCHEMA_VERSIONS = {1}
SUPPORTED_CALCULATION_CONTRACTS = {1}
MAX_DATASET_BYTES = 32 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 5
_WRITE_LOCKS = {}
_WRITE_LOCKS_GUARD = threading.Lock()

STARTUP_LIVE_RESOURCES = {
    "classes_vanilla",
    "weapons_vanilla",
    "armor_vanilla",
    "talismans_vanilla",
    "spells_vanilla",
    "spirit_ashes_vanilla",
    "crystal_tears_vanilla",
    "weapons_err",
    "armor_err",
    "classes_err",
    "talismans_err",
    "spells_err",
    "spirit_ashes_err",
    "crystal_tears_err",
    "affinities_err",
    "fortunes_err",
    "curios_err",
    "runeforging_err",
    "aow_skills_err",
    "enkindling_err",
}

_PATH_RESOURCE_NAMES = {
    ("classes", "elden_ring"): "classes_vanilla",
    ("classes", "err"): "classes_err",
    ("weapons", "elden_ring"): "weapons_vanilla",
    ("weapons", "err"): "weapons_err",
    ("armor", "elden_ring"): "armor_vanilla",
    ("armor", "err"): "armor_err",
    ("talismans", "elden_ring"): "talismans_vanilla",
    ("talismans", "err"): "talismans_err",
    ("spirit-ashes", "elden_ring"): "spirit_ashes_vanilla",
    ("spirit-ashes", "err"): "spirit_ashes_err",
    ("crystal-tears", "elden_ring"): "crystal_tears_vanilla",
    ("err/crystal-tears", None): "crystal_tears_err",
    ("spells", "elden_ring"): "spells_vanilla",
    ("spells", "err"): "spells_err",
    ("err/aow-skills", None): "aow_skills_err",
    ("err/affinities", None): "affinities_err",
    ("err/curios", None): "curios_err",
    ("err/fortunes", None): "fortunes_err",
    ("err/runeforging", None): "runeforging_err",
    ("err/enkindling", None): "enkindling_err",
}

_LEGACY_CACHE_NAMES = {
    ("classes", "elden_ring"): "elden_ring_classes.json",
    ("classes", "err"): "err_classes.json",
    ("stat-caps", "elden_ring"): "elden_ring_stat_caps.json",
    ("stat-caps", "err"): "err_stat_caps.json",
    ("derived-curves", "err"): "err_err_curves.json",
    ("ar-data", "elden_ring"): "elden_ring_ar_data.json",
    ("ar-data", "err"): "err_ar_data.json",
    ("weapons", "elden_ring"): "elden_ring_weapons.json",
    ("weapons", "err"): "err_weapons.json",
    ("aow", "elden_ring"): "elden_ring_aow.json",
    ("armor", "elden_ring"): "elden_ring_armor.json",
    ("armor", "err"): "elden_ring_armor.json",
    ("talismans", "elden_ring"): "elden_ring_talismans.json",
    ("talismans", "err"): "err_talismans.json",
    ("spirit-ashes", "elden_ring"): "elden_ring_spirit_ashes.json",
    ("spirit-ashes", "err"): "err_spirit_ashes.json",
    ("crystal-tears", "elden_ring"): "elden_ring_tears.json",
    ("err/crystal-tears", None): "err_tears.json",
    ("err/aow-skills", None): "err_aow.json",
    ("err/affinities", None): "err_affinities.json",
    ("err/curios", None): "err_curios.json",
    ("err/fortunes", None): "err_fortunes.json",
    ("err/runeforging", None): "err_runeforging.json",
}


class CatalogSyncError(RuntimeError):
    pass


@dataclass
class SyncResult:
    updated: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    offline: bool = False
    app_update_required: bool = False


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _read_json(path: Path, default: Any = None) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (FileNotFoundError, OSError, ValueError):
        return default


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if path.exists() and path.read_bytes() == content:
            return
    except OSError:
        pass
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _safe_cache_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.()' -]+", "_", value).strip().replace(" ", "_")


def _best_effort_write(path: Path, content: bytes, logger=None) -> bool:
    resolved = str(path)
    with _WRITE_LOCKS_GUARD:
        lock = _WRITE_LOCKS.setdefault(resolved, threading.Lock())
    try:
        with lock:
            _atomic_write(path, content)
        return True
    except OSError as error:
        if logger:
            logger.debug("Catalog cache write skipped for %s: %s", path, error)
        return False


def default_cache_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "QuestLog" / "EldenTracker" / "catalog"
    return Path(_data_path("catalog"))


def default_bundled_dir() -> Path:
    return Path(ROOT) / "resources" / "catalog"


class CatalogStore:
    """Content-addressed catalog cache with bundled/offline fallback."""

    def __init__(
        self,
        base_url: str = BASE_URL,
        cache_dir: str | Path | None = None,
        bundled_dir: str | Path | None = None,
        app_version: str = APP_VERSION,
        logger=None,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.cache_dir = Path(cache_dir) if cache_dir is not None else default_cache_dir()
        self.bundled_dir = Path(bundled_dir) if bundled_dir is not None else default_bundled_dir()
        self.app_version = app_version
        self.log = logger
        self.timeout = timeout
        self.manifest_path = self.cache_dir / "manifest.json"
        self.state_path = self.cache_dir / "state.json"
        self.legacy_builder_cache_dir = Path(_data_path("builder_cache"))

    def _request(self, url: str, etag: str | None = None) -> tuple[int, bytes, str | None]:
        headers = {
            "Accept": "application/json",
            "User-Agent": f"QuestLog-EldenTracker/{self.app_version}",
        }
        if etag:
            headers["If-None-Match"] = etag
        request = Request(url, headers=headers, method="GET")
        try:
            with urlopen(request, timeout=self.timeout) as response:
                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) > MAX_DATASET_BYTES:
                    raise CatalogSyncError("download exceeds the 32 MiB safety limit")
                body = response.read(MAX_DATASET_BYTES + 1)
                if len(body) > MAX_DATASET_BYTES:
                    raise CatalogSyncError("download exceeds the 32 MiB safety limit")
                return response.status, body, response.headers.get("ETag")
        except HTTPError as error:
            if error.code == 304:
                return 304, b"", error.headers.get("ETag")
            raise CatalogSyncError(f"HTTP {error.code} for {url}") from error
        except (URLError, TimeoutError, OSError) as error:
            raise CatalogSyncError(f"cannot reach {url}: {error}") from error

    @staticmethod
    def _decode_json(body: bytes, label: str) -> Any:
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as error:
            raise CatalogSyncError(f"{label} is not valid UTF-8 JSON") from error

    def _validate_manifest(self, manifest: Any) -> None:
        if not isinstance(manifest, dict):
            raise CatalogSyncError("manifest must be an object")
        if manifest.get("api_version") != SUPPORTED_API_VERSION:
            raise CatalogSyncError(f"unsupported catalog API version {manifest.get('api_version')!r}")
        if manifest.get("schema_version") not in SUPPORTED_SCHEMA_VERSIONS:
            raise CatalogSyncError(f"unsupported catalog schema {manifest.get('schema_version')!r}")
        if manifest.get("account_required") is not False:
            raise CatalogSyncError("public catalog unexpectedly requires an account")
        if not isinstance(manifest.get("datasets"), dict):
            raise CatalogSyncError("manifest has no datasets object")

    def _download_dataset(self, name: str, metadata: dict[str, Any]) -> bytes:
        revision = metadata.get("revision")
        expected_hash = metadata.get("sha256")
        expected_size = metadata.get("bytes")
        url = metadata.get("url")
        if not all(isinstance(v, str) and v for v in (revision, expected_hash, url)):
            raise CatalogSyncError(f"{name}: incomplete manifest entry")
        if revision != expected_hash or len(expected_hash) != 64:
            raise CatalogSyncError(f"{name}: invalid content revision")
        if not isinstance(expected_size, int) or not 0 < expected_size <= MAX_DATASET_BYTES:
            raise CatalogSyncError(f"{name}: invalid declared byte length")
        if not url.startswith(f"{self.base_url}/api/soulslike/data/"):
            raise CatalogSyncError(f"{name}: rejected download origin")

        status, body, _ = self._request(url)
        if status != 200:
            raise CatalogSyncError(f"{name}: unexpected HTTP {status}")
        if len(body) != expected_size:
            raise CatalogSyncError(f"{name}: byte length does not match manifest")
        if hashlib.sha256(body).hexdigest() != expected_hash:
            raise CatalogSyncError(f"{name}: SHA-256 does not match manifest")

        payload = self._decode_json(body, name)
        if not isinstance(payload, dict) or payload.get("dataset") != name:
            raise CatalogSyncError(f"{name}: dataset identity mismatch")
        if payload.get("schema_version") not in SUPPORTED_SCHEMA_VERSIONS:
            raise CatalogSyncError(f"{name}: unsupported schema version")
        return body

    def refresh(self) -> SyncResult:
        result = SyncResult()
        state = _read_json(self.state_path, {}) or {}
        cached_manifest = _read_json(self.manifest_path)
        manifest_url = f"{self.base_url}/api/soulslike/data/manifest/"

        try:
            status, body, response_etag = self._request(manifest_url, state.get("manifest_etag"))
            if status == 304:
                if not cached_manifest:
                    raise CatalogSyncError("server returned 304 but no cached manifest exists")
                manifest = cached_manifest
            else:
                manifest = self._decode_json(body, "catalog manifest")
                self._validate_manifest(manifest)
                _atomic_write(self.manifest_path, _canonical_json(manifest))
                state["manifest_etag"] = response_etag

            self._validate_manifest(manifest)
            calculation_contract = manifest.get("calculation_contract_version")
            if calculation_contract not in SUPPORTED_CALCULATION_CONTRACTS:
                result.app_update_required = True
                result.warnings.append(
                    "The server calculation contract is newer than this app; cached calculations were retained."
                )

            installed = state.setdefault("datasets", {})
            for name, metadata in manifest["datasets"].items():
                if not isinstance(metadata, dict):
                    result.warnings.append(f"{name}: invalid manifest entry")
                    continue
                if name == "err_calculations" and result.app_update_required:
                    continue
                destination = self.cache_dir / "datasets" / f"{name}.json"
                if installed.get(name) == metadata.get("revision") and destination.exists():
                    result.unchanged.append(name)
                    continue
                try:
                    content = self._download_dataset(name, metadata)
                    _atomic_write(destination, content)
                    installed[name] = metadata["revision"]
                    result.updated.append(name)
                except CatalogSyncError as error:
                    result.warnings.append(str(error))

            state["last_successful_check_unix"] = int(time.time())
            state["poll_after_seconds"] = manifest.get("poll_after_seconds", 21600)
            _atomic_write(self.state_path, _canonical_json(state))
        except CatalogSyncError as error:
            result.offline = True
            result.warnings.append(str(error))
            if self.log:
                self.log.warning("Catalog refresh failed; using verified cache: %s", error)

        return result

    def refresh_live_resources(self, names: set[str]) -> SyncResult:
        result = SyncResult()
        manifest = _read_json(self.manifest_path, {}) or {}
        resources = manifest.get("live_resources", {})
        state = _read_json(self.state_path, {}) or {}
        now = int(time.time())
        next_check = state.get("live_resources_checked_unix", 0) + int(
            manifest.get("live_resource_poll_seconds", 21600)
        )
        if now < next_check:
            result.unchanged.extend(sorted(names))
            return result

        hashes = state.setdefault("live_resource_hashes", {})
        for name in sorted(names):
            url = resources.get(name)
            if not isinstance(url, str) or not url.startswith(f"{self.base_url}/api/soulslike/"):
                result.warnings.append(f"{name}: unavailable or rejected resource URL")
                continue
            try:
                status, body, _ = self._request(url)
                if status != 200:
                    raise CatalogSyncError(f"{name}: unexpected HTTP {status}")
                payload = self._decode_json(body, name)
                canonical = _canonical_json(payload)
                digest = hashlib.sha256(canonical).hexdigest()
                destination = self.cache_dir / "live" / f"{name}.json"
                if digest == hashes.get(name) and destination.exists():
                    result.unchanged.append(name)
                    continue
                _atomic_write(destination, canonical)
                hashes[name] = digest
                result.updated.append(name)
            except CatalogSyncError as error:
                result.warnings.append(str(error))

        if not result.warnings:
            state["live_resources_checked_unix"] = now
        _atomic_write(self.state_path, _canonical_json(state))
        return result

    def load(self, name: str) -> Any:
        cached = _read_json(self.cache_dir / "datasets" / f"{name}.json")
        if cached is not None:
            return cached
        bundled = _read_json(self.bundled_dir / "datasets" / f"{name}.json")
        if bundled is not None:
            return bundled
        bundled_flat = _read_json(self.bundled_dir / f"{name}.json")
        if bundled_flat is not None:
            return bundled_flat
        raise CatalogSyncError(f"no cached or bundled {name} dataset is available")

    def load_live(self, name: str) -> Any:
        cached = _read_json(self.cache_dir / "live" / f"{name}.json")
        if cached is not None:
            return cached
        bundled = _read_json(self.bundled_dir / "live" / f"{name}.json")
        if bundled is not None:
            return bundled
        raise CatalogSyncError(f"no cached or bundled {name} resource is available")

    @staticmethod
    def _calculation_dataset_name(game: str | None) -> str | None:
        if game == "elden_ring":
            return "vanilla_calculations"
        if game == "err":
            return "err_calculations"
        return None

    def load_calculation_payload(self, game: str | None) -> dict[str, Any] | None:
        dataset_name = self._calculation_dataset_name(game)
        if not dataset_name:
            return None
        try:
            dataset = self.load(dataset_name)
        except CatalogSyncError:
            return None
        payload = dataset.get("payload") if isinstance(dataset, dict) else None
        return payload if isinstance(payload, dict) else None

    def _calculation_public_fallback(self, path: str, game: str | None) -> Any:
        payload = self.load_calculation_payload(game)
        if not payload:
            return None
        if path == "derived-curves":
            return {"curves": payload.get("derived_curves", {})}
        if path == "ar-data":
            return {
                "curves": payload.get("curves", {}),
                "aec": payload.get("aec", {}),
                "reinforce": payload.get("reinforce", {}),
            }
        return None

    def load_public_fallback(self, path: str, game: str | None = None, extra_params: dict | None = None) -> Any:
        """Return cached data for an existing public API endpoint when possible."""
        if extra_params:
            normalized = dict(extra_params)
            normalized.pop("limit", None)
            if normalized:
                return None

        resource_name = _PATH_RESOURCE_NAMES.get((path, game)) or _PATH_RESOURCE_NAMES.get((path, None))
        if resource_name:
            try:
                return self.load_live(resource_name)
            except CatalogSyncError:
                pass

        calculated = self._calculation_public_fallback(path, game)
        if calculated is not None:
            return calculated

        legacy_name = _LEGACY_CACHE_NAMES.get((path, game)) or _LEGACY_CACHE_NAMES.get((path, None))
        if legacy_name:
            return _read_json(self.legacy_builder_cache_dir / legacy_name)
        return None

    def store_public_response(self, path: str, payload: Any, game: str | None = None, extra_params: dict | None = None) -> None:
        if extra_params:
            normalized = dict(extra_params)
            normalized.pop("limit", None)
            if normalized:
                return
        resource_name = _PATH_RESOURCE_NAMES.get((path, game)) or _PATH_RESOURCE_NAMES.get((path, None))
        if resource_name:
            _best_effort_write(self.cache_dir / "live" / f"{resource_name}.json", _canonical_json(payload), self.log)
        legacy_name = _LEGACY_CACHE_NAMES.get((path, game)) or _LEGACY_CACHE_NAMES.get((path, None))
        if legacy_name:
            _best_effort_write(self.legacy_builder_cache_dir / legacy_name, _canonical_json(payload), self.log)

    def load_ar_variants_fallback(self, weapon_name: str, game: str) -> Any:
        safe = _safe_cache_name(weapon_name)
        candidates = [
            self.cache_dir / "live" / f"ar_variants_{game}_{safe}.json",
            self.legacy_builder_cache_dir / f"{game}_variants_{safe}.json",
        ]
        for path in candidates:
            data = _read_json(path)
            if data is not None:
                return data
        payload = self.load_calculation_payload(game)
        weapons = payload.get("weapons", {}) if payload else {}
        variants_by_affinity = weapons.get(weapon_name)
        if isinstance(variants_by_affinity, dict):
            variants = []
            for affinity, variant in variants_by_affinity.items():
                if isinstance(variant, dict):
                    enriched = dict(variant)
                    enriched.setdefault("affinity", affinity)
                    enriched.setdefault("name", weapon_name)
                    variants.append(enriched)
            if variants:
                return {"variants": variants}
        return None

    def store_ar_variants(self, weapon_name: str, payload: Any, game: str) -> None:
        safe = _safe_cache_name(weapon_name)
        content = _canonical_json(payload)
        _best_effort_write(self.cache_dir / "live" / f"ar_variants_{game}_{safe}.json", content, self.log)
        _best_effort_write(self.legacy_builder_cache_dir / f"{game}_variants_{safe}.json", content, self.log)


def startup_sync(logger=None) -> SyncResult:
    store = CatalogStore(logger=logger)
    result = store.refresh()
    live = store.refresh_live_resources(STARTUP_LIVE_RESOURCES)
    result.updated.extend(live.updated)
    result.unchanged.extend(live.unchanged)
    result.warnings.extend(live.warnings)
    result.offline = result.offline or live.offline
    result.app_update_required = result.app_update_required or live.app_update_required
    return result
