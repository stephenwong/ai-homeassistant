"""Unit tests for template_validator.py — Jinja2 template linting via HA render API."""

from unittest.mock import MagicMock, patch

import yaml

from tools.common import HARequestError
from tools.validators.templates import TemplateValidator


def _write_automation(config_dir, data):
    f = config_dir / "automations.yaml"
    with open(f, "w") as fh:
        yaml.dump(data, fh)


def _mock_render(success: bool = True, message: str = "") -> MagicMock:
    client = MagicMock()
    resp = MagicMock()
    if success:
        resp.status_code = 200
        resp.text = "42"
    else:
        resp.status_code = 400
        resp.json.return_value = {"message": message}
        resp.text = message
    client.post.return_value = resp
    return client


class TestFileDeps:
    def test_file_deps_empty(self):
        v = TemplateValidator()
        assert v.file_deps() == []


class TestTemplateValidation:
    def test_valid_template_passes(self, config_dir):
        _write_automation(
            config_dir,
            [
                {
                    "id": "t",
                    "alias": "T",
                    "triggers": [],
                    "actions": [
                        {"action": "notify.send", "data": {"message": "{{ 1 + 1 }}"}},
                    ],
                },
            ],
        )
        client = _mock_render(success=True)
        with patch("tools.validators.templates.HAClient.from_env", return_value=client):
            v = TemplateValidator(str(config_dir))
            assert v.validate_all() is True
            assert len(v.errors) == 0

    def test_syntax_error_fails(self, config_dir):
        _write_automation(
            config_dir,
            [
                {
                    "id": "t",
                    "alias": "T",
                    "triggers": [],
                    "actions": [
                        {"action": "notify.send", "data": {"message": "{{ 1 + }}"}},
                    ],
                },
            ],
        )
        client = _mock_render(False, "syntax error: unexpected end of template")
        with patch("tools.validators.templates.HAClient.from_env", return_value=client):
            v = TemplateValidator(str(config_dir))
            assert v.validate_all() is False
            assert any("syntax error" in e.lower() for e in v.errors)

    def test_runtime_undefined_warns(self, config_dir):
        _write_automation(
            config_dir,
            [
                {
                    "id": "t",
                    "alias": "T",
                    "triggers": [],
                    "actions": [
                        {
                            "action": "notify.send",
                            "data": {"message": "{{ trigger.to_state.state }}"},
                        },
                    ],
                },
            ],
        )
        client = _mock_render(False, "'trigger' is undefined")
        with patch("tools.validators.templates.HAClient.from_env", return_value=client):
            v = TemplateValidator(str(config_dir))
            assert v.validate_all() is True
            assert any("trigger" in w for w in v.warnings)
            assert len(v.errors) == 0

    def test_unknown_filter_is_error(self, config_dir):
        _write_automation(
            config_dir,
            [
                {
                    "id": "t",
                    "alias": "T",
                    "triggers": [],
                    "actions": [
                        {
                            "action": "notify.send",
                            "data": {"message": "{{ 'x' | hash }}"},
                        },
                    ],
                },
            ],
        )
        client = _mock_render(False, "No filter named 'hash'")
        with patch("tools.validators.templates.HAClient.from_env", return_value=client):
            v = TemplateValidator(str(config_dir))
            assert v.validate_all() is False
            assert any("no filter named" in e.lower() for e in v.errors)

    def test_extracts_from_value_template(self, config_dir):
        _write_automation(
            config_dir,
            [
                {
                    "id": "t",
                    "alias": "T",
                    "trigger": {
                        "platform": "template",
                        "value_template": "{{ states('sensor.temp') | float > 20 }}",
                    },
                    "action": {"action": "notify.send", "data": {}},
                },
            ],
        )
        client = _mock_render(True)
        with patch("tools.validators.templates.HAClient.from_env", return_value=client):
            v = TemplateValidator(str(config_dir))
            assert v.validate_all() is True

    def test_skips_non_template_strings(self, config_dir):
        _write_automation(
            config_dir,
            [
                {
                    "id": "t",
                    "alias": "T",
                    "triggers": [],
                    "actions": [
                        {"action": "notify.send", "data": {"message": "Hello world"}},
                    ],
                },
            ],
        )
        client = _mock_render()
        with patch("tools.validators.templates.HAClient.from_env", return_value=client):
            v = TemplateValidator(str(config_dir))
            assert v.validate_all() is True
            assert len(v.info) == 0  # no "skipped" — we connected to HA
            assert len(v.errors) == 0

    def test_multiple_templates_all_valid(self, config_dir):
        _write_automation(
            config_dir,
            [
                {
                    "id": "a",
                    "alias": "A",
                    "triggers": [],
                    "actions": [
                        {
                            "action": "notify.send",
                            "data": {
                                "title": "{{ 'hello' }}",
                                "message": "{{ 2 + 2 }}",
                            },
                        },
                    ],
                },
                {
                    "id": "b",
                    "alias": "B",
                    "triggers": [],
                    "actions": [
                        {
                            "action": "light.turn_on",
                            "data": {"brightness": "{{ 255 }}"},
                        },
                    ],
                },
            ],
        )
        client = _mock_render(True)
        with patch("tools.validators.templates.HAClient.from_env", return_value=client):
            v = TemplateValidator(str(config_dir))
            assert v.validate_all() is True


class TestRenderErrors:
    def test_catch_all_warning_path(self, config_dir):
        """A 400 response that matches neither syntax nor runtime signatures
        should produce a warning, not an error."""
        _write_automation(
            config_dir,
            [
                {
                    "id": "t",
                    "alias": "T",
                    "triggers": [],
                    "actions": [
                        {
                            "action": "notify.send",
                            "data": {"message": "{{ something }}"},
                        },
                    ],
                },
            ],
        )
        client = _mock_render(False, "Something went wrong")
        with patch("tools.validators.templates.HAClient.from_env", return_value=client):
            v = TemplateValidator(str(config_dir))
            assert v.validate_all() is True
            assert len(v.errors) == 0
            assert any("warning" in w.lower() for w in v.warnings)

    def test_post_raises_request_error(self, config_dir):
        """When from_env succeeds but post() raises HARequestError, warn."""
        _write_automation(
            config_dir,
            [
                {
                    "id": "t",
                    "alias": "T",
                    "triggers": [],
                    "actions": [
                        {"action": "notify.send", "data": {"message": "{{ 1 + 1 }}"}},
                    ],
                },
            ],
        )
        client = MagicMock()
        client.post.side_effect = HARequestError("connection refused")
        with patch("tools.validators.templates.HAClient.from_env", return_value=client):
            v = TemplateValidator(str(config_dir))
            assert v.validate_all() is True
            assert any("connection refused" in w for w in v.warnings)

    def test_non_json_error_body_handled(self, config_dir):
        """When HA returns 400 with non-JSON body, fall back to resp.text."""
        _write_automation(
            config_dir,
            [
                {
                    "id": "t",
                    "alias": "T",
                    "triggers": [],
                    "actions": [
                        {"action": "notify.send", "data": {"message": "{{ 1 + }}"}},
                    ],
                },
            ],
        )
        client = MagicMock()
        resp = MagicMock()
        resp.status_code = 400
        resp.text = "plain text error"
        resp.json.side_effect = ValueError("not json")
        client.post.return_value = resp
        with patch("tools.validators.templates.HAClient.from_env", return_value=client):
            v = TemplateValidator(str(config_dir))
            assert v.validate_all() is True
            assert len(v.errors) == 0
            assert any("warning" in w.lower() for w in v.warnings)


class TestOfflineDegradation:
    def test_offline_warns_and_static_checks(self, config_dir):
        _write_automation(
            config_dir,
            [
                {
                    "id": "t",
                    "alias": "T",
                    "triggers": [],
                    "actions": [
                        {
                            "action": "notify.send",
                            "data": {"message": "{{ states('sensor.temp') }}"},
                        },
                    ],
                },
            ],
        )
        with patch(
            "tools.validators.templates.HAClient.from_env",
            side_effect=HARequestError("offline"),
        ):
            v = TemplateValidator(str(config_dir))
            assert v.validate_all() is True
            assert any("skipped" in i.lower() for i in v.info)

    def test_offline_balanced_template_passes(self, config_dir):
        _write_automation(
            config_dir,
            [
                {
                    "id": "t",
                    "alias": "T",
                    "triggers": [],
                    "actions": [
                        {
                            "action": "notify.send",
                            "data": {"message": "{{ states('sensor.x') }}"},
                        },
                    ],
                },
            ],
        )
        with patch(
            "tools.validators.templates.HAClient.from_env",
            side_effect=HARequestError("offline"),
        ):
            v = TemplateValidator(str(config_dir))
            assert v.validate_all() is True
            assert len(v.errors) == 0
            assert any("skipped" in i.lower() for i in v.info)

    def test_offline_unbalanced_brace_errors(self, config_dir):
        """A string with balanced {{ }} pairs PLUS extra unmatched }} is
        extractable (regex finds the pairs) but _balanced catches the mismatch."""
        _write_automation(
            config_dir,
            [
                {
                    "id": "t",
                    "alias": "T",
                    "triggers": [],
                    "actions": [
                        {
                            "action": "notify.send",
                            "data": {"message": "{{ a }} }} {{ b }}"},
                        },
                    ],
                },
            ],
        )
        with patch(
            "tools.validators.templates.HAClient.from_env",
            side_effect=HARequestError("offline"),
        ):
            v = TemplateValidator(str(config_dir))
            assert v.validate_all() is False
            assert any("unbalanced" in e.lower() for e in v.errors)


class TestEdgeCases:
    def test_nonexistent_dir_errors(self):
        v = TemplateValidator("/nonexistent")
        assert v.validate_all() is False
        assert any("does not exist" in e for e in v.errors)

    def test_no_templates_passes(self, config_dir):
        _write_automation(
            config_dir,
            [
                {"id": "t", "alias": "T", "triggers": [], "actions": []},
            ],
        )
        client = _mock_render(True)
        with patch("tools.validators.templates.HAClient.from_env", return_value=client):
            v = TemplateValidator(str(config_dir))
            assert v.validate_all() is True

    def test_broken_yaml_fails(self, config_dir):
        (config_dir / "automations.yaml").write_text("{{{ not valid yaml\n")
        client = _mock_render(True)
        with patch("tools.validators.templates.HAClient.from_env", return_value=client):
            v = TemplateValidator(str(config_dir))
            assert v.validate_all() is False
            assert any("syntax error" in e.lower() for e in v.errors)

    def test_secrets_yaml_skipped(self, config_dir):
        (config_dir / "secrets.yaml").write_text(
            "api_key: '{{ template_in_secret }}'\n"
        )
        client = _mock_render(True)
        with patch("tools.validators.templates.HAClient.from_env", return_value=client):
            v = TemplateValidator(str(config_dir))
            assert v.validate_all() is True

    def test_mixed_syntax_and_runtime(self, config_dir):
        _write_automation(
            config_dir,
            [
                {
                    "id": "t",
                    "alias": "T",
                    "triggers": [],
                    "actions": [
                        {
                            "action": "notify.send",
                            "data": {
                                "message": "{{ bad_filter | nonexistent }}",
                                "title": "{{ 'hello' }}",
                            },
                        },
                    ],
                },
            ],
        )
        client = _mock_render(False, "No filter named 'nonexistent'")
        with patch("tools.validators.templates.HAClient.from_env", return_value=client):
            v = TemplateValidator(str(config_dir))
            assert v.validate_all() is False  # syntax error = fail
            assert any("nonexistent" in e.lower() for e in v.errors)

    def test_control_flow_template_detected(self, config_dir):
        _write_automation(
            config_dir,
            [
                {
                    "id": "t",
                    "alias": "T",
                    "triggers": [],
                    "actions": [
                        {
                            "action": "notify.send",
                            "data": {"message": "{% if x %}a{% else %}b{% endif %}"},
                        },
                    ],
                },
            ],
        )
        client = _mock_render(True)
        with patch("tools.validators.templates.HAClient.from_env", return_value=client):
            v = TemplateValidator(str(config_dir))
            assert v.validate_all() is True


class TestL50EmptyErrorBody:
    """L50: empty error body must not IndexError."""

    def test_empty_error_body_does_not_crash(self, config_dir):
        """L50: _render returning ('error', '') must not IndexError."""
        from unittest.mock import MagicMock, patch

        _write_automation(
            config_dir,
            [
                {
                    "id": "t",
                    "alias": "T",
                    "triggers": [],
                    "actions": [
                        {
                            "action": "notify.send",
                            "data": {"message": "{{ something }}"},
                        },
                    ],
                },
            ],
        )
        client = MagicMock()
        resp = MagicMock()
        resp.status_code = 400
        resp.json.return_value = {"message": ""}
        resp.text = ""
        client.post.return_value = resp
        with patch("tools.validators.templates.HAClient.from_env", return_value=client):
            v = TemplateValidator(str(config_dir))
            assert v.validate_all() is True
            assert len(v.errors) == 0


class TestL51OSError:
    """L51: OSError from from_env must degrade gracefully."""

    def test_oserror_from_from_env_is_caught(self, config_dir):
        """L51: OSError from from_env must degrade gracefully."""
        from unittest.mock import patch

        _write_automation(
            config_dir,
            [
                {
                    "id": "t",
                    "alias": "T",
                    "triggers": [],
                    "actions": [
                        {
                            "action": "notify.send",
                            "data": {"message": "{{ 1 + 1 }}"},
                        },
                    ],
                },
            ],
        )
        with patch(
            "tools.validators.templates.HAClient.from_env",
            side_effect=OSError("connection refused"),
        ):
            v = TemplateValidator(str(config_dir))
            assert v.validate_all() is True
            assert any("skipped" in i.lower() for i in v.info)


class TestMain:
    def test_main_dispatches_clean(self, config_dir, monkeypatch):
        from tools.validators.templates import main

        _write_automation(
            config_dir,
            [
                {
                    "id": "t",
                    "alias": "T",
                    "triggers": [],
                    "actions": [
                        {"action": "notify.send", "data": {"message": "{{ 'ok' }}"}},
                    ],
                },
            ],
        )
        client = _mock_render(True)
        monkeypatch.setattr("sys.argv", ["templates", str(config_dir)])
        with patch("tools.validators.templates.HAClient.from_env", return_value=client):
            assert main() == 0

    def test_main_invalid(self, monkeypatch):
        from tools.validators.templates import main

        monkeypatch.setattr("sys.argv", ["templates", "/nonexistent"])
        assert main() == 1
