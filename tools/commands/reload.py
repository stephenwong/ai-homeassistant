#!/usr/bin/env python3
"""``reload`` subcommand: thin wrapper around reload_config.reload_config()."""

from __future__ import annotations

import argparse

from tools.reload_config import reload_config


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    """Wire the ``reload`` subparser."""
    parser = subparsers.add_parser(
        "reload",
        help="Reload Home Assistant configuration via API.",
        description=(
            "Calls HA reload services for changed files. "
            "Reload output is intentionally verbose — this command does not "
            "support --quiet (use validate for quiet mode)."
        ),
    )
    parser.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    """Entry point for the ``reload`` subcommand. Returns exit code."""
    success = reload_config()
    return 0 if success else 1
