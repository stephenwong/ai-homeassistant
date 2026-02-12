"""Tests for tools/entity_explorer.py - entity registry explorer."""

import json

import pytest

from tools.entity_explorer import (
    categorize_entities,
    get_entity_display_name,
    load_area_registry,
    load_entity_registry,
    search_entities,
)


@pytest.fixture
def config_path(tmp_path):
    storage = tmp_path / ".storage"
    storage.mkdir()

    entity_data = {
        "data": {
            "entities": [
                {
                    "entity_id": "light.living_room",
                    "name": "Living Room Light",
                    "original_name": "Light",
                    "platform": "hue",
                    "device_id": "dev1",
                    "area_id": "living_room",
                    "disabled_by": None,
                    "hidden_by": None,
                    "device_class": None,
                    "unit_of_measurement": None,
                    "original_device_class": None,
                },
                {
                    "entity_id": "sensor.temperature",
                    "name": None,
                    "original_name": "Temperature",
                    "platform": "weather",
                    "device_id": "dev2",
                    "area_id": "living_room",
                    "disabled_by": None,
                    "hidden_by": None,
                    "device_class": "temperature",
                    "unit_of_measurement": "C",
                    "original_device_class": "temperature",
                },
                {
                    "entity_id": "binary_sensor.motion",
                    "name": None,
                    "original_name": None,
                    "platform": "zigbee",
                    "device_id": "dev3",
                    "area_id": None,
                    "disabled_by": None,
                    "hidden_by": None,
                    "device_class": "motion",
                    "unit_of_measurement": None,
                    "original_device_class": "motion",
                },
                {
                    "entity_id": "switch.disabled",
                    "name": "Disabled Switch",
                    "original_name": None,
                    "platform": "test",
                    "device_id": "dev4",
                    "area_id": None,
                    "disabled_by": "user",
                    "hidden_by": None,
                    "device_class": None,
                    "unit_of_measurement": None,
                    "original_device_class": None,
                },
                {
                    "entity_id": "camera.front_door",
                    "name": "Front Door Camera",
                    "original_name": None,
                    "platform": "frigate",
                    "device_id": "dev5",
                    "area_id": "front_porch",
                    "disabled_by": None,
                    "hidden_by": None,
                    "device_class": None,
                    "unit_of_measurement": None,
                    "original_device_class": None,
                },
            ]
        }
    }

    area_data = {
        "data": {
            "areas": [
                {"id": "living_room", "name": "Living Room"},
                {"id": "front_porch", "name": "Front Porch"},
            ]
        }
    }

    (storage / "core.entity_registry").write_text(json.dumps(entity_data))
    (storage / "core.area_registry").write_text(json.dumps(area_data))
    return tmp_path


class TestLoadEntityRegistry:
    def test_loads_registry(self, config_path):
        result = load_entity_registry(config_path)
        assert result is not None
        assert "data" in result

    def test_missing_registry(self, tmp_path):
        result = load_entity_registry(tmp_path)
        assert result is None

    def test_invalid_json(self, tmp_path):
        storage = tmp_path / ".storage"
        storage.mkdir()
        (storage / "core.entity_registry").write_text("not json")
        result = load_entity_registry(tmp_path)
        assert result is None


class TestLoadAreaRegistry:
    def test_loads_areas(self, config_path):
        result = load_area_registry(config_path)
        assert "living_room" in result
        assert result["living_room"] == "Living Room"

    def test_missing_area_file(self, tmp_path):
        result = load_area_registry(tmp_path)
        assert result == {}

    def test_invalid_json(self, tmp_path):
        storage = tmp_path / ".storage"
        storage.mkdir()
        (storage / "core.area_registry").write_text("not json")
        result = load_area_registry(tmp_path)
        assert result == {}


class TestGetEntityDisplayName:
    def test_uses_name(self):
        entity = {
            "entity_id": "light.test",
            "name": "My Light",
            "original_name": "Light",
        }
        assert get_entity_display_name(entity) == "My Light"

    def test_uses_original_name(self):
        entity = {"entity_id": "light.test", "name": None, "original_name": "Original"}
        assert get_entity_display_name(entity) == "Original"

    def test_falls_back_to_entity_id(self):
        entity = {"entity_id": "light.living_room", "name": None, "original_name": None}
        assert get_entity_display_name(entity) == "Living Room"


class TestCategorizeEntities:
    def test_categorizes_by_domain(self, config_path):
        registry = load_entity_registry(config_path)
        areas = load_area_registry(config_path)
        entities = registry["data"]["entities"]

        result = categorize_entities(entities, areas)

        assert "light" in result["by_domain"]
        assert "sensor" in result["by_domain"]
        assert "binary_sensor" in result["by_domain"]
        assert "camera" in result["by_domain"]

    def test_excludes_disabled_entities(self, config_path):
        registry = load_entity_registry(config_path)
        areas = load_area_registry(config_path)
        entities = registry["data"]["entities"]

        result = categorize_entities(entities, areas)

        # Disabled switch should not appear
        all_entity_ids = [
            e["entity_id"]
            for domain_list in result["by_domain"].values()
            for e in domain_list
        ]
        assert "switch.disabled" not in all_entity_ids

    def test_categorizes_by_area(self, config_path):
        registry = load_entity_registry(config_path)
        areas = load_area_registry(config_path)
        entities = registry["data"]["entities"]

        result = categorize_entities(entities, areas)

        assert "Living Room" in result["by_area"]
        assert "No Area" in result["by_area"]

    def test_automation_relevant(self, config_path):
        registry = load_entity_registry(config_path)
        areas = load_area_registry(config_path)
        entities = registry["data"]["entities"]

        result = categorize_entities(entities, areas)

        assert "light" in result["automation_relevant"]
        assert "camera" in result["automation_relevant"]


class TestSearchEntities:
    def test_search_by_entity_id(self, config_path, capsys):
        registry = load_entity_registry(config_path)
        areas = load_area_registry(config_path)
        entities = registry["data"]["entities"]
        categorized = categorize_entities(entities, areas)

        search_entities(categorized, "front_door")
        captured = capsys.readouterr()
        assert "camera.front_door" in captured.out

    def test_search_by_name(self, config_path, capsys):
        registry = load_entity_registry(config_path)
        areas = load_area_registry(config_path)
        entities = registry["data"]["entities"]
        categorized = categorize_entities(entities, areas)

        search_entities(categorized, "Living Room")
        captured = capsys.readouterr()
        assert "light.living_room" in captured.out

    def test_search_no_matches(self, config_path, capsys):
        registry = load_entity_registry(config_path)
        areas = load_area_registry(config_path)
        entities = registry["data"]["entities"]
        categorized = categorize_entities(entities, areas)

        search_entities(categorized, "nonexistent_entity_xyz")
        captured = capsys.readouterr()
        assert "No matches found" in captured.out

    def test_search_by_device_class(self, config_path, capsys):
        registry = load_entity_registry(config_path)
        areas = load_area_registry(config_path)
        entities = registry["data"]["entities"]
        categorized = categorize_entities(entities, areas)

        search_entities(categorized, "temperature")
        captured = capsys.readouterr()
        assert "sensor.temperature" in captured.out


class TestCategorizeAutomationRelevantSensors:
    """Cover lines 113-127: sensor/binary_sensor categorization by device_class."""

    def test_sensor_temperature_categorized(self, config_path):
        registry = load_entity_registry(config_path)
        areas = load_area_registry(config_path)
        entities = registry["data"]["entities"]
        result = categorize_entities(entities, areas)

        # sensor.temperature has device_class=temperature,
        # should be in automation_relevant
        sensor_ids = [
            e["entity_id"] for e in result["automation_relevant"].get("sensor", [])
        ]
        assert "sensor.temperature" in sensor_ids

    def test_binary_sensor_motion_categorized(self, config_path):
        registry = load_entity_registry(config_path)
        areas = load_area_registry(config_path)
        entities = registry["data"]["entities"]
        result = categorize_entities(entities, areas)

        # binary_sensor.motion has device_class=motion
        bs_ids = [
            e["entity_id"]
            for e in result["automation_relevant"].get("binary_sensor", [])
        ]
        assert "binary_sensor.motion" in bs_ids

    def test_sensor_humidity_categorized(self, tmp_path):
        """Test sensor with humidity device_class."""
        storage = tmp_path / ".storage"
        storage.mkdir()
        entity_data = {
            "data": {
                "entities": [
                    {
                        "entity_id": "sensor.humidity",
                        "name": "Humidity",
                        "original_name": "Humidity",
                        "platform": "test",
                        "device_id": None,
                        "area_id": None,
                        "disabled_by": None,
                        "hidden_by": None,
                        "device_class": "humidity",
                        "unit_of_measurement": "%",
                        "original_device_class": "humidity",
                    },
                ]
            }
        }
        (storage / "core.entity_registry").write_text(json.dumps(entity_data))
        (storage / "core.area_registry").write_text(json.dumps({"data": {"areas": []}}))

        registry = load_entity_registry(tmp_path)
        areas = load_area_registry(tmp_path)
        result = categorize_entities(registry["data"]["entities"], areas)
        sensor_ids = [
            e["entity_id"] for e in result["automation_relevant"].get("sensor", [])
        ]
        assert "sensor.humidity" in sensor_ids

    def test_binary_sensor_door_categorized(self, tmp_path):
        """Test binary_sensor with door device_class."""
        storage = tmp_path / ".storage"
        storage.mkdir()
        entity_data = {
            "data": {
                "entities": [
                    {
                        "entity_id": "binary_sensor.front_door",
                        "name": "Front Door",
                        "original_name": None,
                        "platform": "zigbee",
                        "device_id": None,
                        "area_id": None,
                        "disabled_by": None,
                        "hidden_by": None,
                        "device_class": "door",
                        "unit_of_measurement": None,
                        "original_device_class": "door",
                    },
                ]
            }
        }
        (storage / "core.entity_registry").write_text(json.dumps(entity_data))
        (storage / "core.area_registry").write_text(json.dumps({"data": {"areas": []}}))

        registry = load_entity_registry(tmp_path)
        areas = load_area_registry(tmp_path)
        result = categorize_entities(registry["data"]["entities"], areas)
        bs_ids = [
            e["entity_id"]
            for e in result["automation_relevant"].get("binary_sensor", [])
        ]
        assert "binary_sensor.front_door" in bs_ids


class TestPrintSummaryAndMore:
    """Cover line 167: 'and X more' printing for domains with >3 entities."""

    def test_and_more_message(self, tmp_path, capsys):
        from tools.entity_explorer import print_summary

        storage = tmp_path / ".storage"
        storage.mkdir()
        # Create 5 sensor entities
        entities = []
        for i in range(5):
            entities.append(
                {
                    "entity_id": f"sensor.temp_{i}",
                    "name": f"Temp {i}",
                    "original_name": f"Temp {i}",
                    "platform": "test",
                    "device_id": None,
                    "area_id": None,
                    "disabled_by": None,
                    "hidden_by": None,
                    "device_class": "temperature",
                    "unit_of_measurement": "C",
                    "original_device_class": "temperature",
                }
            )
        (storage / "core.entity_registry").write_text(
            json.dumps({"data": {"entities": entities}})
        )
        (storage / "core.area_registry").write_text(json.dumps({"data": {"areas": []}}))

        registry = load_entity_registry(tmp_path)
        areas = load_area_registry(tmp_path)
        categorized = categorize_entities(registry["data"]["entities"], areas)
        print_summary(categorized)
        captured = capsys.readouterr()
        assert "and 2 more" in captured.out
