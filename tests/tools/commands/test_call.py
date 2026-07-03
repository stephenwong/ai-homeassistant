"""Tests for the ``call`` subcommand."""

import json
from argparse import Namespace
from unittest.mock import MagicMock, patch

import pytest

from tests.helpers import make_parser
from tools.commands import call as call_cmd
from tools.common import HARequestError
from tools.ha.client import HAClient


def make_args(**overrides):
    defaults = dict(
        service="light.turn_on",
        data=None,
        pretty=False,
        summary=False,
        no_summary=True,
    )
    defaults.update(overrides)
    return Namespace(**defaults)


@pytest.fixture
def mock_client():
    with patch("tools.commands.call.HAClient.from_env") as mock_from_env:
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


def text_resp(text="ok", ct="text/plain", status=200):
    r = MagicMock()
    r.ok = status < 400
    r.status_code = status
    r.headers = {"content-type": ct}
    r.text = text
    return r


class TestAddParser:
    def test_registered_with_service(self):
        parser, subparsers = make_parser()
        call_cmd.add_parser(subparsers)
        args = parser.parse_args(["call", "light.turn_on"])
        assert callable(args.func)
        assert args.service == "light.turn_on"

    def test_data_flag_accepts_json(self):
        parser, subparsers = make_parser()
        call_cmd.add_parser(subparsers)
        args = parser.parse_args(
            ["call", "light.turn_on", "-d", '{"entity_id": "light.kitchen"}']
        )
        assert args.data == '{"entity_id": "light.kitchen"}'

    def test_pretty_flag(self):
        parser, subparsers = make_parser()
        call_cmd.add_parser(subparsers)
        args = parser.parse_args(["call", "light.turn_on", "--pretty"])
        assert args.pretty is True

    def test_has_summary_flags(self):
        parser, subparsers = make_parser()
        call_cmd.add_parser(subparsers)
        args = parser.parse_args(["call", "x.y", "--summary"])
        assert args.summary is True


class TestRun:
    def test_invalid_service_format_returns_1(self, capsys):
        args = make_args(service="not_a_service")
        assert call_cmd.run(args) == 1
        err = capsys.readouterr().err
        assert "Invalid service" in err

    def test_invalid_json_data_returns_1(self, capsys):
        args = make_args(data="{not json")
        assert call_cmd.run(args) == 1
        err = capsys.readouterr().err
        assert "Invalid JSON" in err

    def test_non_dict_json_data_returns_1(self, capsys):
        args = make_args(data='["list", "not", "dict"]')
        assert call_cmd.run(args) == 1
        err = capsys.readouterr().err
        assert "must be a JSON object" in err

    def test_success_compact_json(self, mock_client, capsys):
        mock_client.post.return_value = json_resp(
            [{"entity_id": "light.kitchen", "state": "on"}]
        )
        args = make_args(data='{"entity_id": "light.kitchen"}')
        assert call_cmd.run(args) == 0
        out = capsys.readouterr().out
        assert '"entity_id":"light.kitchen"' in out
        assert "    " not in out  # compact — no indentation

    def test_success_pretty_json(self, mock_client, capsys):
        mock_client.post.return_value = json_resp(
            [{"entity_id": "light.kitchen", "state": "on"}]
        )
        args = make_args(data='{"entity_id": "light.kitchen"}', pretty=True)
        assert call_cmd.run(args) == 0
        out = capsys.readouterr().out
        assert '"entity_id": "light.kitchen"' in out
        assert "    " in out  # indented

    def test_success_no_data_defaults_to_empty_object(self, mock_client, capsys):
        mock_client.post.return_value = json_resp([])
        args = make_args(service="automation.reload")
        assert call_cmd.run(args) == 0
        assert mock_client.post.call_args is not None
        called_path, called_kwargs = mock_client.post.call_args
        assert called_path[0].endswith("/api/services/automation/reload")
        assert called_kwargs.get("json") == {}

    def test_success_empty_body_prints_nothing(self, mock_client, capsys):
        mock_client.post.return_value = text_resp("", ct="text/plain")
        args = make_args(service="automation.reload")
        assert call_cmd.run(args) == 0
        out = capsys.readouterr().out
        assert out == ""

    def test_http_400_returns_1(self, mock_client, capsys):
        mock_client.post.return_value = json_resp({"message": "bad entity"}, status=400)
        args = make_args()
        assert call_cmd.run(args) == 1
        err = capsys.readouterr().err
        assert "HTTP 400" in err

    def test_http_404_returns_1(self, mock_client, capsys):
        mock_client.post.return_value = json_resp(
            {"message": "Service not found"}, status=404
        )
        args = make_args()
        assert call_cmd.run(args) == 1
        err = capsys.readouterr().err
        assert "HTTP 404" in err

    def test_missing_token_returns_1(self, capsys):
        with patch("tools.commands.call.HAClient.from_env") as m:
            m.side_effect = HARequestError("HA_TOKEN not found")
            args = make_args()
            assert call_cmd.run(args) == 1
        err = capsys.readouterr().err
        assert "HA_TOKEN" in err

    def test_network_error_returns_1(self, mock_client, capsys):
        mock_client.post.side_effect = HARequestError("POST failed: boom")
        args = make_args()
        assert call_cmd.run(args) == 1
        err = capsys.readouterr().err
        assert "boom" in err

    def test_summary_suppresses_warnings(self, mock_client, capsys):
        mock_client.post.return_value = json_resp([])
        args = make_args(summary=True, no_summary=False)
        assert call_cmd.run(args) == 0
        err = capsys.readouterr().err
        assert err == ""  # no diagnostics leaked in summary mode

    def test_summary_does_not_suppress_data(self, mock_client, capsys):
        mock_client.post.return_value = json_resp(
            [{"entity_id": "light.kitchen", "state": "on"}]
        )
        args = make_args(
            data='{"entity_id": "light.kitchen"}', summary=True, no_summary=False
        )
        assert call_cmd.run(args) == 0
        out = capsys.readouterr().out
        assert '"entity_id":"light.kitchen"' in out
