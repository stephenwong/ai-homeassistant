"""``history`` subcommand: fetch entity state history from Home Assistant."""

import argparse
import json
import re
import sys
import urllib.parse

from tools.common import HARequestError, resolve_summary
from tools.ha.client import HAClient

_ENTITY_RE = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    """Wire the ``history`` subparser."""
    parser = subparsers.add_parser(
        "history",
        help="Fetch entity state history.",
        description=(
            "Fetch state history for an entity from Home Assistant. "
            "Defaults to the last 24 hours."
        ),
    )
    parser.add_argument(
        "entity_id",
        help="Entity ID (e.g. sensor.temperature)",
    )
    parser.add_argument(
        "--since",
        "-s",
        help="Start timestamp in ISO8601 format (e.g. 2026-07-01T00:00:00Z)",
    )
    parser.add_argument(
        "--end",
        help="End timestamp in ISO8601 format (e.g. 2026-07-02T00:00:00Z)",
    )
    parser.add_argument(
        "--minimal",
        action="store_true",
        help="Omit attributes and context from the response",
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
    """Entry point for the ``history`` subcommand. Returns exit code."""
    resolve_summary(args)

    if not _ENTITY_RE.fullmatch(args.entity_id):
        print(
            f"\u274c Invalid entity_id: {args.entity_id!r}",
            file=sys.stderr,
        )
        return 1

    path = "/api/history/period"
    if args.since:
        path += "/" + urllib.parse.quote(args.since, safe=":")

    params: dict[str, str] = {"filter_entity_id": args.entity_id}
    if args.end:
        params["end_time"] = args.end
    if args.minimal:
        params["minimal"] = "1"

    try:
        client = HAClient.from_env()
    except HARequestError as e:
        print(f"\u274c {e}", file=sys.stderr)
        return 1

    try:
        data = client.get_json(path, params=params)
    except HARequestError as e:
        print(f"\u274c {e}", file=sys.stderr)
        return 1

    # Unwrap nested list: [[state, state, ...]] -> [state, state, ...]
    if isinstance(data, list) and data and isinstance(data[0], list):
        data = data[0]

    if args.pretty:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(data, separators=(",", ":"), ensure_ascii=False))

    return 0
