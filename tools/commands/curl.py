"""``curl`` subcommand: pure-Python HA REST API client.

Replaces the earlier bash/curl/jq pipeline with HAClient (pure Python).
Compact JSON by default; use ``--pretty`` for human-readable output.

Token-efficiency flags for agents:
  ``--count``  — print item count instead of full payload
  ``--keys``   — print key names only (no values)
  ``--first N`` — print first N items
"""

from __future__ import annotations

import argparse
import contextlib
import json
import shutil
import subprocess
import sys

from tools.common import HARequestError
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

    parser.add_argument("endpoint", type=_validate_endpoint, help="API endpoint")

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

    parser.set_defaults(func=run)


# ====================================================================
# run()
# ====================================================================


def run(args: argparse.Namespace) -> int:
    """Execute a curl request.  Returns exit code (0 success, 1 error)."""
    method = args.method
    compact = not args.pretty

    # 1. Conflict: --raw + --pretty (check before costly from_env())
    if args.raw and args.pretty:
        print("\u274c Cannot combine --raw with --pretty", file=sys.stderr)
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
    elif args.data is not None:
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

    # 7. Validate output flag against JSON-ness
    requires_json = args.filter or args.keys or (args.first is not None)
    if requires_json and data is None and not is_json:
        flag = "filter" if args.filter else ("keys" if args.keys else "first")
        print(
            f"\u274c Cannot use --{flag} on non-JSON response "
            f"(Content-Type: {content_type or 'unknown'})",
            file=sys.stderr,
        )
        return 1

    # 8. Pretty-warning for --filter and --keys
    if args.pretty:
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

    # 9. Dispatch by output flag
    if args.filter:
        return _handle_filter(args.filter, data, content_type, compact)
    if args.count:
        return _handle_count(data, raw_text, is_json)
    if args.keys:
        return _handle_keys(data)
    if args.first is not None:
        return _handle_first(data, args.first, compact)
    if args.raw:
        print(raw_text, end="")
        return 0

    # Default: dump JSON
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


def _handle_first(data, n: int, compact: bool) -> int:
    """Print the first N items."""
    if isinstance(data, list):
        subset = data[:n]
        if n > len(data):
            print(f"# requested {n}, only {len(data)} items available", file=sys.stderr)
    elif isinstance(data, dict):
        items = list(data.items())[:n]
        subset = dict(items)
        if n > len(data):
            print(f"# requested {n}, only {len(data)} keys available", file=sys.stderr)
    else:
        subset = [data]

    if compact:
        print(json.dumps(subset, separators=(",", ":"), ensure_ascii=False))
    else:
        print(json.dumps(subset, indent=2, ensure_ascii=False))
    return 0
