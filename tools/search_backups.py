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
import re
import tarfile

from prune_backups import get_backups


def search_backup(backup, pattern, yaml_only=True, context_lines=0):
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
                    f = tar.extractfile(member)
                    if f is None:
                        continue
                    content = f.read().decode("utf-8")
                except (UnicodeDecodeError, KeyError):
                    continue

                lines = content.splitlines()
                for i, line in enumerate(lines):
                    if pattern.search(line):
                        match_entry = {
                            "file": member.name,
                            "line_num": i + 1,
                            "line": line,
                        }
                        if context_lines > 0:
                            start = max(0, i - context_lines)
                            end = min(len(lines), i + context_lines + 1)
                            match_entry["context_before"] = lines[start:i]
                            match_entry["context_after"] = lines[i + 1 : end]
                        matches.append(match_entry)
    except (tarfile.TarError, OSError) as e:
        print(f"  Warning: Could not read {backup['filename']}: {e}")

    return matches


def main():
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
        type=int,
        default=0,
        help="Number of context lines around matches",
    )
    args = parser.parse_args()

    try:
        pattern = re.compile(args.pattern)
    except re.error as e:
        print(f"Invalid regex pattern: {e}")
        return 1

    backups = get_backups()
    if not backups:
        print("No backups found")
        return 1

    # Search newest first
    backups = list(reversed(backups))

    yaml_only = not args.all
    file_type = "all files" if args.all else "YAML files"
    print(f"Searching {len(backups)} backups for: {args.pattern} ({file_type})\n")

    match_count = 0
    for backup in backups:
        date_str = backup["timestamp"].strftime("%b %d")
        matches = search_backup(
            backup, pattern, yaml_only=yaml_only, context_lines=args.context
        )

        if matches:
            match_count += 1
            print(f"  MATCH  {backup['filename']} ({date_str})")
            if not args.files_only:
                seen_files = set()
                for m in matches:
                    if m["file"] not in seen_files:
                        seen_files.add(m["file"])
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

    print(f"\nFound in {match_count} of {len(backups)} backups")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
