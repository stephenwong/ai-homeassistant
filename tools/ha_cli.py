#!/usr/bin/env python3
"""Home Assistant configuration tools — single CLI entry point.

Usage::

    uv run python tools/ha_cli.py <command> [args]

Subcommands:
    validate        Run all configuration validators in-process.
    reload          Reload HA configuration via API.
    curl            Call HA REST API via HAClient (pure Python).
    trace           Fetch automation traces.
    edit            Edit automations/scripts with safe round-trip YAML.
    stale-sensors   Detect stale sensors in the entity registry.

"""

import argparse
import sys

from tools.commands import (
    curl,
    edit,
    reload,
    stale_sensors,
    trace,
    validate,
)

_COMMAND_MODULES = (validate, reload, curl, edit, stale_sensors, trace)


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

    for command_module in _COMMAND_MODULES:
        command_module.add_parser(subparsers)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Top-level entry point. Returns process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    # Each subparser sets `func` via set_defaults; call it.
    func = getattr(args, "func", None)
    if func is None:
        parser.print_help(sys.stderr)
        return 2

    try:
        rc = func(args)
        return rc if isinstance(rc, int) and not isinstance(rc, bool) else 1
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
