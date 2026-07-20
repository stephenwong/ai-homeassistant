"""Shared test helpers for HA config test suite."""

import io
import tarfile
from argparse import ArgumentParser
from typing import Any


def make_tar(tmp_path, files, name="test.tar.gz"):
    """Create a gzipped tar archive containing UTF-8 text files."""
    tar_path = tmp_path / name
    with tarfile.open(tar_path, "w:gz") as tar:
        for filename, content in files.items():
            data = content.encode("utf-8")
            info = tarfile.TarInfo(name=filename)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return tar_path


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
