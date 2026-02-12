"""Tests for tools/reload_config.py - HA config reload via API."""

from unittest.mock import MagicMock, patch

import requests

from tools.reload_config import reload_config


class TestReloadConfig:
    def test_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 200

        with (
            patch.dict(
                "os.environ", {"HA_TOKEN": "test_token", "HA_URL": "http://test:8123"}
            ),
            patch("tools.reload_config.load_env_file"),
            patch("tools.reload_config.requests.post", return_value=mock_response),
        ):
            assert reload_config() is True

    def test_no_token(self):
        with (
            patch.dict("os.environ", {"HA_TOKEN": ""}, clear=False),
            patch("tools.reload_config.load_env_file"),
        ):
            assert reload_config() is False

    def test_api_failure(self):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with (
            patch.dict(
                "os.environ", {"HA_TOKEN": "test_token", "HA_URL": "http://test:8123"}
            ),
            patch("tools.reload_config.load_env_file"),
            patch("tools.reload_config.requests.post", return_value=mock_response),
        ):
            assert reload_config() is False

    def test_timeout(self):
        with (
            patch.dict(
                "os.environ", {"HA_TOKEN": "test_token", "HA_URL": "http://test:8123"}
            ),
            patch("tools.reload_config.load_env_file"),
            patch(
                "tools.reload_config.requests.post",
                side_effect=requests.exceptions.Timeout,
            ),
        ):
            assert reload_config() is False

    def test_connection_error(self):
        with (
            patch.dict(
                "os.environ", {"HA_TOKEN": "test_token", "HA_URL": "http://test:8123"}
            ),
            patch("tools.reload_config.load_env_file"),
            patch(
                "tools.reload_config.requests.post",
                side_effect=requests.exceptions.ConnectionError,
            ),
        ):
            assert reload_config() is False

    def test_generic_exception(self):
        with (
            patch.dict(
                "os.environ", {"HA_TOKEN": "test_token", "HA_URL": "http://test:8123"}
            ),
            patch("tools.reload_config.load_env_file"),
            patch(
                "tools.reload_config.requests.post",
                side_effect=RuntimeError("unexpected"),
            ),
        ):
            assert reload_config() is False
