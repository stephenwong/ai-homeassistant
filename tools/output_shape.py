"""Shared JSON output-shaping helpers for token-efficient CLI output.

Provides ``apply_output_shape()`` — a single transform applying (in order)
first-slice → pick (field projection) → max-chars (byte-length truncation).
Used by curl and other JSON-emitting subcommands to cap token
output for agent consumption.
"""

import json


def apply_output_shape(
    data,
    *,
    first: int | None = None,
    pick: str | None = None,
    max_chars: int | None = None,
):
    """Apply token-reduction transforms to JSON data.

    Order of operations: first → pick → max_chars.

    Args:
        data: Parsed JSON (list, dict, or scalar).
        first: Keep only first N items.
        pick: Comma-separated field names to retain (per-item projection).
        max_chars: Drop trailing list items until compact JSON fits within N chars.
    """
    if first is not None:
        data = _first(data, first)
    if pick and pick.strip():
        fields = [f.strip() for f in pick.split(",") if f.strip()]
        data = _pick_fields(data, fields)
    if max_chars is not None and max_chars > 0:
        data = _truncate_by_chars(data, max_chars)
    return data


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _first(data, n: int):
    """Keep first *n* items from a list/dict.  Scalars become ``[data]``."""
    if isinstance(data, list):
        return data[:n]
    if isinstance(data, dict):
        return dict(list(data.items())[:n])
    return [data]


def _pick_fields(data, fields: list[str]):
    """Keep only the specified *fields* from each dict in *data*."""
    if isinstance(data, list):
        return [_pick_item(item, fields) for item in data]
    if isinstance(data, dict):
        return _pick_item(data, fields)
    return data


def _pick_item(item, fields: list[str]):
    if not isinstance(item, dict):
        return item
    return {k: item[k] for k in fields if k in item}


def print_json(data, *, pretty: bool = False) -> None:
    """Print JSON to stdout with configurable indentation.

    Compact output (no whitespace) by default; pretty-print with indent=2
    when *pretty* is True.
    """
    if pretty:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(data, separators=(",", ":"), ensure_ascii=False))


def _truncate_by_chars(data, max_chars: int):
    """Drop trailing list items until compact JSON fits within *max_chars*.

    Appends a ``{"_truncated": True, "shown": N, "total": M}`` marker.
    Non-list data is passed through unchanged.
    """
    serialized = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    if len(serialized) <= max_chars:
        return data
    if not isinstance(data, list):
        return data

    original_len = len(data)
    for n in range(original_len, 0, -1):
        candidate = data[:n]
        marker = {"_truncated": True, "shown": n, "total": original_len}
        trial = candidate + [marker]
        serialized = json.dumps(trial, separators=(",", ":"), ensure_ascii=False)
        if len(serialized) <= max_chars:
            return trial

    marker = {"_truncated": True, "shown": 0, "total": original_len}
    return [marker]
