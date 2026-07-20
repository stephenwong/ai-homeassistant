"""Tests for tools/ha_cli.py — top-level CLI dispatcher."""

from unittest.mock import MagicMock, patch

import pytest

from tools.ha_cli import _COMMAND_MODULES, build_parser, main


class TestBuildParser:
    def test_command_registry_preserves_registration_order(self):
        assert [module.__name__.rsplit(".", 1)[-1] for module in _COMMAND_MODULES] == [
            "validate",
            "reload",
            "curl",
            "edit",
            "stale_sensors",
            "trace",
        ]
        parser = build_parser()
        subparser_action = parser._subparsers._group_actions[0]
        assert list(subparser_action.choices) == [
            "validate",
            "reload",
            "curl",
            "edit",
            "stale-sensors",
            "trace",
        ]

    def test_has_validate_subcommand(self):
        parser = build_parser()
        args = parser.parse_args(["validate"])
        assert args.command == "validate"
        assert callable(args.func)

    def test_has_reload_subcommand(self):
        parser = build_parser()
        args = parser.parse_args(["reload"])
        assert args.command == "reload"
        assert callable(args.func)

    def test_entities_removed(self):
        """entities subcommand was removed — verify argparse rejects it."""
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["entities"])

    def test_has_stale_sensors_subcommand(self):
        parser = build_parser()
        args = parser.parse_args(["stale-sensors"])
        assert args.command == "stale-sensors"
        assert callable(args.func)

    def test_has_curl_subcommand(self):
        parser = build_parser()
        args = parser.parse_args(["curl", "/api/"])
        assert args.command == "curl"
        assert args.endpoint == "/api/"
        assert callable(args.func)

    def test_has_edit_subcommand(self):
        """L5: the edit subcommand is registered with a func callable."""
        parser = build_parser()
        args = parser.parse_args(["edit", "automations"])
        assert args.command == "edit"
        assert args.file == "automations"
        assert callable(args.func)

    def test_has_trace_subcommand(self):
        """L5: the trace subcommand is registered."""
        parser = build_parser()
        args = parser.parse_args(["trace"])
        assert args.command == "trace"
        assert callable(args.func)

    def test_validate_accepts_config_flag(self):
        parser = build_parser()
        args = parser.parse_args(["validate", "--config", "/tmp/config"])
        assert args.config == "/tmp/config"

    def test_validate_accepts_config_short_flag(self):
        parser = build_parser()
        args = parser.parse_args(["validate", "-c", "/tmp/config"])
        assert args.config == "/tmp/config"

    def test_validate_accepts_quiet_flag(self):
        parser = build_parser()
        args = parser.parse_args(["validate", "--quiet"])
        assert args.quiet is True

    def test_validate_quiet_defaults_false(self):
        parser = build_parser()
        args = parser.parse_args(["validate"])
        assert args.quiet is False

    def test_no_subcommand_prints_help_exits_2(self, capsys):
        with pytest.raises(SystemExit) as exc:
            build_parser().parse_args([])
        # argparse exits with code 2 when a required subparser is missing
        assert exc.value.code == 2


class TestMain:
    def test_validate_dispatches_to_command(self):
        """main() should call the subcommand's run() function."""
        with patch("tools.commands.validate.run", return_value=0) as mock_run:
            result = main(["validate", "--quiet"])
        assert result == 0
        mock_run.assert_called_once()

    def test_stale_sensors_dispatches_to_command(self):
        with patch("tools.commands.stale_sensors.run", return_value=0) as mock_run:
            result = main(["stale-sensors"])
        assert result == 0
        mock_run.assert_called_once()

    def test_reload_dispatches_to_command(self):
        with patch("tools.commands.reload.run", return_value=0) as mock_run:
            result = main(["reload"])
        assert result == 0
        mock_run.assert_called_once()

    def test_returns_command_exit_code_on_success(self):
        with patch("tools.commands.validate.run", return_value=0):
            assert main(["validate"]) == 0

    def test_returns_command_exit_code_on_failure(self):
        with patch("tools.commands.validate.run", return_value=1):
            assert main(["validate"]) == 1

    def test_keyboard_interrupt_returns_130(self):
        def _interrupt(_args):
            raise KeyboardInterrupt

        with patch("tools.commands.validate.run", side_effect=_interrupt):
            assert main(["validate"]) == 130

    def test_no_func_returns_2(self):
        """If somehow no func is set, main returns 2 (misconfiguration)."""
        # Build a parser that doesn't set_defaults(func=...)
        with patch("tools.ha_cli.build_parser") as mock_parser_factory:
            parser = MagicMock()
            args = MagicMock(spec=[])
            # args has no `func` attribute
            parser.parse_args.return_value = args
            mock_parser_factory.return_value = parser
            result = main(["validate"])
        assert result == 2
