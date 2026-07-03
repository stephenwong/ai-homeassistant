"""``logs`` subcommand: fetch Home Assistant error log."""

import argparse
import sys

from tools.common import HARequestError, resolve_summary
from tools.ha.client import HAClient


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    """Wire the ``logs`` subparser."""
    parser = subparsers.add_parser(
        "logs",
        help="Fetch Home Assistant error log.",
        description="Print the Home Assistant error log to stdout via the REST API.",
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
    resolve_summary(args)
    try:
        client = HAClient.from_env()
    except HARequestError as e:
        print(f"\u274c {e}", file=sys.stderr)
        return 1
    try:
        resp = client.get("/api/error_log")
    except HARequestError as e:
        print(f"\u274c {e}", file=sys.stderr)
        return 1
    if not resp.ok:
        print(
            f"\u274c HTTP {resp.status_code}: {resp.text[:200]}",
            file=sys.stderr,
        )
        return 1
    sys.stdout.write(resp.text)
    return 0
