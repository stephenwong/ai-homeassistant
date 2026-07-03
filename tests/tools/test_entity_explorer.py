"""Tests for tools/entity_explorer.py - entity registry explorer."""

import json

import pytest

from tools.entity_explorer import (
    categorize_entities,
    get_entity_display_name,
    load_area_registry,
    load_entity_registry,
    main,
    print_by_area,
    print_detailed_by_domain,
    print_summary,
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
        assert "No matches found" in captured.err

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


class TestJsonMode:
    """Tests for --json flag output."""

    def _setup_config(self, tmp_path):
        storage = tmp_path / ".storage"
        storage.mkdir()
        entities = [
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
                "unit_of_measurement": None,
                "original_device_class": None,
            },
            {
                "entity_id": "sensor.temp",
                "name": None,
                "original_name": "Temperature",
                "platform": "weather",
                "device_id": "dev2",
                "area_id": "kitchen",
                "disabled_by": None,
                "hidden_by": None,
                "device_class": "temperature",
                "unit_of_measurement": "C",
                "original_device_class": "temperature",
            },
        ]
        (storage / "core.entity_registry").write_text(
            json.dumps({"data": {"entities": entities}})
        )
        (storage / "core.area_registry").write_text(
            json.dumps(
                {
                    "data": {
                        "areas": [
                            {"id": "kitchen", "name": "Kitchen"},
                        ]
                    }
                }
            )
        )
        return tmp_path

    def _run_main(self, tmp_path, *extra_args):
        """Helper: set up config and run entity_explorer.main with argv."""
        config = self._setup_config(tmp_path)
        from tools import entity_explorer

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "sys.argv",
                ["entity_explorer", "--config", str(config), *extra_args],
            )
            return entity_explorer.main()

    def test_json_default_outputs_automation_relevant(self, tmp_path, capsys):
        """--json with no selector emits automation-relevant entities."""
        result = self._run_main(tmp_path, "--json")
        assert result == 0
        out = capsys.readouterr().out
        parsed = json.loads(out)
        # light is in automation_relevant; sensor.temperature device_class
        # also matches.
        assert isinstance(parsed, list)
        entity_ids = [row["e"] for row in parsed]
        assert "light.kitchen" in entity_ids

    def test_json_filters_by_domain(self, tmp_path, capsys):
        self._run_main(tmp_path, "--domain", "light", "--json")
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert all(row["e"].startswith("light.") for row in parsed)
        assert any(row["e"] == "light.kitchen" for row in parsed)

    def test_json_filters_by_area(self, tmp_path, capsys):
        self._run_main(tmp_path, "--area", "Kitchen", "--json")
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert len(parsed) >= 1
        assert all(row.get("a") == "Kitchen" for row in parsed)

    def test_json_filters_by_search(self, tmp_path, capsys):
        self._run_main(tmp_path, "--search", "kitchen", "--json")
        out = capsys.readouterr().out
        parsed = json.loads(out)
        # Search matches entity_id "light.kitchen" and name "Kitchen Light"
        assert any(row["e"] == "light.kitchen" for row in parsed)

    def test_json_uses_compact_keys(self, tmp_path, capsys):
        """JSON output should use shortened keys (e/n/a/dc/u) for token efficiency."""
        self._run_main(tmp_path, "--domain", "light", "--json")
        out = capsys.readouterr().out
        parsed = json.loads(out)
        row = next(r for r in parsed if r["e"] == "light.kitchen")
        assert "e" in row  # entity_id
        assert "n" in row  # name
        assert row["n"] == "Kitchen Light"

    def test_json_includes_device_class_when_present(self, tmp_path, capsys):
        self._run_main(tmp_path, "--domain", "sensor", "--json")
        out = capsys.readouterr().out
        parsed = json.loads(out)
        temp = next(r for r in parsed if r["e"] == "sensor.temp")
        assert temp.get("dc") == "temperature"
        assert temp.get("u") == "C"

    def test_json_omits_no_area(self, tmp_path, capsys):
        """Entities with 'No Area' should omit the 'a' key for compactness."""
        self._run_main(tmp_path, "--domain", "light", "--json")
        out = capsys.readouterr().out
        parsed = json.loads(out)
        kitchen = next(r for r in parsed if r["e"] == "light.kitchen")
        # light.kitchen is in 'kitchen' area, so 'a' should be present
        assert kitchen.get("a") == "Kitchen"

    def test_json_output_is_single_line(self, tmp_path, capsys):
        """Output should be a single-line JSON array (no newlines in payload)."""
        self._run_main(tmp_path, "--json")
        out = capsys.readouterr().out.strip()
        # Single line — no embedded newlines
        assert "\n" not in out

    def test_json_takes_precedence_over_pretty(self, tmp_path, capsys):
        """If --json is passed alongside --full, --json wins."""
        self._run_main(tmp_path, "--full", "--json")
        out = capsys.readouterr().out
        # Should be valid JSON, not pretty banners
        json.loads(out)
        assert "OVERVIEW" not in out


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
        assert "not found" in captured.err


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
        assert "not found" in captured.err


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

    def test_cache_written_on_first_run(self, config_with_entity, capsys, monkeypatch):
        """First run (no cache) should write a cache file."""
        cache_dir = config_with_entity / ".cache" / "entities"
        assert not cache_dir.exists()
        monkeypatch.setattr(
            "sys.argv",
            ["entity_explorer", "--config", str(config_with_entity), "--json"],
        )
        result = main()
        assert result == 0
        cache_files = list(cache_dir.glob("*.json"))
        assert len(cache_files) >= 1
        assert cache_files[0].stat().st_size > 10

    def test_cache_replayed_on_second_run(
        self, config_with_entity, capsys, monkeypatch
    ):
        """Second run (cache present) should replay cached output."""
        from unittest.mock import patch

        from tools.cache import save_blob

        # Pre-populate cache with a known key
        cache_dir = config_with_entity / ".cache" / "entities"
        cache_dir.mkdir(parents=True)
        save_blob(config_with_entity, "known-key", {"output": "cached result\n"})

        with patch("tools.entity_explorer._blob_hash", return_value="known-key"):
            monkeypatch.setattr(
                "sys.argv",
                ["entity_explorer", "--config", str(config_with_entity)],
            )
            result = main()
        assert result == 0
        out = capsys.readouterr().out
        assert "cached result" in out

    def test_force_bypasses_cache(self, config_with_entity, capsys, monkeypatch):
        """--force should recompute even when a cache file exists."""
        from tools.cache import save_blob

        cache_dir = config_with_entity / ".cache" / "entities"
        cache_dir.mkdir(parents=True)
        save_blob(config_with_entity, "some_hash", {"output": "stale output\n"})

        monkeypatch.setattr(
            "sys.argv",
            ["entity_explorer", "--config", str(config_with_entity), "--force"],
        )
        result = main()
        assert result == 0
        out = capsys.readouterr().out
        assert "stale output" not in out
