#!/usr/bin/env python3
"""
Generate a human-readable changelog showing what changed between consecutive backups.

Usage:
    python generate_changelog.py backups/ha_config_20260205_204808.tar.gz
    python generate_changelog.py --generate-all
"""

import argparse
import difflib
import functools
import sys
import tarfile
from pathlib import Path

from tools.prune_backups import BACKUP_DIR, get_backups

# Files/directories to skip (noisy runtime state)
SKIP_PATTERNS = [
    ".storage/",
    "zigbee2mqtt/state.json",
    "zigbee2mqtt/log/",
    ".db",
    "__pycache__/",
    ".pyc",
]

# File extensions considered "interesting"
INTERESTING_EXTENSIONS = {
    ".yaml",
    ".yml",
    ".sh",
    ".py",
    ".json",
    ".conf",
    ".cfg",
    ".ini",
    ".txt",
}


def should_include(name: str) -> bool:
    """Check if a file should be included in the diff."""
    for pattern in SKIP_PATTERNS:
        if pattern in name:
            return False
    # Include files with interesting extensions or no extension (likely config)
    ext = Path(name).suffix.lower()
    return ext in INTERESTING_EXTENSIONS or ext == ""


@functools.lru_cache(maxsize=2)
def extract_files(backup_path: Path) -> dict[str, str]:
    """Extract interesting text files from a backup archive. Returns {name: content}."""
    files = {}
    try:
        with tarfile.open(backup_path, "r:gz") as tar:
            for member in tar.getmembers():
                if not member.isfile():
                    continue
                if not should_include(member.name):
                    continue
                try:
                    extracted = tar.extractfile(member)
                    if extracted is None:
                        continue
                    with extracted:
                        files[member.name] = extracted.read().decode("utf-8")
                except UnicodeDecodeError, KeyError:
                    continue
    except (tarfile.TarError, OSError) as e:
        print(f"  Warning: Could not read {backup_path}: {e}", file=sys.stderr)
    return files


def generate_changelog(backup: dict, previous_backup: dict | None) -> str:
    """Generate changelog content comparing two backups."""
    lines = []
    lines.append(f"Backup: {backup['filename']}")

    if previous_backup:
        lines.append(f"Previous: {previous_backup['filename']}")
    else:
        lines.append("Previous: (none - initial backup)")

    lines.append(f"Date: {backup['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    current_files = extract_files(backup["path"])

    if not previous_backup:
        # First backup - list all files
        lines.append("Initial backup - all files:")
        for name in sorted(current_files.keys()):
            line_count = len(current_files[name].splitlines())
            lines.append(f"  A {name} ({line_count} lines)")
        return "\n".join(lines) + "\n"

    previous_files = extract_files(previous_backup["path"])

    all_names = sorted(set(list(current_files.keys()) + list(previous_files.keys())))

    changed_files = []
    diffs = []

    for name in all_names:
        in_current = name in current_files
        in_previous = name in previous_files

        if in_current and not in_previous:
            # Added
            line_count = len(current_files[name].splitlines())
            changed_files.append(f"  A {name} (+{line_count})")
            diff = difflib.unified_diff(
                [],
                current_files[name].splitlines(),
                fromfile=f"a/{name}",
                tofile=f"b/{name}",
                lineterm="",
            )
            diffs.append("\n".join(diff))
        elif not in_current and in_previous:
            # Deleted
            line_count = len(previous_files[name].splitlines())
            changed_files.append(f"  D {name} (-{line_count})")
            diff = difflib.unified_diff(
                previous_files[name].splitlines(),
                [],
                fromfile=f"a/{name}",
                tofile=f"b/{name}",
                lineterm="",
            )
            diffs.append("\n".join(diff))
        elif in_current and in_previous:
            if current_files[name] != previous_files[name]:
                # Modified
                old_lines = previous_files[name].splitlines()
                new_lines = current_files[name].splitlines()
                diff_lines = list(
                    difflib.unified_diff(
                        old_lines,
                        new_lines,
                        fromfile=f"a/{name}",
                        tofile=f"b/{name}",
                        lineterm="",
                    )
                )
                if diff_lines:
                    added = sum(
                        1
                        for line in diff_lines
                        if line.startswith("+") and not line.startswith("+++")
                    )
                    removed = sum(
                        1
                        for line in diff_lines
                        if line.startswith("-") and not line.startswith("---")
                    )
                    changed_files.append(f"  M {name} (+{added}, -{removed})")
                    diffs.append("\n".join(diff_lines))

    if not changed_files:
        lines.append("No changes detected.")
        return "\n".join(lines) + "\n"

    lines.append("Changed files:")
    lines.extend(changed_files)
    lines.append("")
    lines.append("---")

    for diff in diffs:
        if diff:
            lines.append(diff)
            lines.append("")

    return "\n".join(lines) + "\n"


def changelog_path_for(backup: dict) -> Path:
    """Get the changelog path for a backup."""
    return BACKUP_DIR / backup["filename"].replace(".tar.gz", ".changelog")


def generate_for_backup(backup: dict, backups_list: list[dict]) -> Path:
    """Generate changelog for a single backup, finding its predecessor."""
    # Find previous backup
    previous = None
    for i, b in enumerate(backups_list):
        if b["filename"] == backup["filename"]:
            if i > 0:
                previous = backups_list[i - 1]
            break

    changelog_file = changelog_path_for(backup)
    content = generate_changelog(backup, previous)
    changelog_file.write_text(content, encoding="utf-8")
    return changelog_file


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate changelogs for Home Assistant backups"
    )
    parser.add_argument("backup", nargs="?", help="Path to a specific backup")
    parser.add_argument(
        "--generate-all",
        action="store_true",
        help="Generate changelogs for all backups missing one",
    )
    args = parser.parse_args()

    backups = get_backups()  # sorted oldest first
    if not backups:
        print("No backups found", file=sys.stderr)
        return 1

    if args.generate_all:
        generated = 0
        skipped = 0
        for backup in backups:
            cl_path = changelog_path_for(backup)
            if cl_path.exists():
                skipped += 1
                continue
            print(f"Generating changelog for {backup['filename']}...", file=sys.stderr)
            generate_for_backup(backup, backups)
            generated += 1

        print(
            f"\nGenerated {generated} changelog(s), skipped {skipped} existing",
            file=sys.stderr,
        )
        return 0

    if not args.backup:
        parser.error("Provide a backup path or use --generate-all")

    # Find the backup in our list
    backup_path = Path(args.backup)
    target = None
    for b in backups:
        if b["path"] == backup_path or b["filename"] == backup_path.name:
            target = b
            break

    if not target:
        print(f"Backup not found: {args.backup}", file=sys.stderr)
        return 1

    cl_path = generate_for_backup(target, backups)
    print(f"Changelog written to {cl_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
