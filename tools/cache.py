"""Validator result cache — skips re-validation when no relevant files changed."""

import contextlib
import hashlib
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

CACHE_DIR_NAME = ".cache/validators"

CACHE_SCHEMA_VERSION = 1


def compute_hash(config_dir: Path, patterns: list[str]) -> str:
    """Compute a SHA256 hash over all files matching the given glob patterns.

    Files are sorted for deterministic ordering. Missing files/patterns are
    silently skipped (no error).
    """
    sha = hashlib.sha256()
    paths: list[Path] = []
    for pattern in patterns:
        for p in config_dir.glob(pattern):
            if p.is_file():
                paths.append(p)
    # Deduplicate in case patterns overlap
    seen: set[Path] = set()
    for p in sorted(paths):
        if p in seen:
            continue
        seen.add(p)
        sha.update(str(p.relative_to(config_dir)).encode())
        try:
            sha.update(p.read_bytes())
        except OSError as e:
            print(f"WARN: skipping {p} in hash: {e}", file=sys.stderr)
            continue
    return sha.hexdigest()


def cache_path(config_dir: Path, name: str) -> Path:
    """Return the path to the cache file for a given validator name."""
    cache_dir = config_dir / CACHE_DIR_NAME
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{name}.json"


def load_cache(config_dir: Path, name: str) -> dict | None:
    """Load a cached validator result. Returns None on any failure.

    Retries once after 100ms on transient JSON decode errors (per AGENTS.md
    convention for atomic-write safety). Does NOT create directories — only
    reads from existing cache files.
    """
    path = config_dir / CACHE_DIR_NAME / f"{name}.json"
    if not path.is_file():
        return None
    data = None
    for attempt in range(2):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            break
        except json.JSONDecodeError:
            if attempt == 0:
                time.sleep(0.1)
                continue
            return None
        except OSError:
            return None
    if data is None:
        return None
    if not isinstance(data, dict):
        return None
    if "hash" not in data or "passed" not in data:
        return None
    if data.get("schema") != CACHE_SCHEMA_VERSION:
        return None
    return data


# ====================================================================
# Generic blob cache (for entity output)
# ====================================================================

BLOB_CACHE_DIR = ".cache/entities"


def _blob_hash(keys: list[str | bytes]) -> str:
    """Compute a SHA256 hash over the concatenation of all *keys*.

    A null-byte delimiter is inserted between adjacent keys to prevent
    accidental collisions (e.g. ``["ab","c"]`` ≠ ``["a","bc"]``).  Each key
    is hashed in order; the result is a hex digest used as a cache filename.
    Empty *keys* yields the hash of the empty string.
    """
    sha = hashlib.sha256()
    for i, k in enumerate(keys):
        if i > 0:
            sha.update(b"\x00")
        if isinstance(k, str):
            sha.update(k.encode())
        elif isinstance(k, bytes):
            sha.update(k)
        else:
            sha.update(str(k).encode())
    return sha.hexdigest()


def save_blob(config_dir: Path, name: str, data) -> None:
    """Save arbitrary JSON-serializable data to the entity cache.

    Writes to ``{config_dir}/{BLOB_CACHE_DIR}/{name}.json``.  Creates
    the cache directory if needed.  Writes a warning to stderr on failure.
    """
    path = config_dir / BLOB_CACHE_DIR / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except OSError as e:
        print(f"WARN: failed to write cache {path}: {e}", file=sys.stderr)


def load_blob(config_dir: Path, name: str):
    """Load cached blob data.  Returns None on any failure."""
    path = config_dir / BLOB_CACHE_DIR / f"{name}.json"
    if not path.is_file():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except OSError, ValueError:
        return None


def save_cache(
    config_dir: Path,
    name: str,
    validator_name: str,
    file_hash: str,
    passed: bool,
    duration: float,
) -> None:
    """Save a validator result to the cache atomically.

    Writes to a temp file then ``os.replace``s it into place, so a crash
    mid-write never leaves a truncated cache file.  Writes a warning to
    stderr on persistent failure.
    """
    data = {
        "schema": CACHE_SCHEMA_VERSION,
        "validator": validator_name,
        "hash": file_hash,
        "passed": passed,
        "timestamp": datetime.now(UTC).isoformat(),
        "duration": round(duration, 4),
    }
    path = cache_path(config_dir, name)
    tmp = path.with_suffix(".json.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except OSError as e:
        print(f"WARN: failed to write cache {path}: {e}", file=sys.stderr)
    finally:
        if tmp.exists():
            with contextlib.suppress(OSError):
                tmp.unlink()
