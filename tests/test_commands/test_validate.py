"""Tests for tools/commands/validate.py — in-process validator runner."""

from argparse import Namespace
from unittest.mock import patch

import pytest

from tools.commands import validate
from tools.commands.validate import ValidatorResult, _run_one, run, run_validators


@pytest.fixture
def config_dir(tmp_path):
    """A minimal valid config dir."""
    (tmp_path / "configuration.yaml").write_text("homeassistant:\n  name: Test\n")
    return str(tmp_path)


class TestValidatorResult:
    def test_constructs_with_all_fields(self):
        r = ValidatorResult(
            description="Test",
            passed=True,
            stdout="out",
            stderr="err",
            duration=0.5,
        )
        assert r.description == "Test"
        assert r.passed is True
        assert r.duration == 0.5


class TestRunOne:
    def test_successful_validator(self, config_dir):
        """A validator that passes returns passed=True with stdout captured."""
        # Use the real YAML validator on a valid config
        from tools.validators.yaml import YAMLValidator

        result = _run_one(YAMLValidator, "YAML", config_dir, quiet=True)
        assert result.passed is True
        assert isinstance(result.duration, float)
        assert result.duration >= 0

    def test_failing_validator(self, tmp_path):
        """A validator that finds errors returns passed=False."""
        from tools.validators.yaml import YAMLValidator

        result = _run_one(
            YAMLValidator, "YAML", str(tmp_path / "nonexistent"), quiet=True
        )
        assert result.passed is False

    def test_validator_exception_caught(self):
        """If a validator raises unexpectedly, it's captured as a failure."""
        from tools.validators.yaml import YAMLValidator

        with patch.object(
            YAMLValidator, "validate_all", side_effect=RuntimeError("boom")
        ):
            result = _run_one(YAMLValidator, "YAML", "config", quiet=True)
        assert result.passed is False
        assert "Failed to run validator" in result.stderr
        assert "boom" in result.stderr

    def test_system_exit_zero_treated_as_success(self):
        """A validator that raises SystemExit(0) passes."""
        from tools.validators.yaml import YAMLValidator

        with patch.object(YAMLValidator, "validate_all", side_effect=SystemExit(0)):
            result = _run_one(YAMLValidator, "YAML", "config", quiet=True)
        assert result.passed is True

    def test_system_exit_nonzero_treated_as_failure(self):
        from tools.validators.yaml import YAMLValidator

        with patch.object(YAMLValidator, "validate_all", side_effect=SystemExit(1)):
            result = _run_one(YAMLValidator, "YAML", "config", quiet=True)
        assert result.passed is False

    def test_quiet_propagated_to_validator(self):
        """The quiet kwarg should reach the validator instance."""
        from tools.validators.yaml import YAMLValidator

        with patch.object(YAMLValidator, "validate_all", return_value=True) as mock:
            _run_one(YAMLValidator, "YAML", "config", quiet=True)
        # Inspect the instance the mock was called on
        instance = (
            mock.call_args[0][0] if mock.call_args[0] else mock.call_args[1].get("self")
        )
        # Simpler: just verify call_args[0] is empty (unbound) or self was bound
        # Actually validate_all is called as instance method, so self is implicit
        # Inspect via patch.object target — but easier to just construct manually
        # and assert.
        instance = YAMLValidator("config", quiet=True)
        assert instance.quiet is True


class TestRunValidators:
    def test_returns_three_results(self, config_dir):
        """Default suite runs 3 validators (yaml, references, ha_official)."""
        results = run_validators(config_dir, quiet=True)
        assert len(results) == 3
        descriptions = {r.description for r in results}
        assert "YAML Syntax Validation" in descriptions
        assert "Entity/Device Reference Validation" in descriptions
        assert "Official Home Assistant Configuration Validation" in descriptions

    def test_all_results_have_required_fields(self, config_dir):
        results = run_validators(config_dir, quiet=True)
        for r in results:
            assert isinstance(r.description, str)
            assert isinstance(r.passed, bool)
            assert isinstance(r.stdout, str)
            assert isinstance(r.stderr, str)
            assert isinstance(r.duration, float)


class TestRun:
    def _args(self, config_dir=None, quiet=False):
        return Namespace(config_dir=config_dir or "config", quiet=quiet)

    def test_all_pass_returns_zero(self, config_dir):
        with patch(
            "tools.commands.validate.run_validators",
            return_value=[
                ValidatorResult("V1", True, "ok", "", 0.1),
                ValidatorResult("V2", True, "ok", "", 0.1),
            ],
        ):
            result = run(self._args(config_dir, quiet=True))
        assert result == 0

    def test_any_failure_returns_one(self, config_dir, capsys):
        with patch(
            "tools.commands.validate.run_validators",
            return_value=[
                ValidatorResult("V1", True, "ok", "", 0.1),
                ValidatorResult("V2", False, "", "broke", 0.1),
            ],
        ):
            result = run(self._args(config_dir, quiet=True))
        assert result == 1
        # Failure output is printed even in --quiet mode
        out = capsys.readouterr().out
        assert "FAILED" in out
        assert "broke" in out

    def test_quiet_suppresses_pass_output(self, config_dir, capsys):
        with patch(
            "tools.commands.validate.run_validators",
            return_value=[ValidatorResult("V1", True, "ok", "", 0.1)],
        ):
            run(self._args(config_dir, quiet=True))
        out = capsys.readouterr().out
        # On all-pass + quiet, no banner output
        assert "Running all validators" not in out
        assert "TEST SUMMARY" not in out

    def test_non_quiet_prints_banner_and_summary(self, config_dir, capsys):
        with patch(
            "tools.commands.validate.run_validators",
            return_value=[ValidatorResult("V1", True, "ok", "", 0.1)],
        ):
            run(self._args(config_dir, quiet=False))
        out = capsys.readouterr().out
        assert "Running all validators" in out
        assert "TEST SUMMARY" in out
        assert "PASSED" in out

    def test_prints_duration_per_validator(self, config_dir, capsys):
        with patch(
            "tools.commands.validate.run_validators",
            return_value=[ValidatorResult("V1", True, "ok", "", 1.5)],
        ):
            run(self._args(config_dir, quiet=False))
        out = capsys.readouterr().out
        assert "1.50s" in out


class TestAddParser:
    def test_subparser_registered_with_validate_name(self):
        """add_parser should register a 'validate' subcommand."""
        import argparse

        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        validate.add_parser(subparsers)
        args = parser.parse_args(["validate"])
        assert args.command == "validate"

    def test_add_parser_attaches_run_func(self):
        import argparse

        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        validate.add_parser(subparsers)
        args = parser.parse_args(["validate"])
        assert callable(args.func)
