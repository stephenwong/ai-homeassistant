#!/usr/bin/env python3
"""Home Assistant configuration validator using HA's built-in validation.

This script performs deep validation using Home Assistant's own
configuration checking.
"""

import argparse
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml

from tools.common import ValidatorBase, get_env_int


class HAConfigValidator(ValidatorBase):
    """Validates Home Assistant configuration using HA's check_config tool."""

    validator_name = "Home Assistant configuration"

    def __init__(self, config_dir: str = "config"):
        """Initialize validator and timeout configuration."""
        super().__init__(config_dir)
        self.install_check_timeout = self._get_timeout("HA_REQUEST_TIMEOUT", 10)
        self.validation_timeout = self._get_timeout("HA_VALIDATION_TIMEOUT", 60)

    def _get_timeout(self, env_name: str, default: int) -> int:
        """Read timeout env vars with validation."""
        timeout, warning = get_env_int(env_name, default)
        if warning:
            self.warnings.append(warning)
        return timeout

    def check_ha_installation(self) -> bool:
        """Check if Home Assistant is available for configuration checking."""
        try:
            # Try to run hass --version
            result = subprocess.run(
                ["hass", "--version"],
                capture_output=True,
                text=True,
                timeout=self.install_check_timeout,
            )
            if result.returncode == 0:
                self.info.append(f"Using Home Assistant: {result.stdout.strip()}")
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Try python -m homeassistant --version
        try:
            result = subprocess.run(
                ["python", "-m", "homeassistant", "--version"],
                capture_output=True,
                text=True,
                timeout=self.install_check_timeout,
            )
            if result.returncode == 0:
                self.info.append(f"Using Home Assistant: {result.stdout.strip()}")
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        self.warnings.append(
            "Home Assistant not found in PATH. Will perform basic validation only."
        )
        return False

    def run_ha_check_config(self) -> bool:
        """Run Home Assistant's check_config script."""
        if not self.check_ha_installation():
            return self.run_basic_validation()

        try:
            # First try the hass command
            cmd = [
                "hass",
                "--config",
                str(self.config_dir),
                "--script",
                "check_config",
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.validation_timeout,
            )

            if result.returncode != 0 and "No module named" in result.stderr:
                # Try alternative command
                cmd = [
                    "python",
                    "-m",
                    "homeassistant",
                    "--config",
                    str(self.config_dir),
                    "--script",
                    "check_config",
                ]
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.validation_timeout,
                )

            # Parse output
            if result.stdout:
                self.parse_check_config_output(result.stdout)

            if result.stderr:
                self.parse_check_config_errors(result.stderr)

            return result.returncode == 0

        except subprocess.TimeoutExpired:
            self.errors.append(
                "Home Assistant configuration check timed out "
                f"after {self.validation_timeout} seconds"
            )
            return False
        except Exception as e:
            self.errors.append(f"Failed to run HA config check: {e}")
            return self.run_basic_validation()

    def parse_check_config_output(self, output: str):
        """Parse Home Assistant check_config output."""
        lines = output.split("\n")

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Look for common patterns
            lower = line.lower()
            if line.startswith("ERROR"):
                self.errors.append(f"HA Check: {line}")
            elif line.startswith("WARNING"):
                self.warnings.append(f"HA Check: {line}")
            elif "successful" in lower:
                self.info.append(f"HA Check: {line}")
            elif re.search(r"\berror\b", lower):
                self.errors.append(f"HA Check: {line}")
            elif re.search(r"\bwarning\b", lower):
                self.warnings.append(f"HA Check: {line}")

    def parse_check_config_errors(self, stderr: str):
        """Parse Home Assistant check_config error output."""
        lines = stderr.split("\n")

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Filter out common non-error messages
            if any(x in line.lower() for x in ["debug", "info", "starting"]):
                continue

            self.errors.append(f"HA Error: {line}")

    def run_basic_validation(self) -> bool:
        """Run basic configuration validation without HA."""
        all_valid = True

        # Check basic file structure
        config_file = self.config_dir / "configuration.yaml"
        if not config_file.exists():
            self.errors.append("configuration.yaml not found")
            return False

        # Validate configuration.yaml syntax and basic structure
        try:
            config = self.load_yaml(config_file)

            if not isinstance(config, dict):
                self.errors.append("configuration.yaml must contain a dictionary")
                all_valid = False
            else:
                # Check for required sections
                if "homeassistant" not in config:
                    self.warnings.append(
                        "Missing 'homeassistant' section in configuration.yaml"
                    )

                # Check for common mistakes
                self.validate_basic_config_structure(config)

        except yaml.YAMLError as e:
            self.errors.append(f"YAML syntax error in configuration.yaml: {e}")
            all_valid = False
        except Exception as e:
            self.errors.append(f"Error reading configuration.yaml: {e}")
            all_valid = False

        # Validate other common files
        self.validate_automations_file()
        self.validate_scripts_file()
        self.validate_secrets_file()

        return all_valid

    def validate_basic_config_structure(self, config: dict[str, Any]):
        """Validate basic configuration structure."""
        # Check homeassistant section
        if "homeassistant" in config:
            ha_config = config["homeassistant"]
            if isinstance(ha_config, dict):
                # Check for required fields
                if "latitude" not in ha_config or "longitude" not in ha_config:
                    self.warnings.append(
                        "Missing latitude/longitude in homeassistant section"
                    )

                if "time_zone" not in ha_config:
                    self.warnings.append("Missing time_zone in homeassistant section")

        # Check for deprecated keys
        deprecated_keys = ["discovery", "introduction", "cloud"]
        for key in deprecated_keys:
            if key in config:
                if key == "cloud":
                    self.warnings.append(f"'{key}' configuration should be done via UI")
                else:
                    self.warnings.append(f"'{key}' is deprecated and can be removed")

        # Check for common integration configurations
        self.check_integration_configs(config)

    def check_integration_configs(self, config: dict[str, Any]):
        """Check common integration configurations."""
        # Check logger configuration
        if "logger" in config:
            logger_config = config["logger"]
            if isinstance(logger_config, dict) and (
                "logs" in logger_config and not isinstance(logger_config["logs"], dict)
            ):
                self.errors.append("logger.logs must be a dictionary")

        # Check recorder configuration
        if "recorder" in config:
            recorder_config = config["recorder"]
            if isinstance(recorder_config, dict) and "db_url" in recorder_config:
                db_url = recorder_config["db_url"]
                if not isinstance(db_url, str) or not db_url.startswith(
                    ("sqlite:///", "mysql://", "postgresql://")
                ):
                    self.warnings.append("recorder.db_url format may be invalid")

        # Check HTTP configuration
        if "http" in config:
            http_config = config["http"]
            if isinstance(http_config, dict) and (
                "ssl_certificate" in http_config or "ssl_key" in http_config
            ):
                ssl_cert = http_config.get("ssl_certificate")
                ssl_key = http_config.get("ssl_key")
                if ssl_cert and not Path(ssl_cert).exists():
                    self.errors.append(f"SSL certificate file not found: {ssl_cert}")
                if ssl_key and not Path(ssl_key).exists():
                    self.errors.append(f"SSL key file not found: {ssl_key}")

    def validate_automations_file(self):
        """Validate automations.yaml file."""
        automations_file = self.config_dir / "automations.yaml"
        if not automations_file.exists():
            return

        try:
            automations = self.load_yaml(automations_file)

            if automations is not None and not isinstance(automations, list):
                self.errors.append("automations.yaml must contain a list")
            elif isinstance(automations, list):
                self.check_automations_structure(automations, "automations.yaml")

        except yaml.YAMLError as e:
            self.errors.append(f"YAML syntax error in automations.yaml: {e}")
        except Exception as e:
            self.errors.append(f"Error reading automations.yaml: {e}")

    def validate_scripts_file(self):
        """Validate scripts.yaml file."""
        scripts_file = self.config_dir / "scripts.yaml"
        if not scripts_file.exists():
            return

        try:
            scripts = self.load_yaml(scripts_file)

            if scripts is not None and not isinstance(scripts, dict):
                self.errors.append("scripts.yaml must contain a dictionary")
            elif isinstance(scripts, dict):
                self.check_scripts_structure(scripts, "scripts.yaml")

        except yaml.YAMLError as e:
            self.errors.append(f"YAML syntax error in scripts.yaml: {e}")
        except Exception as e:
            self.errors.append(f"Error reading scripts.yaml: {e}")

    def validate_secrets_file(self):
        """Validate secrets.yaml file exists and is accessible."""
        secrets_file = self.config_dir / "secrets.yaml"
        if not secrets_file.exists():
            self.warnings.append("secrets.yaml not found (this is optional)")
            return

        try:
            secrets = self.load_yaml(secrets_file)

            if secrets is not None and not isinstance(secrets, dict):
                self.errors.append("secrets.yaml must contain a dictionary")

            # We don't validate secret values for security reasons

        except yaml.YAMLError as e:
            self.errors.append(f"YAML syntax error in secrets.yaml: {e}")
        except Exception as e:
            self.errors.append(f"Error reading secrets.yaml: {e}")

    def validate_all(self) -> bool:
        """Run all validation checks."""
        if not self.config_dir.exists():
            self.errors.append(f"Config directory {self.config_dir} does not exist")
            return False

        # Try HA's built-in validation first
        return self.run_ha_check_config()


def main():
    """Run main function for command line usage."""
    parser = argparse.ArgumentParser(
        description="Validate Home Assistant configuration using HA's built-in checks."
    )
    parser.add_argument(
        "config_dir",
        nargs="?",
        default="config",
        help="Path to the config directory (default: config)",
    )
    args = parser.parse_args()

    validator = HAConfigValidator(args.config_dir)
    is_valid = validator.validate_all()
    validator.print_results()

    raise SystemExit(0 if is_valid else 1)


if __name__ == "__main__":
    main()
