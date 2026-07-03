"""Tests for tools/commands/entities.py — entities subcommand wrapper."""

from argparse import Namespace
from unittest.mock import patch

from tests.helpers import make_parser
from tools.commands import entities as entities_cmd


class TestAddParser:
    def test_subparser_registered(self):
        parser, subparsers = make_parser()
        entities_cmd.add_parser(subparsers)
        args = parser.parse_args(["entities"])
        assert args.command == "entities"
        assert callable(args.func)

    def test_accepts_all_flags(self):
        parser, subparsers = make_parser()
        entities_cmd.add_parser(subparsers)
        args = parser.parse_args(
            [
                "entities",
                "--config",
                "config",
                "--domain",
                "light",
                "--area",
                "kitchen",
                "--search",
                "temp",
                "--full",
                "--json",
            ]
        )
        assert args.domain == "light"
        assert args.area == "kitchen"
        assert args.search == "temp"
        assert args.full is True
        assert args.json is True

    def test_summary_flag_registered(self):
        parser, subparsers = make_parser()
        entities_cmd.add_parser(subparsers)
        args = parser.parse_args(["entities", "--summary"])
        assert args.summary is True

    def test_no_summary_flag_registered(self):
        parser, subparsers = make_parser()
        entities_cmd.add_parser(subparsers)
        args = parser.parse_args(["entities", "--no-summary"])
        assert args.no_summary is True

    def test_summary_defaults_false(self):
        parser, subparsers = make_parser()
        entities_cmd.add_parser(subparsers)
        args = parser.parse_args(["entities"])
        assert args.summary is False
        assert args.no_summary is False

    def test_force_flag_registered(self):
        parser, subparsers = make_parser()
        entities_cmd.add_parser(subparsers)
        args = parser.parse_args(["entities", "--force"])
        assert args.force is True

    def test_force_defaults_false(self):
        parser, subparsers = make_parser()
        entities_cmd.add_parser(subparsers)
        args = parser.parse_args(["entities"])
        assert args.force is False


class TestRun:
    def test_passes_flags_as_argv(self):
        """run() passes correct argv list to entity_explorer.main()."""
        with patch("tools.commands.entities.entity_explorer.main", return_value=0) as m:
            args = Namespace(
                config="config",
                domain=None,
                area=None,
                search="temp",
                full=False,
                json=False,
            )
            assert entities_cmd.run(args) == 0
            m.assert_called_once()
            passed_argv = m.call_args.args[0]
            assert isinstance(passed_argv, list)
            assert "--search" in passed_argv
            assert "temp" in passed_argv

    def test_passes_json_flag(self):
        """--json should appear in the argv passed to entity_explorer.main()."""
        with patch("tools.commands.entities.entity_explorer.main", return_value=0) as m:
            args = Namespace(
                config="config",
                domain=None,
                area=None,
                search=None,
                full=False,
                json=True,
            )
            entities_cmd.run(args)
            m.assert_called_once()
            passed_argv = m.call_args.args[0]
            assert "--json" in passed_argv

    def test_propagates_nonzero_exit_code(self):
        with patch("tools.commands.entities.entity_explorer.main", return_value=1):
            args = Namespace(
                config="config",
                domain=None,
                area=None,
                search=None,
                full=False,
                json=False,
            )
            assert entities_cmd.run(args) == 1

    def test_non_int_return_coerced_to_zero(self):
        with patch("tools.commands.entities.entity_explorer.main", return_value=None):
            args = Namespace(
                config="config",
                domain=None,
                area=None,
                search=None,
                full=False,
                json=False,
            )
            assert entities_cmd.run(args) == 0

    def test_forwards_summary_flag(self):
        """--summary should appear in argv when summary=True."""
        with patch("tools.commands.entities.entity_explorer.main", return_value=0) as m:
            args = Namespace(
                config="config",
                domain=None,
                area=None,
                search=None,
                full=False,
                json=False,
            )
            args.summary = True
            args.no_summary = False
            entities_cmd.run(args)
            passed_argv = m.call_args.args[0]
            assert "--summary" in passed_argv

    def test_forwards_no_summary_flag(self):
        """--no-summary should appear in argv when no_summary=True."""
        with patch("tools.commands.entities.entity_explorer.main", return_value=0) as m:
            args = Namespace(
                config="config",
                domain=None,
                area=None,
                search=None,
                full=False,
                json=False,
            )
            args.summary = False
            args.no_summary = True
            entities_cmd.run(args)
            passed_argv = m.call_args.args[0]
            assert "--no-summary" in passed_argv

    def test_forwards_force_flag(self):
        """--force should appear in argv when force=True."""
        with patch("tools.commands.entities.entity_explorer.main", return_value=0) as m:
            args = Namespace(
                config="config",
                domain=None,
                area=None,
                search=None,
                full=False,
                json=False,
            )
            args.summary = False
            args.no_summary = False
            args.force = True
            entities_cmd.run(args)
            passed_argv = m.call_args.args[0]
            assert "--force" in passed_argv
