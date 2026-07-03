"""``call`` subcommand: call a Home Assistant service."""

import argparse
import contextlib
import json
import re
import sys

from tools.common import HARequestError, resolve_summary
from tools.ha.client import HAClient

_SERVICE_RE = re.compile(r"^[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*$")


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    """Wire the ``call`` subparser."""
    parser = subparsers.add_parser(
        "call",
        help="Call a Home Assistant service.",
        description=(
            "Call a Home Assistant service via the REST API. "
            "The service argument is in domain.service format (e.g. light.turn_on)."
        ),
    )
    parser.add_argument(
        "service",
        help="Service to call in domain.service format (e.g. light.turn_on)",
    )
    parser.add_argument(
        "--data",
        "-d",
        help="JSON data to pass to the service (must be a JSON object)",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output with indent=2 (default: compact)",
    )
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


def run(args: argparse.Namespace) -> int:
    """Entry point for the ``call`` subcommand. Returns exit code."""
    resolve_summary(args)

    if not _SERVICE_RE.fullmatch(args.service):
        print(
            f"\u274c Invalid service format: {args.service!r} "
            f"(expected 'domain.service')",
            file=sys.stderr,
        )
        return 1

    domain, _, service = args.service.partition(".")

    json_data: dict = {}
    if args.data is not None:
        try:
            parsed = json.loads(args.data)
        except json.JSONDecodeError as e:
            print(f"\u274c Invalid JSON in --data: {e}", file=sys.stderr)
            return 1
        if not isinstance(parsed, dict):
            print(
                "\u274c --data must be a JSON object",
                file=sys.stderr,
            )
            return 1
        json_data = parsed

    try:
        client = HAClient.from_env()
    except HARequestError as e:
        print(f"\u274c {e}", file=sys.stderr)
        return 1

    try:
        resp = client.post(f"/api/services/{domain}/{service}", json=json_data)
    except HARequestError as e:
        print(f"\u274c {e}", file=sys.stderr)
        return 1

    if not resp.ok:
        print(
            f"\u274c HTTP {resp.status_code}: {resp.text[:200]}",
            file=sys.stderr,
        )
        return 1

    content_type = resp.headers.get("content-type", "")
    raw_text = resp.text
    is_json = "application/json" in content_type or raw_text.strip().startswith(
        ("{", "[")
    )
    data = None
    if is_json:
        with contextlib.suppress(ValueError, TypeError, json.JSONDecodeError):
            data = resp.json()

    if data is not None:
        if args.pretty:
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print(json.dumps(data, separators=(",", ":"), ensure_ascii=False))
    else:
        sys.stdout.write(raw_text)

    return 0
