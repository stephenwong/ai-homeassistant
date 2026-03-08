"""Tests for tools/common.py - shared utilities."""

import os
import shutil
import tempfile
from pathlib import Path

import yaml

from tools.common import (
    DEFAULT_HA_URL,
    HAYamlLoader,
    ValidatorBase,
    get_env_int,
    load_env_file,
    validate_ha_url,
)


class TestHAYamlLoader:
    """Test HA-specific YAML tag handling."""

    def test_include_tag(self):
        result = yaml.load("key: !include file.yaml", Loader=HAYamlLoader)
        assert result == {"key": "!include file.yaml"}

    def test_include_dir_named_tag(self):
        result = yaml.load("key: !include_dir_named mydir", Loader=HAYamlLoader)
        assert result == {"key": "!include_dir_named mydir"}

    def test_include_dir_merge_named_tag(self):
        result = yaml.load("key: !include_dir_merge_named mydir", Loader=HAYamlLoader)
        assert result == {"key": "!include_dir_merge_named mydir"}

    def test_include_dir_merge_list_tag(self):
        result = yaml.load("key: !include_dir_merge_list mydir", Loader=HAYamlLoader)
        assert result == {"key": "!include_dir_merge_list mydir"}

    def test_include_dir_list_tag(self):
        result = yaml.load("key: !include_dir_list mydir", Loader=HAYamlLoader)
        assert result == {"key": "!include_dir_list mydir"}

    def test_input_tag(self):
        result = yaml.load("key: !input sensor_name", Loader=HAYamlLoader)
        assert result == {"key": "!input sensor_name"}

    def test_secret_tag(self):
        result = yaml.load("key: !secret api_key", Loader=HAYamlLoader)
        assert result == {"key": "!secret api_key"}


class TestLoadEnvFile:
    """Test .env file loading."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.original_env = os.environ.copy()

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)
        # Restore env
        os.environ.clear()
        os.environ.update(self.original_env)

    def test_load_env_file_sets_variables(self, monkeypatch):
        env_content = 'HA_TOKEN=test_token_123\nHA_URL="http://localhost:8123"\n'
        # Create .env in the parent of tools/
        env_path = Path(__file__).parent.parent / ".env"
        existed = env_path.exists()
        old_content = env_path.read_text() if existed else None

        try:
            env_path.write_text(env_content)
            load_env_file()
            assert os.environ.get("HA_TOKEN") == "test_token_123"
            assert os.environ.get("HA_URL") == "http://localhost:8123"
        finally:
            if existed and old_content is not None:
                env_path.write_text(old_content)
            elif not existed:
                env_path.unlink(missing_ok=True)

    def test_load_env_file_skips_comments(self, monkeypatch):
        env_path = Path(__file__).parent.parent / ".env"
        existed = env_path.exists()
        old_content = env_path.read_text() if existed else None

        try:
            env_path.write_text("# This is a comment\nTEST_VAR=value\n")
            load_env_file()
            assert os.environ.get("TEST_VAR") == "value"
        finally:
            if existed and old_content is not None:
                env_path.write_text(old_content)
            elif not existed:
                env_path.unlink(missing_ok=True)

    def test_load_env_file_skips_empty_lines(self, monkeypatch):
        env_path = Path(__file__).parent.parent / ".env"
        existed = env_path.exists()
        old_content = env_path.read_text() if existed else None

        try:
            env_path.write_text("\n\nTEST_EMPTY=works\n\n")
            load_env_file()
            assert os.environ.get("TEST_EMPTY") == "works"
        finally:
            if existed and old_content is not None:
                env_path.write_text(old_content)
            elif not existed:
                env_path.unlink(missing_ok=True)


class TestGetEnvInt:
    def test_missing_env_uses_default(self, monkeypatch):
        monkeypatch.delenv("HA_REQUEST_TIMEOUT", raising=False)
        value, warning = get_env_int("HA_REQUEST_TIMEOUT", 10)
        assert value == 10
        assert warning is None

    def test_valid_integer_env(self, monkeypatch):
        monkeypatch.setenv("HA_REQUEST_TIMEOUT", "25")
        value, warning = get_env_int("HA_REQUEST_TIMEOUT", 10)
        assert value == 25
        assert warning is None

    def test_invalid_integer_env_warns_and_falls_back(self, monkeypatch):
        monkeypatch.setenv("HA_REQUEST_TIMEOUT", "abc")
        value, warning = get_env_int("HA_REQUEST_TIMEOUT", 10)
        assert value == 10
        assert warning is not None
        assert "must be an integer" in warning

    def test_below_minimum_warns_and_falls_back(self, monkeypatch):
        monkeypatch.setenv("HA_REQUEST_TIMEOUT", "0")
        value, warning = get_env_int("HA_REQUEST_TIMEOUT", 10)
        assert value == 10
        assert warning is not None
        assert "must be >=" in warning


class TestValidateHAURL:
    def test_valid_http_url(self):
        assert validate_ha_url("http://homeassistant.local:8123") is None

    def test_valid_https_url(self):
        assert validate_ha_url("https://example.com") is None

    def test_missing_scheme_is_invalid(self):
        error = validate_ha_url("homeassistant.local:8123")
        assert error is not None
        assert "http://" in error

    def test_missing_host_is_invalid(self):
        error = validate_ha_url("http://")
        assert error is not None
        assert "hostname" in error

    def test_default_ha_url_is_valid(self):
        assert validate_ha_url(DEFAULT_HA_URL) is None


class TestValidatorBase:
    """Test ValidatorBase class."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config_dir = Path(self.temp_dir)

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)

    def test_init_sets_defaults(self):
        v = ValidatorBase(str(self.config_dir))
        assert v.config_dir == self.config_dir
        assert v.errors == []
        assert v.warnings == []
        assert v.info == []

    def test_get_yaml_files(self):
        (self.config_dir / "test.yaml").write_text("key: value")
        (self.config_dir / "test.yml").write_text("key: value")
        (self.config_dir / "test.txt").write_text("not yaml")

        v = ValidatorBase(str(self.config_dir))
        yaml_files = v.get_yaml_files()
        names = {f.name for f in yaml_files}
        assert "test.yaml" in names
        assert "test.yml" in names
        assert "test.txt" not in names

    def test_load_yaml(self):
        test_file = self.config_dir / "test.yaml"
        test_file.write_text("key: value\nlist:\n  - item1\n  - item2\n")

        v = ValidatorBase(str(self.config_dir))
        data = v.load_yaml(test_file)
        assert data == {"key": "value", "list": ["item1", "item2"]}

    def test_load_yaml_with_ha_tags(self):
        test_file = self.config_dir / "test.yaml"
        test_file.write_text("secret: !secret my_password\n")

        v = ValidatorBase(str(self.config_dir))
        data = v.load_yaml(test_file)
        assert data == {"secret": "!secret my_password"}

    def test_check_automations_structure_valid(self):
        v = ValidatorBase(str(self.config_dir))
        automations = [
            {
                "alias": "Test",
                "trigger": {"platform": "state"},
                "action": {"service": "test"},
            },
        ]
        assert v.check_automations_structure(automations, "test") is True
        assert len(v.errors) == 0

    def test_check_automations_structure_blueprint(self):
        v = ValidatorBase(str(self.config_dir))
        automations = [
            {"alias": "Blueprint", "use_blueprint": {"path": "test.yaml"}},
        ]
        assert v.check_automations_structure(automations, "test") is True

    def test_check_automations_structure_not_dict(self):
        v = ValidatorBase(str(self.config_dir))
        automations = ["not a dict"]
        assert v.check_automations_structure(automations, "test") is False
        assert any("must be a dictionary" in e for e in v.errors)

    def test_check_automations_structure_missing_trigger(self):
        v = ValidatorBase(str(self.config_dir))
        automations = [{"alias": "Test", "action": {"service": "test"}}]
        assert v.check_automations_structure(automations, "test") is False
        assert any("trigger" in e for e in v.errors)

    def test_check_automations_structure_missing_action(self):
        v = ValidatorBase(str(self.config_dir))
        automations = [
            {"alias": "Test", "trigger": {"platform": "state"}},
        ]
        assert v.check_automations_structure(automations, "test") is False
        assert any("action" in e for e in v.errors)

    def test_check_automations_structure_missing_alias_warning(self):
        v = ValidatorBase(str(self.config_dir))
        automations = [
            {"trigger": {"platform": "state"}, "action": {"service": "test"}},
        ]
        v.check_automations_structure(automations, "test")
        assert any("alias" in w for w in v.warnings)

    def test_check_scripts_structure_valid(self):
        v = ValidatorBase(str(self.config_dir))
        scripts = {"my_script": {"sequence": [{"service": "test"}]}}
        assert v.check_scripts_structure(scripts, "test") is True

    def test_check_scripts_structure_blueprint(self):
        v = ValidatorBase(str(self.config_dir))
        scripts = {"my_script": {"use_blueprint": {"path": "test.yaml"}}}
        assert v.check_scripts_structure(scripts, "test") is True

    def test_check_scripts_structure_not_dict(self):
        v = ValidatorBase(str(self.config_dir))
        scripts = {"my_script": "not a dict"}
        assert v.check_scripts_structure(scripts, "test") is False
        assert any("must be a dictionary" in e for e in v.errors)

    def test_check_scripts_structure_missing_sequence(self):
        v = ValidatorBase(str(self.config_dir))
        scripts = {"my_script": {"alias": "Test"}}
        assert v.check_scripts_structure(scripts, "test") is False
        assert any("sequence" in e or "use_blueprint" in e for e in v.errors)

    def test_print_results_valid(self, capsys):
        v = ValidatorBase(str(self.config_dir))
        v.print_results()
        captured = capsys.readouterr()
        assert "is valid!" in captured.out

    def test_print_results_with_errors(self, capsys):
        v = ValidatorBase(str(self.config_dir))
        v.errors.append("Test error")
        v.print_results()
        captured = capsys.readouterr()
        assert "Test error" in captured.out
        assert "validation failed" in captured.out

    def test_print_results_with_warnings_only(self, capsys):
        v = ValidatorBase(str(self.config_dir))
        v.warnings.append("Test warning")
        v.print_results()
        captured = capsys.readouterr()
        assert "Test warning" in captured.out
        assert "with warnings" in captured.out

    def test_print_results_with_info(self, capsys):
        v = ValidatorBase(str(self.config_dir))
        v.info.append("Test info")
        v.print_results()
        captured = capsys.readouterr()
        assert "Test info" in captured.out
