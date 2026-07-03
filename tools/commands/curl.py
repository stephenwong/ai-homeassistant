"""``curl`` subcommand: pure-Python HA REST API client.

Replaces the earlier bash/curl/jq pipeline with HAClient (pure Python).
Compact JSON by default; use ``--pretty`` for human-readable output.

Token-efficiency flags for agents:
  ``--count``    — print item count instead of full payload
  ``--keys``     — print key names only (no values)
  ``--first N``  — print first N items
  ``--pick F``   — keep only specified JSON keys (per-item projection)
  ``--entity ID`` — fetch a single entity by id (server-side)
  ``--domain D``  — filter list response by domain (client-side)
  ``--max-chars N`` — truncate JSON output when it exceeds N bytes
"""

import argparse
import contextlib
import json
import re
import sys

from tools.common import (
    HARequestError,
    _has_transform_flags,
    add_output_shape_args,
    positive_int,
    resolve_max_chars,
    resolve_summary,
)
from tools.ha.client import HAClient
from tools.output_shape import apply_output_shape, print_json


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
    output_group = parser.add_mutually_exclusive_group()
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
        type=positive_int,
        help="Print first N items only",
    )
    output_group.add_argument(
        "--raw",
        action="store_true",
        help="Print raw response body (skip JSON processing entirely)",
    )

    # ---- bare-endpoint guardrail ----
    parser.add_argument(
        "--no-guard",
        action="store_true",
        help="Disable guardrail AND default max-chars cap (dump all entities)",
    )

    # ---- shared token-reduction flags (--pick, --max-chars) ----
    add_output_shape_args(parser, first=False)

    # ---- output formatting ----
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON with indent=2 (default: compact)",
    )

    # ---- summary / quiet mode ----
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Compact output; auto-detected when stdout is not a TTY",
    )
    parser.add_argument(
        "--no-summary",
        action="store_true",
        help="Force verbose output even when stdout is piped",
    )

    parser.set_defaults(func=run)


# ====================================================================
# run()
# ====================================================================


def run(args: argparse.Namespace) -> int:
    """Execute a curl request.  Returns exit code (0 success, 1 error)."""
    summary = resolve_summary(args)
    method = args.method
    # 1. Conflict: --raw + --pretty (check before costly from_env())
    if args.raw and args.pretty:
        print("\u274c Cannot combine --raw with --pretty", file=sys.stderr)
        return 1

    # 1b. Conflict: --pick with exclusive transforms (also before from_env)
    if args.pick and (args.count or args.keys or args.raw):
        print(
            "\u274c Cannot combine --pick with --count/--keys/--raw",
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
        if args.count or args.keys or args.raw:
            print(
                "\u274c Cannot combine --entity with --count/--keys/--raw",
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
        if args.count or args.keys or args.raw:
            print(
                "\u274c Cannot combine --domain with --count/--keys/--raw",
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
    requires_json = args.keys or (args.first is not None) or bool(args.pick)
    if requires_json and data is None and not is_json:
        flag = "keys" if args.keys else ("first" if args.first is not None else "pick")
        print(
            f"\u274c Cannot use --{flag} on non-JSON response "
            f"(Content-Type: {content_type or 'unknown'})",
            file=sys.stderr,
        )
        return 1

    # 9. Pretty-warning for --keys
    if args.pretty and not summary and args.keys:
        print(
            "\u26a0\ufe0f  --pretty has no effect with --keys",
            file=sys.stderr,
        )

    # 10. Dispatch by output flag (early-exit handlers)
    if args.count:
        return _handle_count(data, raw_text, is_json)
    if args.keys:
        return _handle_keys(data, summary=summary)
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

    # 12. Warn on --first overcount (verbose mode only)
    if args.first is not None and not summary:
        _warn_first_overcount(data, args.first)

    # 13-15. Apply shared output shaping (first → pick → max_chars)
    effective_max_chars = (
        None
        if args.no_guard and args.max_chars is None
        else resolve_max_chars(args, summary)
    )
    data = apply_output_shape(
        data,
        first=args.first,
        pick=args.pick,
        max_chars=effective_max_chars,
    )

    # 16. Dump JSON
    if data is not None:
        print_json(data, pretty=args.pretty)
    else:
        print(raw_text, end="")

    return 0


# ====================================================================
# Output helper functions
# ====================================================================


def _handle_count(data, raw_text: str, is_json: bool) -> int:
    """Print the length of a JSON collection; 0 otherwise."""
    if isinstance(data, (list, dict)):
        print(len(data))
    else:
        print(0)
    return 0


def _handle_keys(data, summary: bool = False) -> int:
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
                if summary:
                    print(f"# {count} items, {len(keys)} keys", file=sys.stderr)
                else:
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


def _warn_first_overcount(data, n: int):
    """Emit a warning to stderr when ``--first`` exceeds data length (verbose)."""
    if isinstance(data, list) and n > len(data):
        print(
            f"# requested {n}, only {len(data)} items available",
            file=sys.stderr,
        )
    elif isinstance(data, dict) and n > len(data):
        print(
            f"# requested {n}, only {len(data)} keys available",
            file=sys.stderr,
        )
