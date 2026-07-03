"""Tests for tools/search_backups.py - backup search utility."""

import io
import re
import tarfile
from datetime import datetime

from tools.search_backups import is_potentially_unsafe_regex, search_backup


def _make_backup(tmp_path, files_dict, name="test.tar.gz"):
    """Create a tar.gz backup with given files."""
    tar_path = tmp_path / name
    with tarfile.open(tar_path, "w:gz") as tar:
        for fname, content in files_dict.items():
            data = content.encode("utf-8")
            info = tarfile.TarInfo(name=fname)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return tar_path


class TestSearchBackup:
    def test_finds_pattern_in_yaml(self, tmp_path):
        tar_path = _make_backup(
            tmp_path,
            {"config/automations.yaml": "- alias: Test\n  entity_id: sensor.test\n"},
        )
        backup = {
            "path": tar_path,
            "filename": tar_path.name,
            "timestamp": datetime(2026, 2, 1),
        }
        matches = search_backup(backup, re.compile("sensor.test"))
        assert len(matches) == 1
        assert matches[0]["file"] == "config/automations.yaml"
        assert matches[0]["line_num"] == 2

    def test_yaml_only_filter(self, tmp_path):
        tar_path = _make_backup(
            tmp_path,
            {
                "config/test.yaml": "pattern_match\n",
                "config/test.sh": "pattern_match\n",
            },
        )
        backup = {
            "path": tar_path,
            "filename": tar_path.name,
            "timestamp": datetime(2026, 2, 1),
        }
        matches = search_backup(backup, re.compile("pattern_match"), yaml_only=True)
        assert len(matches) == 1
        assert matches[0]["file"] == "config/test.yaml"

    def test_all_files_filter(self, tmp_path):
        tar_path = _make_backup(
            tmp_path,
            {
                "config/test.yaml": "pattern_match\n",
                "config/test.sh": "pattern_match\n",
            },
        )
        backup = {
            "path": tar_path,
            "filename": tar_path.name,
            "timestamp": datetime(2026, 2, 1),
        }
        matches = search_backup(backup, re.compile("pattern_match"), yaml_only=False)
        assert len(matches) == 2

    def test_context_lines(self, tmp_path):
        tar_path = _make_backup(
            tmp_path,
            {
                "config/test.yaml": "line1\nline2\nMATCH\nline4\nline5\n",
            },
        )
        backup = {
            "path": tar_path,
            "filename": tar_path.name,
            "timestamp": datetime(2026, 2, 1),
        }
        matches = search_backup(backup, re.compile("MATCH"), context_lines=1)
        assert len(matches) == 1
        assert matches[0]["context_before"] == ["line2"]
        assert matches[0]["context_after"] == ["line4"]

    def test_no_matches(self, tmp_path):
        tar_path = _make_backup(
            tmp_path,
            {"config/test.yaml": "nothing interesting here\n"},
        )
        backup = {
            "path": tar_path,
            "filename": tar_path.name,
            "timestamp": datetime(2026, 2, 1),
        }
        matches = search_backup(backup, re.compile("nonexistent_pattern"))
        assert matches == []

    def test_handles_corrupt_tar(self, tmp_path):
        bad_file = tmp_path / "bad.tar.gz"
        bad_file.write_text("not a tar")
        backup = {
            "path": bad_file,
            "filename": bad_file.name,
            "timestamp": datetime(2026, 2, 1),
        }
        matches = search_backup(backup, re.compile("test"))
        assert matches == []

    def test_multiple_matches_in_file(self, tmp_path):
        tar_path = _make_backup(
            tmp_path,
            {"config/test.yaml": "match1\nno\nmatch2\n"},
        )
        backup = {
            "path": tar_path,
            "filename": tar_path.name,
            "timestamp": datetime(2026, 2, 1),
        }
        matches = search_backup(backup, re.compile("match"))
        assert len(matches) == 2

    def test_skips_non_file_members(self, tmp_path):
        """Directories in tar should be skipped."""
        tar_path = tmp_path / "test.tar.gz"
        with tarfile.open(tar_path, "w:gz") as tar:
            # Add a directory
            info = tarfile.TarInfo(name="config/")
            info.type = tarfile.DIRTYPE
            tar.addfile(info)
            # Add a file
            data = b"match_line\n"
            finfo = tarfile.TarInfo(name="config/test.yaml")
            finfo.size = len(data)
            tar.addfile(finfo, io.BytesIO(data))

        backup = {
            "path": tar_path,
            "filename": tar_path.name,
            "timestamp": datetime(2026, 2, 1),
        }
        matches = search_backup(backup, re.compile("match"))
        assert len(matches) == 1

    def test_skips_binary_files(self, tmp_path):
        """Non-UTF8 files should be skipped without error."""
        tar_path = tmp_path / "test.tar.gz"
        with tarfile.open(tar_path, "w:gz") as tar:
            # Binary content in a yaml file
            data = b"\xff\xfe\x00\x01match\n"
            info = tarfile.TarInfo(name="config/binary.yaml")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))

        backup = {
            "path": tar_path,
            "filename": tar_path.name,
            "timestamp": datetime(2026, 2, 1),
        }
        matches = search_backup(backup, re.compile("match"))
        assert matches == []


class TestRegexSafety:
    def test_detects_nested_quantifier_pattern(self):
        assert is_potentially_unsafe_regex("(a+)+b") is True

    def test_allows_normal_pattern(self):
        assert is_potentially_unsafe_regex("sensor.temperature") is False


class TestSearchBackupsMainFlow:
    """Test the main() function flow with mocked backups."""

    def test_main_no_backups(self, tmp_path, capsys, monkeypatch):
        from unittest.mock import patch

        monkeypatch.setattr("sys.argv", ["search_backups", "pattern"])
        with patch("tools.search_backups.get_backups", return_value=[]):
            from tools.search_backups import main

            result = main()
            assert result == 1

    def test_main_with_matches(self, tmp_path, capsys, monkeypatch):
        from unittest.mock import patch

        tar_path = _make_backup(tmp_path, {"config/test.yaml": "sensor.temperature\n"})
        backups = [
            {
                "path": tar_path,
                "filename": tar_path.name,
                "timestamp": datetime(2026, 2, 1),
            }
        ]
        monkeypatch.setattr("sys.argv", ["search_backups", "sensor"])
        with patch("tools.search_backups.get_backups", return_value=backups):
            from tools.search_backups import main

            result = main()
            assert result == 0
            captured = capsys.readouterr()
            assert "MATCH" in captured.out

    def test_main_files_only(self, tmp_path, capsys, monkeypatch):
        from unittest.mock import patch

        tar_path = _make_backup(tmp_path, {"config/test.yaml": "sensor.test\n"})
        backups = [
            {
                "path": tar_path,
                "filename": tar_path.name,
                "timestamp": datetime(2026, 2, 1),
            }
        ]
        monkeypatch.setattr("sys.argv", ["search_backups", "--files-only", "sensor"])
        with patch("tools.search_backups.get_backups", return_value=backups):
            from tools.search_backups import main

            result = main()
            assert result == 0

    def test_main_with_context(self, tmp_path, capsys, monkeypatch):
        from unittest.mock import patch

        tar_path = _make_backup(
            tmp_path,
            {"config/test.yaml": "before\nsensor.test\nafter\n"},
        )
        backups = [
            {
                "path": tar_path,
                "filename": tar_path.name,
                "timestamp": datetime(2026, 2, 1),
            }
        ]
        monkeypatch.setattr("sys.argv", ["search_backups", "-C", "1", "sensor"])
        with patch("tools.search_backups.get_backups", return_value=backups):
            from tools.search_backups import main

            result = main()
            assert result == 0

    def test_main_no_matches(self, tmp_path, capsys, monkeypatch):
        from unittest.mock import patch

        tar_path = _make_backup(tmp_path, {"config/test.yaml": "nothing here\n"})
        backups = [
            {
                "path": tar_path,
                "filename": tar_path.name,
                "timestamp": datetime(2026, 2, 1),
            }
        ]
        monkeypatch.setattr("sys.argv", ["search_backups", "nonexistent_pattern"])
        with patch("tools.search_backups.get_backups", return_value=backups):
            from tools.search_backups import main

            result = main()
            assert result == 0
            captured = capsys.readouterr()
            assert "Found in 0" in captured.err

    def test_main_all_files(self, tmp_path, capsys, monkeypatch):
        from unittest.mock import patch

        tar_path = _make_backup(
            tmp_path,
            {"config/test.sh": "sensor_match\n"},
        )
        backups = [
            {
                "path": tar_path,
                "filename": tar_path.name,
                "timestamp": datetime(2026, 2, 1),
            }
        ]
        monkeypatch.setattr("sys.argv", ["search_backups", "--all", "sensor_match"])
        with patch("tools.search_backups.get_backups", return_value=backups):
            from tools.search_backups import main

            result = main()
            assert result == 0

    def test_main_invalid_regex(self, capsys, monkeypatch):
        monkeypatch.setattr("sys.argv", ["search_backups", "[invalid"])
        from tools.search_backups import main

        result = main()
        assert result == 1

    def test_main_unsafe_regex(self, capsys, monkeypatch):
        monkeypatch.setattr("sys.argv", ["search_backups", "(a+)+b"])
        from tools.search_backups import main

        result = main()
        assert result == 1
        captured = capsys.readouterr()
        assert "unsafe" in captured.err
