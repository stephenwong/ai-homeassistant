"""Shared utilities for HA configuration tools."""

import argparse
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml


class HAYamlLoader(yaml.SafeLoader):
    """Custom YAML loader that handles Home Assistant specific tags."""

    pass


_HA_TAGS = [
    "!include",
    "!include_dir_named",
    "!include_dir_merge_named",
    "!include_dir_merge_list",
    "!include_dir_list",
    "!input",
    "!secret",
]


def _make_tag_constructor(tag: str):
    """Return a constructor that round-trips a HA YAML tag as a plain string."""

    def constructor(loader, node):
        return f"{tag} {loader.construct_scalar(node)}"

    return constructor


for _tag in _HA_TAGS:
    HAYamlLoader.add_constructor(_tag, _make_tag_constructor(_tag))

DEFAULT_HA_URL = "http://homeassistant.local:8123"


def load_env_file():
    """Load environment variables from .env file."""
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    if key.strip():
                        os.environ[key.strip()] = value.strip().strip('"').strip("'")


def get_env_int(name: str, default: int, *, minimum: int = 1) -> tuple[int, str | None]:
    """Read an integer env var with validation and fallback.

    Returns:
        A tuple of (value, warning). warning is None when the parsed value is valid.
    """
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default, None

    try:
        value = int(raw)
    except ValueError:
        return default, f"{name} must be an integer, got {raw!r}; using {default}"

    if value < minimum:
        return (
            default,
            f"{name} must be >= {minimum}, got {value}; using {default}",
        )

    return value, None


def validate_ha_url(ha_url: str) -> str | None:
    """Validate HA URL format and return an error message when invalid."""
    parsed = urlparse(ha_url)
    if parsed.scheme not in {"http", "https"}:
        return "HA_URL must start with http:// or https://"
    if not parsed.netloc:
        return "HA_URL must include a hostname"
    return None


def _is_tty() -> bool:
    """Check if stdout is connected to a terminal.

    Returns False when stdout is piped, redirected to a file, or absent
    (e.g. when called from an agent or CI runner). Never raises.
    """
    try:
        return sys.stdout is not None and sys.stdout.isatty()
    except AttributeError, OSError, TypeError:
        return False


def _has_transform_flags(args: argparse.Namespace) -> bool:
    """Check if the curl command has any output-transforming flags active.

    Used by the bare-endpoint guardrail to detect whether the user has
    explicitly requested transformed output.  Returning True means the
    guardrail should not fire.

    Flags checked: count, keys, first, filter, raw, pick, abbrev, entity,
    domain, max_chars.
    """
    return bool(
        args.count
        or args.keys
        or args.first is not None
        or args.filter
        or args.raw
        or bool(args.pick)
        or args.abbrev
        or bool(args.entity)
        or bool(args.domain)
        or args.max_chars is not None
    )


def resolve_summary(args: argparse.Namespace) -> bool:
    """Resolve summary/verbose mode from argparse --summary/--no-summary flags.

    Logic:
        --summary       → True
        --no-summary    → False
        both            → warn on stderr, treat as --summary
        neither         → True when non-TTY, False when TTY

    Returns:
        True for compact/summary output, False for verbose.
    """
    explicit_summary = bool(getattr(args, "summary", False))
    explicit_no_summary = bool(getattr(args, "no_summary", False))
    if explicit_summary and explicit_no_summary:
        print(
            "WARN: conflicting --summary / --no-summary; using --summary",
            file=sys.stderr,
        )
    if explicit_summary:
        return True
    if explicit_no_summary:
        return False
    return not _is_tty()


class HARequestError(Exception):
    """Raised when a Home Assistant REST API request fails."""


class ValidatorBase:
    """Base class for Home Assistant configuration validators."""

    validator_name = "Configuration"

    def __init__(
        self, config_dir: str = "config", quiet: bool = False, summary: bool = False
    ):
        """Initialize the validator with config directory."""
        self.config_dir = Path(config_dir).resolve()
        self.quiet = quiet
        self.summary = summary
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.info: list[str] = []

    def file_deps(self) -> list[str]:
        """Glob patterns (relative to config_dir) for files this validator reads.

        Used by the caching layer to determine when a cached result is stale.
        Subclasses override this to declare their file dependencies.
        """
        return ["*.yaml", "*.yml"]

    def get_yaml_files(self) -> list[Path]:
        """Get all top-level YAML files in the config directory."""
        yaml_files: list[Path] = []
        for pattern in ["*.yaml", "*.yml"]:
            yaml_files.extend(self.config_dir.glob(pattern))
        return yaml_files

    def load_yaml(self, file_path: Path):
        """Load a YAML file with HA-aware loader and UTF-8 encoding."""
        with open(file_path, encoding="utf-8") as f:
            return yaml.load(f, Loader=HAYamlLoader)

    def load_yaml_checked(self, file_path: Path) -> tuple[Any, bool]:
        """Load YAML, recording any error to ``self.errors``.

        Returns:
            (data, ok). On failure, data is None, ok is False, and an error
            message has been appended to self.errors. On success ok is True;
            data may be None for an empty document.
        """
        try:
            with open(file_path, encoding="utf-8") as f:
                return yaml.load(f, Loader=HAYamlLoader), True
        except yaml.YAMLError as e:
            self.errors.append(f"{file_path}: YAML syntax error - {e}")
        except UnicodeDecodeError as e:
            self.errors.append(f"{file_path}: Encoding error - {e}")
        except OSError as e:
            self.errors.append(f"{file_path}: Could not read file - {e}")
        return None, False

    def check_automations_structure(self, automations: list, source: str) -> bool:
        """Validate parsed automations list structure.

        Args:
            automations: Parsed list of automation dictionaries.
            source: Label for error messages (e.g. file path).

        Returns:
            True if all automations are structurally valid.
        """
        all_valid = True
        for i, automation in enumerate(automations):
            if not isinstance(automation, dict):
                self.errors.append(f"{source}: Automation {i} must be a dictionary")
                all_valid = False
                continue

            # Blueprint automations use 'use_blueprint' instead of
            # direct triggers/actions
            if "use_blueprint" not in automation:
                if "trigger" not in automation and "triggers" not in automation:
                    self.errors.append(
                        f"{source}: Automation {i} missing 'trigger' or 'triggers'"
                    )
                    all_valid = False
                if "action" not in automation and "actions" not in automation:
                    self.errors.append(
                        f"{source}: Automation {i} missing 'action' or 'actions'"
                    )
                    all_valid = False

            # Check for alias (recommended)
            if "alias" not in automation:
                self.warnings.append(
                    f"{source}: Automation {i} missing 'alias' (recommended)"
                )

        return all_valid

    def check_scripts_structure(self, scripts: dict, source: str) -> bool:
        """Validate parsed scripts dict structure.

        Args:
            scripts: Parsed dict mapping script names to configs.
            source: Label for error messages (e.g. file path).

        Returns:
            True if all scripts are structurally valid.
        """
        all_valid = True
        for script_name, script_config in scripts.items():
            if not isinstance(script_config, dict):
                self.errors.append(
                    f"{source}: Script '{script_name}' must be a dictionary"
                )
                all_valid = False
                continue

            # Blueprint scripts use 'use_blueprint' instead of direct sequence
            if "use_blueprint" not in script_config and "sequence" not in script_config:
                self.errors.append(
                    f"{source}: Script '{script_name}' missing required "
                    f"'sequence' or 'use_blueprint'"
                )
                all_valid = False

        return all_valid

    def print_results(self):
        """Print validation results."""
        if self.quiet:
            return

        if self.info:
            print("INFO:", file=sys.stderr)
            for info in self.info:
                print(f"  ℹ️  {info}", file=sys.stderr)
            print(file=sys.stderr)

        if self.errors:
            print("ERRORS:", file=sys.stderr)
            for error in self.errors:
                print(f"  ❌ {error}", file=sys.stderr)
            print(file=sys.stderr)

        if self.warnings:
            print("WARNINGS:", file=sys.stderr)
            for warning in self.warnings:
                print(f"  ⚠️  {warning}", file=sys.stderr)
            print(file=sys.stderr)

        if not self.errors and not self.warnings:
            print(f"✅ {self.validator_name} is valid!")
        elif not self.errors:
            print(f"✅ {self.validator_name} is valid (with warnings)")
        else:
            print(f"❌ {self.validator_name} validation failed", file=sys.stderr)
