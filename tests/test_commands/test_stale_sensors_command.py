"""Tests for tools/commands/stale_sensors.py — stale-sensors subcommand wrapper."""

import argparse
from argparse import Namespace
from unittest.mock import MagicMock, patch

# Since tools/commands/stale_sensors.py doesn't exist yet, import under try-except.
try:
    from tools.commands import stale_sensors as stale_cmd
except ImportError:
    stale_cmd = None  # type: ignore


class TestAddParser:
    def test_subparser_registered(self):
        assert stale_cmd is not None
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        stale_cmd.add_parser(subparsers)
        args = parser.parse_args(["stale-sensors"])
        assert args.command == "stale-sensors"
        assert callable(args.func)

    def test_accepts_all_flags(self):
        assert stale_cmd is not None
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        stale_cmd.add_parser(subparsers)
        args = parser.parse_args(
            [
                "stale-sensors",
                "--config",
                "my_config",
                "--threshold",
                "12",
                "--exclude-domains",
                "binary_sensor,light",
                "--exclude-platforms",
                "template, group",
                "--only-domains",
                "sensor",
                "--ignore-restored",
                "--fail-on-stale",
            ]
        )
        assert args.config == "my_config"
        assert args.threshold == 12
        assert args.exclude_domains == "binary_sensor,light"
        assert args.exclude_platforms == "template, group"
        assert args.only_domains == "sensor"
        assert args.ignore_restored is True
        assert args.fail_on_stale is True


class TestRun:
    @patch("tools.commands.stale_sensors.StaleSensorValidator")
    def test_run_delegates_to_validator(self, mock_val_class):
        assert stale_cmd is not None
        mock_val = MagicMock()
        mock_val.validate_all.return_value = True
        mock_val.warnings = []
        mock_val_class.return_value = mock_val

        args = Namespace(
            config="config_path",
            threshold=12,
            exclude_domains="light,switch",
            exclude_platforms="template,group",
            only_domains="sensor",
            ignore_restored=True,
            fail_on_stale=False,
        )

        exit_code = stale_cmd.run(args)
        assert exit_code == 0

        # Verify StaleSensorValidator instantiation
        mock_val_class.assert_called_once_with(
            config_dir="config_path",
            threshold_hours=12,
            only_domains={"sensor"},
            exclude_platforms={"template", "group"},
            ignore_restored=True,
        )
        mock_val.validate_all.assert_called_once()
        mock_val.print_results.assert_called_once()

    @patch("tools.commands.stale_sensors.StaleSensorValidator")
    def test_fail_on_stale_behavior(self, mock_val_class):
        assert stale_cmd is not None
        mock_val = MagicMock()
        mock_val.validate_all.return_value = True
        mock_val.warnings = ["sensor.test_temp is stale"]
        mock_val_class.return_value = mock_val

        # Case 1: fail_on_stale is False -> exit code is 0
        args = Namespace(
            config="config_path",
            threshold=24,
            exclude_domains=None,
            exclude_platforms=None,
            only_domains=None,
            ignore_restored=False,
            fail_on_stale=False,
        )
        assert stale_cmd.run(args) == 0

        # Case 2: fail_on_stale is True -> exit code is 1
        args.fail_on_stale = True
        assert stale_cmd.run(args) == 1
