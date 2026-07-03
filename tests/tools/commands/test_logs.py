"""Tests for the ``logs`` subcommand (WebSocket-based)."""

import json
from argparse import Namespace
from unittest.mock import MagicMock, patch

import pytest

from tests.helpers import make_parser
from tools.commands import logs as logs_cmd
from tools.common import HARequestError


def make_args(**overrides):
    defaults = dict(
        level=None,
        first=None,
        pretty=False,
        summary=False,
        no_summary=True,
        pick=None,
        max_chars=None,
    )
    defaults.update(overrides)
    return Namespace(**defaults)


@pytest.fixture
def mock_client():
    with patch("tools.commands.logs.HAWSClient.from_env") as mock_from_env:
        client = MagicMock()
        mock_from_env.return_value = client
        yield client


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

    def test_has_level_filter(self):
        parser, subparsers = make_parser()
        logs_cmd.add_parser(subparsers)
        args = parser.parse_args(["logs", "--level", "ERROR"])
        assert args.level == "ERROR"

    def test_has_first_flag(self):
        parser, subparsers = make_parser()
        logs_cmd.add_parser(subparsers)
        args = parser.parse_args(["logs", "--first", "5"])
        assert args.first == 5


class TestRun:
    def test_success_prints_json(self, mock_client, capsys):
        mock_client.command.return_value = [
            {
                "level": "ERROR",
                "name": "test.component",
                "message": ["something broke"],
                "timestamp": 123.0,
            },
        ]
        args = make_args()
        assert logs_cmd.run(args) == 0
        out = capsys.readouterr().out
        assert '"ERROR"' in out
        assert "    " not in out  # compact

    def test_success_pretty(self, mock_client, capsys):
        mock_client.command.return_value = [
            {"level": "WARNING", "name": "x", "message": ["warn"], "timestamp": 1.0},
        ]
        args = make_args(pretty=True)
        assert logs_cmd.run(args) == 0
        out = capsys.readouterr().out
        assert "    " in out  # indented

    def test_empty_log_prints_empty_list(self, mock_client, capsys):
        mock_client.command.return_value = []
        args = make_args()
        assert logs_cmd.run(args) == 0
        out = capsys.readouterr().out
        assert out.strip() == "[]"

    def test_level_filter_error(self, mock_client, capsys):
        mock_client.command.return_value = [
            {"level": "ERROR", "name": "a", "message": ["x"], "timestamp": 1.0},
            {"level": "WARNING", "name": "b", "message": ["y"], "timestamp": 2.0},
        ]
        args = make_args(level="ERROR")
        assert logs_cmd.run(args) == 0
        out = capsys.readouterr().out
        assert '"ERROR"' in out
        assert '"WARNING"' not in out

    def test_level_filter_case_insensitive(self, mock_client, capsys):
        mock_client.command.return_value = [
            {"level": "ERROR", "name": "a", "message": ["x"], "timestamp": 1.0},
        ]
        args = make_args(level="error")
        assert logs_cmd.run(args) == 0
        out = capsys.readouterr().out
        assert '"ERROR"' in out

    def test_calls_system_log_list(self, mock_client, capsys):
        mock_client.command.return_value = []
        args = make_args()
        logs_cmd.run(args)
        mock_client.command.assert_called_once_with("system_log/list")

    def test_first_n(self, mock_client, capsys):
        mock_client.command.return_value = [
            {"level": "ERROR", "name": "a", "message": ["x"], "timestamp": 1.0},
            {"level": "WARNING", "name": "b", "message": ["y"], "timestamp": 2.0},
            {"level": "ERROR", "name": "c", "message": ["z"], "timestamp": 3.0},
        ]
        args = make_args(first=2)
        assert logs_cmd.run(args) == 0
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert len(parsed) == 2
        assert parsed[0]["name"] == "a"

    def test_first_invalid_returns_1(self, capsys):
        args = make_args(first=0)
        assert logs_cmd.run(args) == 1
        err = capsys.readouterr().err
        assert "--first must be >= 1" in err

    def test_non_list_response_coerces_to_empty(self, mock_client, capsys):
        mock_client.command.return_value = None
        args = make_args()
        assert logs_cmd.run(args) == 0
        out = capsys.readouterr().out
        assert out.strip() == "[]"

    def test_summary_mode_projects_fields(self, mock_client, capsys):
        mock_client.command.return_value = [
            {
                "level": "ERROR",
                "name": "test",
                "message": ["x"],
                "timestamp": 1.0,
                "source": ["component", None],
                "count": 5,
                "first_occurred": "2026-01-01",
                "exception": None,
            },
        ]
        args = make_args(summary=True, no_summary=False)
        assert logs_cmd.run(args) == 0
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert set(parsed[0].keys()) == {
            "level",
            "name",
            "message",
            "timestamp",
            "count",
            "first_occurred",
        }
        assert parsed[0]["count"] == 5
        assert parsed[0]["first_occurred"] == "2026-01-01"

    def test_summary_drops_first_occurred_when_count_is_one(self, mock_client, capsys):
        mock_client.command.return_value = [
            {
                "level": "ERROR",
                "name": "test",
                "message": ["x"],
                "timestamp": 1.0,
                "count": 1,
                "first_occurred": "2026-01-01",
            },
        ]
        args = make_args(summary=True, no_summary=False)
        assert logs_cmd.run(args) == 0
        result = json.loads(capsys.readouterr().out)
        assert result[0]["count"] == 1
        assert "first_occurred" not in result[0]

    def test_summary_omits_first_occurred_when_count_is_none(self, mock_client, capsys):
        mock_client.command.return_value = [
            {
                "level": "ERROR",
                "name": "test",
                "message": ["x"],
                "timestamp": 1.0,
            },
        ]
        args = make_args(summary=True, no_summary=False)
        assert logs_cmd.run(args) == 0
        result = json.loads(capsys.readouterr().out)
        assert result[0]["count"] is None
        assert "first_occurred" not in result[0]

    def test_summary_bool_count_no_first_occurred(self, mock_client, capsys):
        """Boolean count values should be treated as non-int (bool guard)."""
        mock_client.command.return_value = [
            {
                "level": "ERROR",
                "name": "test",
                "message": ["x"],
                "timestamp": 1.0,
                "count": True,
                "first_occurred": "2026-01-01",
            },
        ]
        args = make_args(summary=True, no_summary=False)
        assert logs_cmd.run(args) == 0
        result = json.loads(capsys.readouterr().out)
        assert result[0]["count"] is True
        assert "first_occurred" not in result[0]

    def test_missing_token_returns_1(self, capsys):
        with patch("tools.commands.logs.HAWSClient.from_env") as m:
            m.side_effect = HARequestError("HA_TOKEN not found")
            args = make_args()
            assert logs_cmd.run(args) == 1
        err = capsys.readouterr().err
        assert "HA_TOKEN" in err

    def test_websocket_error_returns_1(self, mock_client, capsys):
        mock_client.command.side_effect = HARequestError(
            "system_log/list failed: unknown command"
        )
        args = make_args()
        assert logs_cmd.run(args) == 1
        err = capsys.readouterr().err
        assert "unknown command" in err


class TestPick:
    def test_pick_keeps_fields(self, mock_client, capsys):
        mock_client.command.return_value = [
            {
                "level": "ERROR",
                "name": "x.y",
                "message": "m",
                "timestamp": 1.0,
                "extra": "z",
            }
        ]
        args = make_args(pick="level,message")
        assert logs_cmd.run(args) == 0
        result = __import__("json").loads(capsys.readouterr().out)
        assert result == [{"level": "ERROR", "message": "m"}]


class TestSummaryCompaction:
    def test_collapses_long_name(self, mock_client, capsys):
        mock_client.command.return_value = [
            {
                "level": "WARNING",
                "name": "custom_components.localtuya.common",
                "message": "x",
                "timestamp": 1.0,
            }
        ]
        args = make_args(summary=True, no_summary=False)
        assert logs_cmd.run(args) == 0
        result = __import__("json").loads(capsys.readouterr().out)
        assert result[0]["name"] == "localtuya.common"

    def test_flattens_message_list(self, mock_client, capsys):
        mock_client.command.return_value = [
            {
                "level": "WARNING",
                "name": "x.y",
                "message": ["first", "second"],
                "timestamp": 1.0,
            }
        ]
        args = make_args(summary=True, no_summary=False)
        assert logs_cmd.run(args) == 0
        result = __import__("json").loads(capsys.readouterr().out)
        assert result[0]["message"] == "first"


class TestDefaultCap:
    def test_summary_default_cap(self, mock_client, capsys):
        mock_client.command.return_value = [
            {"level": "WARNING", "name": "x.y", "message": "x" * 200, "timestamp": 1.0}
            for _ in range(200)
        ]
        args = make_args(summary=True, no_summary=False)
        assert logs_cmd.run(args) == 0
        out = capsys.readouterr().out
        assert len(out) <= 8000
        result = __import__("json").loads(out)
        assert result[-1].get("_truncated") is True
