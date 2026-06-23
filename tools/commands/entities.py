#!/usr/bin/env python3
"""``entities`` subcommand: thin wrapper around entity_explorer.main()."""

from __future__ import annotations

import argparse

from tools import entity_explorer


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    """Wire the ``entities`` subparser."""
    parser = subparsers.add_parser(
        "entities",
        help="Explore Home Assistant entity registry.",
        description="Browse the entity registry by domain, area, or search term.",
    )
    parser.add_argument(
        "--config",
        "-c",
        default="config",
        help="Path to HA config directory (default: config)",
    )
    parser.add_argument("--domain", "-d", help="Show only entities from a domain")
    parser.add_argument("--area", "-a", help="Show only entities from an area")
    parser.add_argument(
        "--search", "-s", help="Search entities by name/id/device_class"
    )
    parser.add_argument(
        "--full",
        "-f",
        action="store_true",
        help="Show full detailed output",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit compact JSON output (machine-readable, no banners/emojis)",
    )
    parser.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    """Entry point for the ``entities`` subcommand. Returns exit code."""
    argv: list[str] = []
    if args.config:
        argv.extend(["--config", args.config])
    if args.domain:
        argv.extend(["--domain", args.domain])
    if args.area:
        argv.extend(["--area", args.area])
    if args.search:
        argv.extend(["--search", args.search])
    if args.full:
        argv.append("--full")
    if args.json:
        argv.append("--json")
    result = entity_explorer.main(argv)
    return int(result) if isinstance(result, int) else 0
