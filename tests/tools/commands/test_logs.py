"""Tests for the ``logs`` subcommand."""

from argparse import Namespace
from unittest.mock import MagicMock, patch

import pytest

from tests.helpers import make_parser
from tools.commands import logs as logs_cmd
from tools.common import HARequestError
from tools.ha.client import HAClient


def make_args(**overrides):
    defaults = dict(
        summary=False,
        no_summary=True,
    )
    defaults.update(overrides)
    return Namespace(**defaults)


@pytest.fixture
def mock_client():
    with patch("tools.commands.logs.HAClient.from_env") as mock_from_env:
        client = MagicMock(spec=HAClient)
        client.url = "http://ha:8123"
        client.token = "tok"
        client.timeout = 10
        client.headers = {
            "Authorization": "Bearer tok",
            "Content-Type": "application/json",
        }
        mock_from_env.return_value = client
        yield client


def text_resp(text="ok", ct="text/plain", status=200):
    r = MagicMock()
    r.ok = status < 400
    r.status_code = status
    r.headers = {"content-type": ct}
    r.text = text
    return r


class TestAddParser:
    def test_registered_as_subcommand(self):
        parser, subparsers = make_parser()
        logs_cmd.add_parser(subparsers)
        args = parser.parse_args(["logs"])
        assert callable(args.func)

    def test_has_summary_flags(self):
        parser, subparsers = make_parser()
        logs_cmd.add_parser(subparsers)
        args = parser.parse_args(["logs", "--summary"])
        assert args.summary is True
        args2 = parser.parse_args(["logs", "--no-summary"])
        assert args2.no_summary is True


class TestRun:
    def test_success_prints_log_text(self, mock_client, capsys):
        mock_client.get.return_value = text_resp("line1\nline2\n")
        args = make_args()
        assert logs_cmd.run(args) == 0
        out = capsys.readouterr().out
        assert "line1" in out
        assert "line2" in out

    def test_summary_mode_still_prints_text(self, mock_client, capsys):
        mock_client.get.return_value = text_resp("some log content\n")
        args = make_args(summary=True, no_summary=False)
        assert logs_cmd.run(args) == 0
        out = capsys.readouterr().out
        assert "some log content" in out

    def test_no_trailing_newline_added(self, mock_client, capsys):
        mock_client.get.return_value = text_resp("x")
        args = make_args()
        assert logs_cmd.run(args) == 0
        out = capsys.readouterr().out
        assert out == "x"

    def test_empty_log_prints_nothing(self, mock_client, capsys):
        mock_client.get.return_value = text_resp("")
        args = make_args()
        assert logs_cmd.run(args) == 0
        out = capsys.readouterr().out
        assert out == ""

    def test_missing_token_returns_1(self, capsys):
        with patch("tools.commands.logs.HAClient.from_env") as m:
            m.side_effect = HARequestError("HA_TOKEN not found")
            args = make_args()
            assert logs_cmd.run(args) == 1
        err = capsys.readouterr().err
        assert "HA_TOKEN" in err

    def test_network_error_returns_1(self, mock_client, capsys):
        mock_client.get.side_effect = HARequestError("GET /api/error_log failed: boom")
        args = make_args()
        assert logs_cmd.run(args) == 1
        err = capsys.readouterr().err
        assert "boom" in err

    def test_http_500_returns_1(self, mock_client, capsys):
        mock_client.get.return_value = text_resp("server error", status=500)
        args = make_args()
        assert logs_cmd.run(args) == 1
        err = capsys.readouterr().err
        assert "HTTP 500" in err
