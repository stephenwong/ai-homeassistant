"""``trace`` subcommand: fetch Home Assistant automation traces."""

import argparse
import json
import re
import sys

from tools.common import HARequestError, resolve_summary
from tools.ha.client import HAClient

_ENTITY_RE = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    """Wire the ``trace`` subparser."""
    parser = subparsers.add_parser(
        "trace",
        help="Fetch Home Assistant automation traces.",
        description=(
            "Fetch automation trace data from Home Assistant. "
            "With an entity_id, shows the trace for that automation; "
            "without one, lists all available traces."
        ),
    )
    parser.add_argument(
        "entity_id",
        nargs="?",
        default=None,
        help="Automation entity ID (e.g. automation.morning_routine)",
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
    """Entry point for the ``trace`` subcommand. Returns exit code."""
    resolve_summary(args)

    if args.entity_id is not None and not _ENTITY_RE.fullmatch(args.entity_id):
        print(
            f"\u274c Invalid entity_id: {args.entity_id!r}",
            file=sys.stderr,
        )
        return 1

    if args.entity_id:
        path = f"/api/automation/trace/{args.entity_id}"
    else:
        path = "/api/automation/trace"

    try:
        client = HAClient.from_env()
    except HARequestError as e:
        print(f"\u274c {e}", file=sys.stderr)
        return 1

    try:
        data = client.get_json(path)
    except HARequestError as e:
        print(f"\u274c {e}", file=sys.stderr)
        return 1

    if args.pretty:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(data, separators=(",", ":"), ensure_ascii=False))

    return 0
