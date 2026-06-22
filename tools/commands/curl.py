#!/usr/bin/env python3
"""``curl`` subcommand: thin wrapper around tools/ha-curl.sh.

Adds ``--filter`` (jq expression) for compact output. Falls back to plain
curl behavior when jq is unavailable.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

_HA_CURL = Path(__file__).parent.parent / "ha-curl.sh"


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    """Wire the ``curl`` subparser."""
    parser = subparsers.add_parser(
        "curl",
        help="Call HA REST API via the ha-curl.sh wrapper.",
        description=(
            "Wraps tools/ha-curl.sh. Pass --filter to pipe the response "
            "through jq (e.g. --filter '. | length' on /api/states)."
        ),
    )
    parser.add_argument(
        "endpoint",
        help="API endpoint, must start with / (e.g. /api/states)",
    )
    parser.add_argument(
        "--post",
        "-X",
        dest="method",
        action="store_const",
        const="POST",
        default="GET",
        help="Use POST instead of GET (flag, no value)",
    )
    parser.add_argument(
        "--data",
        "-d",
        help="JSON body for POST requests",
    )
    parser.add_argument(
        "--filter",
        help="jq expression to filter JSON response (no-op if jq missing)",
    )
    parser.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    """Entry point for the ``curl`` subcommand. Returns exit code."""
    if not _HA_CURL.exists():
        print(f"\u274c ha-curl.sh not found at {_HA_CURL}", file=sys.stderr)
        return 1

    cmd = ["bash", str(_HA_CURL)]
    if args.method == "POST":
        cmd.append("-X")
        cmd.append("POST")
    if args.data:
        cmd.append("-d")
        cmd.append(args.data)
    cmd.append(args.endpoint)

    if args.filter:
        if not shutil.which("jq"):
            print(
                "\u26a0\ufe0f  jq not installed; returning raw JSON",
                file=sys.stderr,
            )
        else:
            # Pipe curl → jq
            curl_proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            try:
                subprocess.run(
                    ["jq", args.filter],
                    stdin=curl_proc.stdout,
                    check=False,
                )
                if curl_proc.stdout is not None:
                    curl_proc.stdout.close()
                curl_proc.wait()
                return curl_proc.returncode if curl_proc.returncode == 0 else 1
            except Exception as e:
                print(f"\u274c jq failed: {e}", file=sys.stderr)
                return 1

    # Plain passthrough
    result = subprocess.run(cmd, check=False)
    return result.returncode
