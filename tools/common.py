#!/usr/bin/env python3
"""Shared utilities for Home Assistant configuration tools."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

import yaml


class HAYamlLoader(yaml.SafeLoader):
    """Custom YAML loader that handles Home Assistant specific tags."""

    pass


def include_constructor(loader, node):
    """Handle !include tag."""
    filename = loader.construct_scalar(node)
    return f"!include {filename}"


def include_dir_named_constructor(loader, node):
    """Handle !include_dir_named tag."""
    dirname = loader.construct_scalar(node)
    return f"!include_dir_named {dirname}"


def include_dir_merge_named_constructor(loader, node):
    """Handle !include_dir_merge_named tag."""
    dirname = loader.construct_scalar(node)
    return f"!include_dir_merge_named {dirname}"


def include_dir_merge_list_constructor(loader, node):
    """Handle !include_dir_merge_list tag."""
    dirname = loader.construct_scalar(node)
    return f"!include_dir_merge_list {dirname}"


def include_dir_list_constructor(loader, node):
    """Handle !include_dir_list tag."""
    dirname = loader.construct_scalar(node)
    return f"!include_dir_list {dirname}"


def input_constructor(loader, node):
    """Handle !input tag for blueprints."""
    input_name = loader.construct_scalar(node)
    return f"!input {input_name}"


def secret_constructor(loader, node):
    """Handle !secret tag."""
    secret_name = loader.construct_scalar(node)
    return f"!secret {secret_name}"


# Register custom constructors
HAYamlLoader.add_constructor("!include", include_constructor)
HAYamlLoader.add_constructor("!include_dir_named", include_dir_named_constructor)
HAYamlLoader.add_constructor(
    "!include_dir_merge_named", include_dir_merge_named_constructor
)
HAYamlLoader.add_constructor(
    "!include_dir_merge_list", include_dir_merge_list_constructor
)
HAYamlLoader.add_constructor("!include_dir_list", include_dir_list_constructor)
HAYamlLoader.add_constructor("!input", input_constructor)
HAYamlLoader.add_constructor("!secret", secret_constructor)

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


class HARequestError(Exception):
    """Raised when a Home Assistant REST API request fails."""


class ValidatorBase:
    """Base class for Home Assistant configuration validators."""

    validator_name = "Configuration"

    def __init__(self, config_dir: str = "config", quiet: bool = False):
        """Initialize the validator with config directory."""
        self.config_dir = Path(config_dir).resolve()
        self.quiet = quiet
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
            print("INFO:")
            for info in self.info:
                print(f"  \u2139\ufe0f  {info}")
            print()

        if self.errors:
            print("ERRORS:")
            for error in self.errors:
                print(f"  \u274c {error}")
            print()

        if self.warnings:
            print("WARNINGS:")
            for warning in self.warnings:
                print(f"  \u26a0\ufe0f  {warning}")
            print()

        if not self.errors and not self.warnings:
            print(f"\u2705 {self.validator_name} is valid!")
        elif not self.errors:
            print(f"\u2705 {self.validator_name} is valid (with warnings)")
        else:
            print(f"\u274c {self.validator_name} validation failed")
