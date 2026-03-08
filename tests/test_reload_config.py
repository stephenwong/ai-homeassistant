"""Tests for tools/reload_config.py - HA config reload via API."""

import subprocess
from unittest.mock import MagicMock, call, patch

import pytest
import requests

from tools.reload_config import detect_changed_services, reload_config, reload_service


class TestDetectChangedServices:
    def test_automations_yaml_returns_automation_reload(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="config/automations.yaml\n")
            result = detect_changed_services()
        assert result == {"automation/reload"}

    def test_scripts_yaml_returns_script_reload(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="config/scripts.yaml\n")
            result = detect_changed_services()
        assert result == {"script/reload"}

    def test_scenes_yaml_returns_scene_reload(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="config/scenes.yaml\n")
            result = detect_changed_services()
        assert result == {"scene/reload"}

    def test_configuration_yaml_returns_reload_core_config(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="config/configuration.yaml\n"
            )
            result = detect_changed_services()
        assert result == {"homeassistant/reload_core_config"}

    def test_unknown_yaml_returns_reload_core_config(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="config/secrets.yaml\n")
            result = detect_changed_services()
        assert result == {"homeassistant/reload_core_config"}

    def test_subdir_file_not_included(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="config/blueprints/foo.yaml\n"
            )
            result = detect_changed_services()
        assert result == set()

    def test_multiple_files_returns_multiple_services(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="config/automations.yaml\nconfig/scripts.yaml\n"
            )
            result = detect_changed_services()
        assert result == {"automation/reload", "script/reload"}

    def test_no_changed_files_returns_empty_set(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="")
            result = detect_changed_services()
        assert result == set()

    def test_git_nonzero_returns_none(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            result = detect_changed_services()
        assert result is None

    def test_git_not_found_returns_none(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError
            result = detect_changed_services()
        assert result is None

    def test_status_short_picks_up_untracked_files(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout=""),
                MagicMock(returncode=0, stdout="?? config/automations.yaml\n"),
            ]
            result = detect_changed_services()
        assert result == {"automation/reload"}

    def test_timeout_on_diff_returns_none(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=10)
            result = detect_changed_services()
        assert result is None

    def test_timeout_on_status_returns_diff_result(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="config/automations.yaml\n"),
                subprocess.TimeoutExpired(cmd="git", timeout=10),
            ]
            result = detect_changed_services()
        assert result == {"automation/reload"}


class TestReloadService:
    def _headers(self):
        return {"Authorization": "Bearer test", "Content-Type": "application/json"}

    def test_200_returns_service_and_true(self):
        mock_response = MagicMock(status_code=200)
        with patch("tools.reload_config.requests.post", return_value=mock_response):
            result = reload_service("automation/reload", "http://test:8123", self._headers())
        assert result == ("automation/reload", True)

    def test_500_returns_service_and_false(self):
        mock_response = MagicMock(status_code=500)
        with patch("tools.reload_config.requests.post", return_value=mock_response):
            result = reload_service("automation/reload", "http://test:8123", self._headers())
        assert result == ("automation/reload", False)

    def test_timeout_returns_service_and_false(self):
        with patch(
            "tools.reload_config.requests.post", side_effect=requests.exceptions.Timeout
        ):
            result = reload_service("automation/reload", "http://test:8123", self._headers())
        assert result == ("automation/reload", False)

    def test_connection_error_returns_service_and_false(self):
        with patch(
            "tools.reload_config.requests.post",
            side_effect=requests.exceptions.ConnectionError,
        ):
            result = reload_service("automation/reload", "http://test:8123", self._headers())
        assert result == ("automation/reload", False)


class TestReloadConfig:
    def test_success(self):
        mock_response = MagicMock(status_code=200)
        with (
            patch.dict(
                "os.environ", {"HA_TOKEN": "test_token", "HA_URL": "http://test:8123"}
            ),
            patch("tools.reload_config.load_env_file"),
            patch(
                "tools.reload_config.detect_changed_services",
                return_value={"homeassistant/reload_core_config"},
            ),
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
        mock_response = MagicMock(status_code=500)

        with (
            patch.dict(
                "os.environ", {"HA_TOKEN": "test_token", "HA_URL": "http://test:8123"}
            ),
            patch("tools.reload_config.load_env_file"),
            patch(
                "tools.reload_config.detect_changed_services",
                return_value={"homeassistant/reload_core_config"},
            ),
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
                "tools.reload_config.detect_changed_services",
                return_value={"homeassistant/reload_core_config"},
            ),
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
                "tools.reload_config.detect_changed_services",
                return_value={"homeassistant/reload_core_config"},
            ),
            patch(
                "tools.reload_config.requests.post",
                side_effect=requests.exceptions.ConnectionError,
            ),
        ):
            assert reload_config() is False

    def test_request_exception(self):
        with (
            patch.dict(
                "os.environ", {"HA_TOKEN": "test_token", "HA_URL": "http://test:8123"}
            ),
            patch("tools.reload_config.load_env_file"),
            patch(
                "tools.reload_config.detect_changed_services",
                return_value={"homeassistant/reload_core_config"},
            ),
            patch(
                "tools.reload_config.requests.post",
                side_effect=requests.exceptions.RequestException("unexpected"),
            ),
        ):
            assert reload_config() is False

    def test_invalid_ha_url(self):
        with (
            patch.dict("os.environ", {"HA_TOKEN": "test_token", "HA_URL": "not_a_url"}),
            patch("tools.reload_config.load_env_file"),
        ):
            assert reload_config() is False

    def test_detect_returns_none_reloads_all_services(self):
        mock_response = MagicMock(status_code=200)
        with (
            patch.dict(
                "os.environ", {"HA_TOKEN": "test_token", "HA_URL": "http://test:8123"}
            ),
            patch("tools.reload_config.load_env_file"),
            patch("tools.reload_config.detect_changed_services", return_value=None),
            patch(
                "tools.reload_config.requests.post", return_value=mock_response
            ) as mock_post,
        ):
            result = reload_config()
        assert result is True
        assert mock_post.call_count == 4

    def test_detect_returns_empty_set_reloads_all_services(self):
        mock_response = MagicMock(status_code=200)
        with (
            patch.dict(
                "os.environ", {"HA_TOKEN": "test_token", "HA_URL": "http://test:8123"}
            ),
            patch("tools.reload_config.load_env_file"),
            patch("tools.reload_config.detect_changed_services", return_value=set()),
            patch(
                "tools.reload_config.requests.post", return_value=mock_response
            ) as mock_post,
        ):
            result = reload_config()
        assert result is True
        assert mock_post.call_count == 4

    def test_detect_returns_one_service_makes_one_call(self):
        mock_response = MagicMock(status_code=200)
        with (
            patch.dict(
                "os.environ", {"HA_TOKEN": "test_token", "HA_URL": "http://test:8123"}
            ),
            patch("tools.reload_config.load_env_file"),
            patch(
                "tools.reload_config.detect_changed_services",
                return_value={"automation/reload"},
            ),
            patch(
                "tools.reload_config.requests.post", return_value=mock_response
            ) as mock_post,
        ):
            result = reload_config()
        assert result is True
        assert mock_post.call_count == 1

    def test_one_service_fails_returns_false(self):
        def post_side_effect(url, **kwargs):
            if "automation" in url:
                return MagicMock(status_code=200)
            return MagicMock(status_code=500)

        with (
            patch.dict(
                "os.environ", {"HA_TOKEN": "test_token", "HA_URL": "http://test:8123"}
            ),
            patch("tools.reload_config.load_env_file"),
            patch(
                "tools.reload_config.detect_changed_services",
                return_value={"automation/reload", "script/reload"},
            ),
            patch("tools.reload_config.requests.post", side_effect=post_side_effect),
        ):
            result = reload_config()
        assert result is False

    def test_prints_reloading_header(self, capsys):
        mock_response = MagicMock(status_code=200)
        with (
            patch.dict(
                "os.environ", {"HA_TOKEN": "test_token", "HA_URL": "http://test:8123"}
            ),
            patch("tools.reload_config.load_env_file"),
            patch(
                "tools.reload_config.detect_changed_services",
                return_value={"automation/reload"},
            ),
            patch("tools.reload_config.requests.post", return_value=mock_response),
        ):
            reload_config()
        out = capsys.readouterr().out
        assert "🔄 Reloading: automations" in out

    def test_prints_success_per_service(self, capsys):
        mock_response = MagicMock(status_code=200)
        with (
            patch.dict(
                "os.environ", {"HA_TOKEN": "test_token", "HA_URL": "http://test:8123"}
            ),
            patch("tools.reload_config.load_env_file"),
            patch(
                "tools.reload_config.detect_changed_services",
                return_value={"automation/reload"},
            ),
            patch("tools.reload_config.requests.post", return_value=mock_response),
        ):
            reload_config()
        out = capsys.readouterr().out
        assert "✅ automations reloaded" in out

    def test_prints_failure_per_service(self, capsys):
        mock_response = MagicMock(status_code=500)
        with (
            patch.dict(
                "os.environ", {"HA_TOKEN": "test_token", "HA_URL": "http://test:8123"}
            ),
            patch("tools.reload_config.load_env_file"),
            patch(
                "tools.reload_config.detect_changed_services",
                return_value={"script/reload"},
            ),
            patch("tools.reload_config.requests.post", return_value=mock_response),
        ):
            reload_config()
        out = capsys.readouterr().out
        assert "❌ scripts failed to reload" in out

    def test_core_config_reloads_before_domain_services(self):
        call_order = []

        def post_side_effect(url, **kwargs):
            if "reload_core_config" in url:
                call_order.append("core")
            else:
                call_order.append("domain")
            return MagicMock(status_code=200)

        with (
            patch.dict(
                "os.environ", {"HA_TOKEN": "test_token", "HA_URL": "http://test:8123"}
            ),
            patch("tools.reload_config.load_env_file"),
            patch(
                "tools.reload_config.detect_changed_services",
                return_value={"homeassistant/reload_core_config", "automation/reload"},
            ),
            patch("tools.reload_config.requests.post", side_effect=post_side_effect),
        ):
            result = reload_config()

        assert result is True
        assert call_order[0] == "core"
        assert "domain" in call_order[1:]
