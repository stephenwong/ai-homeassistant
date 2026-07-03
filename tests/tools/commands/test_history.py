"""Tests for the ``history`` subcommand."""

import json
from argparse import Namespace
from unittest.mock import MagicMock, patch

import pytest

from tests.helpers import make_parser
from tools.commands import history as history_cmd
from tools.common import HARequestError
from tools.ha.client import HAClient


def make_args(**overrides):
    defaults = dict(
        entity_id="sensor.temp",
        since=None,
        end=None,
        minimal=False,
        pretty=False,
        summary=False,
        no_summary=True,
    )
    defaults.update(overrides)
    return Namespace(**defaults)


@pytest.fixture
def mock_client():
    with patch("tools.commands.history.HAClient.from_env") as mock_from_env:
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


def json_resp(data, status=200):
    r = MagicMock()
    r.ok = status < 400
    r.status_code = status
    r.headers = {"content-type": "application/json"}
    r.text = json.dumps(data)
    r.json.return_value = data
    return r


class TestAddParser:
    def test_registered_with_entity(self):
        parser, subparsers = make_parser()
        history_cmd.add_parser(subparsers)
        args = parser.parse_args(["history", "sensor.temp"])
        assert callable(args.func)
        assert args.entity_id == "sensor.temp"

    def test_since_flag(self):
        parser, subparsers = make_parser()
        history_cmd.add_parser(subparsers)
        args = parser.parse_args(
            ["history", "sensor.temp", "--since", "2026-07-01T00:00:00Z"]
        )
        assert args.since == "2026-07-01T00:00:00Z"

    def test_end_flag(self):
        parser, subparsers = make_parser()
        history_cmd.add_parser(subparsers)
        args = parser.parse_args(
            ["history", "sensor.temp", "--end", "2026-07-02T00:00:00Z"]
        )
        assert args.end == "2026-07-02T00:00:00Z"

    def test_minimal_flag(self):
        parser, subparsers = make_parser()
        history_cmd.add_parser(subparsers)
        args = parser.parse_args(["history", "sensor.temp", "--minimal"])
        assert args.minimal is True

    def test_has_summary_flags(self):
        parser, subparsers = make_parser()
        history_cmd.add_parser(subparsers)
        args = parser.parse_args(["history", "sensor.temp", "--summary"])
        assert args.summary is True


class TestRun:
    def test_invalid_entity_returns_1(self, capsys):
        args = make_args(entity_id="bad")
        assert history_cmd.run(args) == 1
        err = capsys.readouterr().err
        assert "Invalid entity_id" in err

    def test_success_compact_json_unwraps_nested_list(self, mock_client, capsys):
        mock_client.get_json.return_value = [
            [{"entity_id": "sensor.temp", "state": "21.5"}]
        ]
        args = make_args()
        assert history_cmd.run(args) == 0
        out = capsys.readouterr().out
        assert '"entity_id":"sensor.temp"' in out
        assert "[[" not in out  # unwrapped

    def test_success_pretty_json(self, mock_client, capsys):
        mock_client.get_json.return_value = [
            [{"entity_id": "sensor.temp", "state": "21.5"}]
        ]
        args = make_args(pretty=True)
        assert history_cmd.run(args) == 0
        out = capsys.readouterr().out
        assert '"entity_id": "sensor.temp"' in out
        assert "    " in out  # indented

    def test_empty_history_prints_empty_list(self, mock_client, capsys):
        mock_client.get_json.return_value = [[]]
        args = make_args()
        assert history_cmd.run(args) == 0
        out = capsys.readouterr().out
        assert out.strip() == "[]"

    def test_empty_outer_list_prints_empty_list(self, mock_client, capsys):
        mock_client.get_json.return_value = []
        args = make_args()
        assert history_cmd.run(args) == 0
        out = capsys.readouterr().out
        assert out.strip() == "[]"

    def test_since_inserted_into_path(self, mock_client, capsys):
        mock_client.get_json.return_value = [[]]
        args = make_args(since="2026-07-01T00:00:00Z")
        assert history_cmd.run(args) == 0
        call_args = mock_client.get_json.call_args
        path = call_args[0][0]
        assert "/api/history/period/2026-07-01T00:00:00Z" in path

    def test_no_since_uses_bare_period_path(self, mock_client, capsys):
        mock_client.get_json.return_value = [[]]
        args = make_args()
        assert history_cmd.run(args) == 0
        call_args = mock_client.get_json.call_args
        path = call_args[0][0]
        assert path == "/api/history/period"

    def test_end_time_added_as_param(self, mock_client, capsys):
        mock_client.get_json.return_value = [[]]
        args = make_args(end="2026-07-02T00:00:00Z")
        assert history_cmd.run(args) == 0
        call_kwargs = mock_client.get_json.call_args.kwargs
        params = call_kwargs.get("params", {})
        assert params.get("end_time") == "2026-07-02T00:00:00Z"

    def test_minimal_flag_adds_param(self, mock_client, capsys):
        mock_client.get_json.return_value = [[]]
        args = make_args(minimal=True)
        assert history_cmd.run(args) == 0
        call_kwargs = mock_client.get_json.call_args.kwargs
        params = call_kwargs.get("params", {})
        assert params.get("minimal") == "1"

    def test_entity_filter_in_params(self, mock_client, capsys):
        mock_client.get_json.return_value = [[]]
        args = make_args(entity_id="sensor.outside")
        assert history_cmd.run(args) == 0
        call_kwargs = mock_client.get_json.call_args.kwargs
        params = call_kwargs.get("params", {})
        assert params.get("filter_entity_id") == "sensor.outside"

    def test_missing_token_returns_1(self, capsys):
        with patch("tools.commands.history.HAClient.from_env") as m:
            m.side_effect = HARequestError("HA_TOKEN not found")
            args = make_args()
            assert history_cmd.run(args) == 1
        err = capsys.readouterr().err
        assert "HA_TOKEN" in err

    def test_network_error_returns_1(self, mock_client, capsys):
        mock_client.get_json.side_effect = HARequestError(
            "GET /api/history/period failed: boom"
        )
        args = make_args()
        assert history_cmd.run(args) == 1
        err = capsys.readouterr().err
        assert "boom" in err

    def test_summary_does_not_suppress_data(self, mock_client, capsys):
        mock_client.get_json.return_value = [
            [{"entity_id": "sensor.temp", "state": "21.5"}]
        ]
        args = make_args(summary=True, no_summary=False)
        assert history_cmd.run(args) == 0
        out = capsys.readouterr().out
        assert "sensor.temp" in out
