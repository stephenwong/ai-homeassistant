"""Tests for tools/commands/validate.py — in-process validator runner."""

from argparse import Namespace
from unittest.mock import patch

import pytest

from tests.helpers import make_parser
from tools.commands import validate
from tools.commands.validate import ValidatorResult, _run_one, run, run_validators
from tools.validators.yaml import YAMLValidator


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

    def test_cached_defaults_to_false(self):
        r = ValidatorResult("Test", True, "", "", 0.0)
        assert r.cached is False

    def test_cached_true(self):
        r = ValidatorResult("Test", True, "", "", 0.0, cached=True)
        assert r.cached is True


class TestRunOne:
    def test_successful_validator(self, config_dir):
        """A validator that passes returns passed=True."""
        from tools.validators.yaml import YAMLValidator

        result = _run_one(YAMLValidator, "YAML", config_dir, quiet=True, force=True)
        assert result.passed is True
        assert isinstance(result.duration, float)
        assert result.duration >= 0
        assert result.cached is False

    def test_failing_validator(self, tmp_path):
        """A validator that finds errors returns passed=False."""
        from tools.validators.yaml import YAMLValidator

        result = _run_one(
            YAMLValidator,
            "YAML",
            str(tmp_path / "nonexistent"),
            quiet=True,
            force=True,
        )
        assert result.passed is False

    def test_validator_exception_caught(self):
        """If a validator raises unexpectedly, it's captured as a failure."""
        from tools.validators.yaml import YAMLValidator

        with patch.object(
            YAMLValidator, "validate_all", side_effect=RuntimeError("boom")
        ):
            result = _run_one(YAMLValidator, "YAML", "config", quiet=True, force=True)
        assert result.passed is False
        assert "Failed to run validator" in result.stderr
        assert "boom" in result.stderr

    def test_system_exit_zero_treated_as_success(self):
        """A validator that raises SystemExit(0) passes."""
        from tools.validators.yaml import YAMLValidator

        with patch.object(YAMLValidator, "validate_all", side_effect=SystemExit(0)):
            result = _run_one(YAMLValidator, "YAML", "config", quiet=True, force=True)
        assert result.passed is True

    def test_system_exit_nonzero_treated_as_failure(self):
        from tools.validators.yaml import YAMLValidator

        with patch.object(YAMLValidator, "validate_all", side_effect=SystemExit(1)):
            result = _run_one(YAMLValidator, "YAML", "config", quiet=True, force=True)
        assert result.passed is False

    def test_quiet_propagated_to_validator(self, config_dir, monkeypatch):
        """_run_one forwards quiet to the validator instance."""
        (config_dir / "configuration.yaml").write_text("homeassistant:\n")
        captured = {}
        orig_init = YAMLValidator.__init__

        def spy(self, *args, **kwargs):
            captured["kwargs"] = kwargs
            orig_init(self, *args, **kwargs)

        monkeypatch.setattr(YAMLValidator, "__init__", spy)
        _run_one(YAMLValidator, "YAML", config_dir, quiet=True, force=True)
        assert captured["kwargs"].get("quiet") is True

    def test_cache_hit_returns_cached_result(self, config_dir):
        """When file hash matches cache, validation is skipped."""
        from tools.validators.yaml import YAMLValidator

        hash_val = "abc123"
        with (
            patch("tools.commands.validate.compute_hash", return_value=hash_val),
            patch(
                "tools.commands.validate.load_cache",
                return_value={"hash": hash_val, "passed": True, "duration": 0.42},
            ),
        ):
            result = _run_one(
                YAMLValidator, "YAML", config_dir, quiet=True, force=False
            )
        assert result.passed is True
        assert result.cached is True
        assert result.duration == 0.42

    def test_cache_miss_runs_validator(self, config_dir):
        """Hash mismatch runs full validation."""
        from tools.validators.yaml import YAMLValidator

        with (
            patch("tools.commands.validate.compute_hash", return_value="newhash"),
            patch(
                "tools.commands.validate.load_cache",
                return_value={"hash": "oldhash", "passed": True, "duration": 0.1},
            ),
        ):
            result = _run_one(
                YAMLValidator, "YAML", config_dir, quiet=True, force=False
            )
        assert result.cached is False

    def test_force_bypasses_cache(self, config_dir):
        """--force ignores cached result."""
        from tools.validators.yaml import YAMLValidator

        with (
            patch("tools.commands.validate.compute_hash", return_value="abc"),
            patch(
                "tools.commands.validate.load_cache",
                return_value={"hash": "abc", "passed": False, "duration": 0.1},
            ),
        ):
            result = _run_one(YAMLValidator, "YAML", config_dir, quiet=True, force=True)
        assert result.cached is False

    def test_cache_failure_falls_through_to_run(self, config_dir):
        """If load_cache raises, validation still runs."""
        from tools.validators.yaml import YAMLValidator

        with patch(
            "tools.commands.validate.load_cache",
            side_effect=OSError("disk full"),
        ):
            result = _run_one(
                YAMLValidator, "YAML", config_dir, quiet=True, force=False
            )
        assert result.passed is True
        assert result.cached is False

    def test_save_cache_called_on_success(self, config_dir):
        """On pass, result is cached using the pre-validation hash."""
        from tools.validators.yaml import YAMLValidator

        hash_val = "hash123"
        with (
            patch("tools.commands.validate.compute_hash", return_value=hash_val) as mh,
            patch("tools.commands.validate.load_cache", return_value=None),
            patch("tools.commands.validate.save_cache") as mock_save,
        ):
            result = _run_one(YAMLValidator, "YAML", config_dir, quiet=True, force=True)
        assert result.passed is True
        # compute_hash called once (no second call for save)
        assert mh.call_count == 1
        mock_save.assert_called_once()
        args, kwargs = mock_save.call_args
        assert args[2] == "YAML"  # description
        assert args[3] == hash_val  # file_hash (reused from stash)
        assert args[4] is True  # passed

    def test_save_cache_not_called_on_failure(self, tmp_path):
        """Failures are not cached — they always re-run."""
        from tools.validators.yaml import YAMLValidator

        with (
            patch("tools.commands.validate.load_cache", return_value=None),
            patch("tools.commands.validate.save_cache") as mock_save,
        ):
            result = _run_one(
                YAMLValidator,
                "YAML",
                str(tmp_path / "nonexistent"),
                quiet=True,
                force=True,
            )
        assert result.passed is False
        mock_save.assert_not_called()

    def test_compute_hash_non_oserror_propagates(self, monkeypatch, tmp_path):
        import tools.commands.validate as mod
        from tools.validators.yaml import YAMLValidator

        (tmp_path / "configuration.yaml").write_text("a: 1")
        monkeypatch.setattr(
            mod,
            "compute_hash",
            lambda *a, **k: (_ for _ in ()).throw(ValueError("bug")),
        )
        with pytest.raises(ValueError):
            mod._run_one(YAMLValidator, "YAML", str(tmp_path), True, True)

    def test_save_cache_unexpected_error_propagates(self, monkeypatch, tmp_path):
        import tools.commands.validate as mod
        from tools.validators.yaml import YAMLValidator

        (tmp_path / "configuration.yaml").write_text("a: 1")
        monkeypatch.setattr(mod, "compute_hash", lambda *a, **k: "fakehash")
        monkeypatch.setattr(mod, "load_cache", lambda *a, **k: None)
        monkeypatch.setattr(
            mod,
            "save_cache",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        with pytest.raises(RuntimeError):
            mod._run_one(YAMLValidator, "YAML", str(tmp_path), True, False)

    def test_save_cache_failure_does_not_crash(self, config_dir):
        """If saving cache throws, validation result is still returned."""
        from tools.validators.yaml import YAMLValidator

        with (
            patch("tools.commands.validate.load_cache", return_value=None),
            patch(
                "tools.commands.validate.save_cache",
                side_effect=OSError("disk full"),
            ),
        ):
            result = _run_one(YAMLValidator, "YAML", config_dir, quiet=True, force=True)
        assert result.passed is True


class TestRunValidators:
    def test_returns_all_results(self, config_dir):
        """Default suite runs 7 validators (yaml, refs, dup, svc, tpl, stale, ha)."""
        results = run_validators(config_dir, quiet=True, force=True)
        assert len(results) == 7
        descriptions = {r.description for r in results}
        assert "YAML Syntax Validation" in descriptions
        assert "Entity/Device Reference Validation" in descriptions
        assert "Duplicate Automation ID Validation" in descriptions
        assert "Service Reference Validation" in descriptions
        assert "Jinja2 Template Validation" in descriptions
        assert "Stale Sensor Validation" in descriptions
        assert "Official Home Assistant Configuration Validation" in descriptions

    def test_all_results_have_required_fields(self, config_dir):
        results = run_validators(config_dir, quiet=True, force=True)
        for r in results:
            assert isinstance(r.description, str)
            assert isinstance(r.passed, bool)
            assert isinstance(r.stdout, str)
            assert isinstance(r.stderr, str)
            assert isinstance(r.duration, float)

    def test_second_run_uses_real_cache(self, config_dir):
        """End-to-end: first run populates cache; second run hits it."""
        results1 = run_validators(config_dir, quiet=True, force=True)
        # All should be non-cached first time (force=True)
        for r in results1:
            assert r.cached is False

        results2 = run_validators(config_dir, quiet=True, force=False)
        # Without --force, unchanged files should yield cache hits
        cached_count = sum(1 for r in results2 if r.cached)
        assert cached_count >= 1, "Expected at least one validator to hit cache"

    def test_ha_official_is_never_cached(self, config_dir, monkeypatch):
        """HAOfficialValidator depends on the HA environment, not just files."""
        from tools.validators.ha_official import HAOfficialValidator

        monkeypatch.setattr(HAOfficialValidator, "validate_all", lambda self: True)
        monkeypatch.setattr(HAOfficialValidator, "file_deps", lambda self: [])
        with (
            patch("tools.commands.validate.compute_hash", return_value="hash"),
            patch(
                "tools.commands.validate.load_cache",
                return_value={
                    "hash": "hash",
                    "passed": True,
                    "duration": 0.1,
                },
            ),
            patch("tools.commands.validate.save_cache") as mock_save,
        ):
            result = _run_one(
                HAOfficialValidator,
                "HA Official",
                config_dir,
                quiet=True,
                force=False,
            )
        # Even with a cache hit, should run (not cached)
        assert result.cached is False
        assert result.passed is True
        # And should not save (since file_deps is empty, no hash computed)
        mock_save.assert_not_called()

    def test_file_change_invalidates_cache(self, config_dir):
        """Modifying a watched file invalidates that validator's cache."""
        # First run: populate cache
        run_validators(config_dir, quiet=True, force=True)

        # Second run: should be cached
        results2 = run_validators(config_dir, quiet=True, force=False)
        # Count cached for YAML (fast enough to re-run, HA official dominates)
        yaml_result = [r for r in results2 if "YAML" in r.description][0]
        assert yaml_result.cached is True

        # Touch a YAML file
        import os

        cf = os.path.join(config_dir, "configuration.yaml")
        with open(cf, "a") as f:
            f.write("\n# cache bust\n")

        # Third run: YAML validator should re-run (no longer cached)
        results3 = run_validators(config_dir, quiet=True, force=False)
        yaml_result3 = [r for r in results3 if "YAML" in r.description][0]
        assert yaml_result3.cached is False


class TestRun:
    def _args(
        self, config_dir=None, quiet=False, force=False, summary=None, no_summary=None
    ):
        d = {"config": config_dir or "config", "quiet": quiet, "force": force}
        if summary is not None:
            d["summary"] = summary
        if no_summary is not None:
            d["no_summary"] = no_summary
        return Namespace(**d)

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
        out, err = capsys.readouterr()
        assert "FAIL" in out
        assert "broke" in err

    def test_quiet_suppresses_pass_output(self, config_dir, capsys):
        with patch(
            "tools.commands.validate.run_validators",
            return_value=[ValidatorResult("V1", True, "ok", "", 0.1)],
        ):
            run(self._args(config_dir, quiet=True))
        out = capsys.readouterr().out
        assert "Running all validators" not in out
        assert "TEST SUMMARY" not in out

    @patch("tools.common._is_tty", return_value=True)
    def test_non_quiet_prints_banner_and_summary(self, _, config_dir, capsys):
        with patch(
            "tools.commands.validate.run_validators",
            return_value=[ValidatorResult("V1", True, "ok", "", 0.1)],
        ):
            run(self._args(config_dir, quiet=False))
        out, err = capsys.readouterr()
        assert "Running all validators" in err
        assert "TEST SUMMARY" in err
        assert "Passed" in err

    @patch("tools.common._is_tty", return_value=True)
    def test_prints_duration_per_validator(self, _, config_dir, capsys):
        with patch(
            "tools.commands.validate.run_validators",
            return_value=[ValidatorResult("V1", True, "ok", "", 1.5)],
        ):
            run(self._args(config_dir, quiet=False))
        out, err = capsys.readouterr()
        assert "1.50s" in err

    @patch("tools.common._is_tty", return_value=True)
    def test_cached_result_shows_cached_label(self, _, config_dir, capsys):
        with patch(
            "tools.commands.validate.run_validators",
            return_value=[
                ValidatorResult("V1", True, "ok", "", 0.0, cached=True),
            ],
        ):
            run(self._args(config_dir, quiet=False))
        out, err = capsys.readouterr()
        assert "(cached)" in err

    @patch("tools.common._is_tty", return_value=True)
    def test_force_shows_cache_ignored_message(self, _, config_dir, capsys):
        with patch(
            "tools.commands.validate.run_validators",
            return_value=[ValidatorResult("V1", True, "ok", "", 0.1)],
        ):
            run(self._args(config_dir, quiet=False, force=True))
        out, err = capsys.readouterr()
        assert "cache ignored" in err

    def test_passes_force_to_run_validators(self, config_dir):
        with patch(
            "tools.commands.validate.run_validators",
            return_value=[ValidatorResult("V1", True, "ok", "", 0.1)],
        ) as mock_rv:
            run(self._args(config_dir, quiet=True, force=True))
        # config_dir passed positionally, quiet + force + summary as keywords
        mock_rv.assert_called_once_with(
            config_dir, quiet=True, force=True, summary=True
        )

    # ── Summary mode tests ──────────────────────────────────────────

    @patch("tools.common._is_tty", return_value=False)
    def test_summary_compact_output_all_pass(self, _, config_dir, capsys):
        with patch(
            "tools.commands.validate.run_validators",
            return_value=[ValidatorResult("V1", True, "ok", "", 0.1)],
        ):
            run(self._args(config_dir, quiet=False))
        out = capsys.readouterr().out
        assert out.strip().startswith("PASS V1")
        # No banner, no emoji, no TEST SUMMARY
        assert "\U0001f50d" not in out
        assert "TEST SUMMARY" not in out
        # Expect final PASSED line
        assert "PASSED 1/1" in out

    @patch("tools.common._is_tty", return_value=False)
    def test_summary_with_failure_shows_compact_errors(self, _, config_dir, capsys):
        with patch(
            "tools.commands.validate.run_validators",
            return_value=[
                ValidatorResult("V1", True, "ok", "", 0.1),
                ValidatorResult("V2", False, "", "something broke", 0.2),
            ],
        ):
            run(self._args(config_dir, quiet=False))
        out, err = capsys.readouterr()
        # Should show per-validator status
        assert "PASS V1" in out
        assert "FAIL V2" in out
        # Error should appear on stderr (no section headers in summary)
        assert "something broke" in err
        assert "📋" not in err  # no clipboard icon section header
        assert "Status:" not in err
        # Final FAILED line
        assert "FAILED 1/2" in out

    @patch("tools.common._is_tty", return_value=True)
    def test_summary_explicit_flag_in_tty(self, _, config_dir, capsys):
        with (
            patch(
                "tools.commands.validate.run_validators",
                return_value=[ValidatorResult("V1", True, "ok", "", 0.1)],
            ),
        ):
            run(self._args(config_dir, quiet=False, summary=True))
        out = capsys.readouterr().out
        assert "PASS V1" in out
        assert "TEST SUMMARY" not in out

    @patch("tools.common._is_tty", return_value=False)
    def test_summary_with_quiet_suppresses_pass_lines(self, _, config_dir, capsys):
        with patch(
            "tools.commands.validate.run_validators",
            return_value=[
                ValidatorResult("V1", True, "ok", "", 0.1),
                ValidatorResult("V2", False, "", "error detail", 0.2),
            ],
        ):
            run(self._args(config_dir, quiet=True))
        out, err = capsys.readouterr()
        # quiet suppresses PASS lines but still shows FAIL lines
        assert "PASS V1" not in out
        assert "FAIL V2" in out
        assert "error detail" in err
        # Final aggregate line still shows
        assert "FAILED 1/2" in out

    @patch("tools.common._is_tty", return_value=False)
    def test_summary_shows_cached_as_letter_c(self, _, config_dir, capsys):
        with patch(
            "tools.commands.validate.run_validators",
            return_value=[
                ValidatorResult("V1", True, "ok", "", 0.0, cached=True),
            ],
        ):
            run(self._args(config_dir, quiet=False))
        lines = capsys.readouterr().out.strip().splitlines()
        assert len(lines) == 2
        # Per-validator line: "PASS V1 C" (no duration)
        assert lines[0].strip().endswith("C")
        assert "0.00s" not in lines[0]
        # Final aggregate line: "PASSED 1/1 (0.00s)" (has duration)
        assert lines[1].startswith("PASSED 1/1")
        assert "(cached)" not in "\n".join(lines)

    @patch("tools.common._is_tty", return_value=False)
    def test_no_summary_flag_forces_verbose_in_pipe(self, _, config_dir, capsys):
        """--no-summary forces verbose output even when stdout is not a TTY."""
        with patch(
            "tools.commands.validate.run_validators",
            return_value=[ValidatorResult("V1", True, "ok", "", 0.1)],
        ):
            run(self._args(config_dir, quiet=False, no_summary=True))
        out, err = capsys.readouterr()
        assert "🔍" in err  # banner present (verbose mode)
        assert "TEST SUMMARY" in err
        assert "Passed" in err

    @patch("tools.common._is_tty", return_value=False)
    def test_conflicting_flags_warning(self, _, config_dir, capsys):
        """Both --summary and --no-summary prints a warning."""
        with patch(
            "tools.commands.validate.run_validators",
            return_value=[ValidatorResult("V1", True, "ok", "", 0.1)],
        ):
            run(self._args(config_dir, quiet=False, summary=True, no_summary=True))
        _, err = capsys.readouterr()
        assert "WARN" in err
        assert "--summary" in err

    # ── Verbose mode with failure (covers 238, 260-272, 294) ──────

    @patch("tools.common._is_tty", return_value=True)
    def test_verbose_mode_with_failure_prints_detail(self, _, config_dir, capsys):
        with patch(
            "tools.commands.validate.run_validators",
            return_value=[
                ValidatorResult(
                    "MyValidator", False, "some stdout output", "the error text", 1.5
                ),
            ],
        ):
            run(self._args(config_dir, quiet=False))
        _, err = capsys.readouterr()
        assert "MyValidator" in err  # 260
        assert "FAILED" in err  # 238/262
        assert "some stdout output" in err  # 264-267
        assert "the error text" in err  # 268-271
        assert "1.50s" in err  # 263
        assert "failed" in err.lower()  # 294


class TestAddParser:
    def test_subparser_registered_with_validate_name(self):
        """add_parser should register a 'validate' subcommand."""
        parser, subparsers = make_parser()
        validate.add_parser(subparsers)
        args = parser.parse_args(["validate"])
        assert args.command == "validate"

    def test_add_parser_attaches_run_func(self):
        parser, subparsers = make_parser()
        validate.add_parser(subparsers)
        args = parser.parse_args(["validate"])
        assert callable(args.func)

    def test_force_flag_defaults_false(self):
        parser, subparsers = make_parser()
        validate.add_parser(subparsers)
        args = parser.parse_args(["validate"])
        assert args.force is False

    def test_force_flag_set_true(self):
        parser, subparsers = make_parser()
        validate.add_parser(subparsers)
        args = parser.parse_args(["validate", "--force"])
        assert args.force is True

    def test_summary_flag_defaults_false(self):
        parser, subparsers = make_parser()
        validate.add_parser(subparsers)
        args = parser.parse_args(["validate"])
        assert args.summary is False
        assert args.no_summary is False

    def test_summary_flag_set_true(self):
        parser, subparsers = make_parser()
        validate.add_parser(subparsers)
        args = parser.parse_args(["validate", "--summary"])
        assert args.summary is True

    def test_no_summary_flag_set_true(self):
        parser, subparsers = make_parser()
        validate.add_parser(subparsers)
        args = parser.parse_args(["validate", "--no-summary"])
        assert args.no_summary is True
