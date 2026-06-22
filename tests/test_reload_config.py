"""Tests for tools/reload_config.py - HA config reload via API."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from tools.common import HARequestError
from tools.reload_config import detect_changed_services, reload_config, reload_service


def _diff_only(stdout):
    """Return side_effect list: diff returns stdout, status returns empty."""
    return [
        MagicMock(returncode=0, stdout=stdout),
        MagicMock(returncode=0, stdout=""),
    ]


def _make_client():
    """Return a mock HAClient with call_service stubbed to return True."""
    client = MagicMock()
    client.call_service.return_value = True
    client.timeout = 30
    return client


class TestDetectChangedServices:
    def test_automations_yaml_returns_automation_reload(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = _diff_only("config/automations.yaml\n")
            result = detect_changed_services()
        assert result == {"automation/reload"}

    def test_scripts_yaml_returns_script_reload(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = _diff_only("config/scripts.yaml\n")
            result = detect_changed_services()
        assert result == {"script/reload"}

    def test_scenes_yaml_returns_scene_reload(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = _diff_only("config/scenes.yaml\n")
            result = detect_changed_services()
        assert result == {"scene/reload"}

    def test_configuration_yaml_returns_reload_core_config(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = _diff_only("config/configuration.yaml\n")
            result = detect_changed_services()
        assert result == {"homeassistant/reload_core_config"}

    def test_unknown_yaml_returns_reload_core_config(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = _diff_only("config/secrets.yaml\n")
            result = detect_changed_services()
        assert result == {"homeassistant/reload_core_config"}

    def test_subdir_file_not_included(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = _diff_only("config/blueprints/foo.yaml\n")
            result = detect_changed_services()
        assert result == set()

    def test_multiple_files_returns_multiple_services(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = _diff_only(
                "config/automations.yaml\nconfig/scripts.yaml\n"
            )
            result = detect_changed_services()
        assert result == {"automation/reload", "script/reload"}

    def test_no_changed_files_returns_empty_set(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = _diff_only("")
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
    """reload_service now takes a HAClient instead of (url, headers, timeout)."""

    def test_success_returns_service_and_true(self):
        client = _make_client()
        client.call_service.return_value = True
        assert reload_service(client, "automation/reload") == (
            "automation/reload",
            True,
        )

    def test_failure_returns_service_and_false(self):
        client = _make_client()
        client.call_service.return_value = False
        assert reload_service(client, "automation/reload") == (
            "automation/reload",
            False,
        )

    def test_call_service_invoked_with_domain_and_action(self):
        client = _make_client()
        reload_service(client, "automation/reload")
        client.call_service.assert_called_once_with("automation", "reload")

    def test_core_config_service_dispatches_correctly(self):
        client = _make_client()
        reload_service(client, "homeassistant/reload_core_config")
        client.call_service.assert_called_once_with(
            "homeassistant", "reload_core_config"
        )


class TestReloadConfig:
    """All tests stub HAClient.from_env so reload_config() never touches the network."""

    @pytest.fixture(autouse=True)
    def _stub_ha_client(self, monkeypatch):
        """Replace HAClient.from_env with a mock-client factory.

        Tests that need to assert on call_service behavior can read
        `mock_client.call_service` directly.
        """
        client = _make_client()

        def _factory():
            return client

        monkeypatch.setattr("tools.reload_config.HAClient.from_env", _factory)
        # Also expose the client instance for assertions.
        self._mock_client = client

    def test_success(self):
        with patch(
            "tools.reload_config.detect_changed_services",
            return_value={"homeassistant/reload_core_config"},
        ):
            assert reload_config() is True

    def test_api_failure(self):
        self._mock_client.call_service.return_value = False
        with patch(
            "tools.reload_config.detect_changed_services",
            return_value={"homeassistant/reload_core_config"},
        ):
            assert reload_config() is False

    def test_from_env_raises_returns_false(self, capsys):
        """If HAClient.from_env raises HARequestError, reload_config returns False."""
        with (
            patch(
                "tools.reload_config.HAClient.from_env",
                side_effect=HARequestError("HA_URL must start with http://"),
            ),
            patch(
                "tools.reload_config.detect_changed_services",
                return_value={"automation/reload"},
            ),
        ):
            assert reload_config() is False
        out = capsys.readouterr().out
        assert "HA_URL must start with" in out

    def test_from_env_token_error_includes_hint(self, capsys):
        """Token-related errors print the 'create a token' hint."""
        with (
            patch(
                "tools.reload_config.HAClient.from_env",
                side_effect=HARequestError("HA_TOKEN not found"),
            ),
            patch(
                "tools.reload_config.detect_changed_services",
                return_value={"automation/reload"},
            ),
        ):
            assert reload_config() is False
        out = capsys.readouterr().out
        assert "long_lived_access_token" in out

    def test_detect_returns_none_reloads_all_services(self):
        with patch("tools.reload_config.detect_changed_services", return_value=None):
            result = reload_config()
        assert result is True
        assert self._mock_client.call_service.call_count == 4

    def test_detect_returns_empty_set_reloads_all_services(self):
        with patch("tools.reload_config.detect_changed_services", return_value=set()):
            result = reload_config()
        assert result is True
        assert self._mock_client.call_service.call_count == 4

    def test_detect_returns_one_service_makes_one_call(self):
        with patch(
            "tools.reload_config.detect_changed_services",
            return_value={"automation/reload"},
        ):
            result = reload_config()
        assert result is True
        assert self._mock_client.call_service.call_count == 1

    def test_one_service_fails_returns_false(self):
        # call_service returns True for the first call, False for the second.
        self._mock_client.call_service.side_effect = [True, False]
        with patch(
            "tools.reload_config.detect_changed_services",
            return_value={"automation/reload", "script/reload"},
        ):
            result = reload_config()
        assert result is False

    def test_prints_reloading_header(self, capsys):
        with patch(
            "tools.reload_config.detect_changed_services",
            return_value={"automation/reload"},
        ):
            reload_config()
        out = capsys.readouterr().out
        assert "\U0001f504 Reloading: automations" in out

    def test_prints_success_per_service(self, capsys):
        with patch(
            "tools.reload_config.detect_changed_services",
            return_value={"automation/reload"},
        ):
            reload_config()
        out = capsys.readouterr().out
        assert "\u2705 automations reloaded" in out

    def test_prints_failure_per_service(self, capsys):
        self._mock_client.call_service.return_value = False
        with patch(
            "tools.reload_config.detect_changed_services",
            return_value={"script/reload"},
        ):
            reload_config()
        out = capsys.readouterr().out
        assert "\u274c scripts failed to reload" in out

    def test_core_config_reloads_before_domain_services(self):
        """reload_core_config must run before any domain services in the same call."""
        call_order = []

        def _track_call(domain, action, data=None):
            call_order.append(f"{domain}/{action}")
            return True

        self._mock_client.call_service.side_effect = _track_call
        with patch(
            "tools.reload_config.detect_changed_services",
            return_value={"homeassistant/reload_core_config", "automation/reload"},
        ):
            result = reload_config()

        assert result is True
        assert call_order[0] == "homeassistant/reload_core_config"
        assert "automation/reload" in call_order[1:]

    def test_reload_timeout_overrides_client_timeout(self):
        """Reload-specific timeout (HA_RELOAD_TIMEOUT) overrides the client default."""
        with (
            patch(
                "tools.reload_config.detect_changed_services",
                return_value={"automation/reload"},
            ),
            patch.dict("os.environ", {"HA_RELOAD_TIMEOUT": "60"}),
        ):
            reload_config()
        assert self._mock_client.timeout == 60
