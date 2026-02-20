"""Extended tests for entity_explorer.py - print functions and main."""

import json

import pytest

from tools.entity_explorer import (
    categorize_entities,
    main,
    print_by_area,
    print_detailed_by_domain,
    print_summary,
)


@pytest.fixture
def sample_entities():
    return [
        {
            "entity_id": "light.kitchen",
            "name": "Kitchen Light",
            "original_name": "Light",
            "platform": "hue",
            "device_id": "dev1",
            "area_id": "kitchen",
            "disabled_by": None,
            "hidden_by": None,
            "device_class": None,
            "original_device_class": None,
            "unit_of_measurement": None,
        },
        {
            "entity_id": "sensor.temp",
            "name": "Temperature",
            "original_name": None,
            "platform": "weather",
            "device_id": "dev2",
            "area_id": "kitchen",
            "disabled_by": None,
            "hidden_by": None,
            "device_class": "temperature",
            "original_device_class": "temperature",
            "unit_of_measurement": "C",
        },
        {
            "entity_id": "binary_sensor.door",
            "name": "Front Door",
            "original_name": None,
            "platform": "zigbee",
            "device_id": "dev3",
            "area_id": None,
            "disabled_by": None,
            "hidden_by": None,
            "device_class": "door",
            "original_device_class": "door",
            "unit_of_measurement": None,
        },
    ]


@pytest.fixture
def area_names():
    return {"kitchen": "Kitchen"}


@pytest.fixture
def categorized(sample_entities, area_names):
    return categorize_entities(sample_entities, area_names)


class TestPrintSummary:
    def test_prints_overview(self, categorized, capsys):
        print_summary(categorized)
        captured = capsys.readouterr()
        assert "OVERVIEW" in captured.out
        assert "Total Entities" in captured.out

    def test_prints_automation_relevant(self, categorized, capsys):
        print_summary(categorized)
        captured = capsys.readouterr()
        assert "AUTOMATION-RELEVANT" in captured.out
        assert "LIGHT" in captured.out


class TestPrintDetailedByDomain:
    def test_all_domains(self, categorized, capsys):
        print_detailed_by_domain(categorized)
        captured = capsys.readouterr()
        assert "ENTITIES BY DOMAIN" in captured.out
        assert "light.kitchen" in captured.out

    def test_filter_single_domain(self, categorized, capsys):
        print_detailed_by_domain(categorized, "light")
        captured = capsys.readouterr()
        assert "light.kitchen" in captured.out

    def test_nonexistent_domain(self, categorized, capsys):
        print_detailed_by_domain(categorized, "nonexistent")
        captured = capsys.readouterr()
        assert "not found" in captured.out


class TestPrintByArea:
    def test_all_areas(self, categorized, capsys):
        print_by_area(categorized)
        captured = capsys.readouterr()
        assert "ENTITIES BY AREA" in captured.out
        assert "KITCHEN" in captured.out

    def test_filter_single_area(self, categorized, capsys):
        print_by_area(categorized, "Kitchen")
        captured = capsys.readouterr()
        assert "KITCHEN" in captured.out

    def test_nonexistent_area(self, categorized, capsys):
        print_by_area(categorized, "Nonexistent")
        captured = capsys.readouterr()
        assert "not found" in captured.out


class TestMain:
    @pytest.fixture
    def config_with_entity(self, tmp_path):
        """Set up a tmp_path with a single light entity in the registry."""
        storage = tmp_path / ".storage"
        storage.mkdir()
        entity_data = {
            "data": {
                "entities": [
                    {
                        "entity_id": "light.test",
                        "name": "Test Light",
                        "original_name": None,
                        "platform": "test",
                        "area_id": None,
                        "disabled_by": None,
                        "hidden_by": None,
                        "device_class": None,
                        "original_device_class": None,
                        "unit_of_measurement": None,
                    }
                ]
            }
        }
        (storage / "core.entity_registry").write_text(json.dumps(entity_data))
        return tmp_path

    def test_missing_config_dir(self, capsys, monkeypatch):
        monkeypatch.setattr("sys.argv", ["entity_explorer", "--config", "/nonexistent"])
        result = main()
        assert result == 1

    def test_missing_entity_registry(self, tmp_path, capsys, monkeypatch):
        monkeypatch.setattr("sys.argv", ["entity_explorer", "--config", str(tmp_path)])
        result = main()
        assert result == 1

    def test_empty_entities(self, tmp_path, capsys, monkeypatch):
        storage = tmp_path / ".storage"
        storage.mkdir()
        (storage / "core.entity_registry").write_text(
            json.dumps({"data": {"entities": []}})
        )
        monkeypatch.setattr("sys.argv", ["entity_explorer", "--config", str(tmp_path)])
        result = main()
        assert result == 1

    def test_summary_output(self, config_with_entity, capsys, monkeypatch):
        monkeypatch.setattr(
            "sys.argv",
            ["entity_explorer", "--config", str(config_with_entity)],
        )
        result = main()
        assert result == 0

    def test_search_mode(self, config_with_entity, capsys, monkeypatch):
        monkeypatch.setattr(
            "sys.argv",
            [
                "entity_explorer",
                "--config",
                str(config_with_entity),
                "--search",
                "test",
            ],
        )
        result = main()
        assert result == 0

    def test_domain_filter(self, config_with_entity, capsys, monkeypatch):
        monkeypatch.setattr(
            "sys.argv",
            [
                "entity_explorer",
                "--config",
                str(config_with_entity),
                "--domain",
                "light",
            ],
        )
        result = main()
        assert result == 0

    def test_area_filter(self, config_with_entity, capsys, monkeypatch):
        monkeypatch.setattr(
            "sys.argv",
            [
                "entity_explorer",
                "--config",
                str(config_with_entity),
                "--area",
                "No Area",
            ],
        )
        result = main()
        assert result == 0

    def test_full_output(self, config_with_entity, capsys, monkeypatch):
        monkeypatch.setattr(
            "sys.argv",
            ["entity_explorer", "--config", str(config_with_entity), "--full"],
        )
        result = main()
        assert result == 0


class TestCategorizeAutomationRelevant:
    """Test automation-relevant categorization edge cases."""

    def test_sensor_temperature_relevant(self):
        entities = [
            {
                "entity_id": "sensor.temp",
                "name": "Temp",
                "original_name": None,
                "platform": "test",
                "area_id": None,
                "disabled_by": None,
                "hidden_by": None,
                "device_class": "temperature",
                "original_device_class": "temperature",
                "unit_of_measurement": "C",
            }
        ]
        result = categorize_entities(entities, {})
        assert "sensor" in result["automation_relevant"]

    def test_binary_sensor_occupancy_relevant(self):
        entities = [
            {
                "entity_id": "binary_sensor.room",
                "name": "Room",
                "original_name": None,
                "platform": "test",
                "area_id": None,
                "disabled_by": None,
                "hidden_by": None,
                "device_class": "occupancy",
                "original_device_class": "occupancy",
                "unit_of_measurement": None,
            }
        ]
        result = categorize_entities(entities, {})
        assert "binary_sensor" in result["automation_relevant"]
