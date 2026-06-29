#!/usr/bin/env python3
"""``stale-sensors`` subcommand: run stale sensor detection directly."""

from __future__ import annotations

import argparse

from tools.validators.stale_sensors import StaleSensorValidator


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    """Wire the ``stale-sensors`` subparser."""
    parser = subparsers.add_parser(
        "stale-sensors",
        help="Detect stale Home Assistant sensors.",
        description="Query active entities via HA REST API and find stale sensors.",
    )
    parser.add_argument(
        "--config",
        "-c",
        default="config",
        help="Path to HA config directory (default: config)",
    )
    parser.add_argument(
        "--threshold",
        "-t",
        type=int,
        default=24,
        help="Staleness threshold in hours (default: 24)",
    )
    parser.add_argument(
        "--exclude-domains",
        help="Comma-separated domains to completely exclude (default: none)",
    )
    parser.add_argument(
        "--exclude-platforms",
        help="Platforms to exclude (default: template,group,etc.)",
    )
    parser.add_argument(
        "--only-domains",
        default="sensor",
        help="Comma-separated domains to analyze (default: sensor)",
    )
    parser.add_argument(
        "--ignore-restored",
        action="store_true",
        help="Do not flag entities restored at startup",
    )
    parser.add_argument(
        "--fail-on-stale",
        action="store_true",
        help="Exit with non-zero status code if stale sensors are found",
    )
    parser.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    """Entry point for the ``stale-sensors`` subcommand. Returns exit code."""
    only_domains = (
        {d.strip().lower() for d in args.only_domains.split(",")}
        if args.only_domains
        else {"sensor"}
    )

    if args.exclude_domains:
        ex_doms = {d.strip().lower() for d in args.exclude_domains.split(",")}
        only_domains = only_domains - ex_doms

    exclude_platforms = (
        {p.strip().lower() for p in args.exclude_platforms.split(",")}
        if args.exclude_platforms
        else None
    )

    validator = StaleSensorValidator(
        config_dir=args.config,
        threshold_hours=args.threshold,
        only_domains=only_domains,
        exclude_platforms=exclude_platforms,
        ignore_restored=args.ignore_restored,
        fail_on_stale=args.fail_on_stale,
    )

    validator.validate_all()
    validator.print_results()

    if args.fail_on_stale and validator.warnings:
        return 1
    return 0
