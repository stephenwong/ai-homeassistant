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
    def test_forwards_args_to_entity_registry(self):
        """run() passes the Namespace directly to entity_registry.run()."""
        with patch("tools.commands.entities.entity_registry.run", return_value=0) as m:
            flags = Namespace(
                config="my_config",
                domain="light",
                area=None,
                search=None,
                full=False,
                json=False,
                summary=False,
                no_summary=False,
                force=False,
            )
            assert entities_cmd.run(flags) == 0
            m.assert_called_once_with(flags)

    def test_propagates_exit_code(self):
        with patch("tools.commands.entities.entity_registry.run", return_value=1):
            args = Namespace(
                config="config",
                domain=None,
                area=None,
                search=None,
                full=False,
                json=False,
                summary=False,
                no_summary=False,
                force=False,
            )
            assert entities_cmd.run(args) == 1

    def test_non_int_return_coerced_to_zero(self):
        with patch("tools.commands.entities.entity_registry.run", return_value=None):
            args = Namespace(
                config="config",
                domain=None,
                area=None,
                search=None,
                full=False,
                json=False,
                summary=False,
                no_summary=False,
                force=False,
            )
            assert entities_cmd.run(args) == 0
