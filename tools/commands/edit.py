"""``edit`` subcommand: safe round-trip YAML editing for HA config files.

Supports automations.yaml (list) and scripts.yaml (dict) with --show, --set, --add,
and --remove operations.  All writes use atomic save via YAMLEditor.
"""

import argparse
import json
import sys
from pathlib import Path

from ruamel.yaml import YAMLError

from tools.common import resolve_summary
from tools.ha.yaml_editor import YAMLEditor


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    """Wire the ``edit`` subparser."""
    parser = subparsers.add_parser(
        "edit",
        help="Edit automations/scripts with safe round-trip YAML.",
        description="View, add, update, or remove automations/scripts.",
    )
    parser.add_argument(
        "file",
        help="Target file basename (automations, scripts).",
    )
    parser.add_argument(
        "alias",
        nargs="?",
        default=None,
        help="Automation alias or script name to operate on.",
    )
    parser.add_argument(
        "--config",
        "-c",
        default="config",
        help="Path to the config directory (default: config)",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Display the automation/script (or list all aliases if no alias).",
    )
    parser.add_argument(
        "--set",
        nargs="*",
        metavar="KEY=VALUE",
        help="Set top-level key=value pairs. Values are parsed as YAML.",
    )
    parser.add_argument(
        "--add",
        metavar="JSON",
        help="Add a new entry from a JSON string.",
    )
    parser.add_argument(
        "--remove",
        action="store_true",
        help="Remove the entry identified by alias.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress success messages.",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Compact output; auto-detected when stdout is not a TTY",
    )
    parser.add_argument(
        "--no-summary",
        action="store_true",
        help="Force verbose output even when stdout is piped",
    )
    parser.set_defaults(func=run)


def _resolve_target(config_dir: Path, file_basename: str) -> Path:
    """Resolve the target file path, guarding against path traversal."""
    if "." not in file_basename:
        file_basename += ".yaml"
    target = (config_dir / file_basename).resolve()
    try:
        target.relative_to(config_dir.resolve())
    except ValueError:
        raise ValueError(f"'{file_basename}' must be inside config directory") from None
    return target


def _check_exclusive(args: argparse.Namespace) -> str | None:
    """Return an error message if mutually exclusive flags are combined."""
    actions = []
    if args.show:
        actions.append("--show")
    if args.set:
        actions.append("--set")
    if args.add is not None:
        actions.append("--add")
    if args.remove:
        actions.append("--remove")
    if len(actions) > 1:
        return f"Conflicting flags: {' '.join(actions)}"
    return None


def run(args: argparse.Namespace) -> int:
    """Entry point for the ``edit`` subcommand. Returns exit code."""
    quiet = args.quiet or resolve_summary(args)
    config_dir = Path(args.config)
    try:
        target_file = _resolve_target(config_dir, args.file)
    except ValueError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1

    error = _check_exclusive(args)
    if error:
        print(f"❌ {error}", file=sys.stderr)
        return 1

    if args.alias is None and (args.set or args.remove):
        print("❌ alias required for --set or --remove", file=sys.stderr)
        return 1

    if not target_file.exists() and not args.add:
        print(f"❌ file not found: {target_file}", file=sys.stderr)
        return 1

    editor = YAMLEditor(target_file)

    try:
        if args.add is not None:
            return _run_add(editor, args.add, quiet)

        # --show (or default), --set, --remove
        if args.show or not any([args.set, args.remove]):
            return _run_show(editor, args.alias)

        alias: str = args.alias  # type: ignore[assignment]

        if args.set:
            return _run_set(editor, alias, args.set)

        if args.remove:
            return _run_remove(editor, alias, quiet)

        return 1  # pragma: no cover  # unreachable; satisfies type checker

    except FileNotFoundError as e:  # pragma: no cover
        print(f"❌ file not found: {e.filename}", file=sys.stderr)
        return 1


def _detect_file_type(editor: YAMLEditor) -> str:
    """Return 'list' or 'dict' describing the loaded data shape."""
    data = editor.load()
    if isinstance(data, list):
        return "list"
    if isinstance(data, dict):
        return "dict"
    return "unknown"  # pragma: no cover


def _run_show(editor: YAMLEditor, alias: str | None) -> int:
    data = editor.load()
    if isinstance(data, list):
        if alias is not None:
            idx = editor.find_automation(alias)
            if idx is None:
                print(f"❌ automation '{alias}' not found", file=sys.stderr)
                return 1
            editor.dump_to(data[idx], sys.stdout)
        else:
            for item in data:
                if isinstance(item, dict) and "alias" in item:
                    print(item["alias"])
    elif isinstance(data, dict):
        if alias is not None:
            if alias in data:
                editor.dump_to({alias: data[alias]}, sys.stdout)
            else:
                print(f"❌ script '{alias}' not found", file=sys.stderr)
                return 1
        else:
            for key in data:
                print(key)
    return 0


def _run_add(editor: YAMLEditor, json_str: str, quiet: bool) -> int:
    try:
        entry = json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"❌ invalid JSON: {e}", file=sys.stderr)
        return 1
    if not isinstance(entry, dict):
        print("❌ --add value must be a JSON object", file=sys.stderr)
        return 1

    if editor.path.exists():
        ftype = _detect_file_type(editor)
    else:
        # Infer type from file basename for new files
        ftype = "dict" if editor.path.name == "scripts.yaml" else "list"
    try:
        if ftype == "dict":
            key = str(entry.get("id") or entry.get("alias") or "")
            if not key:
                print(
                    "❌ --add requires 'id' or 'alias' key for script files",
                    file=sys.stderr,
                )
                return 1
            editor.add_script(key, entry)
            label = key
        else:
            editor.add_automation(entry)
            if isinstance(entry, dict):
                label = entry.get("alias") or entry.get("id") or "(no alias)"
            else:  # pragma: no cover
                label = "(no alias)"
    except TypeError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1

    editor.save()
    if not quiet:
        print(f"Added: {label}")
    return 0


def _run_set(editor: YAMLEditor, alias: str, kvs: list[str]) -> int:
    updates: dict = {}
    for kv in kvs:
        if "=" not in kv:
            print(
                f"❌ --set value must be KEY=VALUE, got '{kv}'",
                file=sys.stderr,
            )
            return 1
        key, _, value = kv.partition("=")
        updates[key.strip()] = _parse_value(value.strip())

    ftype = _detect_file_type(editor)
    try:
        if ftype == "dict":
            editor.update_script(alias, updates)
        else:
            editor.update_automation(alias, updates)
    except ValueError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1
    except TypeError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1

    editor.save()
    print(f"Updated '{alias}': {list(updates.keys())}")
    return 0


def _run_remove(editor: YAMLEditor, alias: str, quiet: bool) -> int:
    ftype = _detect_file_type(editor)
    try:
        if ftype == "dict":
            editor.remove_script(alias)
        else:
            editor.remove_automation(alias)
    except ValueError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1
    except TypeError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1

    editor.save()
    if not quiet:
        print(f"Removed: {alias}")
    return 0


def _parse_value(raw: str):
    """Parse a single key=value string using YAML for booleans/ints etc."""
    from ruamel.yaml import YAML

    y = YAML(typ="safe")
    try:
        return y.load(raw)
    except YAMLError, ValueError, TypeError:  # pragma: no cover
        return raw
