"""Tests for tools/backup_common.py — shared backup primitives."""

import io
import tarfile

import pytest

from tools.backup_common import iter_tarball_file_members


def _make_tar(tmp_path, files_dict, name="test.tar.gz"):
    """Create a tar.gz archive with given files."""
    tar_path = tmp_path / name
    with tarfile.open(tar_path, "w:gz") as tar:
        for fname, content in files_dict.items():
            data = content.encode("utf-8")
            info = tarfile.TarInfo(name=fname)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return tar_path


class TestIterTarballFileMembers:
    def test_yields_regular_files_only(self, tmp_path):
        tar_path = _make_tar(tmp_path, {"config/test.yaml": "content\n"})
        result = list(iter_tarball_file_members(tar_path))
        assert len(result) == 1
        name, _file = result[0]
        assert name == "config/test.yaml"

    def test_skips_directories(self, tmp_path):
        tar_path = tmp_path / "test.tar.gz"
        with tarfile.open(tar_path, "w:gz") as tar:
            info = tarfile.TarInfo(name="config/")
            info.type = tarfile.DIRTYPE
            tar.addfile(info)
            data = b"content\n"
            finfo = tarfile.TarInfo(name="config/test.yaml")
            finfo.size = len(data)
            tar.addfile(finfo, io.BytesIO(data))
        result = list(iter_tarball_file_members(tar_path))
        assert len(result) == 1
        assert result[0][0] == "config/test.yaml"

    def test_normalizes_dot_slash_prefix(self, tmp_path):
        tar_path = tmp_path / "test.tar.gz"
        with tarfile.open(tar_path, "w:gz") as tar:
            data = b"content\n"
            info = tarfile.TarInfo(name="./config/test.yaml")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        result = list(iter_tarball_file_members(tar_path))
        assert result[0][0] == "config/test.yaml"

    def test_skips_symlinks(self, tmp_path):
        tar_path = tmp_path / "test.tar.gz"
        with tarfile.open(tar_path, "w:gz") as tar:
            link_info = tarfile.TarInfo(name="link.yaml")
            link_info.type = tarfile.SYMTYPE
            link_info.linkname = "config/test.yaml"
            tar.addfile(link_info)
            data = b"content\n"
            finfo = tarfile.TarInfo(name="config/real.yaml")
            finfo.size = len(data)
            tar.addfile(finfo, io.BytesIO(data))
        result = list(iter_tarball_file_members(tar_path))
        assert len(result) == 1
        assert result[0][0] == "config/real.yaml"

    def test_content_readable_from_yielded_file(self, tmp_path):
        tar_path = _make_tar(tmp_path, {"config/test.yaml": "hello world\n"})
        for _name, extracted in iter_tarball_file_members(tar_path):
            content = extracted.read().decode("utf-8")
            assert content == "hello world\n"

    def test_empty_tarball_yields_nothing(self, tmp_path):
        tar_path = tmp_path / "empty.tar.gz"
        with tarfile.open(tar_path, "w:gz"):
            pass
        result = list(iter_tarball_file_members(tar_path))
        assert result == []

    def test_propagates_tar_error(self, tmp_path):
        bad = tmp_path / "bad.tar.gz"
        bad.write_text("not a tar file")
        with pytest.raises((tarfile.TarError, OSError)):
            list(iter_tarball_file_members(bad))
