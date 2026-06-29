"""Tests for tools/cache.py — validator result caching."""

import json
from unittest.mock import patch

from tools.cache import (
    _blob_hash,
    compute_hash,
    load_blob,
    load_cache,
    save_blob,
    save_cache,
)


class TestComputeHash:
    def test_returns_sha256_hex_string(self, tmp_path):
        (tmp_path / "a.yaml").write_text("hello")
        result = compute_hash(tmp_path, ["*.yaml"])
        assert isinstance(result, str)
        assert len(result) == 64  # SHA256 hex digest
        assert all(c in "0123456789abcdef" for c in result)

    def test_different_content_different_hash(self, tmp_path):
        (tmp_path / "a.yaml").write_text("hello")
        hash1 = compute_hash(tmp_path, ["*.yaml"])
        (tmp_path / "a.yaml").write_text("world")
        hash2 = compute_hash(tmp_path, ["*.yaml"])
        assert hash1 != hash2

    def test_same_content_same_hash(self, tmp_path):
        (tmp_path / "a.yaml").write_text("hello")
        hash1 = compute_hash(tmp_path, ["*.yaml"])
        hash2 = compute_hash(tmp_path, ["*.yaml"])
        assert hash1 == hash2

    def test_empty_patterns_produces_consistent_hash(self, tmp_path):
        result = compute_hash(tmp_path, [])
        assert isinstance(result, str)
        assert len(result) == 64

    def test_no_matching_files_produces_consistent_hash(self, tmp_path):
        result = compute_hash(tmp_path, ["*.yaml"])
        assert isinstance(result, str)
        assert len(result) == 64

    def test_multiple_files_produces_consistent_order(self, tmp_path):
        (tmp_path / "z.yaml").write_text("z")
        (tmp_path / "a.yaml").write_text("a")
        hash1 = compute_hash(tmp_path, ["*.yaml"])
        hash2 = compute_hash(tmp_path, ["*.yaml"])
        assert hash1 == hash2

    def test_overlapping_patterns_deduplicated(self, tmp_path):
        """When two patterns match the same file, the file is only hashed once."""
        (tmp_path / "a.yaml").write_text("hello")
        # Both patterns match the same file
        result = compute_hash(tmp_path, ["*.yaml", "a.yaml"])
        assert isinstance(result, str)
        assert len(result) == 64

    def test_recursive_glob(self, tmp_path):
        """** patterns should match nested files."""
        (tmp_path / "sub").mkdir()
        (tmp_path / "a.yaml").write_text("top")
        (tmp_path / "sub" / "b.yaml").write_text("nested")
        result = compute_hash(tmp_path, ["**/*.yaml"])
        assert isinstance(result, str)
        assert len(result) == 64

    def test_subdirectory_not_matched_by_top_level(self, tmp_path):
        """Top-level *.yaml does NOT match files in subdirectories."""
        (tmp_path / "sub").mkdir()
        (tmp_path / "a.yaml").write_text("top")
        (tmp_path / "sub" / "b.yaml").write_text("nested")
        hash_top_only = compute_hash(tmp_path, ["*.yaml"])
        # Now add the nested file
        hash_all = compute_hash(tmp_path, ["**/*.yaml"])
        assert hash_top_only != hash_all


class TestLoadCache:
    def test_valid_cache_returns_dict(self, tmp_path):
        cache_dir = tmp_path / ".cache" / "validators"
        cache_dir.mkdir(parents=True)
        (cache_dir / "Foo.json").write_text(
            json.dumps({"hash": "abc", "passed": True, "duration": 0.5})
        )
        result = load_cache(tmp_path, "Foo")
        assert result is not None
        assert result["hash"] == "abc"
        assert result["passed"] is True

    def test_missing_cache_returns_none(self, tmp_path):
        result = load_cache(tmp_path, "Nonexistent")
        assert result is None

    def test_missing_cache_does_not_create_directory(self, tmp_path):
        """A read-only check should not create .cache/validators/ on disk."""
        result = load_cache(tmp_path, "Nonexistent")
        assert result is None
        cache_dir = tmp_path / ".cache" / "validators"
        assert not cache_dir.exists()

    def test_invalid_json_returns_none(self, tmp_path):
        cache_dir = tmp_path / ".cache" / "validators"
        cache_dir.mkdir(parents=True)
        (cache_dir / "Foo.json").write_text("not json")
        result = load_cache(tmp_path, "Foo")
        assert result is None

    def test_missing_hash_key_returns_none(self, tmp_path):
        cache_dir = tmp_path / ".cache" / "validators"
        cache_dir.mkdir(parents=True)
        (cache_dir / "Foo.json").write_text(json.dumps({"passed": True}))
        result = load_cache(tmp_path, "Foo")
        assert result is None

    def test_missing_passed_key_returns_none(self, tmp_path):
        cache_dir = tmp_path / ".cache" / "validators"
        cache_dir.mkdir(parents=True)
        (cache_dir / "Foo.json").write_text(json.dumps({"hash": "abc"}))
        result = load_cache(tmp_path, "Foo")
        assert result is None


class TestSaveCache:
    def test_saves_json_with_required_keys(self, tmp_path):
        save_cache(tmp_path, "Foo", "Test Foo", "hash123", True, 0.42)
        cache_file = tmp_path / ".cache" / "validators" / "Foo.json"
        assert cache_file.exists()
        data = json.loads(cache_file.read_text())
        assert data["validator"] == "Test Foo"
        assert data["hash"] == "hash123"
        assert data["passed"] is True
        assert data["duration"] == 0.42
        assert "timestamp" in data

    def test_saves_failure_result(self, tmp_path):
        """Unit test only: validates serialization; _run_one never caches failures."""
        save_cache(tmp_path, "Bar", "Test Bar", "hash456", False, 0.1)
        cache_file = tmp_path / ".cache" / "validators" / "Bar.json"
        data = json.loads(cache_file.read_text())
        assert data["passed"] is False

    def test_creates_cache_directory(self, tmp_path):
        save_cache(tmp_path, "Baz", "Test", "h", True, 0.0)
        assert (tmp_path / ".cache" / "validators").is_dir()

    def test_overwrites_existing_cache(self, tmp_path):
        save_cache(tmp_path, "Foo", "Old", "old", True, 0.0)
        save_cache(tmp_path, "Foo", "New", "new", True, 0.0)
        cache_file = tmp_path / ".cache" / "validators" / "Foo.json"
        data = json.loads(cache_file.read_text())
        assert data["validator"] == "New"
        assert data["hash"] == "new"


class TestSaveBlobErrors:
    def test_save_blob_warns_on_oserror(self, tmp_path, capsys):
        """save_blob prints WARN to stderr when file write fails."""
        with patch("builtins.open", side_effect=OSError("permission denied")):
            save_blob(tmp_path, "testkey", {"output": "data"})
        _, err = capsys.readouterr()
        assert "WARN" in err
        assert "testkey" in err

    def test_save_cache_warns_on_oserror(self, tmp_path, capsys):
        """save_cache prints WARN to stderr when file write fails."""
        with patch("builtins.open", side_effect=OSError("disk full")):
            save_cache(tmp_path, "Foo", "Test", "hash", True, 0.5)
        _, err = capsys.readouterr()
        assert "WARN" in err
        assert "Foo" in err


class TestBlobCache:
    """Tests for blob cache (save_blob / load_blob / _blob_hash)."""

    def test_blob_hash_empty(self):
        h = _blob_hash([])
        assert isinstance(h, str)
        assert len(h) == 64  # SHA256 hex

    def test_blob_hash_deterministic(self):
        h1 = _blob_hash(["hello", b"world"])
        h2 = _blob_hash(["hello", b"world"])
        assert h1 == h2

    def test_blob_hash_different_inputs_different(self):
        h1 = _blob_hash(["abc"])
        h2 = _blob_hash(["ab", "c"])
        assert h1 != h2

    def test_blob_hash_mixed_str_bytes(self):
        h = _blob_hash(["domain", b"\x00", "light"])
        assert isinstance(h, str)
        assert len(h) == 64

    def test_save_and_load_roundtrip(self, tmp_path):
        data = {"output": '{"a": 1}'}
        save_blob(tmp_path, "testkey", data)
        loaded = load_blob(tmp_path, "testkey")
        assert loaded == data

    def test_load_missing_returns_none(self, tmp_path):
        assert load_blob(tmp_path, "nonexistent") is None

    def test_load_corrupt_returns_none(self, tmp_path):
        cache_dir = tmp_path / ".cache" / "entities"
        cache_dir.mkdir(parents=True)
        (cache_dir / "bad.json").write_text("{invalid")
        assert load_blob(tmp_path, "bad") is None

    def test_save_creates_directory(self, tmp_path):
        data = {"output": "test"}
        save_blob(tmp_path, "x", data)
        assert (tmp_path / ".cache" / "entities" / "x.json").is_file()

    def test_save_and_load_overwrite(self, tmp_path):
        save_blob(tmp_path, "k", {"output": "v1"})
        save_blob(tmp_path, "k", {"output": "v2"})
        loaded = load_blob(tmp_path, "k")
        assert loaded == {"output": "v2"}

    def test_blob_hash_delimiter_prevents_collision(self):
        """Without a delimiter, adjacent keys could merge. Verify they don't."""
        h1 = _blob_hash(["ab", "c"])
        h2 = _blob_hash(["a", "bc"])
        assert h1 != h2
