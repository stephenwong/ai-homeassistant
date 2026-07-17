"""Shared JSON output-shaping helpers for token-efficient CLI output.

Provides ``apply_output_shape()`` — a single transform applying (in order)
first-slice → pick (field projection) → max-chars (character-length truncation).
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
        first: Keep only first N items (must be >= 1; raises ValueError otherwise).
        pick: Comma-separated field names to retain (per-item projection).
        max_chars: Drop trailing list items until COMPACT JSON fits within N chars.
            Note: the print layer may render with --pretty (indent=2), whose size
            exceeds the compact size — so pretty output can overshoot max_chars.
            This is intentional (compact is the token-cost proxy).
    """
    if first is not None:
        if first < 1:
            raise ValueError(f"first must be >= 1, got {first}")
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
    """Drop trailing list items (or largest dict keys) until compact JSON fits.

    Appends a ``{"_truncated": True, ...}`` marker describing what was dropped.
    Scalars that still exceed *max_chars* are passed through unchanged.
    If even the empty-marker exceeds *max_chars* (tiny limit), the marker is
    returned anyway (same degradation as the list path — preferable to silently
    dropping the whole response).
    """
    serialized = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    if len(serialized) <= max_chars:
        return data
    if isinstance(data, list):
        return _truncate_list(data, max_chars)
    if isinstance(data, dict):
        return _cap_dict(data, max_chars)
    return data


def _truncate_list(data: list, max_chars: int):
    """Drop trailing list items until the (compact) serialization fits.

    Uses a prefix-sum + binary search over per-item serialized lengths so
    the fit check is O(N log N) rather than O(N²).
    """
    original_len = len(data)
    if original_len == 0:
        return [{"_truncated": True, "shown": 0, "total": 0}]

    sep = (",", ":")
    # Per-item compact serialized length
    item_lens = [
        len(json.dumps(item, separators=sep, ensure_ascii=False)) for item in data
    ]
    # prefix[n] = size of JSON array data[:n] (brackets + commas between items).
    prefix = [2]  # "[" + "]"
    for i, ln in enumerate(item_lens):
        prefix.append(prefix[-1] + (1 if i > 0 else 0) + ln)

    # Precompute marker sizes for each possible n.
    marker_lens = {}
    for n in range(0, original_len + 1):
        marker = {"_truncated": True, "shown": n, "total": original_len}
        marker_str = json.dumps(marker, separators=sep, ensure_ascii=False)
        marker_lens[n] = (1 if n > 0 else 0) + len(marker_str)

    # Binary-search: largest n in [0, original_len] such that total fits.
    lo, hi, best = 0, original_len, 0
    while lo <= hi:
        mid = (lo + hi) // 2
        if prefix[mid] + marker_lens[mid] <= max_chars:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1

    if best == 0 and prefix[0] + marker_lens[0] > max_chars:
        return [{"_truncated": True, "shown": 0, "total": original_len}]

    marker = {"_truncated": True, "shown": best, "total": original_len}
    return data[:best] + [marker]


def _cap_dict(data: dict, max_chars: int):
    """Drop largest-value keys until the compact serialization fits.

    Mirrors ``trace._cap_trace_dict``: rank keys by serialized value length,
    drop the largest first, attach a marker describing what was removed.
    """
    keys_by_size = sorted(
        data.keys(),
        key=lambda k: len(
            json.dumps(data[k], separators=(",", ":"), ensure_ascii=False)
        ),
        reverse=True,
    )
    remaining = dict(data)
    dropped: list[str] = []
    for k in keys_by_size:
        dropped.append(k)
        del remaining[k]
        candidate = {
            **remaining,
            "_truncated": True,
            "dropped_keys": dropped,
            "kept_keys": list(remaining.keys()),
        }
        serialized = json.dumps(candidate, separators=(",", ":"), ensure_ascii=False)
        if len(serialized) <= max_chars:
            return candidate
    marker = {"_truncated": True, "dropped_keys": dropped, "kept_keys": []}
    return marker
