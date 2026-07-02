"""Tests for tools/ha_official_validator.py - official HA validation."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from tools.ha_official_validator import HAOfficialValidator


@pytest.fixture
def config_dir(tmp_path):
    (tmp_path / "configuration.yaml").write_text("homeassistant:\n  name: Test\n")
    return tmp_path


@pytest.fixture
def validator(config_dir):
    return HAOfficialValidator(str(config_dir))


class TestHAOfficialValidatorMain:
    """Cover lines 169-186: main() function."""

    def test_main_valid(self, tmp_path, monkeypatch):
        from tools.ha_official_validator import main

        (tmp_path / "configuration.yaml").write_text("homeassistant:\n  name: Test\n")
        monkeypatch.setattr("sys.argv", ["ha_official_validator", str(tmp_path)])

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Configuration check successful!"
        mock_result.stderr = ""
        with patch(
            "tools.ha_official_validator.subprocess.run", return_value=mock_result
        ):
            assert main() == 0

    def test_main_invalid(self, tmp_path, monkeypatch):
        from tools.ha_official_validator import main

        monkeypatch.setattr("sys.argv", ["ha_official_validator", "/nonexistent"])
        assert main() == 1


@pytest.mark.parametrize(
    "message",
    [
        "Unable to locate turbojpeg library",
        "libturbojpeg not found",
        "Camera snapshot performance will be sub-optimal",
        "TurboJPEGSingleton warning",
        "selector']['reorder'] is not valid",
        "Traceback (most recent call last):",
        "RuntimeError: something",
    ],
)
def test_ignorable_message(validator, message):
    assert validator.is_ignorable_message(message) is True


def test_normal_error_not_ignorable(validator):
    msg = "Invalid configuration for sensor"
    assert validator.is_ignorable_message(msg) is False


class TestIsIgnorableTracebackLine:
    def test_python_file_line(self, validator):
        assert (
            validator.is_ignorable_traceback_line(
                '  File "/usr/lib/python3.12/site-packages/test.py", line 42'
            )
            is True
        )

    def test_normal_line(self, validator):
        assert validator.is_ignorable_traceback_line("ERROR: something") is False


class TestParseCheckConfigOutput:
    def test_success_message(self, validator):
        validator.parse_check_config_output(
            "Testing configuration at /config\nConfiguration check successful!\n",
            "",
        )
        assert any("successful" in i for i in validator.info)
        assert len(validator.errors) == 0

    def test_error_message(self, validator):
        validator.parse_check_config_output(
            "ERROR: Invalid config for sensor.test\n", ""
        )
        assert any("Invalid config" in e for e in validator.errors)

    def test_warning_message(self, validator):
        validator.parse_check_config_output("WARNING: Deprecated feature used\n", "")
        assert any("Deprecated" in w for w in validator.warnings)

    def test_zero_errors_found(self, validator):
        validator.parse_check_config_output("0 errors found\n", "")
        assert len(validator.errors) == 0
        assert any("0 errors" in i for i in validator.info)

    def test_nonzero_errors_found(self, validator):
        validator.parse_check_config_output("3 errors found\n", "")
        assert any("3 errors" in e for e in validator.errors)

    def test_skips_ignorable_messages(self, validator):
        validator.parse_check_config_output("Unable to locate turbojpeg library\n", "")
        assert len(validator.errors) == 0
        assert len(validator.warnings) == 0

    def test_stderr_errors(self, validator):
        validator.parse_check_config_output("", "actual error message\n")
        assert any("actual error" in e for e in validator.errors)

    def test_stderr_skips_debug(self, validator):
        validator.parse_check_config_output("", "DEBUG: internal message\n")
        assert len(validator.errors) == 0

    def test_stderr_skips_info(self, validator):
        validator.parse_check_config_output("", "INFO: starting setup\n")
        assert len(validator.errors) == 0

    def test_stderr_skips_setup_messages(self, validator):
        validator.parse_check_config_output("", "Setup of domain sensor done\n")
        assert len(validator.errors) == 0

    def test_info_lines_not_included(self, validator):
        validator.parse_check_config_output("INFO: Some debug info\n", "")
        # INFO: lines are skipped
        assert not any("Some debug info" in i for i in validator.info)

    def test_other_lines_become_info(self, validator):
        validator.parse_check_config_output("Some informational line\n", "")
        assert any("informational" in i for i in validator.info)

    def test_error_substring_in_middle_not_flagged(self, validator):
        """Mid-line 'error' substring no longer triggers error classification."""
        validator.parse_check_config_output("Found no errors in the config\n", "")
        assert len(validator.errors) == 0

    def test_no_errors_found_not_flagged(self, validator):
        """'0 errors found' goes to info, not errors."""
        validator.parse_check_config_output("0 errors found at all\n", "")
        assert len(validator.errors) == 0
        assert any("0 errors" in i for i in validator.info)


class TestRunHACheckConfig:
    def test_successful_check(self, validator):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Configuration check successful!"
        mock_result.stderr = ""

        with patch(
            "tools.ha_official_validator.subprocess.run",
            return_value=mock_result,
        ):
            assert validator.run_ha_check_config() is True

    def test_failed_check(self, validator):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = "ERROR: Invalid configuration"
        mock_result.stderr = ""

        with patch(
            "tools.ha_official_validator.subprocess.run",
            return_value=mock_result,
        ):
            assert validator.run_ha_check_config() is False

    def test_timeout(self, validator):
        with patch(
            "tools.ha_official_validator.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="test", timeout=120),
        ):
            assert validator.run_ha_check_config() is False
            assert any("timed out" in e for e in validator.errors)

    def test_ha_not_found(self, validator):
        with patch(
            "tools.ha_official_validator.subprocess.run",
            side_effect=FileNotFoundError,
        ):
            assert validator.run_ha_check_config() is False
            assert any("not found" in e for e in validator.errors)

    def test_generic_exception_propagates(self, validator):
        with (
            patch(
                "tools.ha_official_validator.subprocess.run",
                side_effect=RuntimeError("unexpected"),
            ),
            pytest.raises(RuntimeError),
        ):
            validator.run_ha_check_config()


class TestValidateAll:
    def test_nonexistent_config_dir(self):
        v = HAOfficialValidator("/nonexistent/path")
        assert v.validate_all() is False

    def test_missing_configuration_yaml(self, tmp_path):
        v = HAOfficialValidator(str(tmp_path))
        assert v.validate_all() is False
        assert any("configuration.yaml not found" in e for e in v.errors)

    def test_delegates_to_check_config(self, config_dir, validator):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Configuration check successful!"
        mock_result.stderr = ""

        with patch(
            "tools.ha_official_validator.subprocess.run",
            return_value=mock_result,
        ):
            assert validator.validate_all() is True


def test_non_subprocess_error_propagates(monkeypatch, tmp_path):
    (tmp_path / "configuration.yaml").write_text("default_config:")
    v = HAOfficialValidator(str(tmp_path))

    def boom(*a, **k):
        raise ValueError("unexpected logic bug")

    monkeypatch.setattr("tools.ha_official_validator.subprocess.run", boom)
    with pytest.raises(ValueError):
        v.validate_all()


class TestTimeoutConfiguration:
    def test_uses_timeout_from_env(self, config_dir, monkeypatch):
        monkeypatch.setenv("HA_VALIDATION_TIMEOUT", "240")
        v = HAOfficialValidator(str(config_dir))
        assert v.validation_timeout == 240

    def test_invalid_timeout_warns_and_falls_back(self, config_dir, monkeypatch):
        monkeypatch.setenv("HA_VALIDATION_TIMEOUT", "bad")
        v = HAOfficialValidator(str(config_dir))
        assert v.validation_timeout == 120
        assert any("HA_VALIDATION_TIMEOUT" in warning for warning in v.warnings)
