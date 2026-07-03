#!/usr/bin/env python3
"""Home Assistant configuration tools — single CLI entry point.

Usage::

    uv run python tools/ha_cli.py <command> [args]

Subcommands:
    validate    Run all configuration validators in-process.
    reload      Reload HA configuration via API.
    entities    Browse the entity registry.
    curl        Call HA REST API via HAClient (pure Python).
    edit        Edit automations/scripts with safe round-trip YAML.

"""

import argparse
import sys

from tools.commands import (
    call,
    curl,
    edit,
    entities,
    history,
    logs,
    reload,
    stale_sensors,
    trace,
    validate,
)


def build_parser() -> argparse.ArgumentParser:
    """Construct the top-level argparse parser."""
    parser = argparse.ArgumentParser(
        prog="ha_cli",
        description="Home Assistant configuration management tools.",
    )
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
        metavar="<command>",
    )

    validate.add_parser(subparsers)
    reload.add_parser(subparsers)
    entities.add_parser(subparsers)
    history.add_parser(subparsers)
    call.add_parser(subparsers)
    curl.add_parser(subparsers)
    edit.add_parser(subparsers)
    logs.add_parser(subparsers)
    stale_sensors.add_parser(subparsers)
    trace.add_parser(subparsers)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Top-level entry point. Returns process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    # Each subparser sets `func` via set_defaults; call it.
    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return 2

    try:
        return int(func(args))
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
