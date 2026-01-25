#!/usr/bin/env python3
"""
Prune Home Assistant configuration backups with smart retention.

Retention rules:
- Keep all backups from last 7 days
- Keep one backup per day for backups 7-30 days old (latest each day)
- Keep one backup per week for backups older than 30 days (latest each week)
"""

import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

BACKUP_DIR = Path(__file__).parent.parent / "backups"
BACKUP_PATTERN = re.compile(r"ha_config_(\d{8})_(\d{6})\.tar\.gz")


def parse_backup_filename(filename):
    """Parse backup filename and return datetime object."""
    match = BACKUP_PATTERN.match(filename)
    if not match:
        return None

    date_str = match.group(1)  # YYYYMMDD
    time_str = match.group(2)  # HHMMSS

    try:
        return datetime.strptime(f"{date_str}_{time_str}", "%Y%m%d_%H%M%S")
    except ValueError:
        return None


def get_backups():
    """Get all backup files with their timestamps."""
    if not BACKUP_DIR.exists():
        return []

    backups = []
    for file in BACKUP_DIR.glob("*.tar.gz"):
        timestamp = parse_backup_filename(file.name)
        if timestamp:
            backups.append({
                'path': file,
                'filename': file.name,
                'timestamp': timestamp
            })

    return sorted(backups, key=lambda x: x['timestamp'])


def group_by_retention_period(backups, now):
    """Group backups into retention periods."""
    groups = {
        'keep_all': [],      # Last 7 days
        'daily': defaultdict(list),     # 7-30 days, one per day
        'weekly': defaultdict(list),    # 30+ days, one per week
    }

    for backup in backups:
        age = now - backup['timestamp']

        if age.days < 7:
            # Keep all from last 7 days
            groups['keep_all'].append(backup)
        elif age.days < 30:
            # Group by day (YYYY-MM-DD)
            day_key = backup['timestamp'].strftime("%Y-%m-%d")
            groups['daily'][day_key].append(backup)
        else:
            # Group by week (YYYY-WW where WW is ISO week number)
            week_key = backup['timestamp'].strftime("%Y-W%W")
            groups['weekly'][week_key].append(backup)

    return groups


def apply_retention(groups):
    """Apply retention rules and return lists of files to keep/delete."""
    to_keep = []
    to_delete = []

    # Keep all recent backups (0-7 days)
    to_keep.extend(groups['keep_all'])

    # Keep one per day (7-30 days) - latest from each day
    for day_backups in groups['daily'].values():
        if day_backups:
            # Sort by timestamp, keep latest
            sorted_backups = sorted(day_backups, key=lambda x: x['timestamp'], reverse=True)
            to_keep.append(sorted_backups[0])
            to_delete.extend(sorted_backups[1:])

    # Keep one per week (30+ days) - latest from each week
    for week_backups in groups['weekly'].values():
        if week_backups:
            # Sort by timestamp, keep latest
            sorted_backups = sorted(week_backups, key=lambda x: x['timestamp'], reverse=True)
            to_keep.append(sorted_backups[0])
            to_delete.extend(sorted_backups[1:])

    return to_keep, to_delete


def format_size(bytes):
    """Format bytes as human-readable size."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes < 1024.0:
            return f"{bytes:.1f}{unit}"
        bytes /= 1024.0
    return f"{bytes:.1f}TB"


def main():
    print("Home Assistant Backup Retention Pruner")
    print("=" * 50)

    backups = get_backups()

    if not backups:
        print(f"No backups found in {BACKUP_DIR}")
        return

    print(f"\nFound {len(backups)} backup(s)")

    now = datetime.now()
    groups = group_by_retention_period(backups, now)
    to_keep, to_delete = apply_retention(groups)

    print(f"\nRetention Summary:")
    print(f"  - Keeping {len(to_keep)} backup(s)")
    print(f"  - Deleting {len(to_delete)} backup(s)")

    if to_delete:
        print(f"\nBackups to delete:")
        total_size = 0
        for backup in sorted(to_delete, key=lambda x: x['timestamp']):
            size = backup['path'].stat().st_size
            total_size += size
            age_days = (now - backup['timestamp']).days
            print(f"  - {backup['filename']} ({format_size(size)}, {age_days} days old)")

        print(f"\nTotal space to free: {format_size(total_size)}")

        # Delete files
        for backup in to_delete:
            backup['path'].unlink()
            print(f"Deleted: {backup['filename']}")

        print(f"\n✓ Successfully deleted {len(to_delete)} backup(s)")
    else:
        print("\n✓ No backups need to be deleted")

    if to_keep:
        print(f"\nRetained backups:")
        for backup in sorted(to_keep, key=lambda x: x['timestamp'], reverse=True):
            age_days = (now - backup['timestamp']).days
            size = backup['path'].stat().st_size
            if age_days == 0:
                age_str = "today"
            elif age_days == 1:
                age_str = "yesterday"
            else:
                age_str = f"{age_days} days ago"
            print(f"  - {backup['filename']} ({format_size(size)}, {age_str})")


if __name__ == "__main__":
    main()
