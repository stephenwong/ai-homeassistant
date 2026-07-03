"""Tests for the ``trace`` subcommand (WebSocket-based)."""

import json
from argparse import Namespace
from unittest.mock import MagicMock, patch

import pytest

from tests.helpers import make_parser
from tools.commands import trace as trace_cmd
from tools.common import HARequestError


def make_args(**overrides):
    defaults = dict(
        entity_id=None,
        first=None,
        pretty=False,
        summary=False,
        no_summary=True,
    )
    defaults.update(overrides)
    return Namespace(**defaults)


@pytest.fixture
def mock_client():
    with patch("tools.commands.trace.HAWSClient.from_env") as mock_from_env:
        client = MagicMock()
        mock_from_env.return_value = client
        yield client


SAMPLE_TRACES = [
    {
        "item_id": "morning_routine",
        "run_id": "abc123",
        "state": "stopped",
        "script_execution": "finished",
        "timestamp": {
            "start": "2026-07-02T11:00:00Z",
            "finish": "2026-07-02T11:00:01Z",
        },
        "last_step": "action/0",
        "trigger": "state of binary_sensor.is_daytime",
        "domain": "automation",
    },
    {
        "item_id": "evening_lights",
        "run_id": "def456",
        "state": "stopped",
        "script_execution": "finished",
        "timestamp": {
            "start": "2026-07-02T20:00:00Z",
            "finish": "2026-07-02T20:00:02Z",
        },
        "last_step": "action/1",
        "trigger": "time",
        "domain": "automation",
    },
]


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

    def test_has_first_flag(self):
        parser, subparsers = make_parser()
        trace_cmd.add_parser(subparsers)
        args = parser.parse_args(["trace", "--first", "5"])
        assert args.first == 5

    def test_has_summary_flags(self):
        parser, subparsers = make_parser()
        trace_cmd.add_parser(subparsers)
        args = parser.parse_args(["trace", "--summary"])
        assert args.summary is True


class TestRun:
    def test_invalid_entity_returns_1(self, capsys):
        args = make_args(entity_id="../../bad")
        assert trace_cmd.run(args) == 1
        err = capsys.readouterr().err
        assert "Invalid entity_id" in err

    def test_list_mode_compact(self, mock_client, capsys):
        mock_client.command.return_value = SAMPLE_TRACES
        args = make_args()
        assert trace_cmd.run(args) == 0
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert len(parsed) == 2
        assert "    " not in out  # compact

    def test_list_mode_calls_trace_list(self, mock_client, capsys):
        mock_client.command.return_value = []
        args = make_args()
        trace_cmd.run(args)
        mock_client.command.assert_called_once_with("trace/list", domain="automation")

    def test_list_mode_pretty(self, mock_client, capsys):
        mock_client.command.return_value = SAMPLE_TRACES
        args = make_args(pretty=True)
        assert trace_cmd.run(args) == 0
        out = capsys.readouterr().out
        assert "    " in out  # indented

    def test_list_mode_summary_projects_fields(self, mock_client, capsys):
        """Summary mode projects trace list to {item_id, state, trigger, timestamp}."""
        mock_client.command.return_value = SAMPLE_TRACES
        args = make_args(summary=True, no_summary=False)
        assert trace_cmd.run(args) == 0
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert set(parsed[0].keys()) == {"item_id", "state", "trigger", "timestamp"}
        # Ensure full-field keys are absent in summary mode
        assert {"script_execution", "last_step", "domain"}.isdisjoint(parsed[0].keys())

    def test_list_mode_first_n(self, mock_client, capsys):
        mock_client.command.return_value = SAMPLE_TRACES
        args = make_args(first=1)
        assert trace_cmd.run(args) == 0
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert len(parsed) == 1
        assert parsed[0]["item_id"] == "morning_routine"  # first in sample order

    def test_first_invalid_returns_1(self, capsys):
        args = make_args(first=0)
        assert trace_cmd.run(args) == 1
        err = capsys.readouterr().err
        assert "--first must be >= 1" in err

    def test_first_plus_entity_id_warns(self, mock_client, capsys):
        """--first is silently ignored when an entity_id is given; stderr warns."""
        mock_client.command.side_effect = [
            SAMPLE_TRACES,
            {"trace": {}, "item_id": "morning_routine"},
        ]
        args = make_args(entity_id="automation.morning_routine", first=3)
        assert trace_cmd.run(args) == 0
        captured = capsys.readouterr()
        assert "ignored" in captured.err

    def test_single_entity_two_step_lookup(self, mock_client, capsys):
        """Single entity calls trace/list then trace/get."""
        mock_client.command.side_effect = [
            SAMPLE_TRACES,
            {
                "trace": {"trigger/1": {}},
                "config": {},
                "item_id": "morning_routine",
            },
        ]
        args = make_args(entity_id="automation.morning_routine")
        assert trace_cmd.run(args) == 0
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert parsed["item_id"] == "morning_routine"
        assert mock_client.command.call_count == 2
        second_call = mock_client.command.call_args_list[1]
        assert second_call[0][0] == "trace/get"
        assert second_call[1] == {
            "domain": "automation",
            "item_id": "morning_routine",
            "run_id": "abc123",
        }

    def test_single_entity_not_found_returns_1(self, mock_client, capsys):
        mock_client.command.return_value = SAMPLE_TRACES
        args = make_args(entity_id="automation.nonexistent")
        assert trace_cmd.run(args) == 1
        err = capsys.readouterr().err
        assert "No traces found" in err

    def test_single_entity_trace_get_failure(self, mock_client, capsys):
        """trace/get may fail if run_id expired between list and get."""
        mock_client.command.side_effect = [
            SAMPLE_TRACES,
            HARequestError("trace/get failed: trace not found"),
        ]
        args = make_args(entity_id="automation.morning_routine")
        assert trace_cmd.run(args) == 1
        err = capsys.readouterr().err
        assert "trace not found" in err

    def test_missing_token_returns_1(self, capsys):
        with patch("tools.commands.trace.HAWSClient.from_env") as m:
            m.side_effect = HARequestError("HA_TOKEN not found")
            args = make_args()
            assert trace_cmd.run(args) == 1
        err = capsys.readouterr().err
        assert "HA_TOKEN" in err

    def test_websocket_error_returns_1(self, mock_client, capsys):
        mock_client.command.side_effect = HARequestError(
            "trace/list failed: unknown command"
        )
        args = make_args()
        assert trace_cmd.run(args) == 1
        err = capsys.readouterr().err
        assert "unknown command" in err


class TestSummaryModeSingle:
    """In summary mode, single-entity trace drops verbose fields."""

    FULL_TRACE = {
        "trace": {"trigger/1": {"result": {"value": True}}},
        "config": {"alias": "Test", "triggers": [], "actions": []},
        "blueprint_inputs": {"param": "x"},
        "item_id": "test",
        "state": "stopped",
        "timestamp": {"start": "t1", "finish": "t2"},
    }

    def test_single_entity_summary_drops_config(self, mock_client, capsys):
        mock_client.command.side_effect = [
            [{"item_id": "test", "run_id": "r1"}],
            self.FULL_TRACE,
        ]
        args = make_args(entity_id="automation.test", summary=True, no_summary=False)
        assert trace_cmd.run(args) == 0
        result = json.loads(capsys.readouterr().out)
        assert "config" not in result
        assert "blueprint_inputs" not in result
        assert result["item_id"] == "test"
        assert result["state"] == "stopped"

    def test_single_entity_no_summary_keeps_config(self, mock_client, capsys):
        mock_client.command.side_effect = [
            [{"item_id": "test", "run_id": "r1"}],
            self.FULL_TRACE,
        ]
        args = make_args(entity_id="automation.test")
        assert trace_cmd.run(args) == 0
        result = json.loads(capsys.readouterr().out)
        assert "config" in result
        assert "blueprint_inputs" in result

    def test_single_entity_summary_with_pretty_keeps_config(self, mock_client, capsys):
        """--pretty overrides summary projection."""
        mock_client.command.side_effect = [
            [{"item_id": "test", "run_id": "r1"}],
            self.FULL_TRACE,
        ]
        args = make_args(
            entity_id="automation.test", summary=True, no_summary=False, pretty=True
        )
        assert trace_cmd.run(args) == 0
        result = json.loads(capsys.readouterr().out)
        assert "config" in result
        assert "blueprint_inputs" in result
