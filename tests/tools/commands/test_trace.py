"""Tests for the ``trace`` subcommand."""

import json
from argparse import Namespace
from unittest.mock import MagicMock, patch

import pytest

from tests.helpers import make_parser
from tools.commands import trace as trace_cmd
from tools.common import HARequestError
from tools.ha.client import HAClient


def make_args(**overrides):
    defaults = dict(
        entity_id=None,
        pretty=False,
        summary=False,
        no_summary=True,
    )
    defaults.update(overrides)
    return Namespace(**defaults)


@pytest.fixture
def mock_client():
    with patch("tools.commands.trace.HAClient.from_env") as mock_from_env:
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
    def test_registered_no_entity_required(self):
        parser, subparsers = make_parser()
        trace_cmd.add_parser(subparsers)
        args = parser.parse_args(["trace"])
        assert callable(args.func)
        assert args.entity_id is None

    def test_registered_with_entity(self):
        parser, subparsers = make_parser()
        trace_cmd.add_parser(subparsers)
        args = parser.parse_args(["trace", "automation.foo"])
        assert args.entity_id == "automation.foo"

    def test_has_summary_flags(self):
        parser, subparsers = make_parser()
        trace_cmd.add_parser(subparsers)
        args = parser.parse_args(["trace", "--summary"])
        assert args.summary is True


class TestRun:
    def test_invalid_entity_returns_1(self, capsys):
        args = make_args(entity_id="../../api/services/light/turn_on")
        assert trace_cmd.run(args) == 1
        err = capsys.readouterr().err
        assert "Invalid entity_id" in err

    def test_list_all_mode_compact(self, mock_client, capsys):
        mock_client.get_json.return_value = {
            "automation.foo": {"last_run": "2026-01-01"},
            "automation.bar": {"last_run": "2026-01-02"},
        }
        args = make_args()
        assert trace_cmd.run(args) == 0
        out = capsys.readouterr().out
        assert '"automation.foo"' in out
        assert '"automation.bar"' in out
        assert "    " not in out  # compact — no indentation

    def test_list_all_mode_pretty(self, mock_client, capsys):
        mock_client.get_json.return_value = {
            "automation.foo": {"last_run": "2026-01-01"},
        }
        args = make_args(pretty=True)
        assert trace_cmd.run(args) == 0
        out = capsys.readouterr().out
        assert '"automation.foo"' in out
        assert "    " in out  # indented

    def test_single_entity_mode(self, mock_client, capsys):
        mock_client.get_json.return_value = {
            "domain": "automation",
            "item_id": "foo",
            "trace": {"steps": []},
        }
        args = make_args(entity_id="automation.foo")
        assert trace_cmd.run(args) == 0
        out = capsys.readouterr().out
        assert '"domain":"automation"' in out

    def test_single_entity_calls_correct_path(self, mock_client, capsys):
        mock_client.get_json.return_value = {}
        args = make_args(entity_id="automation.foo")
        assert trace_cmd.run(args) == 0
        call_args = mock_client.get_json.call_args
        path = call_args[0][0]
        assert path == "/api/automation/trace/automation.foo"

    def test_list_all_calls_bare_path(self, mock_client, capsys):
        mock_client.get_json.return_value = {}
        args = make_args()
        assert trace_cmd.run(args) == 0
        call_args = mock_client.get_json.call_args
        path = call_args[0][0]
        assert path == "/api/automation/trace"

    def test_empty_trace_dict_prints_empty_object(self, mock_client, capsys):
        mock_client.get_json.return_value = {}
        args = make_args()
        assert trace_cmd.run(args) == 0
        out = capsys.readouterr().out
        assert out.strip() == "{}"

    def test_missing_token_returns_1(self, capsys):
        with patch("tools.commands.trace.HAClient.from_env") as m:
            m.side_effect = HARequestError("HA_TOKEN not found")
            args = make_args()
            assert trace_cmd.run(args) == 1
        err = capsys.readouterr().err
        assert "HA_TOKEN" in err

    def test_network_error_returns_1(self, mock_client, capsys):
        mock_client.get_json.side_effect = HARequestError(
            "GET /api/automation/trace failed: boom"
        )
        args = make_args()
        assert trace_cmd.run(args) == 1
        err = capsys.readouterr().err
        assert "boom" in err

    def test_summary_does_not_suppress_data(self, mock_client, capsys):
        mock_client.get_json.return_value = {
            "automation.foo": {"last_run": "2026-01-01"},
        }
        args = make_args(summary=True, no_summary=False)
        assert trace_cmd.run(args) == 0
        out = capsys.readouterr().out
        assert "automation.foo" in out
