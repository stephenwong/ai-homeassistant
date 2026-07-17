#!/usr/bin/env python3
"""
Search across all Home Assistant backup archives for a text pattern.

Usage:
    python search_backups.py 'media_player.play_media'
    python search_backups.py --all 'some_pattern'
    python search_backups.py --files-only 'pattern'
    python search_backups.py -C 2 'pattern'
"""

import argparse
import os
import re
import sys
import tarfile
from collections import deque
from concurrent.futures import ThreadPoolExecutor

from tools.common import get_env_int, non_negative_int
from tools.prune_backups import get_backups


def is_potentially_unsafe_regex(pattern: str) -> bool:
    """Detect common catastrophic-backtracking regex patterns.

    This intentionally targets only obvious nested-quantifier forms.
    """
    nested_quantifier_patterns = [
        r"\([^)]*[+*][^)]*\)[+*]",  # e.g. (a+)+, (.*)+
        r"\([^)]*\{[^}]+\}[^)]*\)[+*]",  # e.g. (a{1,3})+
    ]
    return any(re.search(expr, pattern) for expr in nested_quantifier_patterns)


def search_backup(
    backup: dict, pattern: re.Pattern, yaml_only: bool = True, context_lines: int = 0
) -> list[dict]:
    """Search a single backup archive for a pattern. Returns list of matches."""
    matches = []
    try:
        with tarfile.open(backup["path"], "r:gz") as tar:
            for member in tar.getmembers():
                if not member.isfile():
                    continue

                if yaml_only and not (
                    member.name.endswith(".yaml") or member.name.endswith(".yml")
                ):
                    continue

                try:
                    extracted = tar.extractfile(member)
                    if extracted is None:
                        continue
                except KeyError:
                    continue

                try:
                    with extracted:
                        context_before: deque[str] = deque(maxlen=context_lines)
                        pending_after: list[dict] = []

                        for line_num, raw_line in enumerate(extracted, start=1):
                            line = raw_line.decode("utf-8").rstrip("\n")

                            if pending_after:
                                remaining = []
                                for pending_match in pending_after:
                                    pending_match["context_after"].append(line)
                                    pending_match["_remaining_after"] -= 1
                                    if pending_match["_remaining_after"] > 0:
                                        remaining.append(pending_match)
                                pending_after = remaining

                            if not pattern.search(line):
                                if context_lines > 0:
                                    context_before.append(line)
                                continue

                            match_entry = {
                                "file": member.name,
                                "line_num": line_num,
                                "line": line,
                            }
                            if context_lines > 0:
                                match_entry["context_before"] = list(context_before)
                                match_entry["context_after"] = []
                                match_entry["_remaining_after"] = context_lines
                                pending_after.append(match_entry)

                            matches.append(match_entry)

                            if context_lines > 0:
                                context_before.append(line)
                except UnicodeDecodeError:
                    # Skip non-UTF8 files
                    continue

            for match in matches:
                match.pop("_remaining_after", None)
    except (tarfile.TarError, OSError) as e:
        print(f"  Warning: Could not read {backup['filename']}: {e}", file=sys.stderr)

    return matches


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Search across Home Assistant backup archives"
    )
    parser.add_argument("pattern", help="Text pattern to search for (regex)")
    parser.add_argument(
        "--all", "-a", action="store_true", help="Search all files, not just YAML"
    )
    parser.add_argument(
        "--files-only",
        "-l",
        action="store_true",
        help="Only show backup filenames, not matching lines",
    )
    parser.add_argument(
        "--context",
        "-C",
        type=non_negative_int,
        default=0,
        help="Number of context lines around matches (>= 0)",
    )
    args = parser.parse_args()

    if is_potentially_unsafe_regex(args.pattern):
        print(
            "Invalid regex pattern: pattern appears unsafe "
            "(nested quantifiers can cause catastrophic backtracking)",
            file=sys.stderr,
        )
        return 1

    try:
        pattern = re.compile(args.pattern)
    except re.error as e:
        print(f"Invalid regex pattern: {e}", file=sys.stderr)
        return 1

    backups = get_backups()
    if not backups:
        print("No backups found", file=sys.stderr)
        return 1

    # Search newest first
    backups = list(reversed(backups))

    yaml_only = not args.all
    file_type = "all files" if args.all else "YAML files"
    print(
        f"Searching {len(backups)} backups for: {args.pattern} ({file_type})\n",
        file=sys.stderr,
    )

    default_workers = min(32, (os.cpu_count() or 1) + 4)
    max_workers, worker_warning = get_env_int(
        "BACKUP_SEARCH_MAX_WORKERS", default_workers
    )
    if worker_warning:
        print(f"Warning: {worker_warning}", file=sys.stderr)

    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            (
                backup,
                executor.submit(
                    search_backup,
                    backup,
                    pattern,
                    yaml_only=yaml_only,
                    context_lines=args.context,
                ),
            )
            for backup in backups
        ]

        for backup, future in futures:
            results.append((backup, future.result()))

    match_count = sum(1 for _backup, matches in results if matches)

    for backup, matches in results:
        date_str = backup["timestamp"].strftime("%b %d")
        if matches:
            print(f"  MATCH  {backup['filename']} ({date_str})")
            if not args.files_only:
                for m in matches:
                    if args.context > 0 and "context_before" in m:
                        for ctx_line in m["context_before"]:
                            print(f"           {m['file']}:     {ctx_line}")
                    print(f"         {m['file']}:{m['line_num']}:{m['line']}")
                    if args.context > 0 and "context_after" in m:
                        for ctx_line in m["context_after"]:
                            print(f"           {m['file']}:     {ctx_line}")
                print()
        else:
            print(f"  ----   {backup['filename']} ({date_str})")

    print(f"\nFound in {match_count} of {len(backups)} backups", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
