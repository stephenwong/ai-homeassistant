"""Unit tests for EntityDefinitionExtractor."""

import json

from tools.validators.entity_definitions import EntityDefinitionExtractor


def test_extracts_builtin_entities(tmp_path):
    (tmp_path / ".storage").mkdir(exist_ok=True)
    w, i = [], []
    ext = EntityDefinitionExtractor(tmp_path, tmp_path / ".storage", w, i)
    entities = ext.get_config_defined_entities()
    assert "sun.sun" in entities
    assert "zone.home" in entities


def test_extracts_group_entity(tmp_path):
    (tmp_path / ".storage").mkdir(exist_ok=True)
    (tmp_path / "configuration.yaml").write_text(
        "group:\n  my_group:\n    entities: []\n"
    )
    w, i = [], []
    ext = EntityDefinitionExtractor(tmp_path, tmp_path / ".storage", w, i)
    entities = ext.get_config_defined_entities()
    assert "group.my_group" in entities


def test_extracts_input_helpers(tmp_path):
    (tmp_path / ".storage").mkdir(exist_ok=True)
    (tmp_path / "configuration.yaml").write_text(
        "input_boolean:\n  test_switch:\n    name: Test\n"
    )
    w, i = [], []
    ext = EntityDefinitionExtractor(tmp_path, tmp_path / ".storage", w, i)
    entities = ext.get_config_defined_entities()
    assert "input_boolean.test_switch" in entities


def test_extracts_template_list_entities(tmp_path):
    (tmp_path / ".storage").mkdir(exist_ok=True)
    (tmp_path / "configuration.yaml").write_text(
        "template:\n  - sensor:\n      - name: Anyone Home\n        state: 'on'\n"
    )
    w, i = [], []
    ext = EntityDefinitionExtractor(tmp_path, tmp_path / ".storage", w, i)
    entities = ext.get_config_defined_entities()
    assert "sensor.anyone_home" in entities


def test_extracts_template_dict_entities(tmp_path):
    (tmp_path / ".storage").mkdir(exist_ok=True)
    (tmp_path / "configuration.yaml").write_text(
        "template:\n  sensor:\n    - name: Dict Template\n      state: 'on'\n"
    )
    w, i = [], []
    ext = EntityDefinitionExtractor(tmp_path, tmp_path / ".storage", w, i)
    entities = ext.get_config_defined_entities()
    assert "sensor.dict_template" in entities


def test_extracts_platform_template_sensor(tmp_path):
    (tmp_path / ".storage").mkdir(exist_ok=True)
    (tmp_path / "configuration.yaml").write_text(
        "sensor:\n"
        "  - platform: template\n"
        "    sensors:\n"
        "      custom_temp:\n"
        "        value_template: '{{ 42 }}'\n"
    )
    w, i = [], []
    ext = EntityDefinitionExtractor(tmp_path, tmp_path / ".storage", w, i)
    entities = ext.get_config_defined_entities()
    assert "sensor.custom_temp" in entities


def test_extracts_automation_entity_from_alias(tmp_path):
    (tmp_path / ".storage").mkdir(exist_ok=True)
    (tmp_path / "automations.yaml").write_text(
        "- alias: Morning Lights\n"
        "  trigger:\n"
        "    platform: time\n"
        "  action:\n"
        "    service: test\n"
    )
    w, i = [], []
    ext = EntityDefinitionExtractor(tmp_path, tmp_path / ".storage", w, i)
    entities = ext.get_config_defined_entities()
    assert "automation.morning_lights" in entities


def test_automation_id_fallback(tmp_path):
    (tmp_path / ".storage").mkdir(exist_ok=True)
    (tmp_path / "automations.yaml").write_text(
        "- id: backup_lights\n"
        "  trigger:\n    platform: time\n"
        "  action:\n    service: test\n"
    )
    w, i = [], []
    ext = EntityDefinitionExtractor(tmp_path, tmp_path / ".storage", w, i)
    entities = ext.get_config_defined_entities()
    assert "automation.backup_lights" in entities


def test_automation_empty_alias_and_id_skipped(tmp_path):
    """When alias is empty and id is only symbols, nothing is added."""
    (tmp_path / ".storage").mkdir(exist_ok=True)
    (tmp_path / "automations.yaml").write_text(
        "- alias:\n  trigger:\n    platform: time\n  action:\n    service: test\n"
    )
    w, i = [], []
    ext = EntityDefinitionExtractor(tmp_path, tmp_path / ".storage", w, i)
    entities = ext.get_config_defined_entities()
    assert not any(e.startswith("automation.") for e in entities)


def test_extracts_script_entity(tmp_path):
    (tmp_path / ".storage").mkdir(exist_ok=True)
    (tmp_path / "scripts.yaml").write_text(
        "disable_alarm_timed:\n  alias: Disable Alarm\n  sequence: []\n"
    )
    w, i = [], []
    ext = EntityDefinitionExtractor(tmp_path, tmp_path / ".storage", w, i)
    entities = ext.get_config_defined_entities()
    assert "script.disable_alarm_timed" in entities


def test_script_invalid_object_id_skipped(tmp_path):
    (tmp_path / ".storage").mkdir(exist_ok=True)
    (tmp_path / "scripts.yaml").write_text(
        "UPPERCASE_SCRIPT:\n  sequence: []\nvalid_script:\n  sequence: []\n"
    )
    w, i = [], []
    ext = EntityDefinitionExtractor(tmp_path, tmp_path / ".storage", w, i)
    entities = ext.get_config_defined_entities()
    assert "script.UPPERCASE_SCRIPT" not in entities
    assert "script.valid_script" in entities


def test_extracts_scene_entity(tmp_path):
    (tmp_path / ".storage").mkdir(exist_ok=True)
    (tmp_path / "scenes.yaml").write_text("- name: Office Night\n  entities: {}\n")
    w, i = [], []
    ext = EntityDefinitionExtractor(tmp_path, tmp_path / ".storage", w, i)
    entities = ext.get_config_defined_entities()
    assert "scene.office_night" in entities


def test_scene_name_slugified(tmp_path):
    (tmp_path / ".storage").mkdir(exist_ok=True)
    (tmp_path / "scenes.yaml").write_text("- name: Evening Mode!!\n  entities: {}\n")
    w, i = [], []
    ext = EntityDefinitionExtractor(tmp_path, tmp_path / ".storage", w, i)
    entities = ext.get_config_defined_entities()
    assert "scene.evening_mode" in entities


def test_extracts_zone_from_config_yaml(tmp_path):
    (tmp_path / ".storage").mkdir(exist_ok=True)
    (tmp_path / "configuration.yaml").write_text("zone:\n  - name: Work\n")
    w, i = [], []
    ext = EntityDefinitionExtractor(tmp_path, tmp_path / ".storage", w, i)
    entities = ext.get_config_defined_entities()
    assert "zone.work" in entities


def test_extracts_zone_from_storage(tmp_path):
    (tmp_path / ".storage").mkdir(exist_ok=True)
    zone_data = {"data": {"items": [{"name": "Back Yard"}, {"name": ""}]}}
    (tmp_path / ".storage" / "core.zone").write_text(json.dumps(zone_data))
    w, i = [], []
    ext = EntityDefinitionExtractor(tmp_path, tmp_path / ".storage", w, i)
    entities = ext.get_config_defined_entities()
    assert "zone.back_yard" in entities


def test_handles_missing_configuration_yaml(tmp_path):
    (tmp_path / ".storage").mkdir(exist_ok=True)
    w, i = [], []
    ext = EntityDefinitionExtractor(tmp_path, tmp_path / ".storage", w, i)
    entities = ext.get_config_defined_entities()
    assert "sun.sun" in entities


def test_handles_parse_error(tmp_path):
    (tmp_path / ".storage").mkdir(exist_ok=True)
    (tmp_path / "configuration.yaml").write_text("template: !bad_tag\n")
    w, i = [], []
    ext = EntityDefinitionExtractor(tmp_path, tmp_path / ".storage", w, i)
    entities = ext.get_config_defined_entities()
    assert isinstance(entities, set)
    assert any("Failed to extract entity definitions" in w for w in w)


def test_reports_summary(tmp_path):
    (tmp_path / ".storage").mkdir(exist_ok=True)
    (tmp_path / "configuration.yaml").write_text("group:\n  test_group: {}\n")
    w, i = [], []
    ext = EntityDefinitionExtractor(tmp_path, tmp_path / ".storage", w, i)
    ext.get_config_defined_entities()
    assert any("Config-defined entities:" in info for info in i)


def test_caches_result(tmp_path):
    (tmp_path / ".storage").mkdir(exist_ok=True)
    w, i = [], []
    ext = EntityDefinitionExtractor(tmp_path, tmp_path / ".storage", w, i)
    r1 = ext.get_config_defined_entities()
    r2 = ext.get_config_defined_entities()
    assert r1 is r2


def test_restore_state_missing_file(tmp_path):
    (tmp_path / ".storage").mkdir(exist_ok=True)
    w, i = [], []
    ext = EntityDefinitionExtractor(tmp_path, tmp_path / ".storage", w, i)
    result = ext.load_restore_state_entities()
    assert result == set()


def test_restore_state_bad_json(tmp_path):
    (tmp_path / ".storage").mkdir(exist_ok=True)
    (tmp_path / ".storage" / "core.restore_state").write_text("not json")
    w, i = [], []
    ext = EntityDefinitionExtractor(tmp_path, tmp_path / ".storage", w, i)
    result = ext.load_restore_state_entities()
    assert result == set()
    assert any("Failed to load restore state" in msg for msg in w)


def test_restore_state_various_entries(tmp_path):
    (tmp_path / ".storage").mkdir(exist_ok=True)
    data = {
        "data": [
            "not_a_dict",
            {"state": "not_a_dict"},
            {"state": {"entity_id": 123}},
            {"state": {"entity_id": "no_dot"}},
            {"state": {"entity_id": "sensor.restored"}},
        ]
    }
    (tmp_path / ".storage" / "core.restore_state").write_text(json.dumps(data))
    w, i = [], []
    ext = EntityDefinitionExtractor(tmp_path, tmp_path / ".storage", w, i)
    result = ext.load_restore_state_entities()
    assert result == {"sensor.restored"}


def test_restore_state_cache(tmp_path):
    (tmp_path / ".storage").mkdir(exist_ok=True)
    w, i = [], []
    ext = EntityDefinitionExtractor(tmp_path, tmp_path / ".storage", w, i)
    r1 = ext.load_restore_state_entities()
    r2 = ext.load_restore_state_entities()
    assert r1 is r2


def test_shared_warnings_append_to_validator(tmp_path):
    """Warnings/info lists shared with the validator get populated."""
    (tmp_path / ".storage").mkdir(exist_ok=True)
    (tmp_path / ".storage" / "core.restore_state").write_text("bad json")
    w, i = [], []
    ext = EntityDefinitionExtractor(tmp_path, tmp_path / ".storage", w, i)
    ext.load_restore_state_entities()
    shared_before = len(w)
    ext.load_restore_state_entities()
    assert len(w) == shared_before  # no new warnings on cache hit


def test_shared_info_append(tmp_path):
    """Extraction summary info appears in shared list."""
    (tmp_path / ".storage").mkdir(exist_ok=True)
    w, i = [], []
    ext = EntityDefinitionExtractor(tmp_path, tmp_path / ".storage", w, i)
    ext.get_config_defined_entities()
    assert any("Config-defined entities:" in msg for msg in i)
