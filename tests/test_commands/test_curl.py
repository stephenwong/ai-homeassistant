"""Tests for tools/commands/curl.py — curl subcommand wrapper."""

from argparse import Namespace
from pathlib import Path
from unittest.mock import MagicMock, patch

from tools.commands import curl as curl_cmd


class TestAddParser:
    def test_subparser_registered(self):
        import argparse

        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        curl_cmd.add_parser(subparsers)
        args = parser.parse_args(["curl", "/api/states"])
        assert args.command == "curl"
        assert args.endpoint == "/api/states"
        assert callable(args.func)

    def test_default_method_is_get(self):
        import argparse

        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        curl_cmd.add_parser(subparsers)
        args = parser.parse_args(["curl", "/api/"])
        assert args.method == "GET"

    def test_post_flag_sets_method(self):
        """-X (no value) flag sets method to POST."""
        import argparse

        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        curl_cmd.add_parser(subparsers)
        args = parser.parse_args(["curl", "-X", "/api/services/light/turn_on"])
        assert args.method == "POST"

    def test_filter_flag(self):
        import argparse

        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        curl_cmd.add_parser(subparsers)
        args = parser.parse_args(["curl", "/api/states", "--filter", ". | length"])
        assert args.filter == ". | length"


class TestRun:
    def test_missing_ha_curl_returns_one(self, capsys, tmp_path, monkeypatch):
        """If ha-curl.sh doesn't exist, run() prints error and returns 1."""
        monkeypatch.setattr(curl_cmd, "_HA_CURL", tmp_path / "nonexistent.sh")
        args = Namespace(endpoint="/api/", method="GET", data=None, filter=None)
        assert curl_cmd.run(args) == 1

    def test_get_passthrough_subprocess(self, monkeypatch):
        """GET (no filter) should invoke subprocess.run with the bash command."""
        mock_result = MagicMock(returncode=0)
        monkeypatch.setattr(curl_cmd, "_HA_CURL", Path(__file__))
        with patch("tools.commands.curl.subprocess.run", return_value=mock_result):
            args = Namespace(endpoint="/api/", method="GET", data=None, filter=None)
            assert curl_cmd.run(args) == 0

    def test_post_includes_post_flag_in_command(self, monkeypatch):
        """POST method should append -X POST to the bash command."""
        mock_result = MagicMock(returncode=0)
        monkeypatch.setattr(curl_cmd, "_HA_CURL", Path(__file__))
        with patch(
            "tools.commands.curl.subprocess.run", return_value=mock_result
        ) as mock_run:
            args = Namespace(
                endpoint="/api/services/light/turn_on",
                method="POST",
                data=None,
                filter=None,
            )
            curl_cmd.run(args)
        cmd = mock_run.call_args[0][0]
        assert "-X" in cmd
        assert "POST" in cmd

    def test_data_passed_to_command(self, monkeypatch):
        mock_result = MagicMock(returncode=0)
        monkeypatch.setattr(curl_cmd, "_HA_CURL", Path(__file__))
        with patch(
            "tools.commands.curl.subprocess.run", return_value=mock_result
        ) as mock_run:
            args = Namespace(
                endpoint="/api/states/sensor.test",
                method="POST",
                data='{"state": "on"}',
                filter=None,
            )
            curl_cmd.run(args)
        cmd = mock_run.call_args[0][0]
        assert "-d" in cmd
        idx = cmd.index("-d")
        assert cmd[idx + 1] == '{"state": "on"}'

    def test_propagates_nonzero_returncode(self, monkeypatch):
        mock_result = MagicMock(returncode=2)
        monkeypatch.setattr(curl_cmd, "_HA_CURL", Path(__file__))
        with patch("tools.commands.curl.subprocess.run", return_value=mock_result):
            args = Namespace(endpoint="/api/", method="GET", data=None, filter=None)
            assert curl_cmd.run(args) == 2  # passthrough preserves actual code

    def test_filter_without_jq_warns_and_falls_back(self, monkeypatch, capsys):
        """If jq is missing, fall back to plain curl and warn."""
        monkeypatch.setattr(curl_cmd, "_HA_CURL", Path(__file__))
        with (
            patch("tools.commands.curl.shutil.which", return_value=None),
            patch(
                "tools.commands.curl.subprocess.run",
                return_value=MagicMock(returncode=0),
            ) as mock_run,
        ):
            args = Namespace(endpoint="/api/", method="GET", data=None, filter=".foo")
            curl_cmd.run(args)
        err = capsys.readouterr().err
        assert "jq not installed" in err
        # Should have called subprocess.run (passthrough), not Popen
        mock_run.assert_called_once()

    def test_filter_propagates_jq_failure(self, monkeypatch):
        """When curl succeeds but jq fails, return 1 (not curl's 0)."""
        monkeypatch.setattr(curl_cmd, "_HA_CURL", Path(__file__))
        mock_curl_proc = MagicMock()
        mock_curl_proc.returncode = 0
        mock_curl_proc.stdout = MagicMock()
        jq_result = MagicMock(returncode=3)
        with (
            patch("tools.commands.curl.shutil.which", return_value="/usr/bin/jq"),
            patch("tools.commands.curl.subprocess.Popen", return_value=mock_curl_proc),
            patch("tools.commands.curl.subprocess.run", return_value=jq_result),
        ):
            args = Namespace(endpoint="/api/", method="GET", data=None, filter=".bad")
            assert curl_cmd.run(args) == 1

    def test_filter_returns_zero_on_both_success(self, monkeypatch):
        """When curl and jq both succeed, return 0."""
        monkeypatch.setattr(curl_cmd, "_HA_CURL", Path(__file__))
        mock_curl_proc = MagicMock()
        mock_curl_proc.returncode = 0
        mock_curl_proc.stdout = MagicMock()
        jq_result = MagicMock(returncode=0)
        with (
            patch("tools.commands.curl.shutil.which", return_value="/usr/bin/jq"),
            patch("tools.commands.curl.subprocess.Popen", return_value=mock_curl_proc),
            patch("tools.commands.curl.subprocess.run", return_value=jq_result),
        ):
            args = Namespace(endpoint="/api/", method="GET", data=None, filter=".")
            assert curl_cmd.run(args) == 0
