#!/usr/bin/env python3
"""Unit tests for reference_validator.py UUID support."""

import builtins
import json
from unittest.mock import patch

import pytest
import yaml

from tools.reference_validator import ReferenceValidator


@pytest.fixture
def config_dir(tmp_path):
    """Create config directory with mock registries."""
    storage_dir = tmp_path / ".storage"
    storage_dir.mkdir()

    entity_registry_data = {
        "version": 1,
        "minor_version": 1,
        "data": {
            "entities": [
                {
                    "entity_id": "binary_sensor.test_motion_battery",
                    "id": "88a52f17bf43cb276836f06ac5c07444",
                    "platform": "test",
                    "unique_id": "test_motion_battery",
                    "device_id": "0c086f69ee6b3fa8411af7194876cbd7",
                    "disabled_by": None,
                },
                {
                    "entity_id": "sensor.disabled_sensor",
                    "id": "11223344556677889900aabbccddeeff",
                    "platform": "test",
                    "unique_id": "disabled_sensor",
                    "device_id": "disabled_device_id_123456789012",
                    "disabled_by": "user",
                },
                {
                    "entity_id": "sensor.normal_sensor",
                    "id": "aabbccddeeff00112233445566778899",
                    "platform": "test",
                    "unique_id": "normal_sensor",
                    "disabled_by": None,
                },
                {
                    "entity_id": "sensor.complex",
                    "id": "complexsensoridfortest1234567890",
                    "platform": "test",
                    "unique_id": "complex_sensor",
                    "disabled_by": None,
                },
            ]
        },
    }

    device_registry_data = {
        "version": 1,
        "minor_version": 1,
        "data": {
            "devices": [
                {
                    "id": "0c086f69ee6b3fa8411af7194876cbd7",
                    "name": "Test Motion Sensor",
                    "manufacturer": "Test",
                    "model": "Motion Sensor",
                    "disabled_by": None,
                },
                {
                    "id": "disabled_device_id_123456789012",
                    "name": "Disabled Device",
                    "manufacturer": "Test",
                    "model": "Disabled",
                    "disabled_by": "user",
                },
            ]
        },
    }

    area_registry_data = {
        "version": 1,
        "minor_version": 1,
        "data": {"areas": [{"id": "living_room", "name": "Living Room"}]},
    }

    (storage_dir / "core.entity_registry").write_text(json.dumps(entity_registry_data))
    (storage_dir / "core.device_registry").write_text(json.dumps(device_registry_data))
    (storage_dir / "core.area_registry").write_text(json.dumps(area_registry_data))

    return tmp_path


@pytest.fixture
def validator(config_dir):
    return ReferenceValidator(str(config_dir))


class TestIsUUIDFormat:
    def test_valid_uuid(self, validator):
        assert validator.is_uuid_format("88a52f17bf43cb276836f06ac5c07444") is True
        assert validator.is_uuid_format("aabbccddeeff00112233445566778899") is True

    def test_invalid_formats(self, validator):
        assert validator.is_uuid_format("sensor.kitchen_motion") is False
        assert validator.is_uuid_format("88a52f17bf43cb276836f06ac5c0744") is False
        assert validator.is_uuid_format("88a52f17bf43cb276836f06ac5c074455") is False
        assert validator.is_uuid_format("88a52f17-bf43-cb27-6836-f06ac5c07444") is False
        assert validator.is_uuid_format("gghhiijjkkllmmnnooppqqrrssttuu99") is False


class TestExtractEntityRegistryIds:
    def test_device_automation(self, validator):
        data = {
            "triggers": [
                {
                    "type": "battery_level",
                    "device_id": "0c086f69ee6b3fa8411af7194876cbd7",
                    "entity_id": "88a52f17bf43cb276836f06ac5c07444",
                    "domain": "sensor",
                    "trigger": "device",
                    "below": 20,
                }
            ]
        }
        registry_ids = validator.extract_entity_registry_ids(data)
        assert registry_ids == {"88a52f17bf43cb276836f06ac5c07444"}

    def test_mixed_normal_and_uuid(self, validator):
        data = {
            "entity_id": "sensor.normal_entity",
            "triggers": [
                {
                    "entity_id": "aabbccddeeff00112233445566778899",
                    "platform": "state",
                }
            ],
        }
        registry_ids = validator.extract_entity_registry_ids(data)
        assert registry_ids == {"aabbccddeeff00112233445566778899"}


class TestGetEntityRegistryIdMapping:
    def test_mapping(self, validator):
        mapping = validator.get_entity_registry_id_mapping()
        assert mapping == {
            "88a52f17bf43cb276836f06ac5c07444": "binary_sensor.test_motion_battery",
            "11223344556677889900aabbccddeeff": "sensor.disabled_sensor",
            "aabbccddeeff00112233445566778899": "sensor.normal_sensor",
            "complexsensoridfortest1234567890": "sensor.complex",
        }


class TestValidateEntityRegistryIds:
    def test_valid_uuid(self, config_dir, validator):
        automation_data = [
            {
                "id": "test_automation",
                "alias": "Test Device Automation",
                "triggers": [
                    {
                        "type": "battery_level",
                        "device_id": "0c086f69ee6b3fa8411af7194876cbd7",
                        "entity_id": "88a52f17bf43cb276836f06ac5c07444",
                        "domain": "sensor",
                        "trigger": "device",
                        "below": 20,
                    }
                ],
                "action": [
                    {
                        "service": "notify.mobile_app",
                        "data": {"message": "Low battery"},
                    }
                ],
            }
        ]
        test_file = config_dir / "test_automation.yaml"
        with open(test_file, "w") as f:
            yaml.dump(automation_data, f)
        assert validator.validate_file_references(test_file) is True
        assert len(validator.errors) == 0

    def test_invalid_uuid(self, config_dir, validator):
        automation_data = [
            {
                "id": "test_automation",
                "alias": "Test Device Automation",
                "triggers": [
                    {
                        "entity_id": "ffffffffffffffffffffffffffffffff",
                        "platform": "state",
                    }
                ],
            }
        ]
        test_file = config_dir / "test_automation.yaml"
        with open(test_file, "w") as f:
            yaml.dump(automation_data, f)
        assert validator.validate_file_references(test_file) is False
        assert any("Unknown entity registry ID" in e for e in validator.errors)

    def test_disabled_entity_uuid(self, config_dir, validator):
        automation_data = [
            {
                "id": "test_automation",
                "triggers": [
                    {
                        "entity_id": "11223344556677889900aabbccddeeff",
                        "platform": "state",
                    }
                ],
            }
        ]
        test_file = config_dir / "test_automation.yaml"
        with open(test_file, "w") as f:
            yaml.dump(automation_data, f)
        assert validator.validate_file_references(test_file) is True
        assert any("disabled entity" in w for w in validator.warnings)

    def test_mixed_entity_formats(self, config_dir, validator):
        automation_data = [
            {
                "id": "mixed_automation",
                "triggers": [
                    {
                        "platform": "state",
                        "entity_id": "binary_sensor.test_motion_battery",
                    },
                    {
                        "entity_id": "88a52f17bf43cb276836f06ac5c07444",
                        "platform": "device",
                    },
                ],
            }
        ]
        test_file = config_dir / "test_automation.yaml"
        with open(test_file, "w") as f:
            yaml.dump(automation_data, f)
        assert validator.validate_file_references(test_file) is True
        assert len(validator.errors) == 0


class TestExtractEntityReferencesUUID:
    def test_excludes_uuids(self, validator):
        data = {
            "entity_id": "sensor.normal_entity",
            "triggers": [
                {
                    "entity_id": "88a52f17bf43cb276836f06ac5c07444",
                    "platform": "state",
                },
                {
                    "entity_id": "binary_sensor.another_sensor",
                    "platform": "state",
                },
            ],
        }
        entity_refs = validator.extract_entity_references(data)
        assert entity_refs == {"sensor.normal_entity", "binary_sensor.another_sensor"}


class TestIsTemplate:
    def test_valid_templates(self, setup_config):
        v = ReferenceValidator(str(setup_config))
        assert v.is_template("{{ states('sensor.temperature') }}") is True
        assert (
            v.is_template(
                "Temperature is {{ state_attr('sensor.temp', 'value') }}\u00b0C"
            )
            is True
        )
        assert v.is_template("{{states('binary_sensor.motion')}}") is True
        assert v.is_template("Value: {{ 25 + 5 }}") is True

    def test_non_templates(self, setup_config):
        v = ReferenceValidator(str(setup_config))
        assert v.is_template("sensor.temperature") is False
        assert v.is_template("normal text") is False
        assert v.is_template("{ single brace }") is False
        assert v.is_template("") is False

    def test_detects_control_flow(self, setup_config):
        v = ReferenceValidator(str(setup_config))
        assert v.is_template("{% if true %}sensor.a{% endif %}") is True
        assert v.is_template("{%- if x -%}sensor.a{%- endif -%}") is True


class TestShouldSkipEntityValidation:
    def test_skips_ha_tags(self, validator):
        assert validator.should_skip_entity_validation("!input sensor_name") is True
        assert validator.should_skip_entity_validation("!secret api_key") is True
        assert validator.should_skip_entity_validation("!include entities.yaml") is True

    def test_skips_uuids(self, validator):
        assert (
            validator.should_skip_entity_validation("88a52f17bf43cb276836f06ac5c07444")
            is True
        )

    def test_skips_templates(self, validator):
        assert (
            validator.should_skip_entity_validation("{{ states('sensor.temp') }}")
            is True
        )
        assert (
            validator.should_skip_entity_validation("Temperature {{ sensor.temp }}")
            is True
        )

    def test_skips_special_keywords(self, validator):
        assert validator.should_skip_entity_validation("all") is True
        assert validator.should_skip_entity_validation("none") is True

    def test_does_not_skip_normal_entities(self, validator):
        assert validator.should_skip_entity_validation("sensor.temperature") is False
        assert validator.should_skip_entity_validation("binary_sensor.motion") is False
        assert validator.should_skip_entity_validation("light.living_room") is False


class TestExtractEntityReferencesFiltering:
    def test_skips_templates(self, validator):
        data = {
            "entity_id": "sensor.normal",
            "entity_ids": [
                "{{ states('sensor.template') }}",
                "binary_sensor.door",
                "all",
                "none",
            ],
        }
        entity_refs = validator.extract_entity_references(data)
        assert entity_refs == {"sensor.normal", "binary_sensor.door"}

    def test_skips_blueprint_inputs(self, validator):
        data = {
            "entity_id": "!input motion_sensor",
            "entity_ids": [
                "!input door_sensor",
                "binary_sensor.actual_door",
                "!secret api_entity",
            ],
        }
        entity_refs = validator.extract_entity_references(data)
        assert entity_refs == {"binary_sensor.actual_door"}


class TestValidateFileWithMixedEntityTypes:
    def test_templates_uuids_and_normal(self, config_dir, validator):
        automation_data = [
            {
                "id": "complex_automation",
                "alias": "Complex Mixed Automation",
                "trigger": {
                    "platform": "template",
                    "value_template": "{{ states('sensor.complex') == 'on' }}",
                },
                "condition": [
                    {
                        "condition": "state",
                        "entity_id": "88a52f17bf43cb276836f06ac5c07444",
                        "state": "on",
                    }
                ],
                "action": [
                    {
                        "service": "light.turn_on",
                        "target": {"entity_id": ["all"]},
                    },
                    {
                        "service": "notify.send",
                        "data": {"message": "{{ now() }} - Motion detected"},
                    },
                ],
            }
        ]
        test_file = config_dir / "complex_test.yaml"
        with open(test_file, "w") as f:
            yaml.dump(automation_data, f)
        assert validator.validate_file_references(test_file) is True
        assert len(validator.errors) == 0


class TestConfigDefinedEntitiesEfficiency:
    def test_configuration_yaml_opened_once(self, tmp_path):
        """configuration.yaml should be parsed only once even though both
        _extract_from_configuration and _extract_zone_entities use it."""
        storage = tmp_path / ".storage"
        storage.mkdir()
        (tmp_path / "configuration.yaml").write_text(
            "zone:\n  - name: Work\ngroup:\n  my_group:\n    entities: []\n"
        )
        validator = ReferenceValidator(str(tmp_path))

        open_count = 0
        real_open = builtins.open

        def spy(path, *args, **kwargs):
            nonlocal open_count
            if "configuration.yaml" in str(path):
                open_count += 1
            return real_open(path, *args, **kwargs)

        with patch("builtins.open", side_effect=spy):
            validator.get_config_defined_entities()

        assert open_count == 1


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


class TestGetConfigDefinedEntities:
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
        entities = v.get_config_defined_entities()
        assert "binary_sensor.anyone_home" in entities
        assert "sensor.average_temp" in entities

    def test_extracts_automation_entities_from_alias(self, setup_config):
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
        entities = v.get_config_defined_entities()
        # Entity ID is derived from alias, not id field
        assert "automation.morning_lights" in entities

    def test_extracts_script_entities(self, setup_config):
        scripts_yaml = setup_config / "scripts.yaml"
        scripts_yaml.write_text(
            "disable_alarm_timed:\n  alias: Disable Alarm Timed\n  sequence: []\n"
        )
        v = ReferenceValidator(str(setup_config))
        entities = v.get_config_defined_entities()
        assert "script.disable_alarm_timed" in entities

    def test_extracts_scene_entities(self, setup_config):
        scenes_yaml = setup_config / "scenes.yaml"
        scenes_yaml.write_text("- name: Office Night\n  entities: {}\n")
        v = ReferenceValidator(str(setup_config))
        entities = v.get_config_defined_entities()
        assert "scene.office_night" in entities

    def test_includes_builtin_entities(self, setup_config):
        v = ReferenceValidator(str(setup_config))
        entities = v.get_config_defined_entities()
        assert "sun.sun" in entities
        assert "zone.home" in entities

    def test_handles_missing_files(self, setup_config):
        v = ReferenceValidator(str(setup_config))
        entities = v.get_config_defined_entities()
        assert isinstance(entities, set)

    def test_handles_parse_error(self, setup_config):
        (setup_config / "configuration.yaml").write_text("template: !bad_tag\n")
        v = ReferenceValidator(str(setup_config))
        entities = v.get_config_defined_entities()
        # Should handle gracefully and surface warning context.
        assert isinstance(entities, set)
        assert any("Failed to extract entity definitions" in w for w in v.warnings)

    def test_reports_config_defined_entity_summary(self, setup_config):
        (setup_config / "configuration.yaml").write_text("group:\n  test_group: {}\n")
        v = ReferenceValidator(str(setup_config))
        v.get_config_defined_entities()
        assert any("Config-defined entities:" in info for info in v.info)


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

    def test_state_attr_double_quotes(self, setup_config):
        v = ReferenceValidator(str(setup_config))
        result = v.extract_entities_from_template(
            '{{ state_attr("climate.hvac", "temperature") }}'
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

    def test_area_ids_list_skips_templates(self, setup_config):
        v = ReferenceValidator(str(setup_config))
        data = {"area_ids": ["kitchen", "{{ input_area }}"]}
        result = v.extract_area_references(data)
        assert "kitchen" in result
        assert "{{ input_area }}" not in result


class TestExtractEntityReferences:
    def test_entities_in_nested_repeat_sequence(self, setup_config):
        v = ReferenceValidator(str(setup_config))
        data = {
            "repeat": {
                "count": 3,
                "sequence": [
                    {
                        "service": "notify.send",
                        "target": {"entity_id": "sensor.temperature"},
                    }
                ],
            }
        }
        refs = v.extract_entity_references(data)
        assert "sensor.temperature" in refs


class TestGetConfigDefinedEntitiesEdgeCases:
    def test_automation_with_id_but_no_alias(self, setup_config):
        (setup_config / "automations.yaml").write_text(
            "- id: morning_lights_on\n"
            "  trigger:\n    platform: time\n"
            "  action:\n    service: test\n"
        )
        v = ReferenceValidator(str(setup_config))
        entities = v.get_config_defined_entities()
        assert "automation.morning_lights_on" in entities


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
