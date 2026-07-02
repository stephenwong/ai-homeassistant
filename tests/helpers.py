"""Shared test helpers for HA config test suite."""

from argparse import ArgumentParser
from typing import Any


def make_parser() -> tuple[ArgumentParser, Any]:
    """Create a parser with a subparser group.

    Returns ``(parser, subparsers)`` so callers can register a subcommand
    and then invoke ``parser.parse_args``::

        parser, subparsers = make_parser()
        from tools.commands.edit import add_parser
        add_parser(subparsers)
        args = parser.parse_args(["edit", "automations"])
    """
    parser = ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    return parser, subparsers
