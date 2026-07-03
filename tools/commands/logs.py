"""``logs`` subcommand: fetch Home Assistant system log via WebSocket."""

import argparse
import json
import sys

from tools.common import HARequestError, resolve_summary
from tools.ha.client import HAWSClient


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    """Wire the ``logs`` subparser."""
    parser = subparsers.add_parser(
        "logs",
        help="Fetch Home Assistant system log.",
        description=(
            "Fetch the Home Assistant system log via WebSocket API. "
            "Returns structured JSON entries (ERROR and WARNING levels). "
            "Use --level to filter by severity."
        ),
    )
    parser.add_argument(
        "--level",
        type=str.upper,
        choices=["ERROR", "WARNING"],
        help="Filter by severity level (case-insensitive)",
    )
    parser.add_argument(
        "--first",
        metavar="N",
        type=int,
        help="Show only the first N log entries",
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
    """Entry point for the ``logs`` subcommand. Returns exit code."""
    summary = resolve_summary(args)

    if args.first is not None and args.first < 1:
        print("\u274c --first must be >= 1", file=sys.stderr)
        return 1

    try:
        client = HAWSClient.from_env()
    except HARequestError as e:
        print(f"\u274c {e}", file=sys.stderr)
        return 1

    try:
        entries = client.command("system_log/list")
    except HARequestError as e:
        print(f"\u274c {e}", file=sys.stderr)
        return 1

    if not isinstance(entries, list):
        entries = []

    if args.level:
        target = args.level.upper()
        entries = [e for e in entries if e.get("level", "").upper() == target]

    if args.first is not None:
        entries = entries[: args.first]

    # Summary-mode projection: compact fields for non-TTY agents.
    if summary and not args.pretty:
        entries = [
            {
                "level": e.get("level"),
                "name": e.get("name"),
                "message": e.get("message"),
                "timestamp": e.get("timestamp"),
            }
            for e in entries
        ]

    if args.pretty:
        print(json.dumps(entries, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(entries, separators=(",", ":"), ensure_ascii=False))

    return 0
