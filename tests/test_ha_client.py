"""Tests for tools/ha/client.py — the shared HA REST API client."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from tools.common import HARequestError
from tools.ha.client import HAClient


class TestInit:
    def test_valid_construction(self):
        c = HAClient("http://ha.local:8123", "tok", timeout=15)
        assert c.url == "http://ha.local:8123"
        assert c.token == "tok"
        assert c.timeout == 15

    def test_url_trailing_slash_stripped(self):
        c = HAClient("http://ha.local:8123/", "tok")
        assert c.url == "http://ha.local:8123"

    def test_invalid_url_raises(self):
        with pytest.raises(HARequestError, match="HA_URL"):
            HAClient("ftp://ha.local", "tok")

    def test_missing_token_raises(self):
        with pytest.raises(HARequestError, match="HA_TOKEN"):
            HAClient("http://ha.local:8123", "")

    def test_headers_format(self):
        c = HAClient("http://ha.local:8123", "abc123")
        assert c.headers == {
            "Authorization": "Bearer abc123",
            "Content-Type": "application/json",
        }


class TestFromEnv:
    """All from_env tests patch load_env_file so the project's real .env
    doesn't leak into the test environment and override monkeypatched values.
    """

    @pytest.fixture(autouse=True)
    def _stub_load_env_file(self, monkeypatch):
        monkeypatch.setattr("tools.ha.client.load_env_file", lambda: None)

    def test_reads_env_vars(self, monkeypatch):
        monkeypatch.setenv("HA_URL", "http://ha.example:8123")
        monkeypatch.setenv("HA_TOKEN", "env-token")
        monkeypatch.setenv("HA_REQUEST_TIMEOUT", "42")
        c = HAClient.from_env()
        assert c.url == "http://ha.example:8123"
        assert c.token == "env-token"
        assert c.timeout == 42

    def test_uses_defaults_when_unset(self, monkeypatch):
        monkeypatch.delenv("HA_URL", raising=False)
        monkeypatch.delenv("HA_TOKEN", raising=False)
        monkeypatch.delenv("HA_REQUEST_TIMEOUT", raising=False)
        with pytest.raises(HARequestError, match="HA_TOKEN"):
            HAClient.from_env()

    def test_default_url_when_only_token_set(self, monkeypatch):
        monkeypatch.delenv("HA_URL", raising=False)
        monkeypatch.setenv("HA_TOKEN", "tok")
        monkeypatch.delenv("HA_REQUEST_TIMEOUT", raising=False)
        c = HAClient.from_env()
        assert c.url == "http://homeassistant.local:8123"
        assert c.timeout == 10

    def test_invalid_timeout_warns_and_uses_default(self, monkeypatch, capsys):
        monkeypatch.setenv("HA_URL", "http://ha.example:8123")
        monkeypatch.setenv("HA_TOKEN", "tok")
        monkeypatch.setenv("HA_REQUEST_TIMEOUT", "not-a-number")
        c = HAClient.from_env()
        captured = capsys.readouterr()
        assert "must be an integer" in captured.err
        assert c.timeout == 10

    def test_load_env_file_called_once(self, monkeypatch):
        """Verify from_env delegates to load_env_file (the project's .env loader)."""
        monkeypatch.setenv("HA_URL", "http://ha.example:8123")
        monkeypatch.setenv("HA_TOKEN", "tok")
        with patch("tools.ha.client.load_env_file") as mock_load:
            HAClient.from_env()
            mock_load.assert_called_once()


class TestGet:
    def test_get_returns_response(self):
        session = MagicMock()
        session.get.return_value = MagicMock(status_code=200)
        c = HAClient("http://ha.local:8123", "tok", session=session)
        r = c.get("/api/")
        assert r.status_code == 200
        session.get.assert_called_once()
        args, kwargs = session.get.call_args
        assert args[0] == "http://ha.local:8123/api/"
        assert kwargs["headers"]["Authorization"] == "Bearer tok"
        assert kwargs["timeout"] == 10

    def test_get_raises_on_request_exception(self):
        session = MagicMock()
        session.get.side_effect = requests.ConnectionError("boom")
        c = HAClient("http://ha.local:8123", "tok", session=session)
        with pytest.raises(HARequestError, match="GET /api/ failed: boom"):
            c.get("/api/")


class TestPost:
    def test_post_returns_response(self):
        session = MagicMock()
        session.post.return_value = MagicMock(status_code=200)
        c = HAClient("http://ha.local:8123", "tok", session=session)
        r = c.post("/api/services/light/turn_on", json={"entity_id": "light.kitchen"})
        assert r.status_code == 200
        args, kwargs = session.post.call_args
        assert args[0] == "http://ha.local:8123/api/services/light/turn_on"
        assert kwargs["json"] == {"entity_id": "light.kitchen"}

    def test_post_raises_on_request_exception(self):
        session = MagicMock()
        session.post.side_effect = requests.Timeout("slow")
        c = HAClient("http://ha.local:8123", "tok", session=session)
        with pytest.raises(HARequestError, match="POST .* failed: slow"):
            c.post("/api/services/light/turn_on")


class TestPut:
    def test_put_returns_response(self):
        session = MagicMock()
        session.put.return_value = MagicMock(status_code=200)
        c = HAClient("http://ha.local:8123", "tok", session=session)
        r = c.put("/api/config", json={"key": "val"})
        assert r.status_code == 200
        args, kwargs = session.put.call_args
        assert args[0] == "http://ha.local:8123/api/config"
        assert kwargs["json"] == {"key": "val"}

    def test_put_raises_on_request_exception(self):
        session = MagicMock()
        session.put.side_effect = requests.ConnectionError("boom")
        c = HAClient("http://ha.local:8123", "tok", session=session)
        with pytest.raises(HARequestError, match="PUT .* failed: boom"):
            c.put("/api/config")


class TestDelete:
    def test_delete_returns_response(self):
        session = MagicMock()
        session.delete.return_value = MagicMock(status_code=200)
        c = HAClient("http://ha.local:8123", "tok", session=session)
        r = c.delete("/api/config/section")
        assert r.status_code == 200
        args, kwargs = session.delete.call_args
        assert args[0] == "http://ha.local:8123/api/config/section"

    def test_delete_raises_on_request_exception(self):
        session = MagicMock()
        session.delete.side_effect = requests.Timeout("slow")
        c = HAClient("http://ha.local:8123", "tok", session=session)
        with pytest.raises(HARequestError, match="DELETE .* failed: slow"):
            c.delete("/api/config/section")


class TestPatch:
    def test_patch_returns_response(self):
        session = MagicMock()
        session.patch.return_value = MagicMock(status_code=200)
        c = HAClient("http://ha.local:8123", "tok", session=session)
        r = c.patch("/api/config", json={"key": "val"})
        assert r.status_code == 200
        args, kwargs = session.patch.call_args
        assert args[0] == "http://ha.local:8123/api/config"
        assert kwargs["json"] == {"key": "val"}

    def test_patch_raises_on_request_exception(self):
        session = MagicMock()
        session.patch.side_effect = requests.ConnectionError("boom")
        c = HAClient("http://ha.local:8123", "tok", session=session)
        with pytest.raises(HARequestError, match="PATCH .* failed: boom"):
            c.patch("/api/config")


class TestGetJson:
    def test_parses_json_response(self):
        session = MagicMock()
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"message": "API running."}
        session.get.return_value = resp
        c = HAClient("http://ha.local:8123", "tok", session=session)
        assert c.get_json("/api/") == {"message": "API running."}

    def test_non_200_raises_with_body_preview(self):
        session = MagicMock()
        resp = MagicMock(status_code=401, text="Unauthorized")
        session.get.return_value = resp
        c = HAClient("http://ha.local:8123", "tok", session=session)
        with pytest.raises(HARequestError, match="HTTP 401"):
            c.get_json("/api/")

    def test_non_json_response_raises(self):
        session = MagicMock()
        resp = MagicMock(status_code=200, text="<html>not json</html>")
        resp.json.side_effect = ValueError("bad json")
        session.get.return_value = resp
        c = HAClient("http://ha.local:8123", "tok", session=session)
        with pytest.raises(HARequestError, match="non-JSON"):
            c.get_json("/api/")


class TestCallService:
    def test_success_returns_true(self):
        session = MagicMock()
        session.post.return_value = MagicMock(status_code=200)
        c = HAClient("http://ha.local:8123", "tok", session=session)
        assert c.call_service("automation", "reload") is True
        args, _ = session.post.call_args
        assert args[0] == "http://ha.local:8123/api/services/automation/reload"

    def test_non_200_returns_false(self):
        session = MagicMock()
        session.post.return_value = MagicMock(status_code=500)
        c = HAClient("http://ha.local:8123", "tok", session=session)
        assert (
            c.call_service("light", "turn_on", data={"entity_id": "light.x"}) is False
        )

    def test_data_passed_as_json(self):
        session = MagicMock()
        session.post.return_value = MagicMock(status_code=200)
        c = HAClient("http://ha.local:8123", "tok", session=session)
        c.call_service("light", "turn_on", data={"entity_id": "light.kitchen"})
        _, kwargs = session.post.call_args
        assert kwargs["json"] == {"entity_id": "light.kitchen"}

    def test_no_data_defaults_to_empty_dict(self):
        session = MagicMock()
        session.post.return_value = MagicMock(status_code=200)
        c = HAClient("http://ha.local:8123", "tok", session=session)
        c.call_service("automation", "reload")
        _, kwargs = session.post.call_args
        assert kwargs["json"] == {}
