#!/usr/bin/env python3
"""
Prune Home Assistant configuration backups with smart retention.

Retention rules:
- Keep all backups from last 7 days
- Keep one backup per day for backups 7-30 days old (latest each day)
- Keep one backup per week for backups older than 30 days (latest each week)
"""

import argparse
import contextlib
import sys
from collections import defaultdict
from collections.abc import Mapping
from datetime import datetime
from typing import Any, TypedDict

from tools.backup_common import BACKUP_DIR, changelog_path_for, get_backups


class RetentionGroups(TypedDict):
    """Backups grouped according to the retention policy."""

    keep_all: list[dict[str, Any]]
    daily: defaultdict[str, list[dict[str, Any]]]
    weekly: defaultdict[str, list[dict[str, Any]]]


def group_by_retention_period(
    backups: list[dict[str, Any]], now: datetime
) -> RetentionGroups:
    """Group backups into retention periods."""
    groups: RetentionGroups = {
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


def _keep_latest_per_group(
    grouped: Mapping[str, list[dict[str, Any]]],
    to_keep: list[dict[str, Any]],
    to_delete: list[dict[str, Any]],
) -> None:
    """Keep the latest entry from each group; rest go to delete list."""
    for items in grouped.values():
        if not items:
            continue
        ordered = sorted(items, key=lambda x: x["timestamp"], reverse=True)
        to_keep.append(ordered[0])
        to_delete.extend(ordered[1:])


def apply_retention(
    groups: RetentionGroups,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Apply retention rules and return lists of files to keep/delete."""
    to_keep: list[dict[str, Any]] = []
    to_delete: list[dict[str, Any]] = []

    # Keep all recent backups (0-7 days)
    to_keep.extend(groups["keep_all"])

    # Keep one per day (7-30 days), one per week (30+ days)
    _keep_latest_per_group(groups["daily"], to_keep, to_delete)
    _keep_latest_per_group(groups["weekly"], to_keep, to_delete)

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
                try:
                    orphan.unlink()
                except OSError as e:
                    print(
                        f"⚠️ failed to delete orphaned changelog {orphan.name}: {e}",
                        file=sys.stderr,
                    )
                else:
                    print(f"  Deleted: {orphan.name}", file=sys.stderr)
    return len(orphans)


def _format_delete_line(backup: dict, now: datetime) -> str:
    """Format a to-be-deleted backup for display."""
    try:
        size = backup["path"].stat().st_size
    except OSError:
        size = 0
    age_days = (now - backup["timestamp"]).days
    return f"  - {backup['filename']} ({format_size(size)}, {age_days} days old)"


def _format_keep_line(backup: dict, now: datetime) -> str:
    """Format a retained backup for display."""
    try:
        size = backup["path"].stat().st_size
    except OSError:
        size = 0
    age_days = (now - backup["timestamp"]).days
    if age_days == 0:
        age_str = "today"
    elif age_days == 1:
        age_str = "yesterday"
    else:
        age_str = f"{age_days} days ago"
    return f"  - {backup['filename']} ({format_size(size)}, {age_str})"


def _validate_deletion_safety(
    backups: list[dict], to_delete: list[dict], min_keep: int
) -> str | None:
    """Return an error message if the deletion plan is unsafe, else None."""
    if len(to_delete) >= len(backups):
        return (
            "❌ Refusing to delete: would remove all backups "
            f"(len(to_delete)={len(to_delete)} >= len(backups)={len(backups)}). "
            "Check retention settings."
        )
    remaining = len(backups) - len(to_delete)
    if remaining < min_keep:
        return (
            f"❌ Refusing to delete: would leave {remaining} "
            f"backup(s), below --min-keep {min_keep}."
        )
    return None


def _delete_backups(to_delete: list[dict]) -> int:
    """Delete each backup and its changelog sibling; return error count."""
    errors = 0
    for backup in to_delete:
        try:
            backup["path"].unlink()
        except OSError as e:
            print(f"⚠️ failed to delete {backup['filename']}: {e}", file=sys.stderr)
            errors += 1
            continue
        try:
            changelog_path = changelog_path_for(backup)
            if changelog_path.exists():
                changelog_path.unlink()
        except OSError as e:
            print(
                f"⚠️ failed to delete changelog for {backup['filename']}: {e}",
                file=sys.stderr,
            )
            errors += 1
        print(f"Deleted: {backup['filename']}")
    return errors


def _print_retention_summary(to_keep: list[dict], to_delete: list[dict]) -> None:
    """Print the high-level keep/delete counts."""
    print("\nRetention Summary:", file=sys.stderr)
    print(f"  - Keeping {len(to_keep)} backup(s)", file=sys.stderr)
    print(f"  - Deleting {len(to_delete)} backup(s)", file=sys.stderr)


def _print_delete_preview(to_delete: list[dict], now: datetime) -> None:
    """Print the delete preview and total space freed."""
    print("\nBackups to delete:", file=sys.stderr)
    total_size = 0
    for backup in sorted(to_delete, key=lambda x: x["timestamp"]):
        with contextlib.suppress(OSError):
            total_size += backup["path"].stat().st_size
        print(_format_delete_line(backup, now))
    print(f"\nTotal space to free: {format_size(total_size)}")


def _print_keep_summary(to_keep: list[dict], now: datetime) -> None:
    """Print the retained backup summary."""
    print("\nRetained backups:", file=sys.stderr)
    for backup in sorted(to_keep, key=lambda x: x["timestamp"], reverse=True):
        print(_format_keep_line(backup, now), file=sys.stderr)


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
        print("(no backups found — nothing to prune)", file=sys.stderr)
        clean_orphaned_changelogs(dry_run=not apply_deletes)
        return 0

    print(f"\nFound {len(backups)} backup(s)", file=sys.stderr)

    now = datetime.now().astimezone()
    groups = group_by_retention_period(backups, now)
    to_keep, to_delete = apply_retention(groups)

    _print_retention_summary(to_keep, to_delete)

    if to_delete:
        _print_delete_preview(to_delete, now)

        # Defense-in-depth: never empty the directory.
        if apply_deletes:
            safety_error = _validate_deletion_safety(backups, to_delete, args.min_keep)
            if safety_error:
                print(safety_error, file=sys.stderr)
                return 1

        if apply_deletes:
            errors = _delete_backups(to_delete)

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
        _print_keep_summary(to_keep, now)

    clean_orphaned_changelogs(dry_run=not apply_deletes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
