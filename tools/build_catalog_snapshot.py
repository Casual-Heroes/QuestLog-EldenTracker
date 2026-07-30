"""Build the bundled QuestLog catalog snapshot for offline releases.

Downloads the public catalog manifest, verified datasets, and live reference
resources into resources/catalog/. The app uses this folder when no verified
user cache exists, so release builds should run this before packaging.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.error import URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_URL = "https://questlog.casual-heroes.com"
DEFAULT_OUTPUT = ROOT / "resources" / "catalog"
MAX_BYTES = 32 * 1024 * 1024
REQUIRED_DATASETS = {
    "vanilla_calculations",
    "err_calculations",
    "bosses_vanilla",
    "bosses_err",
}
REQUIRED_LIVE_RESOURCES = {
    "classes_vanilla",
    "weapons_vanilla",
    "armor_vanilla",
    "talismans_vanilla",
    "spells_vanilla",
    "spirit_ashes_vanilla",
    "crystal_tears_vanilla",
    "classes_err",
    "weapons_err",
    "armor_err",
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
REQUIRED_CALCULATION_KEYS = {
    "classes",
    "weapons",
    "armor",
    "talismans",
    "curves",
    "aec",
    "reinforce",
    "derived_curves",
}


def canonical_json(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def fetch_json(url: str, timeout: int, retries: int = 3):
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "QuestLog-CatalogSnapshot/1.0"})
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                body = response.read(MAX_BYTES + 1)
            break
        except (OSError, URLError) as error:
            last_error = error
            if attempt >= retries:
                raise
            time.sleep(min(2 * attempt, 5))
    else:
        raise RuntimeError(f"{url} failed: {last_error}")
    if len(body) > MAX_BYTES:
        raise RuntimeError(f"{url} exceeds {MAX_BYTES} bytes")
    try:
        return json.loads(body.decode("utf-8")), body
    except (UnicodeDecodeError, ValueError) as error:
        raise RuntimeError(f"{url} did not return valid JSON") from error


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = canonical_json(payload)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_bytes(content)
    os.replace(temporary, path)


def require_same_origin(url: str, base_url: str) -> None:
    source = urlparse(url)
    base = urlparse(base_url)
    if (source.scheme, source.netloc) != (base.scheme, base.netloc):
        raise RuntimeError(f"rejected non-QuestLog URL: {url}")


def validate_calculation_dataset(name: str, payload: dict) -> None:
    calculation_payload = payload.get("payload")
    if not isinstance(calculation_payload, dict):
        raise RuntimeError(f"{name}: missing payload object")
    missing = sorted(key for key in REQUIRED_CALCULATION_KEYS if key not in calculation_payload)
    if missing:
        raise RuntimeError(f"{name}: missing calculation keys {missing}")
    if not calculation_payload.get("weapons"):
        raise RuntimeError(f"{name}: empty weapons map")
    if not calculation_payload.get("armor"):
        raise RuntimeError(f"{name}: empty armor map")
    if not calculation_payload.get("reinforce"):
        raise RuntimeError(f"{name}: empty reinforcement map")
    if name == "vanilla_calculations" and not payload.get("regulation_sha256"):
        raise RuntimeError("vanilla_calculations: missing regulation_sha256")
    if name == "err_calculations" and not payload.get("regulation_version"):
        raise RuntimeError("err_calculations: missing regulation_version")


def build_snapshot(base_url: str, output: Path, timeout: int, retries: int) -> None:
    base_url = base_url.rstrip("/")
    manifest_url = f"{base_url}/api/soulslike/data/manifest/"
    manifest, _ = fetch_json(manifest_url, timeout, retries)

    if manifest.get("account_required") is not False:
        raise RuntimeError("manifest unexpectedly requires an account")
    if not isinstance(manifest.get("datasets"), dict):
        raise RuntimeError("manifest has no datasets object")
    missing_datasets = sorted(REQUIRED_DATASETS - set(manifest["datasets"]))
    if missing_datasets:
        raise RuntimeError(f"manifest missing required datasets: {missing_datasets}")
    resources = manifest.get("live_resources", {})
    if not isinstance(resources, dict):
        raise RuntimeError("manifest has no live_resources object")
    missing_resources = sorted(REQUIRED_LIVE_RESOURCES - set(resources))
    if missing_resources:
        raise RuntimeError(f"manifest missing required live resources: {missing_resources}")

    write_json(output / "manifest.json", manifest)
    print(f"manifest -> {output / 'manifest.json'}")

    for name, metadata in sorted(manifest["datasets"].items()):
        if not isinstance(metadata, dict):
            raise RuntimeError(f"{name}: invalid dataset metadata")
        url = metadata.get("url")
        expected_size = metadata.get("bytes")
        expected_hash = metadata.get("sha256")
        if not isinstance(url, str) or not isinstance(expected_size, int) or not isinstance(expected_hash, str):
            raise RuntimeError(f"{name}: incomplete dataset metadata")
        require_same_origin(url, base_url)

        payload, raw_body = fetch_json(url, timeout, retries)
        canonical = canonical_json(payload)
        digest = hashlib.sha256(canonical).hexdigest()
        if digest != expected_hash:
            raise RuntimeError(f"{name}: SHA-256 mismatch {digest} != {expected_hash}")
        if len(raw_body) != expected_size and len(canonical) != expected_size:
            raise RuntimeError(f"{name}: byte length mismatch")
        if payload.get("dataset") != name:
            raise RuntimeError(f"{name}: dataset identity mismatch")
        if name.endswith("_calculations"):
            validate_calculation_dataset(name, payload)
        write_json(output / "datasets" / f"{name}.json", payload)
        print(f"dataset {name} -> {output / 'datasets' / f'{name}.json'}")

    for name, url in sorted(resources.items()):
        if not isinstance(url, str):
            raise RuntimeError(f"{name}: invalid live resource URL")
        require_same_origin(url, base_url)
        payload, _ = fetch_json(url, timeout, retries)
        write_json(output / "live" / f"{name}.json", payload)
        print(f"live {name} -> {output / 'live' / f'{name}.json'}")

    print("Catalog snapshot complete.")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--retries", type=int, default=3)
    args = parser.parse_args(argv)

    try:
        build_snapshot(args.base_url, args.output, args.timeout, max(1, args.retries))
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
