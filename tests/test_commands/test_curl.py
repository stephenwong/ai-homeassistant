"""Tests for tools/commands/curl.py — pure-Python curl subcommand."""

import argparse
import json
from argparse import Namespace
from unittest.mock import MagicMock, patch

import pytest

from tools.commands import curl as curl_cmd
from tools.common import HARequestError
from tools.ha.client import HAClient

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def make_args(**overrides):
    """Build a Namespace with sensible defaults for CLI args."""
    defaults = dict(
        endpoint="/api/states",
        method="GET",
        data=None,
        filter=None,
        count=False,
        keys=False,
        first=None,
        raw=False,
        pretty=False,
    )
    defaults.update(overrides)
    return Namespace(**defaults)


def parse(argv):
    """Parse ``curl <argv>`` through the real argparse and return args."""
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()
    curl_cmd.add_parser(subparsers)
    return parser.parse_args(["curl"] + argv)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _stub_load_env_file(monkeypatch):
    """Prevent HAClient.from_env() reading the real .env."""
    monkeypatch.setattr("tools.ha.client.load_env_file", lambda: None)


@pytest.fixture
def mock_client():
    """Patch HAClient.from_env to return a controlled mock client."""
    with patch("tools.commands.curl.HAClient.from_env") as mock_from_env:
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
    """Build a 200 JSON response mock."""
    r = MagicMock()
    r.ok = status < 400
    r.status_code = status
    r.headers = {"content-type": "application/json"}
    r.text = json.dumps(data)
    r.json.return_value = data
    return r


def text_resp(text="ok", ct="text/plain", status=200):
    """Build a non-JSON response mock."""
    r = MagicMock()
    r.ok = status < 400
    r.status_code = status
    r.headers = {"content-type": ct}
    r.text = text
    return r


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


class TestArgparse:
    def test_subparser_registered(self):
        args = parse(["/api/states"])
        assert args.endpoint == "/api/states"
        assert args.method == "GET"
        assert callable(args.func)

    def test_default_method_is_get(self):
        args = parse(["/api/"])
        assert args.method == "GET"

    def test_post_flag_sets_method(self):
        args = parse(["-X", "/api/services/light/turn_on"])
        assert args.method == "POST"

    def test_method_flag(self):
        args = parse(["--method", "PUT", "/api/config"])
        assert args.method == "PUT"

    def test_method_invalid_value(self):
        with pytest.raises(SystemExit):
            parse(["--method", "POTS", "/api/"])

    def test_endpoint_no_slash_fails(self):
        with pytest.raises(SystemExit):
            parse(["api/states"])

    def test_filter_flag(self):
        args = parse(["/api/states", "--filter", ". | length"])
        assert args.filter == ". | length"

    def test_count_flag(self):
        args = parse(["/api/states", "--count"])
        assert args.count is True

    def test_keys_flag(self):
        args = parse(["/api/states", "--keys"])
        assert args.keys is True

    def test_first_flag(self):
        args = parse(["/api/states", "--first", "5"])
        assert args.first == 5

    def test_first_zero_invalid(self):
        with pytest.raises(SystemExit):
            parse(["/api/states", "--first", "0"])

    def test_first_negative_invalid(self):
        with pytest.raises(SystemExit):
            parse(["/api/states", "--first", "-1"])

    def test_raw_flag(self):
        args = parse(["/api/", "--raw"])
        assert args.raw is True

    def test_pretty_flag(self):
        args = parse(["/api/states", "--pretty"])
        assert args.pretty is True

    def test_filter_raw_conflict(self):
        with pytest.raises(SystemExit):
            parse(["/api/states", "--filter", ".", "--raw"])

    def test_count_keys_conflict(self):
        with pytest.raises(SystemExit):
            parse(["/api/states", "--count", "--keys"])

    def test_post_method_conflict(self):
        with pytest.raises(SystemExit):
            parse(["/api/", "--post", "--method", "PUT"])


# ---------------------------------------------------------------------------
# Basic HTTP methods
# ---------------------------------------------------------------------------


class TestHttpMethods:
    def test_get_compact_json(self, mock_client, capsys):
        data = [{"entity_id": "sensor.test", "state": "on"}]
        mock_client.get.return_value = json_resp(data)
        args = make_args()
        assert curl_cmd.run(args) == 0
        out = capsys.readouterr().out
        assert '"entity_id":"sensor.test"' in out
        assert "    " not in out  # no indentation = compact

    def test_get_pretty_json(self, mock_client, capsys):
        data = [{"entity_id": "sensor.test", "state": "on"}]
        mock_client.get.return_value = json_resp(data)
        args = make_args(pretty=True)
        assert curl_cmd.run(args) == 0
        out = capsys.readouterr().out
        assert '"entity_id": "sensor.test"' in out
        assert "    " in out  # has indentation

    def test_get_non_json_response(self, mock_client, capsys):
        mock_client.get.return_value = text_resp("<html>HA</html>", ct="text/html")
        args = make_args(endpoint="/api/")
        assert curl_cmd.run(args) == 0
        out = capsys.readouterr().out
        assert out == "<html>HA</html>"

    def test_empty_response_body(self, mock_client, capsys):
        r = MagicMock()
        r.ok = True
        r.status_code = 204
        r.headers = {}
        r.text = ""
        mock_client.get.return_value = r
        args = make_args(endpoint="/api/")
        assert curl_cmd.run(args) == 0
        assert capsys.readouterr().out == ""

    def test_json_with_charset_in_content_type(self, mock_client, capsys):
        r = MagicMock()
        r.ok = True
        r.status_code = 200
        r.headers = {"content-type": "application/json; charset=utf-8"}
        r.text = '{"key": "val"}'
        r.json.return_value = {"key": "val"}
        mock_client.get.return_value = r
        args = make_args()
        assert curl_cmd.run(args) == 0
        assert '"key":"val"' in capsys.readouterr().out

    def test_post_with_data(self, mock_client):
        mock_client.post.return_value = json_resp({"success": True})
        args = make_args(method="POST", data='{"entity_id": "light.kitchen"}')
        assert curl_cmd.run(args) == 0
        mock_client.post.assert_called_once()
        _args, _kwargs = mock_client.post.call_args
        assert _kwargs["json"] == {"entity_id": "light.kitchen"}

    def test_post_without_data(self, mock_client):
        mock_client.post.return_value = json_resp({"success": True})
        args = make_args(method="POST")
        assert curl_cmd.run(args) == 0
        mock_client.post.assert_called_once()

    def test_put_without_data(self, mock_client):
        mock_client.put.return_value = json_resp({"ok": True})
        args = make_args(method="PUT", endpoint="/api/config")
        assert curl_cmd.run(args) == 0
        mock_client.put.assert_called_once_with("/api/config", json=None)

    def test_method_put(self, mock_client):
        mock_client.put.return_value = json_resp({"ok": True})
        args = make_args(method="PUT", endpoint="/api/config", data='{"key": "val"}')
        assert curl_cmd.run(args) == 0
        mock_client.put.assert_called_once()
        _path, kwargs = mock_client.put.call_args
        assert kwargs["json"] == {"key": "val"}

    def test_method_delete(self, mock_client):
        mock_client.delete.return_value = json_resp({"ok": True})
        args = make_args(method="DELETE", endpoint="/api/config/section")
        assert curl_cmd.run(args) == 0
        mock_client.delete.assert_called_once_with("/api/config/section", json=None)

    def test_method_patch(self, mock_client):
        mock_client.patch.return_value = json_resp({"ok": True})
        args = make_args(method="PATCH", endpoint="/api/config", data='{"key": "val"}')
        assert curl_cmd.run(args) == 0
        mock_client.patch.assert_called_once()
        _path, kwargs = mock_client.patch.call_args
        assert kwargs["json"] == {"key": "val"}

    def test_patch_without_data(self, mock_client):
        mock_client.patch.return_value = json_resp({"ok": True})
        args = make_args(method="PATCH", endpoint="/api/config")
        assert curl_cmd.run(args) == 0
        mock_client.patch.assert_called_once_with("/api/config", json=None)


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_http_404(self, mock_client, capsys):
        mock_client.get.return_value = text_resp("Not found", status=404)
        args = make_args()
        assert curl_cmd.run(args) == 1
        err = capsys.readouterr().err
        assert "HTTP 404" in err
        assert "Not found" in err

    def test_http_500(self, mock_client, capsys):
        mock_client.get.return_value = text_resp("Internal error", status=500)
        args = make_args()
        assert curl_cmd.run(args) == 1
        err = capsys.readouterr().err
        assert "HTTP 500" in err

    def test_connection_error(self, mock_client, capsys):
        mock_client.get.side_effect = HARequestError("GET /api/states failed: boom")
        args = make_args()
        assert curl_cmd.run(args) == 1
        err = capsys.readouterr().err
        assert "boom" in err

    def test_missing_token(self, capsys):
        with patch("tools.commands.curl.HAClient.from_env") as m:
            m.side_effect = HARequestError("HA_TOKEN not found")
            args = make_args()
            assert curl_cmd.run(args) == 1
        err = capsys.readouterr().err
        assert "HA_TOKEN" in err

    def test_data_invalid_json(self, capsys):
        with patch("tools.commands.curl.HAClient.from_env"):
            args = make_args(method="POST", data="bad{")
            assert curl_cmd.run(args) == 1
        err = capsys.readouterr().err
        assert "Invalid JSON" in err

    def test_data_absent_is_none(self, mock_client):
        """POST without --data does not crash (json=None is valid)."""
        mock_client.post.return_value = json_resp({"ok": True})
        args = make_args(method="POST")  # no data passed
        assert curl_cmd.run(args) == 0

    def test_data_with_get_warns(self, mock_client, capsys):
        mock_client.get.return_value = json_resp([])
        args = make_args(data='{"ignore": true}')
        assert curl_cmd.run(args) == 0
        err = capsys.readouterr().err
        assert "ignored for GET" in err

    def test_delete_with_data_warns(self, mock_client, capsys):
        mock_client.delete.return_value = json_resp({"ok": True})
        args = make_args(method="DELETE", endpoint="/api/config/x", data='{"x": "y"}')
        assert curl_cmd.run(args) == 0
        err = capsys.readouterr().err
        assert "ignored for DELETE" in err

    def test_non_json_filter_errors(self, mock_client, capsys):
        mock_client.get.return_value = text_resp("<html>HA</html>", ct="text/html")
        args = make_args(filter=".")
        assert curl_cmd.run(args) == 1
        err = capsys.readouterr().err
        assert "Cannot use --filter on non-JSON response" in err

    def test_non_json_first_errors(self, mock_client, capsys):
        mock_client.get.return_value = text_resp("<html>HA</html>", ct="text/html")
        args = make_args(first=3)
        assert curl_cmd.run(args) == 1
        err = capsys.readouterr().err
        assert "Cannot use --first on non-JSON" in err

    def test_non_json_keys_errors(self, mock_client, capsys):
        mock_client.get.return_value = text_resp("<html>HA</html>", ct="text/html")
        args = make_args(keys=True)
        assert curl_cmd.run(args) == 1
        err = capsys.readouterr().err
        assert "Cannot use --keys on non-JSON" in err

    def test_raw_pretty_conflict(self, capsys):
        with patch("tools.commands.curl.HAClient.from_env"):
            args = make_args(raw=True, pretty=True)
            assert curl_cmd.run(args) == 1
        err = capsys.readouterr().err
        assert "Cannot combine --raw with --pretty" in err


# ---------------------------------------------------------------------------
# Token efficiency: --count
# ---------------------------------------------------------------------------


class TestCount:
    def test_count_list(self, mock_client, capsys):
        mock_client.get.return_value = json_resp([{}, {"a": 1}, {"b": 2}])
        args = make_args(count=True)
        assert curl_cmd.run(args) == 0
        assert capsys.readouterr().out.strip() == "3"

    def test_count_dict(self, mock_client, capsys):
        mock_client.get.return_value = json_resp({"a": 1, "b": 2, "c": 3})
        args = make_args(count=True)
        assert curl_cmd.run(args) == 0
        assert capsys.readouterr().out.strip() == "3"

    def test_count_scalar_null(self, mock_client, capsys):
        mock_client.get.return_value = json_resp(None)
        args = make_args(count=True)
        assert curl_cmd.run(args) == 0
        assert capsys.readouterr().out.strip() == "0"

    def test_count_scalar_number(self, mock_client, capsys):
        mock_client.get.return_value = json_resp(42)
        args = make_args(count=True)
        assert curl_cmd.run(args) == 0
        assert capsys.readouterr().out.strip() == "0"

    def test_count_scalar_boolean(self, mock_client, capsys):
        mock_client.get.return_value = json_resp(True)
        args = make_args(count=True)
        assert curl_cmd.run(args) == 0
        assert capsys.readouterr().out.strip() == "0"

    def test_count_non_json(self, mock_client, capsys):
        mock_client.get.return_value = text_resp("hello world", ct="text/plain")
        args = make_args(count=True, endpoint="/api/")
        assert curl_cmd.run(args) == 0
        assert capsys.readouterr().out.strip() == "11"  # len(b"hello world")

    def test_count_empty_non_json(self, mock_client, capsys):
        r = MagicMock()
        r.ok = True
        r.status_code = 204
        r.headers = {}
        r.text = ""
        mock_client.get.return_value = r
        args = make_args(count=True, endpoint="/api/")
        assert curl_cmd.run(args) == 0
        assert capsys.readouterr().out.strip() == "0"

    def test_keys_with_pretty_warns(self, mock_client, capsys):
        mock_client.get.return_value = json_resp({"a": 1, "b": 2})
        args = make_args(keys=True, pretty=True)
        assert curl_cmd.run(args) == 0
        err = capsys.readouterr().err
        assert "no effect with --keys" in err


# ---------------------------------------------------------------------------
# Token efficiency: --keys
# ---------------------------------------------------------------------------


class TestKeys:
    def test_keys_list_of_dicts(self, mock_client, capsys):
        mock_client.get.return_value = json_resp(
            [
                {"id": 1, "name": "a"},
                {"id": 2, "name": "b", "extra": True},
            ]
        )
        args = make_args(keys=True)
        assert curl_cmd.run(args) == 0
        out, err = capsys.readouterr()
        assert "2 items" in err
        assert "extra" in out and "id" in out and "name" in out
        parsed = json.loads(out)
        assert sorted(parsed) == ["extra", "id", "name"]

    def test_keys_dict(self, mock_client, capsys):
        mock_client.get.return_value = json_resp({"name": "test", "state": "on"})
        args = make_args(keys=True)
        assert curl_cmd.run(args) == 0
        out, err = capsys.readouterr()
        assert "2 keys" in err
        parsed = json.loads(out)
        assert sorted(parsed) == ["name", "state"]

    def test_keys_empty_list(self, mock_client, capsys):
        mock_client.get.return_value = json_resp([])
        args = make_args(keys=True)
        assert curl_cmd.run(args) == 0
        out, err = capsys.readouterr()
        assert "empty list" in err
        assert json.loads(out) == []

    def test_keys_non_dict_items(self, mock_client, capsys):
        mock_client.get.return_value = json_resp(["a", "b", "c"])
        args = make_args(keys=True)
        assert curl_cmd.run(args) == 0
        out, err = capsys.readouterr()
        assert "non-dict" in err
        assert json.loads(out) == []

    def test_keys_mixed_list_first_non_dict(self, mock_client, capsys):
        """First item is not a dict, but later items are — keys should still emit."""
        mock_client.get.return_value = json_resp(["skip", {"a": 1}, {"b": 2}])
        args = make_args(keys=True)
        assert curl_cmd.run(args) == 0
        out, err = capsys.readouterr()
        assert "2 unique keys" in err
        parsed = json.loads(out)
        assert sorted(parsed) == ["a", "b"]

    def test_keys_on_scalar(self, mock_client, capsys):
        mock_client.get.return_value = json_resp(42)
        args = make_args(keys=True)
        assert curl_cmd.run(args) == 0
        out, err = capsys.readouterr()
        assert "not a JSON object or list" in err
        assert out.strip() == "42"


# ---------------------------------------------------------------------------
# Token efficiency: --first
# ---------------------------------------------------------------------------


class TestFirst:
    def test_first_n(self, mock_client, capsys):
        data = [{"id": i} for i in range(10)]
        mock_client.get.return_value = json_resp(data)
        args = make_args(first=3)
        assert curl_cmd.run(args) == 0
        parsed = json.loads(capsys.readouterr().out)
        assert len(parsed) == 3
        assert parsed == [{"id": 0}, {"id": 1}, {"id": 2}]

    def test_first_with_pretty(self, mock_client, capsys):
        data = [{"id": i} for i in range(3)]
        mock_client.get.return_value = json_resp(data)
        args = make_args(first=3, pretty=True)
        assert curl_cmd.run(args) == 0
        out = capsys.readouterr().out
        assert "    " in out
        assert '"id": 0' in out

    def test_first_on_dict(self, mock_client, capsys):
        data = {"a": 1, "b": 2, "c": 3, "d": 4, "e": 5}
        mock_client.get.return_value = json_resp(data)
        args = make_args(first=3)
        assert curl_cmd.run(args) == 0
        parsed = json.loads(capsys.readouterr().out)
        assert len(parsed) == 3

    def test_first_overcount(self, mock_client, capsys):
        data = [{"id": i} for i in range(3)]
        mock_client.get.return_value = json_resp(data)
        args = make_args(first=999)
        assert curl_cmd.run(args) == 0
        out, err = capsys.readouterr()
        parsed = json.loads(out)
        assert len(parsed) == 3
        assert "999" in err and "3" in err

    def test_first_dict_overcount(self, mock_client, capsys):
        data = {"a": 1, "b": 2, "c": 3}
        mock_client.get.return_value = json_resp(data)
        args = make_args(first=999)
        assert curl_cmd.run(args) == 0
        out, err = capsys.readouterr()
        assert "999" in err and "3" in err
        assert len(json.loads(out)) == 3

    def test_first_on_scalar(self, mock_client, capsys):
        mock_client.get.return_value = json_resp(42)
        args = make_args(first=3)
        assert curl_cmd.run(args) == 0
        assert json.loads(capsys.readouterr().out) == [42]


# ---------------------------------------------------------------------------
# --filter (jq)
# ---------------------------------------------------------------------------


class TestFilter:
    def test_filter_with_jq(self, mock_client):
        data = [{"entity_id": "sensor.test"}]
        mock_client.get.return_value = json_resp(data)
        mock_jq = MagicMock()
        mock_jq.returncode = 0
        mock_jq.stdout = "1\n"
        with (
            patch("tools.commands.curl.shutil.which", return_value="/usr/bin/jq"),
            patch(
                "tools.commands.curl.subprocess.run", return_value=mock_jq
            ) as mock_run,
        ):
            args = make_args(filter=". | length")
            assert curl_cmd.run(args) == 0
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args.args[0] == ["jq", "--raw-output", ". | length"]
        kw = call_args.kwargs
        assert kw["input"] == '[{"entity_id":"sensor.test"}]'
        assert kw["capture_output"] is True
        assert kw["text"] is True
        assert kw["timeout"] == 10

    def test_filter_without_jq(self, mock_client, capsys):
        mock_client.get.return_value = json_resp([{"id": 1}])
        with patch("tools.commands.curl.shutil.which", return_value=None):
            args = make_args(filter=".")
            assert curl_cmd.run(args) == 0
        out, err = capsys.readouterr()
        assert "jq not installed" in err
        assert '"id":1' in out or '"id": 1' in out

    def test_filter_on_non_json(self, mock_client, capsys):
        mock_client.get.return_value = text_resp("not json", ct="text/html")
        with patch("tools.commands.curl.shutil.which", return_value="/usr/bin/jq"):
            args = make_args(filter=".")
            assert curl_cmd.run(args) == 1
        err = capsys.readouterr().err
        assert "Cannot use --filter on non-JSON response" in err

    def test_filter_with_jq_on_empty_array(self, mock_client):
        """--filter on [] should pass through to jq, not reject as 'not JSON'."""
        mock_client.get.return_value = json_resp([])
        mock_jq = MagicMock()
        mock_jq.returncode = 0
        mock_jq.stdout = "0\n"
        with (
            patch("tools.commands.curl.shutil.which", return_value="/usr/bin/jq"),
            patch(
                "tools.commands.curl.subprocess.run", return_value=mock_jq
            ) as mock_run,
        ):
            args = make_args(filter=".")
            assert curl_cmd.run(args) == 0
        mock_run.assert_called_once()

    def test_unknown_method_returns_one(self, mock_client, capsys):
        """Calling run() with an unrecognized method should error."""
        args = make_args(endpoint="/api/")
        args.method = "UNKNOWN"
        assert curl_cmd.run(args) == 1
        err = capsys.readouterr().err
        assert "Unknown HTTP method" in err

    def test_pretty_with_filter_warns(self, mock_client, capsys):
        mock_client.get.return_value = json_resp([{"id": 1}])
        with (
            patch("tools.commands.curl.shutil.which", return_value="/usr/bin/jq"),
            patch("tools.commands.curl.subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0, stdout="1\n")
            args = make_args(filter=".", pretty=True)
            assert curl_cmd.run(args) == 0
        err = capsys.readouterr().err
        assert "no effect with --filter" in err


# ---------------------------------------------------------------------------
# --raw
# ---------------------------------------------------------------------------


class TestRaw:
    def test_raw_output(self, mock_client, capsys):
        mock_client.get.return_value = text_resp("raw body", ct="text/plain")
        args = make_args(raw=True)
        assert curl_cmd.run(args) == 0
        assert capsys.readouterr().out == "raw body"
