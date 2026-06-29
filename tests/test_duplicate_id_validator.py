"""Unit tests for duplicate_id_validator.py — duplicate automation ID detection."""

import builtins

import pytest
import yaml

from tools.validators.duplicate_ids import DuplicateIDValidator


@pytest.fixture
def validator(config_dir):
    return DuplicateIDValidator(str(config_dir))


class TestFileDeps:
    def test_file_deps_automations_only(self):
        """DuplicateIDValidator only reads automations.yaml (cacheable)."""
        v = DuplicateIDValidator()
        deps = v.file_deps()
        assert "automations.yaml" in deps
        assert len(deps) == 1


class TestNoDuplicates:
    def test_no_duplicates_passes(self, config_dir, validator):
        automations = [
            {
                "id": "morning_lights",
                "alias": "Morning Lights",
                "trigger": [],
                "action": [],
            },
            {
                "id": "motion_light",
                "alias": "Motion Light",
                "trigger": [],
                "action": [],
            },
            {"id": "doorbell", "alias": "Doorbell", "trigger": [], "action": []},
        ]
        f = config_dir / "automations.yaml"
        with open(f, "w") as fh:
            yaml.dump(automations, fh)
        assert validator.validate_all() is True
        assert len(validator.errors) == 0

    def test_duplicate_ids_fail(self, config_dir, validator):
        automations = [
            {"id": "same_id", "alias": "First", "trigger": [], "action": []},
            {"id": "same_id", "alias": "Second", "trigger": [], "action": []},
        ]
        f = config_dir / "automations.yaml"
        with open(f, "w") as fh:
            yaml.dump(automations, fh)
        assert validator.validate_all() is False
        assert any(
            "duplicate" in e.lower() and "same_id" in e for e in validator.errors
        )

    def test_missing_id_warns(self, config_dir, validator):
        automations = [
            {"alias": "No Id Automation", "trigger": [], "action": []},
        ]
        f = config_dir / "automations.yaml"
        with open(f, "w") as fh:
            yaml.dump(automations, fh)
        assert validator.validate_all() is True
        assert any(
            "missing" in w.lower() and "id" in w.lower() for w in validator.warnings
        )

    def test_empty_file_passes(self, config_dir, validator):
        """No automations.yaml at all — nothing to check."""
        assert validator.validate_all() is True

    def test_nonexistent_dir_errors(self):
        v = DuplicateIDValidator("/nonexistent")
        assert v.validate_all() is False
        assert any("does not exist" in e for e in v.errors)

    def test_non_list_automations_handled(self, config_dir, validator):
        f = config_dir / "automations.yaml"
        f.write_text("not_a_list: true\n")
        assert validator.validate_all() is False
        assert any("must be a list" in e for e in validator.errors)

    def test_broken_yaml_fails(self, config_dir, validator):
        f = config_dir / "automations.yaml"
        f.write_text("{{{ not valid yaml\n")
        assert validator.validate_all() is False
        assert any("syntax error" in e.lower() for e in validator.errors)

    def test_empty_file_exists_passes(self, config_dir, validator):
        """File exists but YAML parses to None (empty doc)."""
        f = config_dir / "automations.yaml"
        f.write_text("")
        assert validator.validate_all() is True
        assert len(validator.errors) == 0

    def test_non_dict_entry_handled(self, config_dir, validator):
        automations = [
            "not_a_dict",
            {"id": "ok", "alias": "OK", "trigger": [], "action": []},
        ]
        f = config_dir / "automations.yaml"
        with open(f, "w") as fh:
            yaml.dump(automations, fh)
        assert validator.validate_all() is False
        assert any("must be a dictionary" in e for e in validator.errors)

    def test_mixed_duplicates_and_missing(self, config_dir, validator):
        automations = [
            {"id": "dup", "alias": "First", "trigger": [], "action": []},
            {"alias": "No ID", "trigger": [], "action": []},
            {"id": "dup", "alias": "Second", "trigger": [], "action": []},
        ]
        f = config_dir / "automations.yaml"
        with open(f, "w") as fh:
            yaml.dump(automations, fh)
        assert validator.validate_all() is False
        assert any("duplicate" in e.lower() and "dup" in e for e in validator.errors)
        assert any(
            "missing" in w.lower() and "id" in w.lower() for w in validator.warnings
        )
        assert any("missing 'id'" in i for i in validator.info)

    def test_three_way_duplicate_detected(self, config_dir, validator):
        automations = [
            {"id": "dup", "alias": "A", "trigger": [], "action": []},
            {"id": "dup", "alias": "B", "trigger": [], "action": []},
            {"id": "dup", "alias": "C", "trigger": [], "action": []},
        ]
        f = config_dir / "automations.yaml"
        with open(f, "w") as fh:
            yaml.dump(automations, fh)
        assert validator.validate_all() is False
        dup_errors = [e for e in validator.errors if "duplicate" in e.lower()]
        assert len(dup_errors) == 1
        assert "3 times" in dup_errors[0]

    def test_null_id_treated_as_missing(self, config_dir, validator):
        automations = [
            {"id": None, "alias": "Null ID", "trigger": [], "action": []},
        ]
        f = config_dir / "automations.yaml"
        with open(f, "w") as fh:
            yaml.dump(automations, fh)
        assert validator.validate_all() is True
        assert any(
            "missing" in w.lower() and "id" in w.lower() for w in validator.warnings
        )

    def test_int_id_handled(self, config_dir, validator):
        automations = [
            {"id": 123, "alias": "Int ID", "trigger": [], "action": []},
            {"id": 123, "alias": "Dup Int", "trigger": [], "action": []},
        ]
        f = config_dir / "automations.yaml"
        with open(f, "w") as fh:
            yaml.dump(automations, fh)
        assert validator.validate_all() is False
        assert any("duplicate" in e.lower() and "123" in e for e in validator.errors)


class TestConfigurationYamlOpenedOnce:
    def test_configuration_yaml_not_accessed_unnecessarily(self, config_dir):
        """Validator should not parse configuration.yaml at all — it only reads
        automations.yaml. This is an efficiency regression test."""
        yaml_content = (
            "- id: a\n  alias: A\n  trigger:\n"
            "    platform: state\n  action:\n    service: test\n"
        )
        (config_dir / "automations.yaml").write_text(yaml_content)
        (config_dir / "configuration.yaml").write_text("homeassistant:\n  name: Test\n")

        open_count = 0
        real_open = builtins.open

        def spy(path, *args, **kwargs):
            nonlocal open_count
            if "configuration.yaml" in str(path):
                open_count += 1
            return real_open(path, *args, **kwargs)

        from unittest.mock import patch

        with patch("builtins.open", side_effect=spy):
            v = DuplicateIDValidator(str(config_dir))
            v.validate_all()

        assert open_count == 0


class TestMain:
    def test_main_dispatches_clean(self, config_dir, monkeypatch):
        from tools.validators.duplicate_ids import main

        yaml_content = (
            "- id: a\n  alias: A\n  trigger:\n"
            "    platform: state\n  action:\n    service: test\n"
        )
        (config_dir / "automations.yaml").write_text(yaml_content)
        monkeypatch.setattr("sys.argv", ["duplicate_ids", str(config_dir)])
        assert main() == 0

    def test_main_invalid(self, monkeypatch):
        from tools.validators.duplicate_ids import main

        monkeypatch.setattr("sys.argv", ["duplicate_ids", "/nonexistent"])
        assert main() == 1
