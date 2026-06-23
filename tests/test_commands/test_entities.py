"""Tests for tools/commands/entities.py — entities subcommand wrapper."""

from argparse import Namespace
from unittest.mock import patch

from tools.commands import entities as entities_cmd


class TestAddParser:
    def test_subparser_registered(self):
        import argparse

        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        entities_cmd.add_parser(subparsers)
        args = parser.parse_args(["entities"])
        assert args.command == "entities"
        assert callable(args.func)

    def test_accepts_all_flags(self):
        import argparse

        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
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
