"""TDD tests for tools/commands/edit.py — ha_cli edit subcommand."""

from argparse import Namespace
from unittest.mock import patch

from tests.helpers import make_parser
from tools.commands.edit import add_parser, run


def _boom(*arguments, **keywords):
    """Helper: raises TypeError. Used in monkeypatch tests."""
    raise TypeError("boom")


class TestAddParser:
    def test_subparser_registered(self):
        parser, subparsers = make_parser()
        add_parser(subparsers)
        args = parser.parse_args(["edit", "automations"])
        assert args.command == "edit"
        assert args.file == "automations"

    def test_alias_positional_parsed_correctly(self):
        """edit <file> <alias> --show should parse alias as a positional."""
        parser, subparsers = make_parser()
        add_parser(subparsers)
        args = parser.parse_args(["edit", "automations", "Turn on Alarm", "--show"])
        assert args.file == "automations"
        assert args.alias == "Turn on Alarm"
        assert args.show is True

    def test_config_dir_flag_defaults(self):
        """--config should default to 'config'."""
        parser, subparsers = make_parser()
        add_parser(subparsers)
        args = parser.parse_args(["edit", "automations", "--show"])
        assert args.config == "config"
        assert args.file == "automations"

    def test_summary_flag_registered(self):
        parser, subparsers = make_parser()
        add_parser(subparsers)
        args = parser.parse_args(["edit", "automations", "--summary"])
        assert args.summary is True

    def test_no_summary_flag_registered(self):
        parser, subparsers = make_parser()
        add_parser(subparsers)
        args = parser.parse_args(["edit", "automations", "--no-summary"])
        assert args.no_summary is True

    def test_summary_defaults_false(self):
        parser, subparsers = make_parser()
        add_parser(subparsers)
        args = parser.parse_args(["edit", "automations"])
        assert args.summary is False
        assert args.no_summary is False


def _write_file(cfg_dir, basename, content):
    path = cfg_dir / f"{basename}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


class TestRunShow:
    def _args(self, cfg_dir, file="automations", alias=None):
        return Namespace(
            config=str(cfg_dir),
            file=file,
            alias=alias,
            show=True,
            set=None,
            add=None,
            remove=False,
            quiet=False,
        )

    def test_show_all_lists_aliases(self, tmp_path, capsys):
        _write_file(
            tmp_path,
            "automations",
            """\
- id: a1
  alias: First
  triggers: []
  conditions: []
  actions: []
  mode: single
- id: a2
  alias: Second
  triggers: []
  conditions: []
  actions: []
  mode: single
""",
        )
        run(self._args(tmp_path))
        out = capsys.readouterr().out
        assert "First" in out
        assert "Second" in out

    def test_show_one_displays_full_automation(self, tmp_path, capsys):
        _write_file(
            tmp_path,
            "automations",
            """\
- id: abc
  alias: Target
  triggers:
    - trigger: state
      entity_id: binary_sensor.test
      to: 'on'
  conditions: []
  actions:
    - action: notify.test
      data:
        message: Hello
  mode: single
""",
        )
        run(self._args(tmp_path, alias="Target"))
        out = capsys.readouterr().out
        assert "Target" in out
        assert "notify.test" in out

    def test_show_missing_alias_prints_error(self, tmp_path, capsys):
        _write_file(tmp_path, "automations", "[]")
        result = run(self._args(tmp_path, alias="Ghost"))
        assert result == 1
        assert "not found" in capsys.readouterr().err.lower()


class TestRunSet:
    def _args(self, cfg_dir, alias=None, kvs=None):
        return Namespace(
            config=str(cfg_dir),
            file="automations",
            alias=alias,
            show=False,
            set=kvs or [],
            add=None,
            remove=False,
            quiet=False,
        )

    def test_set_updates_automation(self, tmp_path):
        _write_file(
            tmp_path,
            "automations",
            """\
- id: abc
  alias: Target
  description: Old
  triggers: []
  conditions: []
  actions: []
  mode: single
""",
        )
        run(self._args(tmp_path, alias="Target", kvs=["description=Updated"]))
        import yaml

        reloaded = yaml.safe_load((tmp_path / "automations.yaml").read_text())
        assert reloaded[0]["description"] == "Updated"

    def test_set_missing_alias_returns_error(self, tmp_path, capsys):
        _write_file(tmp_path, "automations", "[]")
        result = run(self._args(tmp_path, alias="Ghost", kvs=["x=y"]))
        assert result == 1
        err = capsys.readouterr().err
        assert "not found" in err.lower()


class TestRunAdd:
    def _args(self, cfg_dir, json_str=None):
        return Namespace(
            config=str(cfg_dir),
            file="automations",
            alias=None,
            show=False,
            set=None,
            add=json_str,
            remove=False,
            quiet=False,
        )

    def test_add_appends_automation(self, tmp_path):
        _write_file(
            tmp_path,
            "automations",
            """\
- id: existing
  alias: Existing
  triggers: []
  conditions: []
  actions: []
  mode: single
""",
        )
        run(
            self._args(
                tmp_path,
                json_str='{"alias":"New","id":"new_id","triggers":[],"conditions":[],"actions":[],"mode":"single"}',
            )
        )
        import yaml

        reloaded = yaml.safe_load((tmp_path / "automations.yaml").read_text())
        assert len(reloaded) == 2
        assert reloaded[1]["alias"] == "New"


class TestRunRemove:
    def _args(self, cfg_dir, alias=None):
        return Namespace(
            config=str(cfg_dir),
            file="automations",
            alias=alias,
            show=False,
            set=None,
            add=None,
            remove=True,
            quiet=False,
        )

    def test_remove_automation(self, tmp_path):
        _write_file(
            tmp_path,
            "automations",
            """\
- id: keep
  alias: Keep Me
  triggers: []
  conditions: []
  actions: []
  mode: single
- id: del
  alias: Delete Me
  triggers: []
  conditions: []
  actions: []
  mode: single
""",
        )
        run(self._args(tmp_path, alias="Delete Me"))
        import yaml

        reloaded = yaml.safe_load((tmp_path / "automations.yaml").read_text())
        assert len(reloaded) == 1
        assert reloaded[0]["alias"] == "Keep Me"

    def test_remove_missing_alias_returns_error(self, tmp_path, capsys):
        _write_file(tmp_path, "automations", "[]")
        result = run(self._args(tmp_path, alias="Ghost"))
        assert result == 1
        err = capsys.readouterr().err
        assert "not found" in err.lower()


# ---------------------------------------------------------------------------
# Edge case tests (from rubber-duck review)
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def _ns(self, **overrides):
        defaults = {
            "config": "config",
            "file": "automations",
            "alias": None,
            "show": False,
            "set": None,
            "add": None,
            "remove": False,
            "quiet": False,
        }
        defaults.update(overrides)
        return Namespace(**defaults)

    def test_conflicting_show_and_remove_rejected(self, capsys):
        result = run(self._ns(show=True, remove=True, alias="X"))
        assert result == 1
        assert "conflicting" in capsys.readouterr().err.lower()

    def test_conflicting_add_and_show_rejected(self, capsys):
        result = run(self._ns(show=True, add='{"x":1}'))
        assert result == 1
        assert "conflicting" in capsys.readouterr().err.lower()

    def test_nonexistent_file_errors(self, tmp_path, capsys):
        args = self._ns(config=str(tmp_path), show=True)
        result = run(args)
        assert result == 1
        assert "not found" in capsys.readouterr().err.lower()

    def test_set_on_nonexistent_file_errors(self, tmp_path, capsys):
        args = self._ns(config=str(tmp_path), set=["x=y"], alias="X")
        result = run(args)
        assert result == 1
        assert "not found" in capsys.readouterr().err.lower()

    def test_add_creates_file(self, tmp_path):
        """--add creates the file if it didn't exist."""
        args = self._ns(
            config=str(tmp_path),
            add='{"alias":"New","id":"n","triggers":[],"conditions":[],"actions":[],"mode":"single"}',
        )
        result = run(args)
        assert result == 0
        import yaml

        data = yaml.safe_load((tmp_path / "automations.yaml").read_text())
        assert data[0]["alias"] == "New"

    def test_add_to_scripts_file(self, tmp_path):
        """--add on a scripts (dict) file adds as a new key."""
        _write_file(tmp_path, "scripts", "{}")
        args = self._ns(
            config=str(tmp_path),
            file="scripts",
            add='{"alias":"Notify","id":"notify","sequence":[]}',
        )
        result = run(args)
        assert result == 0
        import yaml

        data = yaml.safe_load((tmp_path / "scripts.yaml").read_text())
        assert isinstance(data, dict)
        assert "notify" in data

    def test_add_to_new_scripts_file_creates_dict(self, tmp_path):
        """--add to a non-existent scripts file creates a dict, not a list."""
        args = self._ns(
            config=str(tmp_path),
            file="scripts",
            add='{"alias":"Notify","id":"notify","sequence":[]}',
        )
        result = run(args)
        assert result == 0
        import yaml

        data = yaml.safe_load((tmp_path / "scripts.yaml").read_text())
        assert isinstance(data, dict)
        assert "notify" in data

    def test_no_action_defaults_to_show(self, tmp_path, capsys):
        """No flag defaults to --show (lists aliases or errors if no file)."""
        args = self._ns(config=str(tmp_path), show=False)
        result = run(args)
        assert (
            result == 1
        )  # file not found since tmp_path doesn't have automations.yaml
        err = capsys.readouterr().err
        assert "not found" in err.lower()

    def test_missing_alias_for_set_errors(self, capsys):
        result = run(self._ns(set=["x=y"]))
        assert result == 1
        assert "alias required" in capsys.readouterr().err.lower()

    def test_set_on_scripts_file(self, tmp_path):
        """--set on scripts (dict) updates via update_script."""
        _write_file(
            tmp_path,
            "scripts",
            """\
morning:
  alias: Morning
  sequence: []
""",
        )
        args = self._ns(
            config=str(tmp_path),
            file="scripts",
            alias="morning",
            set=["description=Updated"],
        )
        result = run(args)
        assert result == 0
        import yaml

        data = yaml.safe_load((tmp_path / "scripts.yaml").read_text())
        assert data["morning"]["description"] == "Updated"

    def test_remove_on_scripts_file(self, tmp_path):
        """--remove on scripts (dict) removes via remove_script."""
        _write_file(
            tmp_path,
            "scripts",
            """\
keep:
  alias: Keep
  sequence: []
delete:
  alias: Delete
  sequence: []
""",
        )
        args = self._ns(
            config=str(tmp_path),
            file="scripts",
            alias="delete",
            remove=True,
        )
        result = run(args)
        assert result == 0
        import yaml

        data = yaml.safe_load((tmp_path / "scripts.yaml").read_text())
        assert "delete" not in data
        assert "keep" in data

    # ── Scripts --show (covers edit.py:181-190) ─────────────────────

    def test_show_scripts_lists_keys(self, tmp_path, capsys):
        _write_file(
            tmp_path,
            "scripts",
            "morning:\n  sequence: []\nevening:\n  sequence: []\n",
        )
        run(self._ns(config=str(tmp_path), file="scripts", show=True))
        out = capsys.readouterr().out
        assert "morning" in out
        assert "evening" in out

    def test_show_one_script_displays_full(self, tmp_path, capsys):
        _write_file(
            tmp_path,
            "scripts",
            "morning:\n  alias: Morning\n  sequence: []\n",
        )
        run(self._ns(config=str(tmp_path), file="scripts", alias="morning", show=True))
        assert "Morning" in capsys.readouterr().out

    def test_show_missing_script_prints_error(self, tmp_path, capsys):
        _write_file(tmp_path, "scripts", "morning:\n  sequence: []\n")
        result = run(
            self._ns(config=str(tmp_path), file="scripts", alias="ghost", show=True)
        )
        assert result == 1
        assert "not found" in capsys.readouterr().err.lower()

    # ── --add / --set error branches (covers 197-202, 213-217, 243-247) ──

    def test_add_invalid_json_returns_error(self, tmp_path, capsys):
        result = run(self._ns(config=str(tmp_path), add="{not json"))
        assert result == 1
        assert "invalid json" in capsys.readouterr().err.lower()

    def test_add_json_array_returns_error(self, tmp_path, capsys):
        result = run(self._ns(config=str(tmp_path), add="[1,2,3]"))
        assert result == 1
        assert "json object" in capsys.readouterr().err.lower()

    def test_add_scripts_without_id_or_alias_errors(self, tmp_path, capsys):
        _write_file(tmp_path, "scripts", "{}\n")
        result = run(
            self._ns(config=str(tmp_path), file="scripts", add='{"foo":"bar"}')
        )
        assert result == 1
        err = capsys.readouterr().err.lower()
        assert "id" in err or "alias" in err

    def test_set_malformed_kv_returns_error(self, tmp_path, capsys):
        _write_file(tmp_path, "automations", "[]")
        result = run(self._ns(config=str(tmp_path), alias="X", set=["no_equals"]))
        assert result == 1
        assert "key=value" in capsys.readouterr().err.lower()

    # ── TypeError handlers (covers 226-228, 260-262, 279-281) ──────────

    def test_add_type_error_returns_error(self, tmp_path, capsys, monkeypatch):
        _write_file(tmp_path, "automations", "[]")
        monkeypatch.setattr("tools.commands.edit.YAMLEditor.add_automation", _boom)
        result = run(self._ns(config=str(tmp_path), add='{"alias":"X","id":"x"}'))
        assert result == 1
        assert "boom" in capsys.readouterr().err

    def test_set_type_error_returns_error(self, tmp_path, capsys, monkeypatch):
        _write_file(
            tmp_path,
            "automations",
            "- id: a\n  alias: A\n  triggers: []\n"
            "  conditions: []\n  actions: []\n  mode: single\n",
        )
        monkeypatch.setattr("tools.commands.edit.YAMLEditor.update_automation", _boom)
        result = run(self._ns(config=str(tmp_path), alias="A", set=["x=y"]))
        assert result == 1
        assert "boom" in capsys.readouterr().err

    def test_remove_type_error_returns_error(self, tmp_path, capsys, monkeypatch):
        _write_file(
            tmp_path,
            "automations",
            "- id: a\n  alias: A\n  triggers: []\n"
            "  conditions: []\n  actions: []\n  mode: single\n",
        )
        monkeypatch.setattr("tools.commands.edit.YAMLEditor.remove_automation", _boom)
        result = run(self._ns(config=str(tmp_path), alias="A", remove=True))
        assert result == 1
        assert "boom" in capsys.readouterr().err

    # ── ValueError on duplicate script key (covers 229-231) ─────────────

    def test_add_duplicate_script_key_returns_error(self, tmp_path, capsys):
        _write_file(tmp_path, "scripts", "morning:\n  sequence: []\n")
        result = run(
            self._ns(
                config=str(tmp_path),
                file="scripts",
                add='{"id":"morning","alias":"M","sequence":[]}',
            )
        )
        assert result == 1
        assert "already exists" in capsys.readouterr().err.lower()

    # ── Path traversal guard (covers 87-88, 116-118) ──────────────────

    def test_path_traversal_rejected(self, capsys):
        result = run(self._ns(config="config", file="../../../etc/passwd", show=True))
        assert result == 1
        assert "inside config directory" in capsys.readouterr().err.lower()

    # ── Success prints (covers 235, 285) ──────────────────────────────

    @patch("tools.common._is_tty", return_value=True)
    def test_add_prints_success_when_verbose(self, mock_is_tty, tmp_path, capsys):
        run(self._ns(config=str(tmp_path), add='{"alias":"New","id":"n"}'))
        assert "Added:" in capsys.readouterr().out

    @patch("tools.common._is_tty", return_value=True)
    def test_remove_prints_success_when_verbose(self, mock_is_tty, tmp_path, capsys):
        _write_file(
            tmp_path,
            "automations",
            "- id: a\n  alias: A\n  triggers: []\n"
            "  conditions: []\n  actions: []\n  mode: single\n",
        )
        run(self._ns(config=str(tmp_path), alias="A", remove=True))
        assert "Removed:" in capsys.readouterr().out
