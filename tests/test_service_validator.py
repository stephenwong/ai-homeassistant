"""Unit tests for service_validator.py — service reference validation."""

from unittest.mock import MagicMock, patch

import pytest
import yaml

from tools.common import HARequestError
from tools.validators.services import ServiceValidator


@pytest.fixture
def config_dir(tmp_path):
    return tmp_path


def _write_automation(config_dir, data):
    f = config_dir / "automations.yaml"
    with open(f, "w") as fh:
        yaml.dump(data, fh)


def _mock_services(entries: list[dict]) -> MagicMock:
    client = MagicMock()
    client.get_json.return_value = entries
    return client


def _mock_offline() -> MagicMock:
    client = MagicMock()
    client.get_json.side_effect = HARequestError("offline")
    return client


class TestFileDeps:
    def test_file_deps_empty(self):
        v = ServiceValidator()
        assert v.file_deps() == []


class TestServiceValidation:
    def test_valid_service_passes(self, config_dir):
        _write_automation(
            config_dir,
            [
                {
                    "id": "t",
                    "alias": "T",
                    "triggers": [],
                    "actions": [
                        {"action": "light.turn_on", "data": {}},
                    ],
                },
            ],
        )
        mock_client = _mock_services([{"domain": "light", "services": {"turn_on": {}}}])
        with patch(
            "tools.validators.services.HAClient.from_env", return_value=mock_client
        ):
            v = ServiceValidator(str(config_dir))
            assert v.validate_all() is True
            assert len(v.errors) == 0

    def test_unknown_service_warns(self, config_dir):
        _write_automation(
            config_dir,
            [
                {
                    "id": "t",
                    "alias": "T",
                    "triggers": [],
                    "actions": [
                        {"action": "light.turn_onn", "data": {}},
                    ],
                },
            ],
        )
        mock_client = _mock_services([{"domain": "light", "services": {"turn_on": {}}}])
        with patch(
            "tools.validators.services.HAClient.from_env", return_value=mock_client
        ):
            v = ServiceValidator(str(config_dir))
            assert v.validate_all() is True
            assert any("light.turn_onn" in w for w in v.warnings)

    def test_legacy_service_key_supported(self, config_dir):
        _write_automation(
            config_dir,
            [
                {
                    "id": "t",
                    "alias": "T",
                    "triggers": [],
                    "actions": [
                        {"service": "notify.mobile_devices", "data": {}},
                    ],
                },
            ],
        )
        mock_client = _mock_services(
            [
                {"domain": "notify", "services": {"mobile_devices": {}}},
            ]
        )
        with patch(
            "tools.validators.services.HAClient.from_env", return_value=mock_client
        ):
            v = ServiceValidator(str(config_dir))
            assert v.validate_all() is True

    def test_template_action_skipped(self, config_dir):
        _write_automation(
            config_dir,
            [
                {
                    "id": "t",
                    "alias": "T",
                    "triggers": [],
                    "actions": [
                        {"action": "{{ 'light.turn_on' }}", "data": {}},
                    ],
                },
            ],
        )
        mock_client = _mock_services([{"domain": "light", "services": {"turn_on": {}}}])
        with patch(
            "tools.validators.services.HAClient.from_env", return_value=mock_client
        ):
            v = ServiceValidator(str(config_dir))
            assert v.validate_all() is True
            assert len(v.errors) == 0

    def test_secrets_yml_skipped(self, config_dir):
        f = config_dir / "secrets.yaml"
        f.write_text("api_key: secret123\n")
        mock_client = _mock_services([])
        with patch(
            "tools.validators.services.HAClient.from_env", return_value=mock_client
        ):
            v = ServiceValidator(str(config_dir))
            assert v.validate_all() is True

    def test_non_domain_service_value_ignored(self, config_dir):
        """Bare service names without a dot (e.g. notify.group sub-services)
        are not domain-qualified service calls and should be skipped."""
        _write_automation(
            config_dir,
            [
                {
                    "id": "t",
                    "alias": "T",
                    "triggers": [],
                    "actions": [
                        {"action": "mobile_app_sm_s926b", "data": {}},
                    ],
                },
            ],
        )
        mock_client = _mock_services([])
        with patch(
            "tools.validators.services.HAClient.from_env", return_value=mock_client
        ):
            v = ServiceValidator(str(config_dir))
            assert v.validate_all() is True
            assert any("non-domain" in i.lower() for i in v.info)

    def test_no_actions_found_passes(self, config_dir):
        _write_automation(
            config_dir,
            [
                {"id": "t", "alias": "T", "triggers": [], "actions": []},
            ],
        )
        mock_client = _mock_services([])
        with patch(
            "tools.validators.services.HAClient.from_env", return_value=mock_client
        ):
            v = ServiceValidator(str(config_dir))
            assert v.validate_all() is True

    def test_service_in_script_detected(self, config_dir):
        f = config_dir / "scripts.yaml"
        with open(f, "w") as fh:
            yaml.dump(
                {"my_script": {"sequence": [{"action": "light.turn_on", "data": {}}]}},
                fh,
            )
        mock_client = _mock_services([{"domain": "light", "services": {"turn_on": {}}}])
        with patch(
            "tools.validators.services.HAClient.from_env", return_value=mock_client
        ):
            v = ServiceValidator(str(config_dir))
            assert v.validate_all() is True
            assert len(v.warnings) == 0

    def test_broken_yaml_fails(self, config_dir):
        (config_dir / "automations.yaml").write_text("{{{ not valid yaml\n")
        mock_client = _mock_services([])
        with patch(
            "tools.validators.services.HAClient.from_env", return_value=mock_client
        ):
            v = ServiceValidator(str(config_dir))
            assert v.validate_all() is False
            assert any("syntax error" in e.lower() for e in v.errors)


class TestOfflineDegradation:
    def test_offline_degrades_to_format_check(self, config_dir):
        _write_automation(
            config_dir,
            [
                {
                    "id": "t",
                    "alias": "T",
                    "triggers": [],
                    "actions": [
                        {"action": "light.turn_on", "data": {}},
                    ],
                },
            ],
        )
        mock_client = _mock_offline()
        with patch(
            "tools.validators.services.HAClient.from_env", return_value=mock_client
        ):
            v = ServiceValidator(str(config_dir))
            assert v.validate_all() is True
            assert any("skipped" in i.lower() for i in v.info)

    def test_offline_bad_format_fails(self, config_dir):
        _write_automation(
            config_dir,
            [
                {
                    "id": "t",
                    "alias": "T",
                    "triggers": [],
                    "actions": [
                        {"action": "light..turn_on", "data": {}},
                    ],
                },
            ],
        )
        mock_client = _mock_offline()
        with patch(
            "tools.validators.services.HAClient.from_env", return_value=mock_client
        ):
            v = ServiceValidator(str(config_dir))
            assert v.validate_all() is False

    def test_catalog_is_none_handled(self, config_dir):
        _write_automation(
            config_dir,
            [
                {
                    "id": "t",
                    "alias": "T",
                    "triggers": [],
                    "actions": [
                        {"action": "light.turn_on", "data": {}},
                    ],
                },
            ],
        )
        mock_client = MagicMock()
        mock_client.get_json.return_value = None
        with patch(
            "tools.validators.services.HAClient.from_env", return_value=mock_client
        ):
            v = ServiceValidator(str(config_dir))
            assert v.validate_all() is True
            assert any("skipped" in i.lower() for i in v.info)
            assert len(v.errors) == 0

    def test_offline_from_env_fails(self, config_dir):
        _write_automation(
            config_dir,
            [
                {
                    "id": "t",
                    "alias": "T",
                    "triggers": [],
                    "actions": [
                        {"action": "light.turn_on", "data": {}},
                    ],
                },
            ],
        )
        with patch(
            "tools.validators.services.HAClient.from_env",
            side_effect=HARequestError("no env"),
        ):
            v = ServiceValidator(str(config_dir))
            assert v.validate_all() is True
            assert any("skipped" in i.lower() for i in v.info)


class TestEdgeCases:
    def test_nonexistent_dir_errors(self):
        v = ServiceValidator("/nonexistent")
        assert v.validate_all() is False
        assert any("does not exist" in e for e in v.errors)

    def test_mixed_known_and_unknown(self, config_dir):
        _write_automation(
            config_dir,
            [
                {
                    "id": "t",
                    "alias": "T",
                    "triggers": [],
                    "actions": [
                        {"action": "light.turn_on", "data": {}},
                        {"action": "light.turn_off", "data": {}},
                        {"action": "light.nonexistent", "data": {}},
                    ],
                },
            ],
        )
        mock_client = _mock_services(
            [{"domain": "light", "services": {"turn_on": {}, "turn_off": {}}}]
        )
        with patch(
            "tools.validators.services.HAClient.from_env", return_value=mock_client
        ):
            v = ServiceValidator(str(config_dir))
            assert v.validate_all() is True
            assert any("light.nonexistent" in w for w in v.warnings)
            assert not any("light.turn_on" in e for e in v.errors)
            assert not any("light.turn_off" in e for e in v.errors)


class TestMain:
    def test_main_dispatches_clean(self, config_dir, monkeypatch):
        from tools.validators.services import main

        _write_automation(
            config_dir,
            [
                {
                    "id": "t",
                    "alias": "T",
                    "triggers": [],
                    "actions": [
                        {"action": "light.turn_on", "data": {}},
                    ],
                },
            ],
        )
        mock_client = _mock_services([{"domain": "light", "services": {"turn_on": {}}}])
        monkeypatch.setattr("sys.argv", ["services", str(config_dir)])
        with patch(
            "tools.validators.services.HAClient.from_env", return_value=mock_client
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0

    def test_main_invalid(self, monkeypatch):
        from tools.validators.services import main

        monkeypatch.setattr("sys.argv", ["services", "/nonexistent"])
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 1
