#!/usr/bin/env python3
"""
Prune Home Assistant configuration backups with smart retention.

Retention rules:
- Keep all backups from last 7 days
- Keep one backup per day for backups 7-30 days old (latest each day)
- Keep one backup per week for backups older than 30 days (latest each week)
"""

import argparse
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

BACKUP_DIR = Path(__file__).parent.parent / "backups"
BACKUP_PATTERN = re.compile(r"ha_config_(\d{8})_(\d{6})\.tar\.gz")


def parse_backup_filename(filename: str) -> datetime | None:
    """Parse backup filename and return datetime object."""
    match = BACKUP_PATTERN.match(filename)
    if not match:
        return None

    date_str = match.group(1)  # YYYYMMDD
    time_str = match.group(2)  # HHMMSS

    try:
        return datetime.strptime(f"{date_str}_{time_str}", "%Y%m%d_%H%M%S").astimezone()
    except ValueError:
        return None


def get_backups() -> list[dict]:
    """Get all backup files with their timestamps."""
    if not BACKUP_DIR.exists():
        return []

    backups = []
    for file in BACKUP_DIR.glob("*.tar.gz"):
        timestamp = parse_backup_filename(file.name)
        if timestamp:
            backups.append(
                {"path": file, "filename": file.name, "timestamp": timestamp}
            )

    return sorted(backups, key=lambda x: x["timestamp"])


def group_by_retention_period(backups: list[dict], now: datetime) -> dict:
    """Group backups into retention periods."""
    groups: dict[str, Any] = {
        "keep_all": [],  # Last 7 days
        "daily": defaultdict(list),  # 7-30 days, one per day
        "weekly": defaultdict(list),  # 30+ days, one per week
    }

    for backup in backups:
        age = now - backup["timestamp"]

        if age.days <= 7:
            # Keep all from last 7 days
            groups["keep_all"].append(backup)
        elif age.days <= 30:
            # Group by day (YYYY-MM-DD)
            day_key = backup["timestamp"].strftime("%Y-%m-%d")
            groups["daily"][day_key].append(backup)
        else:
            # Group by ISO week (%G = ISO year, %V = ISO week 01-53)
            week_key = backup["timestamp"].strftime("%G-W%V")
            groups["weekly"][week_key].append(backup)

    return groups


def apply_retention(groups: dict) -> tuple[list[dict], list[dict]]:
    """Apply retention rules and return lists of files to keep/delete."""
    to_keep = []
    to_delete = []

    # Keep all recent backups (0-7 days)
    to_keep.extend(groups["keep_all"])

    # Keep one per day (7-30 days) - latest from each day
    for day_backups in groups["daily"].values():
        if day_backups:
            # Sort by timestamp, keep latest
            sorted_backups = sorted(
                day_backups, key=lambda x: x["timestamp"], reverse=True
            )
            to_keep.append(sorted_backups[0])
            to_delete.extend(sorted_backups[1:])

    # Keep one per week (30+ days) - latest from each week
    for week_backups in groups["weekly"].values():
        if week_backups:
            # Sort by timestamp, keep latest
            sorted_backups = sorted(
                week_backups, key=lambda x: x["timestamp"], reverse=True
            )
            to_keep.append(sorted_backups[0])
            to_delete.extend(sorted_backups[1:])

    return to_keep, to_delete


def format_size(size_bytes: int | float) -> str:
    """Format bytes as human-readable size."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f}{unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f}TB"


def clean_orphaned_changelogs(dry_run: bool = False) -> int:
    """Remove changelog files that have no matching backup tar.gz."""
    if not BACKUP_DIR.exists():
        return 0
    orphans = []
    for changelog in BACKUP_DIR.glob("*.changelog"):
        tar_path = BACKUP_DIR / (changelog.stem + ".tar.gz")
        if not tar_path.exists():
            orphans.append(changelog)
    if orphans:
        print(f"\nOrphaned changelogs: {len(orphans)}", file=sys.stderr)
        for orphan in orphans:
            if dry_run:
                print(f"  Would delete: {orphan.name}", file=sys.stderr)
            else:
                orphan.unlink()
                print(f"  Deleted: {orphan.name}", file=sys.stderr)
    return len(orphans)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prune Home Assistant backups")
    parser.add_argument(
        "--apply",
        "--execute",
        dest="apply",
        action="store_true",
        help="Actually delete files (default: dry-run — no files are removed).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Explicit dry-run (default behaviour; accepted for clarity).",
    )
    parser.add_argument(
        "--min-keep",
        type=int,
        default=3,
        help="Refuse to delete if fewer than N backups would remain (default: 3).",
    )
    args = parser.parse_args(argv)
    apply_deletes = args.apply and not args.dry_run

    print("Home Assistant Backup Retention Pruner", file=sys.stderr)
    if not apply_deletes:
        print(
            "(DRY RUN — no files will be deleted; pass --apply to delete)",
            file=sys.stderr,
        )
    print("=" * 50, file=sys.stderr)

    backups = get_backups()

    if not backups:
        print(f"No backups found in {BACKUP_DIR}", file=sys.stderr)
        clean_orphaned_changelogs(dry_run=not apply_deletes)
        return 0

    print(f"\nFound {len(backups)} backup(s)", file=sys.stderr)

    now = datetime.now().astimezone()
    groups = group_by_retention_period(backups, now)
    to_keep, to_delete = apply_retention(groups)

    print("\nRetention Summary:", file=sys.stderr)
    print(f"  - Keeping {len(to_keep)} backup(s)", file=sys.stderr)
    print(f"  - Deleting {len(to_delete)} backup(s)", file=sys.stderr)

    if to_delete:
        print("\nBackups to delete:", file=sys.stderr)
        total_size = 0
        for backup in sorted(to_delete, key=lambda x: x["timestamp"]):
            try:
                size = backup["path"].stat().st_size
            except OSError:
                size = 0
            total_size += size
            age_days = (now - backup["timestamp"]).days
            print(
                f"  - {backup['filename']} ({format_size(size)}, {age_days} days old)"
            )

        print(f"\nTotal space to free: {format_size(total_size)}")

        # Defense-in-depth: never empty the directory.
        if apply_deletes and len(to_delete) >= len(backups):
            print(
                "❌ Refusing to delete: would remove all backups "
                f"(len(to_delete)={len(to_delete)} >= len(backups)={len(backups)}). "
                "Check retention settings.",
                file=sys.stderr,
            )
            return 1
        if apply_deletes and (len(backups) - len(to_delete)) < args.min_keep:
            print(
                f"❌ Refusing to delete: would leave {len(backups) - len(to_delete)} "
                f"backup(s), below --min-keep {args.min_keep}.",
                file=sys.stderr,
            )
            return 1

        if apply_deletes:
            errors = 0
            for backup in to_delete:
                try:
                    backup["path"].unlink()
                    changelog_name = (
                        backup["filename"].removesuffix(".tar.gz") + ".changelog"
                    )
                    changelog_path = BACKUP_DIR / changelog_name
                    if changelog_path.exists():
                        changelog_path.unlink()
                    print(f"Deleted: {backup['filename']}")
                except OSError as e:
                    print(f"Error deleting {backup['filename']}: {e}", file=sys.stderr)
                    errors += 1

            if errors:
                print(
                    f"\n✗ Deleted {len(to_delete) - errors}, failed {errors}",
                    file=sys.stderr,
                )
                clean_orphaned_changelogs(dry_run=not apply_deletes)
                return 1

            print(f"\n✓ Successfully deleted {len(to_delete)} backup(s)")
    else:
        print("\n✓ No backups need to be deleted")

    if to_keep:
        print("\nRetained backups:", file=sys.stderr)
        for backup in sorted(to_keep, key=lambda x: x["timestamp"], reverse=True):
            age_days = (now - backup["timestamp"]).days
            try:
                size = backup["path"].stat().st_size
            except OSError:
                size = 0
            if age_days == 0:
                age_str = "today"
            elif age_days == 1:
                age_str = "yesterday"
            else:
                age_str = f"{age_days} days ago"
            print(
                f"  - {backup['filename']} ({format_size(size)}, {age_str})",
                file=sys.stderr,
            )

    clean_orphaned_changelogs(dry_run=not apply_deletes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
