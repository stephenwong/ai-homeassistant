"""``history`` subcommand: fetch entity state history from Home Assistant."""

import argparse
import re
import sys
import urllib.parse
from datetime import UTC, datetime, timedelta

from tools.common import (
    HARequestError,
    add_output_shape_args,
    positive_float,
    resolve_max_chars,
    resolve_summary,
)
from tools.ha.client import HAClient
from tools.output_shape import apply_output_shape, print_json

_ENTITY_RE = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    """Wire the ``history`` subparser."""
    parser = subparsers.add_parser(
        "history",
        help="Fetch entity state history.",
        description=(
            "Fetch state history for an entity from Home Assistant. "
            "Defaults to 6 hours in summary mode, 24 hours otherwise."
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
        "--hours",
        type=positive_float,
        help="Time window in hours (default: 6 in summary, 24 in verbose)",
    )
    parser.add_argument(
        "--minimal",
        action="store_true",
        help="Omit attributes and context from the response",
    )
    add_output_shape_args(parser)
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
    summary = resolve_summary(args)

    if not _ENTITY_RE.fullmatch(args.entity_id):
        print(
            f"\u274c Invalid entity_id: {args.entity_id!r}",
            file=sys.stderr,
        )
        return 1

    path = "/api/history/period"
    if args.hours is not None:
        since = datetime.now(UTC) - timedelta(hours=args.hours)
        path += "/" + urllib.parse.quote(since.isoformat(), safe=":")
    elif args.since:
        path += "/" + urllib.parse.quote(args.since, safe=":")
    elif summary:
        since = datetime.now(UTC) - timedelta(hours=6)
        path += "/" + urllib.parse.quote(since.isoformat(), safe=":")

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

    # Empty-result hint for agents (stderr, stdout stays []).
    if isinstance(data, list) and not data:
        if args.hours is not None:
            window = f"last {args.hours:g}h"
        elif args.since:
            window = f"since {args.since}" + (f" until {args.end}" if args.end else "")
        elif summary:
            window = "last 6h"
        else:
            window = "last 24h (HA default)"
        print(
            f"# no history for {args.entity_id} in {window} "
            f"(verify entity_id; try --hours 48 or wider)",
            file=sys.stderr,
        )

    # Apply token-reduction shapes (--first, --pick, --max-chars)
    data = apply_output_shape(
        data,
        first=args.first,
        pick=args.pick,
        max_chars=resolve_max_chars(args, summary),
    )

    print_json(data, pretty=args.pretty)

    return 0
