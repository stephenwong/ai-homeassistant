"""TDD tests for tools/commands/edit.py — ha_cli edit subcommand."""

from argparse import Namespace

from tools.commands.edit import add_parser, run


class TestAddParser:
    def test_subparser_registered(self):
        import argparse

        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        add_parser(subparsers)
        args = parser.parse_args(["edit", "config", "automations"])
        assert args.command == "edit"
        assert args.file == "automations"

    def test_attaches_run_func(self):
        import argparse

        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        add_parser(subparsers)
        args = parser.parse_args(["edit", "config", "automations", "--show"])
        assert callable(args.func)


def _write_file(cfg_dir, basename, content):
    path = cfg_dir / f"{basename}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


class TestRunShow:
    def _args(self, cfg_dir, file="automations", alias=None):
        return Namespace(
            config_dir=str(cfg_dir),
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
            config_dir=str(cfg_dir),
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
            config_dir=str(cfg_dir),
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
            config_dir=str(cfg_dir),
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
            "config_dir": "config",
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
        args = self._ns(config_dir=str(tmp_path), show=True)
        result = run(args)
        assert result == 1
        assert "not found" in capsys.readouterr().err.lower()

    def test_set_on_nonexistent_file_errors(self, tmp_path, capsys):
        args = self._ns(config_dir=str(tmp_path), set=["x=y"], alias="X")
        result = run(args)
        assert result == 1
        assert "not found" in capsys.readouterr().err.lower()

    def test_add_creates_file(self, tmp_path):
        """--add creates the file if it didn't exist."""
        args = self._ns(
            config_dir=str(tmp_path),
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
            config_dir=str(tmp_path),
            file="scripts",
            add='{"alias":"Notify","id":"notify","sequence":[]}',
        )
        result = run(args)
        assert result == 0
        import yaml

        data = yaml.safe_load((tmp_path / "scripts.yaml").read_text())
        assert isinstance(data, dict)
        assert "notify" in data

    def test_no_action_prints_error(self, capsys):
        result = run(self._ns())
        assert result == 1
        err = capsys.readouterr().err
        assert "no action" in err.lower()

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
            config_dir=str(tmp_path),
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
            config_dir=str(tmp_path),
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
