#!/usr/bin/env python3
"""YAML syntax validator for Home Assistant configuration files."""

import argparse
from pathlib import Path

import yaml

from tools.common import ValidatorBase


class YAMLValidator(ValidatorBase):
    """Validates YAML syntax and basic structure for Home Assistant files."""

    validator_name = "YAML syntax"

    def validate_yaml_syntax(self, file_path: Path) -> bool:
        """Validate YAML syntax of a single file."""
        try:
            self.load_yaml(file_path)
            return True
        except yaml.YAMLError as e:
            self.errors.append(f"{file_path}: YAML syntax error - {e}")
            return False
        except UnicodeDecodeError as e:
            self.errors.append(f"{file_path}: Encoding error - {e}")
            return False
        except Exception as e:
            self.errors.append(f"{file_path}: Unexpected error - {e}")
            return False

    def validate_file_encoding(self, file_path: Path) -> bool:
        """Ensure file is UTF-8 encoded as required by Home Assistant."""
        try:
            with open(file_path, encoding="utf-8") as f:
                f.read()
            return True
        except UnicodeDecodeError:
            self.errors.append(f"{file_path}: File must be UTF-8 encoded")
            return False

    def validate_configuration_structure(self, file_path: Path) -> bool:
        """Validate basic Home Assistant configuration.yaml structure."""
        if file_path.name != "configuration.yaml":
            return True

        try:
            config = self.load_yaml(file_path)

            if not isinstance(config, dict):
                self.errors.append(f"{file_path}: Configuration must be a dictionary")
                return False

            # Check for common configuration issues
            if "homeassistant" not in config:
                self.warnings.append(f"{file_path}: Missing 'homeassistant' section")
            elif not isinstance(config.get("homeassistant"), dict):
                self.warnings.append(
                    f"{file_path}: 'homeassistant' section should be a dictionary"
                )

            # Check for deprecated keys
            deprecated_keys = ["discovery", "introduction"]
            for key in deprecated_keys:
                if key in config:
                    self.warnings.append(f"{file_path}: '{key}' is deprecated")

            return True
        except Exception as e:
            self.errors.append(f"{file_path}: Failed to validate structure - {e}")
            return False

    def validate_automations_structure(self, file_path: Path) -> bool:
        """Validate automations.yaml structure."""
        if file_path.name != "automations.yaml":
            return True

        try:
            automations = self.load_yaml(file_path)

            if automations is None:
                return True  # Empty file is valid

            if not isinstance(automations, list):
                self.errors.append(f"{file_path}: Automations must be a list")
                return False

            return self.check_automations_structure(automations, str(file_path))
        except Exception as e:
            self.errors.append(
                f"{file_path}: Failed to validate automations structure - {e}"
            )
            return False

    def validate_scripts_structure(self, file_path: Path) -> bool:
        """Validate scripts.yaml structure."""
        if file_path.name != "scripts.yaml":
            return True

        try:
            scripts = self.load_yaml(file_path)

            if scripts is None:
                return True  # Empty file is valid

            if not isinstance(scripts, dict):
                self.errors.append(f"{file_path}: Scripts must be a dictionary")
                return False

            return self.check_scripts_structure(scripts, str(file_path))
        except Exception as e:
            self.errors.append(
                f"{file_path}: Failed to validate scripts structure - {e}"
            )
            return False

    def validate_all(self) -> bool:
        """Validate all YAML files in the config directory."""
        if not self.config_dir.exists():
            self.errors.append(f"Config directory {self.config_dir} does not exist")
            return False

        yaml_files = self.get_yaml_files()
        if not yaml_files:
            self.warnings.append("No YAML files found in config directory")
            return True

        all_valid = True

        for file_path in yaml_files:
            # Skip secrets.yaml as it may contain sensitive data
            if file_path.name == "secrets.yaml":
                continue

            if not self.validate_file_encoding(file_path):
                all_valid = False
                continue

            if not self.validate_yaml_syntax(file_path):
                all_valid = False
                continue

            # Structure validation for specific files
            self.validate_configuration_structure(file_path)
            self.validate_automations_structure(file_path)
            self.validate_scripts_structure(file_path)

        return all_valid


def main():
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

    raise SystemExit(0 if is_valid else 1)


if __name__ == "__main__":
    main()
