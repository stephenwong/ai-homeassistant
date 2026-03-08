"""Tests for tools/ha_config_validator.py - HA config validation."""

import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tools.ha_config_validator import HAConfigValidator


@pytest.fixture
def config_dir():
    temp = tempfile.mkdtemp()
    yield Path(temp)
    shutil.rmtree(temp)


@pytest.fixture
def validator(config_dir):
    return HAConfigValidator(str(config_dir))


class TestCheckHAInstallation:
    def test_hass_found(self, validator):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "2024.1.0"
        with patch(
            "tools.ha_config_validator.subprocess.run",
            return_value=mock_result,
        ):
            assert validator.check_ha_installation() is True
            assert any("2024.1.0" in i for i in validator.info)

    def test_hass_not_found_python_module_found(self, validator):
        # First call (hass) fails, second call (python -m) succeeds
        mock_success = MagicMock()
        mock_success.returncode = 0
        mock_success.stdout = "2024.2.0"

        with patch(
            "tools.ha_config_validator.subprocess.run",
            side_effect=[FileNotFoundError, mock_success],
        ):
            assert validator.check_ha_installation() is True

    def test_neither_found(self, validator):
        with patch(
            "tools.ha_config_validator.subprocess.run",
            side_effect=FileNotFoundError,
        ):
            assert validator.check_ha_installation() is False
            assert any("not found" in w for w in validator.warnings)

    def test_hass_timeout(self, validator):
        import subprocess

        with patch(
            "tools.ha_config_validator.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="hass", timeout=10),
        ):
            assert validator.check_ha_installation() is False


class TestTimeoutConfiguration:
    def test_uses_timeout_from_env(self, config_dir, monkeypatch):
        monkeypatch.setenv("HA_VALIDATION_TIMEOUT", "75")
        v = HAConfigValidator(str(config_dir))
        assert v.validation_timeout == 75

    def test_invalid_timeout_env_warns_and_falls_back(self, config_dir, monkeypatch):
        monkeypatch.setenv("HA_VALIDATION_TIMEOUT", "not-int")
        v = HAConfigValidator(str(config_dir))
        assert v.validation_timeout == 60
        assert any("HA_VALIDATION_TIMEOUT" in warning for warning in v.warnings)


class TestParseCheckConfigOutput:
    def test_parse_errors(self, validator):
        validator.parse_check_config_output("ERROR: Something went wrong\n")
        assert any("Something went wrong" in e for e in validator.errors)

    def test_parse_warnings(self, validator):
        validator.parse_check_config_output("WARNING: Deprecated feature\n")
        assert any("Deprecated feature" in w for w in validator.warnings)

    def test_parse_success(self, validator):
        validator.parse_check_config_output("Configuration check successful!\n")
        assert any("successful" in i for i in validator.info)

    def test_parse_error_keyword(self, validator):
        validator.parse_check_config_output("There was an error in config\n")
        assert len(validator.errors) > 0

    def test_parse_warning_keyword(self, validator):
        validator.parse_check_config_output("There was a warning about something\n")
        assert len(validator.warnings) > 0

    def test_skip_empty_lines(self, validator):
        validator.parse_check_config_output("\n\n\n")
        assert len(validator.errors) == 0
        assert len(validator.warnings) == 0

    def test_parse_output_entity_with_error_in_name(self, validator):
        validator.parse_check_config_output(
            "Setup of sensor.water_error_code successful\n"
        )
        assert len(validator.errors) == 0


class TestParseCheckConfigErrors:
    def test_parse_stderr_errors(self, validator):
        validator.parse_check_config_errors("something went wrong\n")
        assert len(validator.errors) > 0

    def test_skip_debug_messages(self, validator):
        validator.parse_check_config_errors("DEBUG: test message\n")
        assert len(validator.errors) == 0

    def test_skip_info_messages(self, validator):
        validator.parse_check_config_errors("INFO: starting up\n")
        assert len(validator.errors) == 0

    def test_skip_starting_messages(self, validator):
        validator.parse_check_config_errors("Starting configuration check\n")
        assert len(validator.errors) == 0

    def test_skip_empty_lines(self, validator):
        validator.parse_check_config_errors("\n\n")
        assert len(validator.errors) == 0


class TestRunBasicValidation:
    def test_missing_configuration_yaml(self, config_dir, validator):
        assert validator.run_basic_validation() is False
        assert any("configuration.yaml not found" in e for e in validator.errors)

    def test_configuration_yaml_not_dict(self, config_dir, validator):
        (config_dir / "configuration.yaml").write_text("- item1\n- item2\n")
        assert validator.run_basic_validation() is False
        assert any("must contain a dictionary" in e for e in validator.errors)

    def test_valid_basic_config(self, config_dir, validator):
        (config_dir / "configuration.yaml").write_text(
            "homeassistant:\n  name: Test\n  latitude: 0\n"
            "  longitude: 0\n  time_zone: UTC\n"
        )
        assert validator.run_basic_validation() is True

    def test_missing_homeassistant_section(self, config_dir, validator):
        (config_dir / "configuration.yaml").write_text("logger:\n  default: info\n")
        validator.run_basic_validation()
        assert any("homeassistant" in w for w in validator.warnings)

    def test_yaml_syntax_error(self, config_dir, validator):
        (config_dir / "configuration.yaml").write_text("key: value\n  bad: indent\n")
        assert validator.run_basic_validation() is False


class TestValidateBasicConfigStructure:
    def test_missing_lat_long(self, config_dir, validator):
        config = {"homeassistant": {"name": "Test"}}
        validator.validate_basic_config_structure(config)
        assert any("latitude/longitude" in w for w in validator.warnings)

    def test_missing_timezone(self, config_dir, validator):
        config = {"homeassistant": {"latitude": 0, "longitude": 0}}
        validator.validate_basic_config_structure(config)
        assert any("time_zone" in w for w in validator.warnings)

    def test_deprecated_discovery(self, config_dir, validator):
        config = {"discovery": None}
        validator.validate_basic_config_structure(config)
        assert any("discovery" in w and "deprecated" in w for w in validator.warnings)

    def test_deprecated_cloud(self, config_dir, validator):
        config = {"cloud": None}
        validator.validate_basic_config_structure(config)
        assert any("cloud" in w and "via UI" in w for w in validator.warnings)


class TestCheckIntegrationConfigs:
    def test_invalid_logger_logs(self, config_dir, validator):
        config = {"logger": {"logs": "not_a_dict"}}
        validator.check_integration_configs(config)
        assert any("logger.logs must be a dictionary" in e for e in validator.errors)

    def test_valid_logger_logs(self, config_dir, validator):
        config = {"logger": {"logs": {"custom_component": "debug"}}}
        validator.check_integration_configs(config)
        assert len(validator.errors) == 0

    def test_invalid_recorder_db_url(self, config_dir, validator):
        config = {"recorder": {"db_url": "invalid://url"}}
        validator.check_integration_configs(config)
        assert any("db_url" in w for w in validator.warnings)

    def test_valid_recorder_sqlite(self, config_dir, validator):
        config = {"recorder": {"db_url": "sqlite:///config/home-assistant_v2.db"}}
        validator.check_integration_configs(config)
        assert not any("db_url" in w for w in validator.warnings)

    def test_missing_ssl_cert(self, config_dir, validator):
        config = {"http": {"ssl_certificate": "/nonexistent/cert.pem"}}
        validator.check_integration_configs(config)
        assert any("SSL certificate" in e for e in validator.errors)

    def test_missing_ssl_key(self, config_dir, validator):
        config = {"http": {"ssl_key": "/nonexistent/key.pem"}}
        validator.check_integration_configs(config)
        assert any("SSL key" in e for e in validator.errors)


class TestValidateAutomationsFile:
    def test_no_automations_file(self, config_dir, validator):
        # Should just return without errors
        validator.validate_automations_file()
        assert len(validator.errors) == 0

    def test_automations_not_list(self, config_dir, validator):
        (config_dir / "automations.yaml").write_text("key: value\n")
        validator.validate_automations_file()
        assert any("must contain a list" in e for e in validator.errors)

    def test_valid_automations(self, config_dir, validator):
        (config_dir / "automations.yaml").write_text(
            "- alias: Test\n  trigger:\n    platform: state\n"
            "  action:\n    service: test\n"
        )
        validator.validate_automations_file()
        assert len(validator.errors) == 0

    def test_empty_automations(self, config_dir, validator):
        (config_dir / "automations.yaml").write_text("")
        validator.validate_automations_file()
        assert len(validator.errors) == 0


class TestValidateScriptsFile:
    def test_no_scripts_file(self, config_dir, validator):
        validator.validate_scripts_file()
        assert len(validator.errors) == 0

    def test_scripts_not_dict(self, config_dir, validator):
        (config_dir / "scripts.yaml").write_text("- item1\n- item2\n")
        validator.validate_scripts_file()
        assert any("must contain a dictionary" in e for e in validator.errors)

    def test_valid_scripts(self, config_dir, validator):
        (config_dir / "scripts.yaml").write_text(
            "my_script:\n  sequence:\n    - service: test\n"
        )
        validator.validate_scripts_file()
        assert len(validator.errors) == 0


class TestValidateSecretsFile:
    def test_no_secrets_file(self, config_dir, validator):
        validator.validate_secrets_file()
        assert any("secrets.yaml not found" in w for w in validator.warnings)

    def test_secrets_not_dict(self, config_dir, validator):
        (config_dir / "secrets.yaml").write_text("- item1\n- item2\n")
        validator.validate_secrets_file()
        assert any("must contain a dictionary" in e for e in validator.errors)

    def test_valid_secrets(self, config_dir, validator):
        (config_dir / "secrets.yaml").write_text("api_key: my_secret_key\n")
        validator.validate_secrets_file()
        assert len(validator.errors) == 0


class TestValidateAll:
    def test_nonexistent_config_dir(self):
        v = HAConfigValidator("/nonexistent/path")
        assert v.validate_all() is False

    def test_falls_back_to_basic_when_no_ha(self, config_dir, validator):
        (config_dir / "configuration.yaml").write_text(
            "homeassistant:\n  name: Test\n  latitude: 0\n"
            "  longitude: 0\n  time_zone: UTC\n"
        )
        with patch(
            "tools.ha_config_validator.subprocess.run",
            side_effect=FileNotFoundError,
        ):
            result = validator.validate_all()
            # Falls back to basic validation which should pass
            assert result is True


class TestRunHACheckConfig:
    def test_timeout(self, config_dir, validator):
        import subprocess

        with patch(
            "tools.ha_config_validator.subprocess.run",
        ) as mock_run:
            # First call for check_ha_installation succeeds
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "2024.1.0"
            # Second call for actual check times out
            mock_run.side_effect = [
                mock_result,
                subprocess.TimeoutExpired(cmd="hass", timeout=60),
            ]
            assert validator.run_ha_check_config() is False
            assert any("timed out" in e for e in validator.errors)

    def test_successful_check(self, config_dir, validator):
        mock_install = MagicMock()
        mock_install.returncode = 0
        mock_install.stdout = "2024.1.0"

        mock_check = MagicMock()
        mock_check.returncode = 0
        mock_check.stdout = "Configuration check successful!"
        mock_check.stderr = ""

        with patch(
            "tools.ha_config_validator.subprocess.run",
            side_effect=[mock_install, mock_check],
        ):
            assert validator.run_ha_check_config() is True

    def test_fallback_to_python_module(self, config_dir, validator):
        """Cover lines 76-85: hass gives 'No module named', falls back to python -m."""
        mock_install = MagicMock()
        mock_install.returncode = 0
        mock_install.stdout = "2024.1.0"

        mock_hass_fail = MagicMock()
        mock_hass_fail.returncode = 1
        mock_hass_fail.stderr = "No module named homeassistant"
        mock_hass_fail.stdout = ""

        mock_python_success = MagicMock()
        mock_python_success.returncode = 0
        mock_python_success.stdout = "Configuration check successful!"
        mock_python_success.stderr = ""

        with patch(
            "tools.ha_config_validator.subprocess.run",
            side_effect=[mock_install, mock_hass_fail, mock_python_success],
        ):
            assert validator.run_ha_check_config() is True

    def test_check_with_stderr(self, config_dir, validator):
        """Cover line 92: stderr is parsed via parse_check_config_errors."""
        mock_install = MagicMock()
        mock_install.returncode = 0
        mock_install.stdout = "2024.1.0"

        mock_check = MagicMock()
        mock_check.returncode = 0
        mock_check.stdout = "Configuration check successful!"
        mock_check.stderr = "some warning text"

        with patch(
            "tools.ha_config_validator.subprocess.run",
            side_effect=[mock_install, mock_check],
        ):
            validator.run_ha_check_config()
            # stderr should have been parsed
            assert any("some warning text" in e for e in validator.errors)

    def test_exception_falls_back_to_basic(self, config_dir, validator):
        """Cover lines 99-101: exception in run_ha_check_config falls back to basic."""
        mock_install = MagicMock()
        mock_install.returncode = 0
        mock_install.stdout = "2024.1.0"

        (config_dir / "configuration.yaml").write_text(
            "homeassistant:\n  name: Test\n  latitude: 0\n"
            "  longitude: 0\n  time_zone: UTC\n"
        )

        with patch(
            "tools.ha_config_validator.subprocess.run",
            side_effect=[mock_install, RuntimeError("unexpected")],
        ):
            result = validator.run_ha_check_config()
            # Falls back to basic validation which succeeds with valid config
            assert result is True
            assert any("Failed to run" in e for e in validator.errors)


class TestHAConfigValidatorMain:
    """Cover lines 311-326: main() function."""

    def test_main_valid(self, tmp_path, monkeypatch):
        from tools.ha_config_validator import main

        (tmp_path / "configuration.yaml").write_text(
            "homeassistant:\n  name: Test\n  latitude: 0\n"
            "  longitude: 0\n  time_zone: UTC\n"
        )
        monkeypatch.setattr("sys.argv", ["ha_config_validator", str(tmp_path)])
        with patch(
            "tools.ha_config_validator.subprocess.run",
            side_effect=FileNotFoundError,
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0

    def test_main_invalid(self, tmp_path, monkeypatch):
        from tools.ha_config_validator import main

        monkeypatch.setattr("sys.argv", ["ha_config_validator", "/nonexistent"])
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 1
