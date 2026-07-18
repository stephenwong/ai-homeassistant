"""Shared helpers for reading HA ``.storage/`` registry JSON files."""

import json
from pathlib import Path
from typing import Any


def load_storage_registry(
    storage_path: Path,
    *,
    list_key: str,
    key_field: str,
) -> dict[str, Any]:
    """Read a HA ``.storage/`` registry JSON and index items by *key_field*.

    Performs the parse-and-index step common to every registry loader in the
    validators package (entity, device, area). Callers own their own
    missing-file and parse-failure policy — this helper does one thing: open,
    parse, index.

    Args:
        storage_path: Path to the registry file (e.g.
            ``<config_dir>/.storage/core.entity_registry``).
        list_key: Key under ``data["data"][list_key]`` holding the item list
            (e.g. ``"entities"``, ``"devices"``, ``"areas"``).
        key_field: Item field to use as the result-dict key
            (e.g. ``"entity_id"``, ``"id"``).

    Returns:
        Dict mapping ``item[key_field]`` → item dict. Empty dict when the
        list is absent or empty (does **not** distinguish "missing key" from
        "empty list" — both yield ``{}``).

    Raises:
        OSError: ``storage_path`` does not exist or is unreadable
            (``FileNotFoundError``, ``PermissionError``, etc.).
        json.JSONDecodeError: File contents are not valid JSON.
        KeyError, TypeError, ValueError, AttributeError: Malformed structure
            (e.g. ``data["data"]`` is a list, items are not iterable, an
            item is missing *key_field*).
    """
    with open(storage_path, encoding="utf-8") as f:
        data = json.load(f)
    return {item[key_field]: item for item in data.get("data", {}).get(list_key, [])}
