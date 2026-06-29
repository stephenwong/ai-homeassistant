"""``curl`` subcommand: pure-Python HA REST API client.

Replaces the earlier bash/curl/jq pipeline with HAClient (pure Python).
Compact JSON by default; use ``--pretty`` for human-readable output.

Token-efficiency flags for agents:
  ``--count``    — print item count instead of full payload
  ``--keys``     — print key names only (no values)
  ``--first N``  — print first N items
  ``--pick F``   — keep only specified JSON keys (per-item projection)
  ``--abbrev``   — rename known keys to short forms (e, s, at, lc, lu, ctx)
  ``--entity ID`` — fetch a single entity by id (server-side)
  ``--domain D``  — filter list response by domain (client-side)
  ``--max-chars N`` — truncate JSON output when it exceeds N bytes
"""

import argparse
import contextlib
import json
import re
import shutil
import subprocess
import sys

from tools.common import HARequestError, _has_transform_flags, resolve_summary
from tools.ha.client import HAClient


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    """Wire the ``curl`` subparser."""
    parser = subparsers.add_parser(
        "curl",
        help="Call HA REST API via HAClient (pure Python).",
        description=(
            "Pure-Python HA API client using HAClient. "
            "Compact JSON by default; use --pretty for human-readable output. "
            "Agent-friendly flags: --count, --keys, --first N."
        ),
    )

    # ---- endpoint positional ----
    def _validate_endpoint(value: str) -> str:
        if not value.startswith("/"):
            raise argparse.ArgumentTypeError("endpoint must start with /")
        return value

    parser.add_argument(
        "endpoint",
        type=_validate_endpoint,
        nargs="?",
        default=None,
        help="API endpoint (optional when --entity is used)",
    )

    # ---- method ----
    method_group = parser.add_mutually_exclusive_group()
    method_group.add_argument(
        "--post",
        "-X",
        dest="method",
        action="store_const",
        const="POST",
        default="GET",
        help="Use POST (backward compat; prefer --method POST)",
    )
    method_group.add_argument(
        "--method",
        "-M",
        choices=["GET", "POST", "PUT", "DELETE", "PATCH"],
        help="HTTP method (default: GET)",
    )

    parser.add_argument("--data", "-d", help="JSON request body")

    # ---- domain filter / entity filter ----
    parser.add_argument(
        "--domain",
        help="Filter response items by domain (entity_id prefix, e.g. light)",
    )
    # ---- entity filter (single-entity fetch) ----
    parser.add_argument(
        "--entity",
        help="Fetch a single entity by entity_id (e.g. sensor.temperature)",
    )

    # ---- output processing (mutually exclusive) ----
    def _positive_int(value: str) -> int:
        n = int(value)
        if n < 1:
            raise argparse.ArgumentTypeError("--first must be >= 1")
        return n

    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "--filter",
        metavar="F",
        help="jq filter expression (requires jq installed)",
    )
    output_group.add_argument(
        "--count",
        action="store_true",
        help="Print number of items (list items or top-level dict keys)",
    )
    output_group.add_argument(
        "--keys",
        action="store_true",
        help="Print all unique JSON key names (no values)",
    )
    output_group.add_argument(
        "--first",
        metavar="N",
        type=_positive_int,
        help="Print first N items only",
    )
    output_group.add_argument(
        "--raw",
        action="store_true",
        help="Print raw response body (skip JSON processing entirely)",
    )

    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON with indent=2 (default: compact)",
    )

    # ---- bare-endpoint guardrail ----
    parser.add_argument(
        "--no-guard",
        action="store_true",
        help="Disable bare-endpoint guardrail (dump all entities even in summary)",
    )

    # ---- byte-length truncation ----
    def _positive_int_or_zero(value: str) -> int:
        n = int(value)
        if n < 0:
            raise argparse.ArgumentTypeError("--max-chars must be >= 0")
        return n

    parser.add_argument(
        "--max-chars",
        metavar="N",
        type=_positive_int_or_zero,
        help="Truncate JSON output when serialized form exceeds N characters",
    )

    # ---- key abbreviation ----
    parser.add_argument(
        "--abbrev",
        action="store_true",
        help="Shorten known JSON keys (e→entity_id, s→state, at→attributes, etc.)",
    )

    # ---- field projection (outside output_group — stacks with --first) ----
    parser.add_argument(
        "--pick",
        metavar="FIELDS",
        help="Keep only specified JSON keys (comma-separated). Stacks with --first.",
    )

    # ---- summary / quiet mode ----
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Compact output; suppresses informational stderr warnings",
    )
    parser.add_argument(
        "--no-summary",
        action="store_true",
        help="Force verbose stderr output even when stdout is piped",
    )

    parser.set_defaults(func=run)


# ====================================================================
# run()
# ====================================================================


def run(args: argparse.Namespace) -> int:
    """Execute a curl request.  Returns exit code (0 success, 1 error)."""
    summary = resolve_summary(args)
    method = args.method
    compact = not args.pretty

    # 1. Conflict: --raw + --pretty (check before costly from_env())
    if args.raw and args.pretty:
        print("\u274c Cannot combine --raw with --pretty", file=sys.stderr)
        return 1

    # 1b. Conflict: --pick with exclusive transforms (also before from_env)
    if args.pick and (args.count or args.keys or args.filter or args.raw):
        print(
            "\u274c Cannot combine --pick with --count/--keys/--filter/--raw",
            file=sys.stderr,
        )
        return 1

    # 1c. Handle --entity (single-entity fetch)
    if args.entity:
        if not re.match(r"^[a-z0-9_]+\.[a-z0-9_]+$", args.entity):
            print(f"\u274c Invalid entity_id: {args.entity!r}", file=sys.stderr)
            return 1
        if args.endpoint and args.endpoint != "/api/states":
            print(
                "\u274c --entity requires endpoint /api/states (or omit endpoint)",
                file=sys.stderr,
            )
            return 1
        if args.count or args.keys or args.filter or args.raw:
            print(
                "\u274c Cannot combine --entity with --count/--keys/--filter/--raw",
                file=sys.stderr,
            )
            return 1
        if method != "GET" and not summary:
            print(
                "\u26a0\ufe0f  --entity forces GET method (ignoring --method)",
                file=sys.stderr,
            )
        args.endpoint = f"/api/states/{args.entity}"
        method = "GET"

    # 1d. Handle --domain (client-side list filter)
    if args.domain:
        if args.entity:
            print(
                "\u274c Cannot combine --domain with --entity",
                file=sys.stderr,
            )
            return 1
        if args.count or args.keys or args.filter or args.raw:
            print(
                "\u274c Cannot combine --domain with --count/--keys/--filter/--raw",
                file=sys.stderr,
            )
            return 1

    # 1e. Ensure endpoint is set
    if not args.endpoint:
        print(
            "\u274c endpoint path is required (use --entity to fetch by id)",
            file=sys.stderr,
        )
        return 1

    # 2. Build client
    try:
        client = HAClient.from_env()
    except HARequestError as e:
        print(f"\u274c {e}", file=sys.stderr)
        return 1

    body_methods = {"POST", "PUT", "PATCH"}

    # 3. Parse request body (only for body-applicable methods)
    json_data = None
    if method in body_methods:
        if args.data is not None:
            try:
                json_data = json.loads(args.data)
            except (json.JSONDecodeError, TypeError) as e:
                print(f"\u274c Invalid JSON in --data: {e}", file=sys.stderr)
                return 1
    elif args.data is not None and not summary:
        print(f"\u26a0\ufe0f  --data ignored for {method} requests", file=sys.stderr)

    # 4. Execute request
    try:
        if method == "GET":
            resp = client.get(args.endpoint)
        elif method == "POST":
            resp = client.post(args.endpoint, json=json_data)
        elif method == "PUT":
            resp = client.put(args.endpoint, json=json_data)
        elif method == "DELETE":
            resp = client.delete(args.endpoint, json=json_data)
        elif method == "PATCH":
            resp = client.patch(args.endpoint, json=json_data)
        else:
            print(f"\u274c Unknown HTTP method: {method}", file=sys.stderr)
            return 1
    except HARequestError as e:
        print(f"\u274c {e}", file=sys.stderr)
        return 1

    # 5. Check HTTP status
    if not resp.ok:
        print(
            f"\u274c HTTP {resp.status_code}: {resp.text[:200]}",
            file=sys.stderr,
        )
        return 1

    # 6. Detect and parse JSON
    content_type = resp.headers.get("content-type", "")
    raw_text = resp.text
    is_json = "application/json" in content_type or raw_text.strip().startswith(
        ("{", "[")
    )

    data = None
    if is_json:
        with contextlib.suppress(ValueError, TypeError, json.JSONDecodeError):
            data = resp.json()

    # 7. Bare endpoint guardrail: instead of dumping all /api/states in summary
    # mode, print the count and a hint pointing to --first / --pick / --entity.
    if (
        method == "GET"
        and args.endpoint == "/api/states"
        and not _has_transform_flags(args)
        and not args.pretty
        and summary
        and not args.no_guard
    ):
        count_result = _handle_count(data, raw_text, is_json)
        # _handle_count printed the count to stdout; now add a hint to stderr
        print(
            "Hint: use --first/--pick/--entity/--domain to narrow, "
            "or --no-guard to dump all",
            file=sys.stderr,
        )
        return count_result

    # 8. Validate output flag against JSON-ness
    requires_json = (
        args.filter or args.keys or (args.first is not None) or bool(args.pick)
    )
    if requires_json and data is None and not is_json:
        flag = (
            "filter"
            if args.filter
            else (
                "keys" if args.keys else ("first" if args.first is not None else "pick")
            )
        )
        print(
            f"\u274c Cannot use --{flag} on non-JSON response "
            f"(Content-Type: {content_type or 'unknown'})",
            file=sys.stderr,
        )
        return 1

    # 8. Pretty-warning for --filter and --keys
    if args.pretty and not summary:
        if args.filter:
            print(
                "\u26a0\ufe0f  --pretty has no effect with --filter",
                file=sys.stderr,
            )
        elif args.keys:
            print(
                "\u26a0\ufe0f  --pretty has no effect with --keys",
                file=sys.stderr,
            )

    # 10. Dispatch by output flag (early-exit handlers)
    if args.filter:
        return _handle_filter(args.filter, data, content_type, compact)
    if args.count:
        return _handle_count(data, raw_text, is_json)
    if args.keys:
        return _handle_keys(data)
    if args.raw:
        print(raw_text, end="")
        return 0

    # 11. Apply --domain (client-side list filter)
    if args.domain and isinstance(data, list):
        prefix = f"{args.domain}."
        filtered = [
            i
            for i in data
            if isinstance(i, dict)
            and isinstance(i.get("entity_id"), str)
            and i["entity_id"].startswith(prefix)
        ]
        if not summary and len(filtered) < len(data):
            print(
                f"# domain {args.domain!r}: {len(filtered)}/{len(data)} items matched",
                file=sys.stderr,
            )
        data = filtered

    # 12. Apply --first (slice)
    if args.first is not None:
        if isinstance(data, list):
            if args.first > len(data) and not summary:
                print(
                    f"# requested {args.first}, only {len(data)} items available",
                    file=sys.stderr,
                )
            data = data[: args.first]
        elif isinstance(data, dict):
            items = list(data.items())
            if args.first > len(items) and not summary:
                print(
                    f"# requested {args.first}, only {len(items)} keys available",
                    file=sys.stderr,
                )
            data = dict(items[: args.first])
        else:
            data = [data]

    # 13. Apply --pick (field projection)
    if args.pick and args.pick.strip():
        fields = [f.strip() for f in args.pick.split(",") if f.strip()]
        data = _pick_fields(data, fields)

    # 14. Apply --abbrev (short-key rename)
    if args.abbrev:
        data = _abbreviate(data)

    # 15. Apply --max-chars (byte-length truncation)
    is_exempt = args.count or args.keys or args.filter or args.raw
    if args.max_chars is not None and not is_exempt:
        data = _truncate_by_chars(data, args.max_chars, compact)

    # 16. Dump JSON
    if data is not None:
        if compact:
            print(json.dumps(data, separators=(",", ":"), ensure_ascii=False))
        else:
            print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(raw_text, end="")

    return 0


# ====================================================================
# Output helper functions
# ====================================================================


def _handle_filter(
    filter_expr: str, data, content_type: str, compact: bool = True
) -> int:
    """Apply a jq filter to parsed JSON data."""
    if data is None:
        print(
            f"\u274c --filter: response body is empty or could not be parsed as JSON "
            f"(Content-Type: {content_type or 'unknown'})",
            file=sys.stderr,
        )
        return 1

    if not shutil.which("jq"):
        print(
            "\u26a0\ufe0f  jq not installed; printing raw JSON",
            file=sys.stderr,
        )
        if compact:
            print(json.dumps(data, separators=(",", ":"), ensure_ascii=False))
        else:
            print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0

    text = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    try:
        result = subprocess.run(
            ["jq", "--raw-output", filter_expr],
            input=text,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, OSError) as e:
        print(f"\u274c jq failed: {e}", file=sys.stderr)
        return 1

    if result.returncode != 0:
        print(f"\u274c jq: {result.stderr.strip()}", file=sys.stderr)
        return 1

    print(result.stdout, end="")
    return 0


def _handle_count(data, raw_text: str, is_json: bool) -> int:
    """Print the length of a JSON collection or scalar indicator."""
    if isinstance(data, (list, dict)):
        print(len(data))
    elif isinstance(data, (bool, int, float, str)):
        print(0)
    elif is_json and data is None:
        print(0)  # JSON null → not a collection
    elif raw_text:
        print(len(raw_text.encode("utf-8")))  # non-JSON fallback
    else:
        print(0)
    return 0


def _handle_keys(data) -> int:
    """Print unique JSON key names (metadata to stderr, keys to stdout)."""
    if isinstance(data, list):
        count = len(data)
        if count == 0:
            print("# empty list", file=sys.stderr)
            print("[]")
        else:
            all_keys: set[str] = set()
            for item in data:
                if isinstance(item, dict):
                    all_keys.update(item.keys())
            keys = sorted(all_keys)
            if keys:
                print(
                    f"# {count} items, {len(keys)} unique keys: {', '.join(keys)}",
                    file=sys.stderr,
                )
                print(json.dumps(keys, separators=(",", ":")))
            else:
                print(f"# {count} items (non-dict, no keys available)", file=sys.stderr)
                print("[]")
    elif isinstance(data, dict):
        keys = list(data.keys())
        print(f"# {len(keys)} keys", file=sys.stderr)
        print(json.dumps(keys, separators=(",", ":")))
    else:
        print("# not a JSON object or list", file=sys.stderr)
        printable = (
            json.dumps(data, separators=(",", ":"), ensure_ascii=False)
            if data is not None
            else "null"
        )
        print(printable)
    return 0


def _pick_fields(data, fields: list[str]):
    """Keep only the specified keys from each dict in data.

    Args:
        data: Parsed JSON — list, dict, or scalar.
        fields: Key names to retain.

    Returns:
        Projected data (same shape as input).
    """
    if isinstance(data, list):
        return [_pick_item(item, fields) for item in data]
    if isinstance(data, dict):
        return _pick_item(data, fields)
    return data


def _pick_item(item, fields: list[str]):
    if not isinstance(item, dict):
        return item
    return {k: item[k] for k in fields if k in item}


# ---------------------------------------------------------------------------
# Byte-length truncation
# ---------------------------------------------------------------------------


def _truncate_by_chars(data, max_chars: int, compact: bool):
    """Trim data so its JSON form fits within *max_chars* characters.

    For lists, items are dropped from the end and a truncation marker is
    appended.  For dicts/scalars no structural truncation is performed
    (pass-through).  0 or negative *max_chars* disables truncation.
    """
    if max_chars <= 0:
        return data

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

    # Even a single item + marker doesn't fit; return just the marker
    marker = {"_truncated": True, "shown": 0, "total": original_len}
    return [marker]


# ---------------------------------------------------------------------------
# Key abbreviation
# ---------------------------------------------------------------------------

ABBREV_MAP: dict[str, str] = {
    "entity_id": "e",
    "state": "s",
    "attributes": "at",
    "last_changed": "lc",
    "last_updated": "lu",
    "context": "ctx",
}


def _abbreviate(data):
    """Shorten known JSON keys using ABBREV_MAP."""
    if isinstance(data, list):
        return [_abbreviate_item(item) for item in data]
    if isinstance(data, dict):
        return _abbreviate_item(data)
    return data


def _abbreviate_item(item):
    if not isinstance(item, dict):
        return item
    return {ABBREV_MAP.get(k, k): v for k, v in item.items()}
