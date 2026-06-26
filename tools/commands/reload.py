#!/usr/bin/env python3
"""``reload`` subcommand: thin wrapper around reload_config.reload_config()."""

from __future__ import annotations

import argparse
import sys

from tools.common import _is_tty
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
    explicit_summary = bool(getattr(args, "summary", False))
    explicit_no_summary = bool(getattr(args, "no_summary", False))
    if explicit_summary and explicit_no_summary:
        print(
            "WARN: conflicting --summary / --no-summary; using --summary",
            file=sys.stderr,
        )
    if explicit_summary:
        summary = True
    elif explicit_no_summary:
        summary = False
    else:
        summary = not _is_tty()
    success = reload_config(summary=summary)
    return 0 if success else 1
