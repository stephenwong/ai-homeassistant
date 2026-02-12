"""Tests for tools/generate_changelog.py - backup changelog generation."""

import io
import tarfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from tools.generate_changelog import (
    changelog_path_for,
    extract_files,
    generate_changelog,
    generate_for_backup,
    should_include,
)


class TestShouldInclude:
    def test_yaml_included(self):
        assert should_include("config/automations.yaml") is True

    def test_yml_included(self):
        assert should_include("config/test.yml") is True

    def test_sh_included(self):
        assert should_include("scripts/debug.sh") is True

    def test_py_included(self):
        assert should_include("tools/test.py") is True

    def test_json_included(self):
        assert should_include("config/data.json") is True

    def test_storage_excluded(self):
        assert should_include("config/.storage/core.entity_registry") is False

    def test_zigbee_state_excluded(self):
        assert should_include("zigbee2mqtt/state.json") is False

    def test_zigbee_log_excluded(self):
        assert should_include("zigbee2mqtt/log/2026-01-01.log") is False

    def test_db_excluded(self):
        assert should_include("config/home-assistant_v2.db") is False

    def test_pycache_excluded(self):
        assert should_include("tools/__pycache__/test.pyc") is False

    def test_pyc_excluded(self):
        assert should_include("tools/test.pyc") is False

    def test_no_extension_included(self):
        # Files with no extension are included (likely config)
        assert should_include("Makefile") is True

    def test_binary_excluded(self):
        assert should_include("image.png") is False


def _make_tar(tmp_path, files_dict):
    """Create a tar.gz archive with given files."""
    tar_path = tmp_path / "test.tar.gz"
    with tarfile.open(tar_path, "w:gz") as tar:
        for name, content in files_dict.items():
            data = content.encode("utf-8")
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return tar_path


class TestExtractFiles:
    def test_extracts_yaml_files(self, tmp_path):
        tar_path = _make_tar(
            tmp_path,
            {"config/automations.yaml": "- alias: Test\n"},
        )
        files = extract_files(tar_path)
        assert "config/automations.yaml" in files
        assert files["config/automations.yaml"] == "- alias: Test\n"

    def test_skips_storage_files(self, tmp_path):
        tar_path = _make_tar(
            tmp_path,
            {
                "config/.storage/core.entity_registry": '{"data": {}}',
                "config/test.yaml": "key: value",
            },
        )
        files = extract_files(tar_path)
        assert "config/.storage/core.entity_registry" not in files
        assert "config/test.yaml" in files

    def test_handles_invalid_tar(self, tmp_path):
        bad_file = tmp_path / "bad.tar.gz"
        bad_file.write_text("not a tar file")
        files = extract_files(bad_file)
        assert files == {}

    def test_skips_non_file_members(self, tmp_path):
        tar_path = tmp_path / "test.tar.gz"
        with tarfile.open(tar_path, "w:gz") as tar:
            # Add directory
            info = tarfile.TarInfo(name="config/")
            info.type = tarfile.DIRTYPE
            tar.addfile(info)
            # Add file
            data = b"key: value\n"
            finfo = tarfile.TarInfo(name="config/test.yaml")
            finfo.size = len(data)
            tar.addfile(finfo, io.BytesIO(data))
        files = extract_files(tar_path)
        assert "config/test.yaml" in files
        assert "config/" not in files

    def test_skips_binary_content(self, tmp_path):
        tar_path = tmp_path / "test.tar.gz"
        with tarfile.open(tar_path, "w:gz") as tar:
            data = b"\xff\xfe\x00\x01"
            info = tarfile.TarInfo(name="config/binary.yaml")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        files = extract_files(tar_path)
        assert "config/binary.yaml" not in files


class TestGenerateChangelog:
    def test_initial_backup(self, tmp_path):
        tar_path = _make_tar(tmp_path, {"config/test.yaml": "key: value\n"})
        backup = {
            "path": tar_path,
            "filename": "ha_config_20260201_120000.tar.gz",
            "timestamp": datetime(2026, 2, 1, 12, 0, 0),
        }
        content = generate_changelog(backup, None)
        assert "Initial backup" in content
        assert "config/test.yaml" in content

    def test_no_changes(self, tmp_path):
        sub1 = tmp_path / "d1"
        sub1.mkdir()
        sub2 = tmp_path / "d2"
        sub2.mkdir()
        tar_path_1 = _make_tar(sub1, {"config/test.yaml": "same"})
        tar_path_2 = _make_tar(sub2, {"config/test.yaml": "same"})

        prev = {
            "path": tar_path_1,
            "filename": "prev.tar.gz",
            "timestamp": datetime(2026, 2, 1, 12, 0, 0),
        }
        curr = {
            "path": tar_path_2,
            "filename": "curr.tar.gz",
            "timestamp": datetime(2026, 2, 2, 12, 0, 0),
        }
        content = generate_changelog(curr, prev)
        assert "No changes detected" in content

    def test_modified_file(self, tmp_path):
        tar_path_1 = tmp_path / "b1.tar.gz"
        tar_path_2 = tmp_path / "b2.tar.gz"

        with tarfile.open(tar_path_1, "w:gz") as tar:
            data = b"old content\n"
            info = tarfile.TarInfo(name="config/test.yaml")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))

        with tarfile.open(tar_path_2, "w:gz") as tar:
            data = b"new content\nmore lines\n"
            info = tarfile.TarInfo(name="config/test.yaml")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))

        prev = {
            "path": tar_path_1,
            "filename": "prev.tar.gz",
            "timestamp": datetime(2026, 2, 1, 12, 0, 0),
        }
        curr = {
            "path": tar_path_2,
            "filename": "curr.tar.gz",
            "timestamp": datetime(2026, 2, 2, 12, 0, 0),
        }
        content = generate_changelog(curr, prev)
        assert "M config/test.yaml" in content

    def test_added_file(self, tmp_path):
        tar_path_1 = tmp_path / "b1.tar.gz"
        tar_path_2 = tmp_path / "b2.tar.gz"

        with tarfile.open(tar_path_1, "w:gz") as tar:
            pass  # empty archive

        with tarfile.open(tar_path_2, "w:gz") as tar:
            data = b"new file\n"
            info = tarfile.TarInfo(name="config/new.yaml")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))

        prev = {
            "path": tar_path_1,
            "filename": "prev.tar.gz",
            "timestamp": datetime(2026, 2, 1, 12, 0, 0),
        }
        curr = {
            "path": tar_path_2,
            "filename": "curr.tar.gz",
            "timestamp": datetime(2026, 2, 2, 12, 0, 0),
        }
        content = generate_changelog(curr, prev)
        assert "A config/new.yaml" in content

    def test_deleted_file(self, tmp_path):
        tar_path_1 = tmp_path / "b1.tar.gz"
        tar_path_2 = tmp_path / "b2.tar.gz"

        with tarfile.open(tar_path_1, "w:gz") as tar:
            data = b"old file\n"
            info = tarfile.TarInfo(name="config/old.yaml")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))

        with tarfile.open(tar_path_2, "w:gz") as tar:
            pass  # empty archive

        prev = {
            "path": tar_path_1,
            "filename": "prev.tar.gz",
            "timestamp": datetime(2026, 2, 1, 12, 0, 0),
        }
        curr = {
            "path": tar_path_2,
            "filename": "curr.tar.gz",
            "timestamp": datetime(2026, 2, 2, 12, 0, 0),
        }
        content = generate_changelog(curr, prev)
        assert "D config/old.yaml" in content


class TestChangelogPathFor:
    def test_generates_changelog_path(self):
        backup = {"filename": "ha_config_20260201_120000.tar.gz"}
        with patch("tools.generate_changelog.BACKUP_DIR", Path("/tmp/backups")):
            result = changelog_path_for(backup)
            assert result == Path("/tmp/backups/ha_config_20260201_120000.changelog")


class TestGenerateForBackup:
    def test_generates_for_single_backup(self, tmp_path):
        tar_path = _make_tar(tmp_path, {"config/test.yaml": "key: value\n"})
        backup = {
            "path": tar_path,
            "filename": "ha_config_20260201_120000.tar.gz",
            "timestamp": datetime(2026, 2, 1, 12, 0, 0),
        }
        backups_list = [backup]

        with patch("tools.generate_changelog.BACKUP_DIR", tmp_path):
            result = generate_for_backup(backup, backups_list)
            assert result.exists()
            content = result.read_text()
            assert "Initial backup" in content

    def test_generates_with_predecessor(self, tmp_path):
        tar1 = _make_tar(tmp_path, {"config/test.yaml": "old\n"})
        # Need a second tar at different path
        sub = tmp_path / "sub"
        sub.mkdir()
        tar2 = _make_tar(sub, {"config/test.yaml": "new\n"})

        prev = {
            "path": tar1,
            "filename": "ha_config_20260201_120000.tar.gz",
            "timestamp": datetime(2026, 2, 1, 12, 0, 0),
        }
        curr = {
            "path": tar2,
            "filename": "ha_config_20260202_120000.tar.gz",
            "timestamp": datetime(2026, 2, 2, 12, 0, 0),
        }
        backups_list = [prev, curr]

        with patch("tools.generate_changelog.BACKUP_DIR", tmp_path):
            result = generate_for_backup(curr, backups_list)
            assert result.exists()
            content = result.read_text()
            assert "Previous:" in content


class TestExtractFilesNoneExtract:
    def test_extractfile_returns_none(self, tmp_path):
        """Cover line 64: f is None case in extract_files."""
        tar_path = tmp_path / "test.tar.gz"
        with tarfile.open(tar_path, "w:gz") as tar:
            # Add a hardlink (extractfile returns None for links)
            data = b"real content\n"
            real_info = tarfile.TarInfo(name="config/real.yaml")
            real_info.size = len(data)
            tar.addfile(real_info, io.BytesIO(data))

            link_info = tarfile.TarInfo(name="config/link.yaml")
            link_info.type = tarfile.LNKTYPE
            link_info.linkname = "config/real.yaml"
            tar.addfile(link_info)

        files = extract_files(tar_path)
        assert "config/real.yaml" in files
        # Link may or may not extract, but should not crash


class TestMain:
    def test_no_backups(self, monkeypatch):
        from tools.generate_changelog import main

        monkeypatch.setattr("sys.argv", ["generate_changelog"])
        with patch("tools.generate_changelog.get_backups", return_value=[]):
            result = main()
            assert result == 1

    def test_generate_all(self, tmp_path, monkeypatch, capsys):
        from tools.generate_changelog import main

        tar1 = _make_tar(tmp_path, {"config/test.yaml": "content1\n"})
        sub = tmp_path / "sub"
        sub.mkdir()
        tar2 = _make_tar(sub, {"config/test.yaml": "content2\n"})

        backups = [
            {
                "path": tar1,
                "filename": "ha_config_20260201_120000.tar.gz",
                "timestamp": datetime(2026, 2, 1, 12, 0, 0),
            },
            {
                "path": tar2,
                "filename": "ha_config_20260202_120000.tar.gz",
                "timestamp": datetime(2026, 2, 2, 12, 0, 0),
            },
        ]

        monkeypatch.setattr("sys.argv", ["generate_changelog", "--generate-all"])
        with (
            patch("tools.generate_changelog.get_backups", return_value=backups),
            patch("tools.generate_changelog.BACKUP_DIR", tmp_path),
        ):
            result = main()
            assert result == 0
            captured = capsys.readouterr()
            assert "Generated 2" in captured.out

    def test_generate_all_skips_existing(self, tmp_path, monkeypatch, capsys):
        from tools.generate_changelog import main

        tar1 = _make_tar(tmp_path, {"config/test.yaml": "content1\n"})
        backups = [
            {
                "path": tar1,
                "filename": "ha_config_20260201_120000.tar.gz",
                "timestamp": datetime(2026, 2, 1, 12, 0, 0),
            },
        ]
        # Pre-create changelog
        (tmp_path / "ha_config_20260201_120000.changelog").write_text("existing")

        monkeypatch.setattr("sys.argv", ["generate_changelog", "--generate-all"])
        with (
            patch("tools.generate_changelog.get_backups", return_value=backups),
            patch("tools.generate_changelog.BACKUP_DIR", tmp_path),
        ):
            result = main()
            assert result == 0
            captured = capsys.readouterr()
            assert "skipped 1" in captured.out

    def test_specific_backup(self, tmp_path, monkeypatch, capsys):
        from tools.generate_changelog import main

        tar1 = _make_tar(tmp_path, {"config/test.yaml": "content\n"})
        backups = [
            {
                "path": tar1,
                "filename": "ha_config_20260201_120000.tar.gz",
                "timestamp": datetime(2026, 2, 1, 12, 0, 0),
            },
        ]

        monkeypatch.setattr(
            "sys.argv",
            ["generate_changelog", "ha_config_20260201_120000.tar.gz"],
        )
        with (
            patch("tools.generate_changelog.get_backups", return_value=backups),
            patch("tools.generate_changelog.BACKUP_DIR", tmp_path),
        ):
            result = main()
            assert result == 0
            captured = capsys.readouterr()
            assert "Changelog written" in captured.out

    def test_backup_not_found(self, tmp_path, monkeypatch, capsys):
        from tools.generate_changelog import main

        backups = [
            {
                "path": tmp_path / "other.tar.gz",
                "filename": "other.tar.gz",
                "timestamp": datetime(2026, 2, 1, 12, 0, 0),
            },
        ]

        monkeypatch.setattr(
            "sys.argv",
            ["generate_changelog", "nonexistent.tar.gz"],
        )
        with patch("tools.generate_changelog.get_backups", return_value=backups):
            result = main()
            assert result == 1
            captured = capsys.readouterr()
            assert "not found" in captured.out
