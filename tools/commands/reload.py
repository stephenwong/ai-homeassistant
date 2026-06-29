"""``reload`` subcommand: thin wrapper around reload_config.reload_config()."""

import argparse

from tools.common import resolve_summary
from tools.reload_config import reload_config


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    """Wire the ``reload`` subparser."""
    parser = subparsers.add_parser(
        "reload",
        help="Reload Home Assistant configuration via API.",
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
    """Entry point for the ``reload`` subcommand. Returns exit code."""
    summary = resolve_summary(args)
    success = reload_config(summary=summary)
    return 0 if success else 1
