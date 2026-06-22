"""Tests for tools/ha_api_diagnostic.py - API diagnostic tool."""

from unittest.mock import MagicMock, patch

import requests

import tools._dev.api_diagnostic as diag


class TestGetConfig:
    def test_returns_config_dict(self):
        with (
            patch("tools._dev.api_diagnostic.load_env_file"),
            patch.dict(
                "os.environ",
                {"HA_URL": "http://test:8123", "HA_TOKEN": "test_token"},
            ),
        ):
            config = diag.get_config()
            assert config["ha_url"] == "http://test:8123"
            assert config["token"] == "test_token"

    def test_default_values(self):
        with (
            patch("tools._dev.api_diagnostic.load_env_file"),
            patch.dict("os.environ", {}, clear=True),
        ):
            config = diag.get_config()
            assert config["ha_url"] == "http://homeassistant.local:8123"
            assert config["token"] == ""


class TestApiConnection:
    def test_success(self, capsys):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": "API running"}

        with patch(
            "tools._dev.api_diagnostic.requests.get", return_value=mock_response
        ):
            result = diag.test_api_connection("http://test:8123", "token")
            assert result is True
            captured = capsys.readouterr()
            assert "API running" in captured.out

    def test_failure(self, capsys):
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        with patch(
            "tools._dev.api_diagnostic.requests.get", return_value=mock_response
        ):
            result = diag.test_api_connection("http://test:8123", "token")
            assert result is False

    def test_exception(self, capsys):
        with patch(
            "tools._dev.api_diagnostic.requests.get",
            side_effect=requests.exceptions.RequestException("connection failed"),
        ):
            result = diag.test_api_connection("http://test:8123", "token")
            assert result is False

    def test_invalid_json_response(self, capsys):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("bad json")
        mock_response.text = "not-json"

        with patch(
            "tools._dev.api_diagnostic.requests.get", return_value=mock_response
        ):
            result = diag.test_api_connection("http://test:8123", "token")
            assert result is False


class TestApiEndpoints:
    def test_successful_list_endpoints(self, capsys):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"entity_id": "test.entity"}]

        with patch(
            "tools._dev.api_diagnostic.requests.get", return_value=mock_response
        ):
            result = diag.test_api_endpoints("http://test:8123", "token")
            assert len(result) > 0

    def test_failed_endpoints(self, capsys):
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not found"

        with patch(
            "tools._dev.api_diagnostic.requests.get", return_value=mock_response
        ):
            result = diag.test_api_endpoints("http://test:8123", "token")
            assert len(result) == 0

    def test_dict_response(self, capsys):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"key": "value", "key2": "value2"}

        with patch(
            "tools._dev.api_diagnostic.requests.get", return_value=mock_response
        ):
            result = diag.test_api_endpoints("http://test:8123", "token")
            assert len(result) > 0

    def test_non_json_response(self, capsys):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("not json")
        mock_response.text = "plain text response"

        with patch(
            "tools._dev.api_diagnostic.requests.get", return_value=mock_response
        ):
            result = diag.test_api_endpoints("http://test:8123", "token")
            assert len(result) > 0

    def test_exception(self, capsys):
        with patch(
            "tools._dev.api_diagnostic.requests.get",
            side_effect=requests.exceptions.RequestException("timeout"),
        ):
            result = diag.test_api_endpoints("http://test:8123", "token")
            assert len(result) == 0


class TestEntityRegistryRead:
    def test_success(self, capsys):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "entity_id": "sensor.test",
                "platform": "test",
                "device_id": "dev1",
                "unique_id": "unique1",
            }
        ]

        with patch(
            "tools._dev.api_diagnostic.requests.get", return_value=mock_response
        ):
            result = diag.test_entity_registry_read("http://test:8123", "token")
            assert len(result) == 1

    def test_failure(self, capsys):
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        with patch(
            "tools._dev.api_diagnostic.requests.get", return_value=mock_response
        ):
            result = diag.test_entity_registry_read("http://test:8123", "token")
            assert result == []

    def test_exception(self, capsys):
        with patch(
            "tools._dev.api_diagnostic.requests.get",
            side_effect=requests.exceptions.RequestException("error"),
        ):
            result = diag.test_entity_registry_read("http://test:8123", "token")
            assert result == []

    def test_invalid_json(self, capsys):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("invalid json")
        mock_response.text = "nope"

        with patch(
            "tools._dev.api_diagnostic.requests.get", return_value=mock_response
        ):
            result = diag.test_entity_registry_read("http://test:8123", "token")
            assert result == []


class TestStatesEndpoint:
    def test_success(self, capsys):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"entity_id": "sensor.test", "attributes": {"unit": "C"}}
        ]

        with patch(
            "tools._dev.api_diagnostic.requests.get", return_value=mock_response
        ):
            result = diag.test_states_endpoint("http://test:8123", "token")
            assert result is True

    def test_empty_states(self, capsys):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []

        with patch(
            "tools._dev.api_diagnostic.requests.get", return_value=mock_response
        ):
            result = diag.test_states_endpoint("http://test:8123", "token")
            assert result is False

    def test_failure(self, capsys):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Error"

        with patch(
            "tools._dev.api_diagnostic.requests.get", return_value=mock_response
        ):
            result = diag.test_states_endpoint("http://test:8123", "token")
            assert result is False

    def test_exception(self, capsys):
        with patch(
            "tools._dev.api_diagnostic.requests.get",
            side_effect=requests.exceptions.RequestException("error"),
        ):
            result = diag.test_states_endpoint("http://test:8123", "token")
            assert result is False

    def test_invalid_json(self, capsys):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("invalid json")
        mock_response.text = "plain text"

        with patch(
            "tools._dev.api_diagnostic.requests.get", return_value=mock_response
        ):
            result = diag.test_states_endpoint("http://test:8123", "token")
            assert result is False


class TestEntityRename:
    def test_no_entity_data(self, capsys):
        result = diag.test_entity_rename("http://test:8123", "token", [])
        assert result is False

    def test_method1_success(self, capsys):
        mock_response = MagicMock()
        mock_response.status_code = 200
        entity_data = [{"entity_id": "sensor.test"}]

        with patch(
            "tools._dev.api_diagnostic.requests.post", return_value=mock_response
        ):
            result = diag.test_entity_rename("http://test:8123", "token", entity_data)
            assert result is True

    def test_both_methods_fail(self, capsys):
        mock_response = MagicMock()
        mock_response.status_code = 405
        mock_response.text = "Method not allowed"
        entity_data = [{"entity_id": "sensor.test"}]

        with patch(
            "tools._dev.api_diagnostic.requests.post", return_value=mock_response
        ):
            result = diag.test_entity_rename("http://test:8123", "token", entity_data)
            assert result is False

    def test_exception_method1(self, capsys):
        entity_data = [{"entity_id": "sensor.test"}]
        # Both methods raise exceptions
        with patch(
            "tools._dev.api_diagnostic.requests.post",
            side_effect=requests.exceptions.RequestException("error"),
        ):
            result = diag.test_entity_rename("http://test:8123", "token", entity_data)
            assert result is False


class TestServiceCallMethod:
    def test_no_entity_data(self, capsys):
        diag.test_service_call_method("http://test:8123", "token", [])
        captured = capsys.readouterr()
        assert "No entity data" in captured.out

    def test_success(self, capsys):
        mock_response = MagicMock()
        mock_response.status_code = 200
        entity_data = [{"entity_id": "sensor.test"}]

        with patch(
            "tools._dev.api_diagnostic.requests.post", return_value=mock_response
        ):
            diag.test_service_call_method("http://test:8123", "token", entity_data)
            captured = capsys.readouterr()
            assert "successful" in captured.out

    def test_failure(self, capsys):
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not found"
        entity_data = [{"entity_id": "sensor.test"}]

        with patch(
            "tools._dev.api_diagnostic.requests.post", return_value=mock_response
        ):
            diag.test_service_call_method("http://test:8123", "token", entity_data)
            captured = capsys.readouterr()
            assert "failed" in captured.out

    def test_exception(self, capsys):
        entity_data = [{"entity_id": "sensor.test"}]
        with patch(
            "tools._dev.api_diagnostic.requests.post",
            side_effect=requests.exceptions.RequestException("error"),
        ):
            diag.test_service_call_method("http://test:8123", "token", entity_data)
            captured = capsys.readouterr()
            assert "Exception" in captured.out


class TestShowWebsocketInfo:
    def test_prints_info(self, capsys):
        diag.show_websocket_info()
        captured = capsys.readouterr()
        assert "WebSocket" in captured.out
        assert "entity_registry" in captured.out


class TestMainFunction:
    """Cover lines 284-335: main() function."""

    def test_main_no_token(self, capsys):
        with (
            patch("tools._dev.api_diagnostic.load_env_file"),
            patch.dict("os.environ", {"HA_URL": "http://test:8123"}, clear=True),
        ):
            diag.main()
            captured = capsys.readouterr()
            assert "No HA_TOKEN" in captured.out

    def test_main_connection_fails(self, capsys):
        with (
            patch("tools._dev.api_diagnostic.load_env_file"),
            patch.dict(
                "os.environ",
                {"HA_URL": "http://test:8123", "HA_TOKEN": "test_token"},
            ),
            patch(
                "tools._dev.api_diagnostic.test_api_connection",
                return_value=False,
            ),
        ):
            diag.main()
            captured = capsys.readouterr()
            assert "Basic connection failed" in captured.out

    def test_main_full_run(self, capsys):
        with (
            patch("tools._dev.api_diagnostic.load_env_file"),
            patch.dict(
                "os.environ",
                {"HA_URL": "http://test:8123", "HA_TOKEN": "test_token"},
            ),
            patch(
                "tools._dev.api_diagnostic.test_api_connection",
                return_value=True,
            ),
            patch(
                "tools._dev.api_diagnostic.test_api_endpoints",
                return_value=["/api/states"],
            ),
            patch(
                "tools._dev.api_diagnostic.test_entity_registry_read",
                return_value=[{"entity_id": "sensor.test"}],
            ),
            patch(
                "tools._dev.api_diagnostic.test_states_endpoint",
                return_value=True,
            ),
            patch("tools._dev.api_diagnostic.test_entity_rename"),
            patch("tools._dev.api_diagnostic.test_service_call_method"),
            patch("tools._dev.api_diagnostic.show_websocket_info"),
        ):
            diag.main()
            captured = capsys.readouterr()
            assert "DIAGNOSTIC SUMMARY" in captured.out
            assert "RECOMMENDATIONS" in captured.out
