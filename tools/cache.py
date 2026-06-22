#!/usr/bin/env python3
"""Validator result cache — skips re-validation when no relevant files changed."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

CACHE_DIR_NAME = ".cache/validators"


def compute_hash(config_dir: Path, patterns: list[str]) -> str:
    """Compute a SHA256 hash over all files matching the given glob patterns.

    Files are sorted for deterministic ordering. Missing files/patterns are
    silently skipped (no error).
    """
    sha = hashlib.sha256()
    paths: list[Path] = []
    for pattern in patterns:
        for p in sorted(config_dir.glob(pattern)):
            if p.is_file():
                paths.append(p)
    # Deduplicate in case patterns overlap
    seen: set[Path] = set()
    for p in sorted(paths):
        if p in seen:
            continue
        seen.add(p)
        sha.update(str(p.relative_to(config_dir)).encode())
        sha.update(p.read_bytes())
    return sha.hexdigest()


def cache_path(config_dir: Path, name: str) -> Path:
    """Return the path to the cache file for a given validator name."""
    cache_dir = config_dir / CACHE_DIR_NAME
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{name}.json"


def load_cache(config_dir: Path, name: str) -> dict | None:
    """Load a cached validator result. Returns None on any failure."""
    path = cache_path(config_dir, name)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return None
        if "hash" not in data or "passed" not in data:
            return None
        return data
    except OSError, json.JSONDecodeError, ValueError:
        return None


def save_cache(
    config_dir: Path,
    name: str,
    validator_name: str,
    file_hash: str,
    passed: bool,
    duration: float,
) -> None:
    """Save a validator result to the cache."""
    data = {
        "validator": validator_name,
        "hash": file_hash,
        "passed": passed,
        "timestamp": datetime.now(UTC).isoformat(),
        "duration": round(duration, 4),
    }
    path = cache_path(config_dir, name)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except OSError:
        pass
