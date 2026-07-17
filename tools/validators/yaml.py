#!/usr/bin/env python3
"""YAML syntax validator for Home Assistant configuration files."""

import argparse
from pathlib import Path
from typing import Any

from tools.validators.base import ValidatorBase


class YAMLValidator(ValidatorBase):
    """Validates YAML syntax and basic structure for Home Assistant files."""

    validator_name = "YAML syntax"

    def validate_yaml_syntax(self, file_path: Path) -> bool:
        """Validate YAML syntax of a single file."""
        _, ok = self.load_yaml_checked(file_path)
        return ok

    def validate_file_encoding(self, file_path: Path) -> bool:
        """Ensure file is UTF-8 encoded as required by Home Assistant."""
        try:
            with open(file_path, encoding="utf-8") as f:
                f.read()
            return True
        except UnicodeDecodeError:
            self.errors.append(f"{file_path}: File must be UTF-8 encoded")
            return False

    def validate_configuration_structure(self, file_path: Path, data: Any) -> bool:
        """Validate basic Home Assistant configuration.yaml structure."""
        if file_path.name != "configuration.yaml":
            return True

        if not isinstance(data, dict):
            self.errors.append(f"{file_path}: Configuration must be a dictionary")
            return False

        # Check for common configuration issues
        if "homeassistant" not in data:
            self.warnings.append(f"{file_path}: Missing 'homeassistant' section")
        elif not isinstance(data.get("homeassistant"), dict):
            self.warnings.append(
                f"{file_path}: 'homeassistant' section should be a dictionary"
            )

        # Check for deprecated keys
        deprecated_keys = ["discovery", "introduction"]
        for key in deprecated_keys:
            if key in data:
                self.warnings.append(f"{file_path}: '{key}' is deprecated")

        return True

    def validate_automations_structure(self, file_path: Path, data: Any) -> bool:
        """Validate automations.yaml structure."""
        if file_path.name != "automations.yaml":
            return True

        if data is None:
            return True  # Empty file is valid

        if not isinstance(data, list):
            self.errors.append(f"{file_path}: Automations must be a list")
            return False

        return self.check_automations_structure(data, str(file_path))

    def validate_scripts_structure(self, file_path: Path, data: Any) -> bool:
        """Validate scripts.yaml structure."""
        if file_path.name != "scripts.yaml":
            return True

        if data is None:
            return True  # Empty file is valid

        if not isinstance(data, dict):
            self.errors.append(f"{file_path}: Scripts must be a dictionary")
            return False

        return self.check_scripts_structure(data, str(file_path))

    def _validate(self) -> bool:
        """Validate all YAML files in the config directory."""
        yaml_files = self.get_yaml_files()
        if not yaml_files:
            self.warnings.append("No YAML files found in config directory")
            return True

        all_valid = True

        for file_path in yaml_files:
            # Skip secrets.yaml as it may contain sensitive data
            if file_path.name == "secrets.yaml":
                continue

            # Parse once; catches encoding errors and YAML syntax errors
            data, ok = self.load_yaml_checked(file_path)
            if not ok:
                all_valid = False
                continue

            # Structure validation for specific files (data already parsed)
            all_valid &= self.validate_configuration_structure(file_path, data)
            all_valid &= self.validate_automations_structure(file_path, data)
            all_valid &= self.validate_scripts_structure(file_path, data)

        return all_valid


def main() -> int:
    """Run YAML syntax validation from command line."""
    parser = argparse.ArgumentParser(
        description="Validate YAML syntax for Home Assistant configuration files."
    )
    parser.add_argument(
        "config_dir",
        nargs="?",
        default="config",
        help="Path to the config directory (default: config)",
    )
    args = parser.parse_args()

    validator = YAMLValidator(args.config_dir)
    is_valid = validator.validate_all()
    validator.print_results()

    return 0 if is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
