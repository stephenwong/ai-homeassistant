"""Tests for tools/commands/reload.py — reload subcommand wrapper."""

from argparse import Namespace
from unittest.mock import patch

from tools.commands import reload as reload_cmd


class TestAddParser:
    def test_subparser_registered(self):
        import argparse

        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        reload_cmd.add_parser(subparsers)
        args = parser.parse_args(["reload"])
        assert args.command == "reload"
        assert callable(args.func)


class TestRun:
    def test_success_returns_zero(self):
        with patch("tools.commands.reload.reload_config", return_value=True):
            assert reload_cmd.run(Namespace()) == 0

    def test_failure_returns_one(self):
        with patch("tools.commands.reload.reload_config", return_value=False):
            assert reload_cmd.run(Namespace()) == 1

    def test_delegates_to_reload_config(self):
        """run() should call reload_config() and propagate its return value."""
        with patch(
            "tools.commands.reload.reload_config", return_value=True
        ) as mock_reload:
            reload_cmd.run(Namespace())
        mock_reload.assert_called_once()
