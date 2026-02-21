"""Tests for tools/yaml_validator.py - YAML syntax validation."""

import shutil
import tempfile
from pathlib import Path

import pytest
import yaml

from tools.yaml_validator import YAMLValidator


@pytest.fixture
def config_dir():
    temp = tempfile.mkdtemp()
    yield Path(temp)
    shutil.rmtree(temp)


@pytest.fixture
def validator(config_dir):
    return YAMLValidator(str(config_dir))


class TestValidateYamlSyntax:
    def test_valid_yaml(self, config_dir, validator):
        f = config_dir / "test.yaml"
        f.write_text("key: value\nlist:\n  - a\n  - b\n")
        assert validator.validate_yaml_syntax(f) is True
        assert len(validator.errors) == 0

    def test_invalid_yaml(self, config_dir, validator):
        f = config_dir / "test.yaml"
        f.write_text("key: value\n  bad indent: oops\n")
        assert validator.validate_yaml_syntax(f) is False
        assert any("YAML syntax error" in e for e in validator.errors)

    def test_non_utf8_encoding(self, config_dir, validator):
        f = config_dir / "test.yaml"
        f.write_bytes(b"\xff\xfe key: value")
        assert validator.validate_yaml_syntax(f) is False


class TestValidateFileEncoding:
    def test_utf8_file(self, config_dir, validator):
        f = config_dir / "test.yaml"
        f.write_text("key: value", encoding="utf-8")
        assert validator.validate_file_encoding(f) is True

    def test_non_utf8_file(self, config_dir, validator):
        f = config_dir / "test.yaml"
        f.write_bytes(b"\xff\xfe\x00\x01invalid utf8")
        assert validator.validate_file_encoding(f) is False
        assert any("UTF-8" in e for e in validator.errors)


class TestValidateConfigurationStructure:
    def test_non_configuration_yaml_skipped(self, config_dir, validator):
        f = config_dir / "other.yaml"
        f.write_text("key: value")
        assert validator.validate_configuration_structure(f, {"key": "value"}) is True

    def test_valid_configuration(self, config_dir, validator):
        f = config_dir / "configuration.yaml"
        content = "homeassistant:\n  name: Test\n"
        f.write_text(content)
        assert validator.validate_configuration_structure(f, yaml.safe_load(content)) is True
        assert len(validator.errors) == 0

    def test_configuration_not_dict(self, config_dir, validator):
        f = config_dir / "configuration.yaml"
        content = "- item1\n- item2\n"
        f.write_text(content)
        assert validator.validate_configuration_structure(f, yaml.safe_load(content)) is False
        assert any("must be a dictionary" in e for e in validator.errors)

    def test_configuration_missing_homeassistant(self, config_dir, validator):
        f = config_dir / "configuration.yaml"
        content = "logger:\n  default: info\n"
        f.write_text(content)
        validator.validate_configuration_structure(f, yaml.safe_load(content))
        assert any("homeassistant" in w for w in validator.warnings)

    def test_configuration_deprecated_keys(self, config_dir, validator):
        f = config_dir / "configuration.yaml"
        content = "homeassistant:\n  name: Test\ndiscovery:\nintroduction:\n"
        f.write_text(content)
        validator.validate_configuration_structure(f, yaml.safe_load(content))
        assert any("discovery" in w and "deprecated" in w for w in validator.warnings)
        assert any(
            "introduction" in w and "deprecated" in w for w in validator.warnings
        )

    def test_configuration_homeassistant_not_dict(self, config_dir, validator):
        f = config_dir / "configuration.yaml"
        content = "homeassistant: null\n"
        f.write_text(content)
        validator.validate_configuration_structure(f, yaml.safe_load(content))
        assert any("homeassistant" in w for w in validator.warnings)


class TestValidateAutomationsStructure:
    def test_non_automations_yaml_skipped(self, config_dir, validator):
        f = config_dir / "other.yaml"
        f.write_text("key: value")
        assert validator.validate_automations_structure(f, {"key": "value"}) is True

    def test_empty_automations(self, config_dir, validator):
        f = config_dir / "automations.yaml"
        f.write_text("")
        assert validator.validate_automations_structure(f, None) is True

    def test_valid_automations(self, config_dir, validator):
        f = config_dir / "automations.yaml"
        content = (
            "- alias: Test\n  trigger:\n    platform: state\n"
            "  action:\n    service: test\n"
        )
        f.write_text(content)
        assert validator.validate_automations_structure(f, yaml.safe_load(content)) is True

    def test_automations_not_list(self, config_dir, validator):
        f = config_dir / "automations.yaml"
        content = "key: value\n"
        f.write_text(content)
        assert validator.validate_automations_structure(f, yaml.safe_load(content)) is False
        assert any("must be a list" in e for e in validator.errors)


class TestValidateScriptsStructure:
    def test_non_scripts_yaml_skipped(self, config_dir, validator):
        f = config_dir / "other.yaml"
        f.write_text("key: value")
        assert validator.validate_scripts_structure(f, {"key": "value"}) is True

    def test_empty_scripts(self, config_dir, validator):
        f = config_dir / "scripts.yaml"
        f.write_text("")
        assert validator.validate_scripts_structure(f, None) is True

    def test_valid_scripts(self, config_dir, validator):
        f = config_dir / "scripts.yaml"
        content = "my_script:\n  sequence:\n    - service: test\n"
        f.write_text(content)
        assert validator.validate_scripts_structure(f, yaml.safe_load(content)) is True

    def test_scripts_not_dict(self, config_dir, validator):
        f = config_dir / "scripts.yaml"
        content = "- item1\n- item2\n"
        f.write_text(content)
        assert validator.validate_scripts_structure(f, yaml.safe_load(content)) is False
        assert any("must be a dictionary" in e for e in validator.errors)


class TestValidateAll:
    def test_nonexistent_config_dir(self):
        v = YAMLValidator("/nonexistent/path")
        assert v.validate_all() is False
        assert any("does not exist" in e for e in v.errors)

    def test_empty_config_dir(self, config_dir, validator):
        assert validator.validate_all() is True
        assert any("No YAML files" in w for w in validator.warnings)

    def test_skips_secrets_yaml(self, config_dir, validator):
        (config_dir / "secrets.yaml").write_text("api_key: secret123\n")
        (config_dir / "configuration.yaml").write_text("homeassistant:\n  name: Test\n")
        assert validator.validate_all() is True

    def test_validates_all_files(self, config_dir, validator):
        (config_dir / "configuration.yaml").write_text("homeassistant:\n  name: Test\n")
        (config_dir / "automations.yaml").write_text(
            "- alias: Test\n  trigger:\n    platform: state\n"
            "  action:\n    service: test\n"
        )
        (config_dir / "scripts.yaml").write_text(
            "my_script:\n  sequence:\n    - service: test\n"
        )
        assert validator.validate_all() is True

    def test_stops_on_encoding_error(self, config_dir, validator):
        (config_dir / "bad.yaml").write_bytes(b"\xff\xfe\x00\x01")
        assert validator.validate_all() is False

    def test_stops_on_syntax_error(self, config_dir, validator):
        (config_dir / "bad.yaml").write_text("key: value\n  bad: indent\n")
        assert validator.validate_all() is False


class TestYAMLValidatorMain:
    """Cover lines 149-164: main() function."""

    def test_main_valid(self, config_dir, monkeypatch):

        from tools.yaml_validator import main

        (config_dir / "configuration.yaml").write_text("homeassistant:\n  name: Test\n")
        monkeypatch.setattr("sys.argv", ["yaml_validator", str(config_dir)])
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 0

    def test_main_invalid(self, monkeypatch):
        from tools.yaml_validator import main

        monkeypatch.setattr("sys.argv", ["yaml_validator", "/nonexistent"])
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 1
