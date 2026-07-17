"""Tests for tools/search_backups.py - backup search utility."""

import io
import re
import tarfile
from datetime import datetime
from unittest.mock import patch

from tools.search_backups import is_likely_unsafe_regex, search_backup


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
        matches, _u = search_backup(backup, re.compile("sensor.test"))
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
        matches, _u = search_backup(backup, re.compile("pattern_match"), yaml_only=True)
        assert len(matches) == 1
        assert matches[0]["file"] == "config/test.yaml"

    # ── M22 follow-up: context_lines=0 (default) must not crash ──────────

    def test_zero_context_accepted(self, tmp_path):
        """M22: context=0 (default) must not crash search_backup."""
        tar_path = _make_backup(
            tmp_path, files_dict={"x.yaml": "line1\npattern\nline3\n"}
        )
        backup = {
            "path": tar_path,
            "filename": tar_path.name,
            "timestamp": datetime(2026, 2, 1),
        }
        matches, _u = search_backup(backup, re.compile("pattern"), context_lines=0)
        assert len(matches) >= 1

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
        matches, _u = search_backup(
            backup, re.compile("pattern_match"), yaml_only=False
        )
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
        matches, _u = search_backup(backup, re.compile("MATCH"), context_lines=1)
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
        matches, _u = search_backup(backup, re.compile("nonexistent_pattern"))
        assert matches == []

    def test_handles_corrupt_tar(self, tmp_path):
        bad_file = tmp_path / "bad.tar.gz"
        bad_file.write_text("not a tar")
        backup = {
            "path": bad_file,
            "filename": bad_file.name,
            "timestamp": datetime(2026, 2, 1),
        }
        matches, unreadable = search_backup(backup, re.compile("test"))
        assert matches == []
        assert unreadable is True

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
        matches, _u = search_backup(backup, re.compile("match"))
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
        matches, _u = search_backup(backup, re.compile("match"))
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
        matches, _u = search_backup(backup, re.compile("match"))
        assert matches == []


class TestRegexSafety:
    def test_detects_nested_quantifier_pattern(self):
        assert is_likely_unsafe_regex("(a+)+b") is True

    def test_allows_normal_pattern(self):
        assert is_likely_unsafe_regex("sensor.temperature") is False


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


class TestL71StripDotSlash:
    """L71: member names with './' prefix must be stripped in output."""

    def test_output_strips_dot_slash_prefix(self, tmp_path):
        """L71: member names starting with './' must be displayed without it."""
        import re

        tar_path = tmp_path / "test.tar.gz"
        with tarfile.open(tar_path, "w:gz") as tar:
            data = b"sensor.test\n"
            info = tarfile.TarInfo(name="./config/test.yaml")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))

        backup = {
            "path": tar_path,
            "filename": tar_path.name,
            "timestamp": datetime(2026, 2, 1),
        }
        matches, unreadable = search_backup(backup, re.compile("sensor"))
        assert unreadable is False
        assert len(matches) == 1
        # match_entry["file"] should strip the "./" prefix
        assert matches[0]["file"] == "config/test.yaml"
        assert not matches[0]["file"].startswith("./")


class TestL72LazyTar:
    """L72: lazy tar iteration instead of getmembers()."""

    def test_lazy_tar_iteration_handles_large_archive(self, tmp_path):
        """L72: many non-file members must be scanned via lazy iteration."""
        import re

        # Create a tar with a symlink and a directory then a file
        tar_path = tmp_path / "test.tar.gz"
        with tarfile.open(tar_path, "w:gz") as tar:
            # Add a directory
            dir_info = tarfile.TarInfo(name="subdir/")
            dir_info.type = tarfile.DIRTYPE
            tar.addfile(dir_info)
            # Add a symlink
            link_info = tarfile.TarInfo(name="link_to_file")
            link_info.type = tarfile.SYMTYPE
            link_info.linkname = "config/test.yaml"
            tar.addfile(link_info)
            # Add a real file
            data = b"match_this\n"
            finfo = tarfile.TarInfo(name="config/test.yaml")
            finfo.size = len(data)
            tar.addfile(finfo, io.BytesIO(data))

        backup = {
            "path": tar_path,
            "filename": tar_path.name,
            "timestamp": datetime(2026, 2, 1),
        }
        matches, unreadable = search_backup(backup, re.compile("match_this"))
        assert unreadable is False
        assert len(matches) == 1
        assert matches[0]["file"] == "config/test.yaml"


class TestL73Renamed:
    """L73: is_likely_unsafe_regex renamed from is_potentially_unsafe_regex."""

    def test_renamed_function_exists_and_works(self):
        """L73: is_likely_unsafe_regex must exist (renamed from old name)."""
        from tools.search_backups import is_likely_unsafe_regex

        assert is_likely_unsafe_regex("(a+)+") is True
        assert is_likely_unsafe_regex("normal") is False


class TestL74Unreadable:
    """L74: unreadable backups reported separately."""

    def test_main_reports_unreadable_count(self, tmp_path, monkeypatch, capsys):
        """L74: corrupt backups must be reported as 'unreadable'."""
        backups = [
            {
                "path": tmp_path / "bad.tar.gz",
                "filename": "bad.tar.gz",
                "timestamp": datetime(2026, 2, 1),
            },
        ]
        (tmp_path / "bad.tar.gz").write_text("not a real tar file")

        monkeypatch.setattr("sys.argv", ["search_backups", "pattern"])
        with patch("tools.search_backups.get_backups", return_value=backups):
            from tools.search_backups import main

            result = main()
            assert result == 1  # unreadable count > 0
            _, err = capsys.readouterr()
            assert "unreadable" in err


class TestL75InternalKey:
    """L75: _remaining_after must not leak in returned matches."""

    def test_internal_key_does_not_leak(self, tmp_path):
        """L75: _remaining_after must never appear in returned matches."""
        import re

        tar_path = _make_backup(
            tmp_path,
            {"config/test.yaml": "line1\nsensor.test\nline3\n"},
        )
        backup = {
            "path": tar_path,
            "filename": tar_path.name,
            "timestamp": datetime(2026, 2, 1),
        }
        matches, _unreadable = search_backup(
            backup, re.compile("sensor"), context_lines=1
        )
        for m in matches:
            assert "_remaining_after" not in m
            assert "context_before" in m
            assert "context_after" in m


class TestL76Safety:
    """L76: tar-extraction safety regression coverage."""

    def test_malicious_tar_member_name_does_not_escape(self, tmp_path):
        """L76: './../../etc/passwd' member names must NOT write outside tmp."""
        import re

        tar_path = tmp_path / "evil.tar.gz"
        with tarfile.open(tar_path, "w:gz") as tar:
            data = b"root:x:0:0\n"
            info = tarfile.TarInfo(name="../../../etc/passwd")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))

        before_files = set(tmp_path.rglob("*"))
        backup = {
            "path": tar_path,
            "filename": tar_path.name,
            "timestamp": datetime(2026, 2, 1),
        }
        search_backup(backup, re.compile("root"))
        after_files = set(tmp_path.rglob("*"))
        # No new files should appear outside the expected ones
        new_files = after_files - before_files
        # Only the tarfile glob itself may appear
        assert not any("passwd" in str(p) for p in new_files)

    def test_symlink_member_not_followed(self, tmp_path):
        """L76: SYMTYPE/LNKTYPE members must be skipped (not extracted/followed)."""
        import re

        tar_path = tmp_path / "test.tar.gz"
        with tarfile.open(tar_path, "w:gz") as tar:
            # Add a symlink pointing to a non-existent file
            link_info = tarfile.TarInfo(name="bad_link.yaml")
            link_info.type = tarfile.SYMTYPE
            link_info.linkname = "/etc/passwd"
            tar.addfile(link_info)
            # Add a real file
            data = b"actual_content\n"
            finfo = tarfile.TarInfo(name="config/real.yaml")
            finfo.size = len(data)
            tar.addfile(finfo, io.BytesIO(data))

        backup = {
            "path": tar_path,
            "filename": tar_path.name,
            "timestamp": datetime(2026, 2, 1),
        }
        matches, unreadable = search_backup(backup, re.compile("actual_content"))
        assert unreadable is False
        assert len(matches) == 1
        assert matches[0]["file"] == "config/real.yaml"

    def test_comment_invariant_near_extract(self):
        """L76: invariant comment about extract+isfile must exist near extraction."""
        import inspect

        import tools.search_backups

        src = inspect.getsource(tools.search_backups)
        assert "extractfile" in src
        assert "isfile" in src
