"""Tests for tools/run_tests.py - validation test suite runner."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tools.run_tests import ValidationTestRunner


@pytest.fixture
def config_dir(tmp_path):
    (tmp_path / "configuration.yaml").write_text("homeassistant:\n  name: Test\n")
    return tmp_path


@pytest.fixture
def runner(config_dir):
    return ValidationTestRunner(str(config_dir))


class TestInit:
    def test_sets_config_dir(self, config_dir, runner):
        assert runner.config_dir == config_dir

    def test_results_empty(self, runner):
        assert runner.results == {}


class TestGetPythonExecutable:
    def test_uses_venv_if_exists(self, runner, tmp_path):
        fake_venv = tmp_path / "fake_venv"
        fake_python = fake_venv / "bin" / "python"
        fake_python.parent.mkdir(parents=True)
        fake_python.touch()
        runner.venv_dir = fake_venv
        assert runner.get_python_executable() == str(fake_python)

    def test_falls_back_to_sys_executable(self, runner):
        # If venv doesn't exist, use sys.executable
        import sys

        runner.venv_dir = Path("/nonexistent/venv")
        assert runner.get_python_executable() == sys.executable


class TestTimeoutConfiguration:
    def test_uses_timeout_from_env(self, config_dir, monkeypatch):
        monkeypatch.setenv("HA_RUNNER_TIMEOUT", "150")
        runner = ValidationTestRunner(str(config_dir))
        assert runner.validator_timeout == 150

    def test_invalid_timeout_env_falls_back(self, config_dir, monkeypatch, capsys):
        monkeypatch.setenv("HA_RUNNER_TIMEOUT", "invalid")
        runner = ValidationTestRunner(str(config_dir))
        assert runner.validator_timeout == 120
        captured = capsys.readouterr()
        assert "HA_RUNNER_TIMEOUT" in captured.out


class TestRunValidator:
    def test_successful_validator(self, runner, tmp_path):
        # Create a dummy script
        script = runner.tools_dir / "test_script.py"
        script.write_text("import sys; print('OK'); sys.exit(0)")

        try:
            passed, stdout, stderr, duration = runner.run_validator(
                "test_script.py", "Test Script"
            )
            assert passed is True
            assert "OK" in stdout
            assert duration > 0
        finally:
            script.unlink(missing_ok=True)

    def test_failing_validator(self, runner):
        script = runner.tools_dir / "fail_script.py"
        script.write_text("import sys; print('FAIL', file=sys.stderr); sys.exit(1)")

        try:
            passed, stdout, stderr, duration = runner.run_validator(
                "fail_script.py", "Fail Script"
            )
            assert passed is False
            assert "FAIL" in stderr
        finally:
            script.unlink(missing_ok=True)

    def test_missing_script(self, runner):
        passed, stdout, stderr, duration = runner.run_validator(
            "nonexistent.py", "Missing"
        )
        assert passed is False
        assert "not found" in stderr

    def test_timeout(self, runner):
        with patch(
            "tools.run_tests.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="test", timeout=120),
        ):
            # Need a real script path
            script = runner.tools_dir / "timeout_test.py"
            script.write_text("pass")
            try:
                passed, stdout, stderr, duration = runner.run_validator(
                    "timeout_test.py", "Timeout"
                )
                assert passed is False
                assert "timed out" in stderr
            finally:
                script.unlink(missing_ok=True)

    def test_generic_exception(self, runner):
        with patch(
            "tools.run_tests.subprocess.run",
            side_effect=OSError("permission denied"),
        ):
            script = runner.tools_dir / "error_test.py"
            script.write_text("pass")
            try:
                passed, stdout, stderr, duration = runner.run_validator(
                    "error_test.py", "Error"
                )
                assert passed is False
                assert "Failed to run" in stderr
            finally:
                script.unlink(missing_ok=True)


class TestRunAllTests:
    def test_all_pass(self, runner, capsys):
        with patch.object(
            runner,
            "run_validator",
            return_value=(True, "OK", "", 0.1),
        ):
            result = runner.run_all_tests()
            assert result is True
            captured = capsys.readouterr()
            assert "PASSED" in captured.out

    def test_some_fail(self, runner, capsys):
        call_count = 0

        def alternating_results(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (True, "OK", "", 0.1)
            return (False, "", "ERROR", 0.1)

        with patch.object(runner, "run_validator", side_effect=alternating_results):
            result = runner.run_all_tests()
            assert result is False
            captured = capsys.readouterr()
            assert "FAILED" in captured.out


class TestPrintDetailedResults:
    def test_prints_passed(self, runner, capsys):
        runner.results = {
            "test.py": {
                "description": "Test",
                "passed": True,
                "stdout": "All good",
                "stderr": "",
                "duration": 0.5,
            }
        }
        runner.print_detailed_results()
        captured = capsys.readouterr()
        assert "PASSED" in captured.out
        assert "All good" in captured.out

    def test_prints_failed_with_errors(self, runner, capsys):
        runner.results = {
            "test.py": {
                "description": "Test",
                "passed": False,
                "stdout": "",
                "stderr": "Something broke",
                "duration": 0.5,
            }
        }
        runner.print_detailed_results()
        captured = capsys.readouterr()
        assert "FAILED" in captured.out
        assert "Something broke" in captured.out


class TestPrintSummary:
    def test_all_passed(self, runner, capsys):
        runner.results = {
            "test1.py": {"passed": True},
            "test2.py": {"passed": True},
        }
        runner.print_summary()
        captured = capsys.readouterr()
        assert "All tests passed" in captured.out

    def test_some_failed(self, runner, capsys):
        runner.results = {
            "test1.py": {"passed": True},
            "test2.py": {"passed": False},
        }
        runner.print_summary()
        captured = capsys.readouterr()
        assert "1 test(s) failed" in captured.out


class TestCheckDependencies:
    def test_all_present(self, runner):
        with patch("tools.run_tests.importlib.util.find_spec", return_value=object()):
            assert runner.check_dependencies() is True

    def test_missing_module(self, runner, capsys):
        with patch("tools.run_tests.importlib.util.find_spec", return_value=None):
            assert runner.check_dependencies() is False
            captured = capsys.readouterr()
            assert "Missing" in captured.out


class TestRun:
    def test_missing_config_dir(self, capsys):
        runner = ValidationTestRunner("/nonexistent")
        assert runner.run() is False

    def test_successful_run(self, runner, capsys):
        with (
            patch.object(runner, "check_dependencies", return_value=True),
            patch.object(runner, "run_all_tests", return_value=True),
        ):
            # Populate results with all required keys for print methods
            runner.results = {
                "test.py": {
                    "description": "Test Validator",
                    "passed": True,
                    "stdout": "OK",
                    "stderr": "",
                    "duration": 0.1,
                }
            }
            assert runner.run() is True


class TestRunTestsMain:
    """Cover lines 212-226: main() function."""

    def test_main_success(self, tmp_path, monkeypatch):
        from tools.run_tests import main

        (tmp_path / "configuration.yaml").write_text("homeassistant:\n  name: Test\n")
        monkeypatch.setattr("sys.argv", ["run_tests", str(tmp_path)])

        with patch(
            "tools.run_tests.ValidationTestRunner.run",
            return_value=True,
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0

    def test_main_failure(self, tmp_path, monkeypatch):
        from tools.run_tests import main

        (tmp_path / "configuration.yaml").write_text("homeassistant:\n  name: Test\n")
        monkeypatch.setattr("sys.argv", ["run_tests", str(tmp_path)])

        with patch(
            "tools.run_tests.ValidationTestRunner.run",
            return_value=False,
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1
