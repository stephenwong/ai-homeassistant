#!/usr/bin/env python3
"""Unit tests for reference_validator.py UUID support."""

import builtins
import json
from unittest.mock import patch

import pytest
import yaml

from tools.validators.references import ReferenceValidator


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

    def test_extracts_uuids_from_entity_ids_list(self, validator):
        data = {
            "entity_ids": [
                "aabbccddeeff00112233445566778899",
                "00000000000000000000000000000000",
            ]
        }
        refs = validator.extract_entity_registry_ids(data)
        assert "aabbccddeeff00112233445566778899" in refs
        assert "00000000000000000000000000000000" in refs

    def test_extracts_uuids_from_list_valued_entity_id(self, validator):
        data = {"entity_id": ["aabbccddeeff00112233445566778899"]}
        refs = validator.extract_entity_registry_ids(data)
        assert "aabbccddeeff00112233445566778899" in refs


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

    def test_extracts_scene_entities_dict_keys(self, setup_config):
        """Scene entities dict keys are entity references (H4 fix)."""
        v = ReferenceValidator(str(setup_config))
        data = {
            "entities": {
                "light.kitchen": {"state": "on"},
                "light.unknown": {"state": "off"},
            }
        }
        refs = v.extract_entity_references(data)
        assert "light.kitchen" in refs
        assert "light.unknown" in refs


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
        assert "AVAILABLE ENTITIES" in captured.err
        assert "sensor" in captured.err
        assert "light" in captured.err

    def test_summary_mode_compact_format(self, setup_config, capsys):
        v = ReferenceValidator(str(setup_config), summary=True)
        v.print_results()
        captured = capsys.readouterr()
        assert "AVAILABLE ENTITIES" not in captured.out
        assert (
            "PASS" in captured.out
            or "Entity/device references is valid" in captured.out
        )

    def test_summary_mode_no_emoji(self, setup_config, capsys):
        v = ReferenceValidator(str(setup_config), summary=True)
        v.print_results()
        captured = capsys.readouterr()
        assert "\u2705" not in captured.out
        assert "\u274c" not in captured.out

    def test_summary_mode_failure_shows_errors(self, setup_config, capsys):
        v = ReferenceValidator(str(setup_config), summary=True)
        v.errors.append("Something went wrong")
        v.print_results()
        captured = capsys.readouterr()
        assert "FAIL" in captured.out
        assert "Something went wrong" in captured.err

    def test_summary_mode_warning_shows_warn(self, setup_config, capsys):
        v = ReferenceValidator(str(setup_config), summary=True)
        v.warnings.append("A warning occurred")
        v.print_results()
        captured = capsys.readouterr()
        assert "PASS" in captured.out
        assert "with warnings" in captured.out
        assert "A warning occurred" in captured.err


class TestReferenceValidatorMain:
    """Cover lines 509-524: main() function."""

    def test_main_valid(self, setup_config, monkeypatch):
        from tools.validators.references import main

        (setup_config / "automations.yaml").write_text(
            "entity_id: sensor.temperature\n"
        )
        monkeypatch.setattr("sys.argv", ["reference_validator", str(setup_config)])
        assert main() == 0

    def test_main_invalid(self, monkeypatch):
        from tools.validators.references import main

        monkeypatch.setattr("sys.argv", ["reference_validator", "/nonexistent"])
        assert main() == 1


class TestCoverageExtras:
    """Coverage Phase 0: remaining uncovered branches in references.py."""

    def test_file_deps(self, setup_config):
        v = ReferenceValidator(str(setup_config))
        deps = v.file_deps()
        assert isinstance(deps, list)
        assert "*.yaml" in deps

    def test_load_restore_state_cache(self, setup_config):
        v = ReferenceValidator(str(setup_config))
        r1 = v.load_restore_state_entities()
        r2 = v.load_restore_state_entities()
        assert r1 is r2

    def test_load_restore_state_bad_json(self, setup_config):
        restore_file = setup_config / ".storage" / "core.restore_state"
        restore_file.write_text("not json")
        v = ReferenceValidator(str(setup_config))
        result = v.load_restore_state_entities()
        assert result == set()
        assert any("Failed to load restore state" in w for w in v.warnings)

    def test_load_restore_state_various_entries(self, tmp_path):
        storage = tmp_path / ".storage"
        storage.mkdir()
        data = {
            "data": [
                "not_a_dict",
                {"state": "not_a_dict"},
                {"state": {"entity_id": 123}},
                {"state": {"entity_id": "no_dot"}},
                {"state": {"entity_id": "sensor.restored"}},
            ]
        }
        (storage / "core.restore_state").write_text(json.dumps(data))
        v = ReferenceValidator(str(tmp_path))
        result = v.load_restore_state_entities()
        assert result == {"sensor.restored"}

    def test_get_config_defined_entities_cache(self, setup_config):
        v = ReferenceValidator(str(setup_config))
        r1 = v.get_config_defined_entities()
        r2 = v.get_config_defined_entities()
        assert r1 is r2

    def test_extract_all_config_features(self, setup_config):
        config_yaml = setup_config / "configuration.yaml"
        config_yaml.write_text(
            "group:\n"
            "  my_group:\n"
            "    entities: []\n"
            "input_boolean:\n"
            "  test_switch:\n"
            "    name: Test\n"
            "input_number:\n"
            "  test_slider:\n"
            "    initial: 5\n"
            "input_text:\n"
            "  test_text:\n"
            "    initial: ''\n"
            "input_select:\n"
            "  test_select:\n"
            "    options: [a]\n"
            "input_datetime:\n"
            "  test_date:\n"
            "input_button:\n"
            "  test_button:\n"
            "template:\n"
            "  - sensor:\n"
            "      - name: Template One\n"
            "        state: 'on'\n"
            "  - sensor:\n"
            "      - name: Template Two\n"
            "        state: 'off'\n"
            "sensor:\n"
            "  - platform: template\n"
            "    sensors:\n"
            "      custom_temp:\n"
            "        value_template: '{{ 42 }}'\n"
            "binary_sensor:\n"
            "  - platform: template\n"
            "    sensors:\n"
            "      custom_motion:\n"
            "        value_template: '{{ 1 }}'\n"
        )
        v = ReferenceValidator(str(setup_config))
        entities = v.get_config_defined_entities()
        assert "group.my_group" in entities
        assert "input_boolean.test_switch" in entities
        assert "input_number.test_slider" in entities
        assert "input_text.test_text" in entities
        assert "input_select.test_select" in entities
        assert "input_datetime.test_date" in entities
        assert "input_button.test_button" in entities
        assert "sensor.template_one" in entities
        assert "sensor.template_two" in entities
        assert "sensor.custom_temp" in entities
        assert "binary_sensor.custom_motion" in entities

    def test_extract_template_entities_non_dict(self, setup_config):
        config_yaml = setup_config / "configuration.yaml"
        config_yaml.write_text("template:\n  - not_a_dict\n")
        v = ReferenceValidator(str(setup_config))
        entities = v.get_config_defined_entities()
        assert isinstance(entities, set)

    def test_extract_template_entities_default_entity_id(self, setup_config):
        config_yaml = setup_config / "configuration.yaml"
        config_yaml.write_text(
            "template:\n"
            "  - sensor:\n"
            "      - name: Named Only\n"
            "        state: 'on'\n"
            "      - default_entity_id: custom_sensor\n"
            "        state: 'off'\n"
            "      - default_entity_id: sensor.prefixed\n"
            "        state: 'off'\n"
            "  - binary_sensor:\n"
            "      - default_entity_id: custom_binary\n"
            "        state: 'on'\n"
        )
        v = ReferenceValidator(str(setup_config))
        entities = v.get_config_defined_entities()
        assert "sensor.named_only" in entities
        assert "sensor.custom_sensor" in entities
        assert "sensor.prefixed" in entities
        assert "binary_sensor.custom_binary" in entities

    def test_automation_id_fallback(self, setup_config):
        (setup_config / "automations.yaml").write_text(
            "- id: backup_lights\n"
            "  trigger:\n    platform: time\n"
            "  action:\n    service: test\n"
        )
        v = ReferenceValidator(str(setup_config))
        entities = v.get_config_defined_entities()
        assert "automation.backup_lights" in entities

    def test_script_invalid_object_id_skipped(self, setup_config):
        (setup_config / "scripts.yaml").write_text(
            "UPPERCASE_SCRIPT:\n  sequence: []\nvalid_script:\n  sequence: []\n"
        )
        v = ReferenceValidator(str(setup_config))
        entities = v.get_config_defined_entities()
        assert "script.UPPERCASE_SCRIPT" not in entities
        assert "script.valid_script" in entities

    def test_scene_slugify(self, setup_config):
        (setup_config / "scenes.yaml").write_text(
            "- name: Evening Mode!!\n  entities: {}\n"
        )
        v = ReferenceValidator(str(setup_config))
        entities = v.get_config_defined_entities()
        assert "scene.evening_mode" in entities

    def test_zone_storage_json(self, tmp_path):
        storage = tmp_path / ".storage"
        storage.mkdir()
        (storage / "core.entity_registry").write_text('{"data":{"entities":[]}}')
        (storage / "core.device_registry").write_text('{"data":{"devices":[]}}')
        (storage / "core.area_registry").write_text('{"data":{"areas":[]}}')
        zone_data = {"data": {"items": [{"name": "Back Yard"}, {"name": ""}]}}
        (storage / "core.zone").write_text(json.dumps(zone_data))
        v = ReferenceValidator(str(tmp_path))
        entities = v.get_config_defined_entities()
        assert "zone.back_yard" in entities
        assert "zone." not in entities

    def test_validate_uuid_registry_id_known(self, setup_config):
        """UUID referencing a known registry entity_id passes validation."""
        test_file = setup_config / "test.yaml"
        test_file.write_text("entity_id: aabbccddeeff00112233445566778899\n")
        v = ReferenceValidator(str(setup_config))
        assert v.validate_file_references(test_file) is True

    def test_validate_restore_state_diagnostic(self, setup_config):
        restore_file = setup_config / ".storage" / "core.restore_state"
        restore_file.write_text(
            json.dumps({"data": [{"state": {"entity_id": "sensor.old_relic"}}]})
        )
        test_file = setup_config / "test.yaml"
        test_file.write_text("entity_id: sensor.old_relic\n")
        v = ReferenceValidator(str(setup_config))
        assert v.validate_file_references(test_file) is False
        assert any("found in restore state" in w for w in v.warnings)
        assert any("Unknown entity" in e for e in v.errors)

    def test_validate_disabled_entity_behind_registry_id(self, setup_config):
        test_file = setup_config / "test.yaml"
        test_file.write_text("entity_id: ffeeddccbbaa99887766554433221100\n")
        v = ReferenceValidator(str(setup_config))
        assert v.validate_file_references(test_file) is True
        assert any("disabled entity" in w for w in v.warnings)

    def test_validate_unknown_area_warning(self, tmp_path):
        storage = tmp_path / ".storage"
        storage.mkdir()
        (storage / "core.entity_registry").write_text('{"data":{"entities":[]}}')
        (storage / "core.device_registry").write_text('{"data":{"devices":[]}}')
        (storage / "core.area_registry").write_text('{"data":{"areas":[]}}')
        test_file = tmp_path / "test.yaml"
        test_file.write_text("area_id: missing_area\n")
        v = ReferenceValidator(str(tmp_path))
        assert v.validate_file_references(test_file) is True
        assert any("Unknown area" in w for w in v.warnings)

    def test_validate_disabled_entity_warning(self, setup_config):
        """Entity in registry but disabled_by is not None."""
        test_file = setup_config / "test.yaml"
        test_file.write_text("entity_id: sensor.disabled_temp\n")
        v = ReferenceValidator(str(setup_config))
        assert v.validate_file_references(test_file) is True
        assert any("disabled entity" in w for w in v.warnings)

    def test_print_results_quiet(self, setup_config, capsys):
        v = ReferenceValidator(str(setup_config), quiet=True)
        v.print_results()
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_print_results_summary_errors_only(self, setup_config, capsys):
        v = ReferenceValidator(str(setup_config), summary=True)
        v.errors.append("Error one")
        v.print_results()
        captured = capsys.readouterr()
        assert "FAIL" in captured.out
        assert "Error one" in captured.err

    def test_print_results_summary_warnings_only(self, setup_config, capsys):
        v = ReferenceValidator(str(setup_config), summary=True)
        v.warnings.append("Notify only")
        v.print_results()
        captured = capsys.readouterr()
        assert "PASS" in captured.out
        assert "with warnings" in captured.out
        assert "Notify only" in captured.err
