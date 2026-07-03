"""Tests for tools/prune_backups.py - backup retention management."""

from datetime import datetime, timedelta
from unittest.mock import patch

from tools.prune_backups import (
    apply_retention,
    clean_orphaned_changelogs,
    format_size,
    group_by_retention_period,
    parse_backup_filename,
)


class TestParseBackupFilename:
    def test_parsed_timestamp_is_timezone_aware(self):
        result = parse_backup_filename("ha_config_20260205_204808.tar.gz")
        assert result is not None
        assert result.tzinfo is not None

    def test_valid_filename(self):
        result = parse_backup_filename("ha_config_20260205_204808.tar.gz")
        assert result is not None
        assert result.year == 2026
        assert result.month == 2
        assert result.day == 5
        assert result.hour == 20
        assert result.minute == 48
        assert result.second == 8

    def test_invalid_filename(self):
        assert parse_backup_filename("not_a_backup.tar.gz") is None

    def test_invalid_date(self):
        assert parse_backup_filename("ha_config_99991399_999999.tar.gz") is None

    def test_no_match(self):
        assert parse_backup_filename("random_file.txt") is None


class TestGetBackups:
    def test_get_backups_with_files(self, tmp_path):
        # Create fake backup files
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        (backup_dir / "ha_config_20260201_120000.tar.gz").write_text("data1")
        (backup_dir / "ha_config_20260202_120000.tar.gz").write_text("data2")
        (backup_dir / "not_a_backup.txt").write_text("skip")

        with patch("tools.prune_backups.BACKUP_DIR", backup_dir):
            from tools.prune_backups import get_backups

            backups = get_backups()
            assert len(backups) == 2
            # Should be sorted oldest first
            assert backups[0]["filename"] == "ha_config_20260201_120000.tar.gz"
            assert backups[1]["filename"] == "ha_config_20260202_120000.tar.gz"

    def test_get_backups_empty_dir(self, tmp_path):
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()

        with patch("tools.prune_backups.BACKUP_DIR", backup_dir):
            from tools.prune_backups import get_backups

            assert get_backups() == []

    def test_get_backups_nonexistent_dir(self, tmp_path):
        with patch("tools.prune_backups.BACKUP_DIR", tmp_path / "nonexistent"):
            from tools.prune_backups import get_backups

            assert get_backups() == []


class TestGroupByRetentionPeriod:
    def test_recent_backups_keep_all(self):
        now = datetime(2026, 2, 12, 12, 0, 0)
        backups = [
            {"timestamp": now - timedelta(days=1), "filename": "b1"},
            {"timestamp": now - timedelta(days=3), "filename": "b2"},
            {"timestamp": now - timedelta(days=6), "filename": "b3"},
        ]
        groups = group_by_retention_period(backups, now)
        assert len(groups["keep_all"]) == 3
        assert len(groups["daily"]) == 0
        assert len(groups["weekly"]) == 0

    def test_daily_grouping(self):
        now = datetime(2026, 2, 12, 12, 0, 0)
        backups = [
            {"timestamp": now - timedelta(days=10), "filename": "b1"},
            {"timestamp": now - timedelta(days=10, hours=6), "filename": "b2"},
            {"timestamp": now - timedelta(days=15), "filename": "b3"},
        ]
        groups = group_by_retention_period(backups, now)
        assert len(groups["keep_all"]) == 0
        assert len(groups["daily"]) == 2  # two different days
        assert len(groups["weekly"]) == 0

    def test_weekly_grouping(self):
        now = datetime(2026, 2, 12, 12, 0, 0)
        backups = [
            {"timestamp": now - timedelta(days=40), "filename": "b1"},
            {"timestamp": now - timedelta(days=50), "filename": "b2"},
        ]
        groups = group_by_retention_period(backups, now)
        assert len(groups["keep_all"]) == 0
        assert len(groups["daily"]) == 0
        assert len(groups["weekly"]) > 0

    def test_mixed_periods(self):
        now = datetime(2026, 2, 12, 12, 0, 0)
        backups = [
            {"timestamp": now - timedelta(days=1), "filename": "recent"},
            {"timestamp": now - timedelta(days=15), "filename": "daily"},
            {"timestamp": now - timedelta(days=45), "filename": "weekly"},
        ]
        groups = group_by_retention_period(backups, now)
        assert len(groups["keep_all"]) == 1
        assert sum(len(v) for v in groups["daily"].values()) == 1
        assert sum(len(v) for v in groups["weekly"].values()) == 1

    def test_year_boundary_same_iso_week(self):
        """Dec 29 2025 and Jan 2 2026 are ISO week 2026-W01 — must group together."""
        now = datetime(2026, 2, 12, 12, 0, 0)
        backups = [
            {"timestamp": datetime(2025, 12, 29, 10, 0), "filename": "dec29"},
            {"timestamp": datetime(2026, 1, 2, 10, 0), "filename": "jan02"},
        ]
        groups = group_by_retention_period(backups, now)
        # Both should land in the same weekly group
        assert len(groups["weekly"]) == 1
        week_key = list(groups["weekly"].keys())[0]
        assert len(groups["weekly"][week_key]) == 2

    def test_jan1_not_week_zero(self):
        """Jan 1 2026 should not produce a W00 group — ISO weeks are 01-53."""
        now = datetime(2026, 2, 12, 12, 0, 0)
        backups = [
            {"timestamp": datetime(2026, 1, 1, 10, 0), "filename": "jan01"},
        ]
        groups = group_by_retention_period(backups, now)
        for week_key in groups["weekly"]:
            assert "W00" not in week_key

    def test_exactly_7_days_old_is_keep_all(self):
        """A backup exactly 7 days old should be in keep_all, not daily."""
        now = datetime(2026, 2, 12, 12, 0, 0)
        backups = [
            {"timestamp": now - timedelta(days=7), "filename": "b_7d"},
        ]
        groups = group_by_retention_period(backups, now)
        assert len(groups["keep_all"]) == 1
        assert sum(len(v) for v in groups["daily"].values()) == 0

    def test_8_days_old_is_daily(self):
        """A backup 8 days old should be in daily, not keep_all."""
        now = datetime(2026, 2, 12, 12, 0, 0)
        backups = [
            {"timestamp": now - timedelta(days=8), "filename": "b_8d"},
        ]
        groups = group_by_retention_period(backups, now)
        assert len(groups["keep_all"]) == 0
        assert sum(len(v) for v in groups["daily"].values()) == 1

    def test_exactly_30_days_old_is_daily(self):
        """A backup exactly 30 days old should be in daily, not weekly."""
        now = datetime(2026, 2, 12, 12, 0, 0)
        backups = [
            {"timestamp": now - timedelta(days=30), "filename": "b_30d"},
        ]
        groups = group_by_retention_period(backups, now)
        assert sum(len(v) for v in groups["daily"].values()) == 1
        assert sum(len(v) for v in groups["weekly"].values()) == 0

    def test_31_days_old_is_weekly(self):
        """A backup 31 days old should be in weekly, not daily."""
        now = datetime(2026, 2, 12, 12, 0, 0)
        backups = [
            {"timestamp": now - timedelta(days=31), "filename": "b_31d"},
        ]
        groups = group_by_retention_period(backups, now)
        assert sum(len(v) for v in groups["daily"].values()) == 0
        assert sum(len(v) for v in groups["weekly"].values()) == 1


class TestApplyRetention:
    def test_keep_all_recent(self):
        groups = {
            "keep_all": [{"filename": "b1"}, {"filename": "b2"}],
            "daily": {},
            "weekly": {},
        }
        to_keep, to_delete = apply_retention(groups)
        assert len(to_keep) == 2
        assert len(to_delete) == 0

    def test_daily_keeps_latest(self):
        groups = {
            "keep_all": [],
            "daily": {
                "2026-02-01": [
                    {"filename": "b1", "timestamp": datetime(2026, 2, 1, 10, 0)},
                    {"filename": "b2", "timestamp": datetime(2026, 2, 1, 20, 0)},
                ]
            },
            "weekly": {},
        }
        to_keep, to_delete = apply_retention(groups)
        assert len(to_keep) == 1
        assert to_keep[0]["filename"] == "b2"  # Latest
        assert len(to_delete) == 1
        assert to_delete[0]["filename"] == "b1"

    def test_weekly_keeps_latest(self):
        groups = {
            "keep_all": [],
            "daily": {},
            "weekly": {
                "2026-W01": [
                    {"filename": "b1", "timestamp": datetime(2026, 1, 5, 10, 0)},
                    {"filename": "b2", "timestamp": datetime(2026, 1, 7, 20, 0)},
                ]
            },
        }
        to_keep, to_delete = apply_retention(groups)
        assert len(to_keep) == 1
        assert to_keep[0]["filename"] == "b2"
        assert len(to_delete) == 1

    def test_year_boundary_weekly_prunes_correctly(self):
        """Two backups in same ISO week across year boundary — keep only latest."""
        groups = {
            "keep_all": [],
            "daily": {},
            "weekly": {
                "2026-W01": [
                    {
                        "filename": "dec29",
                        "timestamp": datetime(2025, 12, 29, 10, 0),
                    },
                    {
                        "filename": "jan02",
                        "timestamp": datetime(2026, 1, 2, 10, 0),
                    },
                ]
            },
        }
        to_keep, to_delete = apply_retention(groups)
        assert len(to_keep) == 1
        assert to_keep[0]["filename"] == "jan02"
        assert len(to_delete) == 1
        assert to_delete[0]["filename"] == "dec29"


class TestCleanOrphanedChangelogs:
    def test_removes_orphaned_changelogs(self, tmp_path):
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        # Create a changelog with no matching tar.gz
        orphan = backup_dir / "ha_config_20260101_120000.changelog"
        orphan.write_text("orphan")
        # Create a matched pair (should survive)
        (backup_dir / "ha_config_20260201_120000.tar.gz").write_bytes(b"data")
        (backup_dir / "ha_config_20260201_120000.changelog").write_text("matched")

        with patch("tools.prune_backups.BACKUP_DIR", backup_dir):
            count = clean_orphaned_changelogs()
            assert count == 1
            assert not orphan.exists()
            assert (backup_dir / "ha_config_20260201_120000.changelog").exists()

    def test_no_orphans(self, tmp_path):
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        (backup_dir / "ha_config_20260201_120000.tar.gz").write_bytes(b"data")
        (backup_dir / "ha_config_20260201_120000.changelog").write_text("matched")

        with patch("tools.prune_backups.BACKUP_DIR", backup_dir):
            assert clean_orphaned_changelogs() == 0

    def test_nonexistent_dir(self, tmp_path):
        with patch("tools.prune_backups.BACKUP_DIR", tmp_path / "nonexistent"):
            assert clean_orphaned_changelogs() == 0

    def test_dry_run_does_not_delete(self, tmp_path):
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        orphan = backup_dir / "ha_config_20260101_120000.changelog"
        orphan.write_text("orphan")

        with patch("tools.prune_backups.BACKUP_DIR", backup_dir):
            count = clean_orphaned_changelogs(dry_run=True)
            assert count == 1
            assert orphan.exists()  # Not deleted


class TestFormatSize:
    def test_bytes(self):
        assert format_size(500) == "500.0B"

    def test_kilobytes(self):
        assert format_size(1536) == "1.5KB"

    def test_megabytes(self):
        assert format_size(2 * 1024 * 1024) == "2.0MB"

    def test_gigabytes(self):
        assert format_size(3 * 1024**3) == "3.0GB"

    def test_terabytes(self):
        assert format_size(1.5 * 1024**4) == "1.5TB"


class TestMain:
    def test_no_backups(self, tmp_path, capsys):
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        with patch("tools.prune_backups.BACKUP_DIR", backup_dir):
            from tools.prune_backups import main

            result = main([])
            assert result == 0
            captured = capsys.readouterr()
            assert "No backups found" in captured.err

    def test_with_recent_backups(self, tmp_path, capsys):
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        # Create a recent backup (today)
        now = datetime.now()
        fname = f"ha_config_{now.strftime('%Y%m%d_%H%M%S')}.tar.gz"
        (backup_dir / fname).write_bytes(b"x" * 1024)

        with patch("tools.prune_backups.BACKUP_DIR", backup_dir):
            from tools.prune_backups import main

            result = main([])
            assert result == 0
            captured = capsys.readouterr()
            assert "No backups need to be deleted" in captured.out

    def test_yesterday_backup(self, tmp_path, capsys):
        """Cover 'yesterday' age string."""
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        yesterday = datetime.now() - timedelta(days=1)
        fname = f"ha_config_{yesterday.strftime('%Y%m%d_%H%M%S')}.tar.gz"
        (backup_dir / fname).write_bytes(b"x" * 1024)

        with patch("tools.prune_backups.BACKUP_DIR", backup_dir):
            from tools.prune_backups import main

            result = main([])
            assert result == 0
            captured = capsys.readouterr()
            assert "yesterday" in captured.err

    def test_deletes_old_daily_duplicates(self, tmp_path, capsys):
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()

        # Create two backups on the same day, 15 days ago
        old_date = datetime.now() - timedelta(days=15)
        date_str = old_date.strftime("%Y%m%d")
        fname1 = f"ha_config_{date_str}_100000.tar.gz"
        fname2 = f"ha_config_{date_str}_200000.tar.gz"
        (backup_dir / fname1).write_bytes(b"x" * 512)
        (backup_dir / fname2).write_bytes(b"x" * 512)
        # Also add a changelog for the first one
        (backup_dir / fname1.replace(".tar.gz", ".changelog")).write_text("old")

        with patch("tools.prune_backups.BACKUP_DIR", backup_dir):
            from tools.prune_backups import main

            result = main([])
            assert result == 0
            # Should keep the later one (200000) and delete earlier (100000)
            assert (backup_dir / fname2).exists()
            assert not (backup_dir / fname1).exists()
            # Changelog for deleted backup should also be gone
            assert not (backup_dir / fname1.replace(".tar.gz", ".changelog")).exists()

    def test_kept_backup_changelog_preserved(self, tmp_path, capsys):
        """Changelog for a kept backup must not be deleted."""
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()

        old_date = datetime.now() - timedelta(days=15)
        date_str = old_date.strftime("%Y%m%d")
        fname1 = f"ha_config_{date_str}_100000.tar.gz"
        fname2 = f"ha_config_{date_str}_200000.tar.gz"
        (backup_dir / fname1).write_bytes(b"x" * 512)
        (backup_dir / fname2).write_bytes(b"x" * 512)
        # Changelogs for both
        (backup_dir / fname1.replace(".tar.gz", ".changelog")).write_text("old")
        (backup_dir / fname2.replace(".tar.gz", ".changelog")).write_text("kept")

        with patch("tools.prune_backups.BACKUP_DIR", backup_dir):
            from tools.prune_backups import main

            main([])
            # Kept backup's changelog survives
            assert (backup_dir / fname2.replace(".tar.gz", ".changelog")).exists()

    def test_weekly_pruning_end_to_end(self, tmp_path, capsys):
        """Two backups in the same week, 35+ days old — only latest survives."""
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()

        # Pick a Monday 40 days ago and the following Wednesday
        base = datetime.now() - timedelta(days=40)
        # Align to Monday
        base = base - timedelta(days=base.weekday())
        d1 = base
        d2 = base + timedelta(days=2)  # Wednesday, same ISO week

        fname1 = f"ha_config_{d1.strftime('%Y%m%d')}_100000.tar.gz"
        fname2 = f"ha_config_{d2.strftime('%Y%m%d')}_100000.tar.gz"
        (backup_dir / fname1).write_bytes(b"x" * 512)
        (backup_dir / fname2).write_bytes(b"x" * 512)

        with patch("tools.prune_backups.BACKUP_DIR", backup_dir):
            from tools.prune_backups import main

            result = main([])
            assert result == 0
            # Wednesday (later) kept, Monday (earlier) deleted
            assert (backup_dir / fname2).exists()
            assert not (backup_dir / fname1).exists()

    def test_dry_run_does_not_delete(self, tmp_path, capsys):
        """--dry-run should report but not delete anything."""
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()

        old_date = datetime.now() - timedelta(days=15)
        date_str = old_date.strftime("%Y%m%d")
        fname1 = f"ha_config_{date_str}_100000.tar.gz"
        fname2 = f"ha_config_{date_str}_200000.tar.gz"
        (backup_dir / fname1).write_bytes(b"x" * 512)
        (backup_dir / fname2).write_bytes(b"x" * 512)

        with patch("tools.prune_backups.BACKUP_DIR", backup_dir):
            from tools.prune_backups import main

            result = main(["--dry-run"])
            assert result == 0
            # Both files should still exist
            assert (backup_dir / fname1).exists()
            assert (backup_dir / fname2).exists()
            captured = capsys.readouterr()
            assert "DRY RUN" in captured.err

    def test_orphaned_changelogs_cleaned_during_main(self, tmp_path, capsys):
        """main() should clean orphaned changelogs after pruning."""
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()

        # Recent backup (won't be pruned)
        now = datetime.now()
        fname = f"ha_config_{now.strftime('%Y%m%d_%H%M%S')}.tar.gz"
        (backup_dir / fname).write_bytes(b"x" * 1024)

        # Orphaned changelog (no matching tar.gz)
        orphan = backup_dir / "ha_config_20250101_120000.changelog"
        orphan.write_text("orphan")

        with patch("tools.prune_backups.BACKUP_DIR", backup_dir):
            from tools.prune_backups import main

            main([])
            assert not orphan.exists()

    def test_delete_error_returns_nonzero(self, tmp_path, capsys):
        """If a file can't be deleted, main() should return 1."""
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()

        old_date = datetime.now() - timedelta(days=15)
        date_str = old_date.strftime("%Y%m%d")
        fname1 = f"ha_config_{date_str}_100000.tar.gz"
        fname2 = f"ha_config_{date_str}_200000.tar.gz"
        (backup_dir / fname1).write_bytes(b"x" * 512)
        (backup_dir / fname2).write_bytes(b"x" * 512)

        # Make fname1 undeletable by removing write permission on the directory
        # This is platform-specific but works on Linux
        import os
        import stat

        with patch("tools.prune_backups.BACKUP_DIR", backup_dir):
            from tools.prune_backups import main

            # Remove write permission from dir to prevent unlink
            orig_mode = backup_dir.stat().st_mode
            try:
                os.chmod(backup_dir, stat.S_IRUSR | stat.S_IXUSR)
                result = main([])
                assert result == 1
                captured = capsys.readouterr()
                assert "Error deleting" in captured.err
            finally:
                os.chmod(backup_dir, orig_mode)
