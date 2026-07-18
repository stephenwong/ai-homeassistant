"""Direct unit tests for tools.validators._storage.load_storage_registry."""

import json

import pytest

from tools.validators._storage import load_storage_registry


@pytest.fixture
def registry_file(tmp_path):
    """Write a registry JSON with two entities indexed by entity_id."""
    path = tmp_path / "core.entity_registry"
    data = {
        "version": 1,
        "minor_version": 1,
        "data": {
            "entities": [
                {"entity_id": "sensor.one", "id": "aaa"},
                {"entity_id": "sensor.two", "id": "bbb"},
            ]
        },
    }
    path.write_text(json.dumps(data))
    return path


class TestLoadStorageRegistry:
    def test_indexes_items_by_key_field(self, registry_file):
        result = load_storage_registry(
            registry_file, list_key="entities", key_field="entity_id"
        )
        assert set(result.keys()) == {"sensor.one", "sensor.two"}
        assert result["sensor.one"]["id"] == "aaa"

    def test_index_by_alternate_key_field(self, registry_file):
        result = load_storage_registry(
            registry_file, list_key="entities", key_field="id"
        )
        assert set(result.keys()) == {"aaa", "bbb"}

    def test_returns_empty_when_list_empty(self, tmp_path):
        path = tmp_path / "core.entity_registry"
        path.write_text(json.dumps({"data": {"entities": []}}))
        result = load_storage_registry(path, list_key="entities", key_field="entity_id")
        assert result == {}

    def test_returns_empty_when_list_key_missing(self, tmp_path):
        path = tmp_path / "core.entity_registry"
        path.write_text(json.dumps({"data": {}}))
        result = load_storage_registry(path, list_key="entities", key_field="entity_id")
        assert result == {}

    def test_returns_empty_when_data_key_missing(self, tmp_path):
        path = tmp_path / "core.entity_registry"
        path.write_text(json.dumps({"version": 1}))
        result = load_storage_registry(path, list_key="entities", key_field="entity_id")
        assert result == {}

    def test_raises_filenotfound_for_missing_file(self, tmp_path):
        with pytest.raises(OSError):
            load_storage_registry(
                tmp_path / "nonexistent", list_key="entities", key_field="entity_id"
            )

    def test_raises_jsondecodeerror_for_malformed_json(self, tmp_path):
        path = tmp_path / "core.entity_registry"
        path.write_text("not valid json{")
        with pytest.raises(json.JSONDecodeError):
            load_storage_registry(path, list_key="entities", key_field="entity_id")

    def test_raises_typeerror_when_top_level_is_list(self, tmp_path):
        path = tmp_path / "core.entity_registry"
        path.write_text("[]")
        with pytest.raises((TypeError, AttributeError)):
            load_storage_registry(path, list_key="entities", key_field="entity_id")

    def test_raises_keyerror_when_item_missing_key_field(self, tmp_path):
        path = tmp_path / "core.entity_registry"
        path.write_text(json.dumps({"data": {"entities": [{"wrong_field": "x"}]}}))
        with pytest.raises(KeyError):
            load_storage_registry(path, list_key="entities", key_field="entity_id")

    def test_raises_attributeerror_when_top_level_is_null(self, tmp_path):
        path = tmp_path / "core.entity_registry"
        path.write_text("null")
        with pytest.raises(AttributeError):
            load_storage_registry(path, list_key="entities", key_field="entity_id")

    def test_raises_attributeerror_when_top_level_is_string(self, tmp_path):
        path = tmp_path / "core.entity_registry"
        path.write_text('"a string"')
        with pytest.raises(AttributeError):
            load_storage_registry(path, list_key="entities", key_field="entity_id")

    def test_raises_typeerror_when_item_not_dict(self, tmp_path):
        path = tmp_path / "core.entity_registry"
        path.write_text(json.dumps({"data": {"entities": ["not_a_dict"]}}))
        with pytest.raises(TypeError):
            load_storage_registry(path, list_key="entities", key_field="entity_id")

    def test_duplicate_keys_last_wins(self, tmp_path):
        path = tmp_path / "core.entity_registry"
        path.write_text(
            json.dumps(
                {
                    "data": {
                        "entities": [
                            {"entity_id": "sensor.dup", "id": "first"},
                            {"entity_id": "sensor.dup", "id": "second"},
                        ]
                    }
                }
            )
        )
        result = load_storage_registry(path, list_key="entities", key_field="entity_id")
        assert result["sensor.dup"]["id"] == "second"
