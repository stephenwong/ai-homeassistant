#!/usr/bin/env python3
"""Unit tests for reference_validator.py UUID support."""

import json

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


class TestIsTemplateBasic:
    def test_valid_templates(self, validator):
        assert validator.is_template("{{ states('sensor.temperature') }}") is True
        assert (
            validator.is_template(
                "Temperature is {{ state_attr('sensor.temp', 'value') }}\u00b0C"
            )
            is True
        )
        assert validator.is_template("{{states('binary_sensor.motion')}}") is True
        assert validator.is_template("Value: {{ 25 + 5 }}") is True

    def test_non_templates(self, validator):
        assert validator.is_template("sensor.temperature") is False
        assert validator.is_template("normal text") is False
        assert validator.is_template("{ single brace }") is False
        assert validator.is_template("") is False


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
