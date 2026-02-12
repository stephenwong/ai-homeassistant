"""Extended tests for reference_validator.py - covering validate_all, summaries, etc."""

import json

import pytest

from tools.reference_validator import ReferenceValidator


@pytest.fixture
def setup_config(tmp_path):
    """Create a full config directory with registries."""
    config_dir = tmp_path
    storage_dir = config_dir / ".storage"
    storage_dir.mkdir()

    entity_data = {
        "data": {
            "entities": [
                {
                    "entity_id": "sensor.temperature",
                    "id": "aabbccddeeff00112233445566778899",
                    "platform": "test",
                    "unique_id": "temp1",
                    "device_id": "device_001",
                    "disabled_by": None,
                },
                {
                    "entity_id": "light.kitchen",
                    "id": "11223344556677889900aabbccddeeff",
                    "platform": "hue",
                    "unique_id": "light1",
                    "device_id": "device_002",
                    "disabled_by": None,
                },
                {
                    "entity_id": "sensor.disabled_temp",
                    "id": "ffeeddccbbaa99887766554433221100",
                    "platform": "test",
                    "unique_id": "temp2",
                    "device_id": "device_001",
                    "disabled_by": "user",
                },
            ]
        }
    }

    device_data = {
        "data": {
            "devices": [
                {"id": "device_001", "name": "Temp Sensor", "disabled_by": None},
                {"id": "device_002", "name": "Kitchen Light", "disabled_by": None},
            ]
        }
    }

    area_data = {
        "data": {
            "areas": [
                {"id": "kitchen", "name": "Kitchen"},
                {"id": "bedroom", "name": "Bedroom"},
            ]
        }
    }

    (storage_dir / "core.entity_registry").write_text(json.dumps(entity_data))
    (storage_dir / "core.device_registry").write_text(json.dumps(device_data))
    (storage_dir / "core.area_registry").write_text(json.dumps(area_data))

    return config_dir


class TestLoadYamlDefinedEntities:
    def test_extracts_template_entities(self, setup_config):
        config_yaml = setup_config / "configuration.yaml"
        config_yaml.write_text(
            "template:\n"
            "  - binary_sensor:\n"
            "      - name: Anyone Home\n"
            "        state: 'on'\n"
            "  - sensor:\n"
            "      - name: Average Temp\n"
            "        state: '22'\n"
        )
        v = ReferenceValidator(str(setup_config))
        entities = v.load_yaml_defined_entities()
        assert "binary_sensor.anyone_home" in entities
        assert "sensor.average_temp" in entities

    def test_extracts_automation_ids(self, setup_config):
        automations_yaml = setup_config / "automations.yaml"
        automations_yaml.write_text(
            "- id: morning_lights\n"
            "  alias: Morning Lights\n"
            "  trigger:\n"
            "    platform: time\n"
            "  action:\n"
            "    service: test\n"
        )
        v = ReferenceValidator(str(setup_config))
        entities = v.load_yaml_defined_entities()
        assert "automation.morning_lights" in entities

    def test_caches_result(self, setup_config):
        (setup_config / "configuration.yaml").write_text("homeassistant:\n")
        v = ReferenceValidator(str(setup_config))
        result1 = v.load_yaml_defined_entities()
        result2 = v.load_yaml_defined_entities()
        assert result1 is result2  # Same object = cached

    def test_handles_missing_files(self, setup_config):
        v = ReferenceValidator(str(setup_config))
        entities = v.load_yaml_defined_entities()
        assert isinstance(entities, set)

    def test_handles_parse_error(self, setup_config):
        (setup_config / "configuration.yaml").write_text("template: !bad_tag\n")
        v = ReferenceValidator(str(setup_config))
        entities = v.load_yaml_defined_entities()
        # Should handle gracefully with warning
        assert isinstance(entities, set)


class TestLoadRegistries:
    def test_load_entity_registry(self, setup_config):
        v = ReferenceValidator(str(setup_config))
        entities = v.load_entity_registry()
        assert "sensor.temperature" in entities
        assert "light.kitchen" in entities

    def test_entity_registry_cached(self, setup_config):
        v = ReferenceValidator(str(setup_config))
        e1 = v.load_entity_registry()
        e2 = v.load_entity_registry()
        assert e1 is e2

    def test_missing_entity_registry(self, tmp_path):
        v = ReferenceValidator(str(tmp_path))
        result = v.load_entity_registry()
        assert result == {}
        assert any("not found" in e for e in v.errors)

    def test_invalid_entity_registry(self, tmp_path):
        storage = tmp_path / ".storage"
        storage.mkdir()
        (storage / "core.entity_registry").write_text("not json")
        v = ReferenceValidator(str(tmp_path))
        result = v.load_entity_registry()
        assert result == {}

    def test_load_device_registry(self, setup_config):
        v = ReferenceValidator(str(setup_config))
        devices = v.load_device_registry()
        assert "device_001" in devices

    def test_device_registry_cached(self, setup_config):
        v = ReferenceValidator(str(setup_config))
        d1 = v.load_device_registry()
        d2 = v.load_device_registry()
        assert d1 is d2

    def test_missing_device_registry(self, tmp_path):
        v = ReferenceValidator(str(tmp_path))
        result = v.load_device_registry()
        assert result == {}

    def test_invalid_device_registry(self, tmp_path):
        storage = tmp_path / ".storage"
        storage.mkdir()
        (storage / "core.device_registry").write_text("not json")
        v = ReferenceValidator(str(tmp_path))
        result = v.load_device_registry()
        assert result == {}

    def test_load_area_registry(self, setup_config):
        v = ReferenceValidator(str(setup_config))
        areas = v.load_area_registry()
        assert "kitchen" in areas

    def test_area_registry_cached(self, setup_config):
        v = ReferenceValidator(str(setup_config))
        a1 = v.load_area_registry()
        a2 = v.load_area_registry()
        assert a1 is a2

    def test_missing_area_registry(self, tmp_path):
        v = ReferenceValidator(str(tmp_path))
        result = v.load_area_registry()
        assert result == {}
        assert any("not found" in w for w in v.warnings)

    def test_invalid_area_registry(self, tmp_path):
        storage = tmp_path / ".storage"
        storage.mkdir()
        (storage / "core.area_registry").write_text("not json")
        v = ReferenceValidator(str(tmp_path))
        result = v.load_area_registry()
        assert result == {}


class TestExtractEntitiesFromTemplate:
    def test_states_single_quotes(self, setup_config):
        v = ReferenceValidator(str(setup_config))
        result = v.extract_entities_from_template("{{ states('sensor.test') }}")
        assert "sensor.test" in result

    def test_states_double_quotes(self, setup_config):
        v = ReferenceValidator(str(setup_config))
        result = v.extract_entities_from_template('{{ states("sensor.test") }}')
        assert "sensor.test" in result

    def test_states_dot_notation(self, setup_config):
        v = ReferenceValidator(str(setup_config))
        result = v.extract_entities_from_template("{{ states.sensor.test }}")
        assert "sensor.test" in result

    def test_is_state(self, setup_config):
        v = ReferenceValidator(str(setup_config))
        result = v.extract_entities_from_template(
            "{{ is_state('binary_sensor.motion', 'on') }}"
        )
        assert "binary_sensor.motion" in result

    def test_state_attr(self, setup_config):
        v = ReferenceValidator(str(setup_config))
        result = v.extract_entities_from_template(
            "{{ state_attr('climate.hvac', 'temperature') }}"
        )
        assert "climate.hvac" in result


class TestExtractDeviceReferences:
    def test_single_device_id(self, setup_config):
        v = ReferenceValidator(str(setup_config))
        data = {"device_id": "device_001"}
        result = v.extract_device_references(data)
        assert "device_001" in result

    def test_device_id_list(self, setup_config):
        v = ReferenceValidator(str(setup_config))
        data = {"device_ids": ["device_001", "device_002"]}
        result = v.extract_device_references(data)
        assert "device_001" in result
        assert "device_002" in result

    def test_skips_templates_in_device_id(self, setup_config):
        v = ReferenceValidator(str(setup_config))
        data = {"device_id": "{{ trigger.device_id }}"}
        result = v.extract_device_references(data)
        assert len(result) == 0

    def test_skips_ha_tags(self, setup_config):
        v = ReferenceValidator(str(setup_config))
        data = {"device_id": "!input my_device"}
        result = v.extract_device_references(data)
        assert len(result) == 0

    def test_recursive_extraction(self, setup_config):
        v = ReferenceValidator(str(setup_config))
        data = {"actions": [{"target": {"device_id": "device_001"}}]}
        result = v.extract_device_references(data)
        assert "device_001" in result

    def test_list_extraction(self, setup_config):
        v = ReferenceValidator(str(setup_config))
        data = [{"device_id": "device_001"}, {"device_id": "device_002"}]
        result = v.extract_device_references(data)
        assert len(result) == 2


class TestExtractAreaReferences:
    def test_single_area_id(self, setup_config):
        v = ReferenceValidator(str(setup_config))
        data = {"area_id": "kitchen"}
        result = v.extract_area_references(data)
        assert "kitchen" in result

    def test_area_id_list(self, setup_config):
        v = ReferenceValidator(str(setup_config))
        data = {"area_ids": ["kitchen", "bedroom"]}
        result = v.extract_area_references(data)
        assert "kitchen" in result
        assert "bedroom" in result

    def test_skips_templates(self, setup_config):
        v = ReferenceValidator(str(setup_config))
        data = {"area_id": "{{ area }}"}
        result = v.extract_area_references(data)
        assert len(result) == 0

    def test_skips_ha_tags(self, setup_config):
        v = ReferenceValidator(str(setup_config))
        data = {"area_id": "!input my_area"}
        result = v.extract_area_references(data)
        assert len(result) == 0

    def test_recursive_extraction(self, setup_config):
        v = ReferenceValidator(str(setup_config))
        data = {"target": {"area_id": "kitchen"}}
        result = v.extract_area_references(data)
        assert "kitchen" in result


class TestValidateFileReferences:
    def test_valid_references(self, setup_config):
        test_file = setup_config / "test.yaml"
        test_file.write_text(
            "- entity_id: sensor.temperature\n"
            "  device_id: device_001\n"
            "  area_id: kitchen\n"
        )
        v = ReferenceValidator(str(setup_config))
        assert v.validate_file_references(test_file) is True

    def test_unknown_entity(self, setup_config):
        test_file = setup_config / "test.yaml"
        test_file.write_text("entity_id: sensor.nonexistent\n")
        v = ReferenceValidator(str(setup_config))
        assert v.validate_file_references(test_file) is False
        assert any("Unknown entity" in e for e in v.errors)

    def test_disabled_entity_passes(self, setup_config):
        """Disabled entities are still in the registry so validation passes."""
        test_file = setup_config / "test.yaml"
        test_file.write_text("entity_id: sensor.disabled_temp\n")
        v = ReferenceValidator(str(setup_config))
        assert v.validate_file_references(test_file) is True

    def test_unknown_device(self, setup_config):
        test_file = setup_config / "test.yaml"
        test_file.write_text("device_id: unknown_device\n")
        v = ReferenceValidator(str(setup_config))
        assert v.validate_file_references(test_file) is False

    def test_unknown_area_warning(self, setup_config):
        test_file = setup_config / "test.yaml"
        test_file.write_text("area_id: nonexistent_area\n")
        v = ReferenceValidator(str(setup_config))
        v.validate_file_references(test_file)
        assert any("Unknown area" in w for w in v.warnings)

    def test_skips_secrets_yaml(self, setup_config):
        test_file = setup_config / "secrets.yaml"
        test_file.write_text("api_key: secret123\n")
        v = ReferenceValidator(str(setup_config))
        assert v.validate_file_references(test_file) is True

    def test_empty_file(self, setup_config):
        test_file = setup_config / "empty.yaml"
        test_file.write_text("")
        v = ReferenceValidator(str(setup_config))
        assert v.validate_file_references(test_file) is True

    def test_invalid_yaml(self, setup_config):
        test_file = setup_config / "bad.yaml"
        test_file.write_text("key: value\n  bad: indent\n")
        v = ReferenceValidator(str(setup_config))
        assert v.validate_file_references(test_file) is False

    def test_builtin_entity_skipped(self, setup_config):
        test_file = setup_config / "test.yaml"
        test_file.write_text("entity_id: sun.sun\n")
        v = ReferenceValidator(str(setup_config))
        assert v.validate_file_references(test_file) is True

    def test_template_entity_references(self, setup_config):
        test_file = setup_config / "test.yaml"
        test_file.write_text("value_template: \"{{ states('sensor.temperature') }}\"\n")
        v = ReferenceValidator(str(setup_config))
        assert v.validate_file_references(test_file) is True


class TestValidateAll:
    def test_nonexistent_dir(self):
        v = ReferenceValidator("/nonexistent")
        assert v.validate_all() is False

    def test_empty_dir(self, tmp_path):
        v = ReferenceValidator(str(tmp_path))
        assert v.validate_all() is True
        assert any("No YAML" in w for w in v.warnings)

    def test_full_validation(self, setup_config):
        (setup_config / "automations.yaml").write_text(
            "- alias: Test\n"
            "  trigger:\n"
            "    platform: state\n"
            "    entity_id: sensor.temperature\n"
            "  action:\n"
            "    service: light.turn_on\n"
            "    entity_id: light.kitchen\n"
        )
        v = ReferenceValidator(str(setup_config))
        assert v.validate_all() is True


class TestGetEntitySummary:
    def test_summary_structure(self, setup_config):
        v = ReferenceValidator(str(setup_config))
        summary = v.get_entity_summary()
        assert "sensor" in summary
        assert "light" in summary
        assert summary["sensor"]["count"] == 2  # temperature + disabled_temp
        assert summary["sensor"]["enabled"] == 1
        assert summary["sensor"]["disabled"] == 1

    def test_summary_examples(self, setup_config):
        v = ReferenceValidator(str(setup_config))
        summary = v.get_entity_summary()
        assert len(summary["light"]["examples"]) > 0


class TestPrintResults:
    def test_prints_entity_summary(self, setup_config, capsys):
        v = ReferenceValidator(str(setup_config))
        v.print_results()
        captured = capsys.readouterr()
        assert "AVAILABLE ENTITIES" in captured.out
        assert "sensor" in captured.out
        assert "light" in captured.out


class TestLoadYamlDefinedEntitiesAutomationException:
    """Cover lines 110-111: exception parsing automations.yaml."""

    def test_automations_parse_error(self, setup_config):
        # Write non-UTF-8 bytes to automations.yaml to trigger exception
        (setup_config / "automations.yaml").write_bytes(b"\xff\xfe invalid bytes")
        v = ReferenceValidator(str(setup_config))
        entities = v.load_yaml_defined_entities()
        assert isinstance(entities, set)
        assert any("Failed to parse automations" in w for w in v.warnings)


class TestValidateFileReferencesEdgeCases:
    """Cover line 395: YAML entity skip."""

    def test_yaml_defined_entity_passes(self, setup_config):
        """Cover line 395: entity defined in YAML templates is accepted."""
        (setup_config / "configuration.yaml").write_text(
            "template:\n  - sensor:\n      - name: Custom Sensor\n        state: '42'\n"
        )
        test_file = setup_config / "automations.yaml"
        test_file.write_text("entity_id: sensor.custom_sensor\n")
        v = ReferenceValidator(str(setup_config))
        assert v.validate_file_references(test_file) is True


class TestValidateAllReturnsFalse:
    """Cover line 459: validate_all returns False when a file has invalid refs."""

    def test_validate_all_fails_on_bad_refs(self, setup_config):
        test_file = setup_config / "automations.yaml"
        test_file.write_text("entity_id: sensor.totally_nonexistent_entity\n")
        v = ReferenceValidator(str(setup_config))
        result = v.validate_all()
        assert result is False


class TestReferenceValidatorMain:
    """Cover lines 509-524: main() function."""

    def test_main_valid(self, setup_config, monkeypatch):
        from tools.reference_validator import main

        (setup_config / "automations.yaml").write_text(
            "entity_id: sensor.temperature\n"
        )
        monkeypatch.setattr("sys.argv", ["reference_validator", str(setup_config)])
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 0

    def test_main_invalid(self, monkeypatch):
        from tools.reference_validator import main

        monkeypatch.setattr("sys.argv", ["reference_validator", "/nonexistent"])
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 1
