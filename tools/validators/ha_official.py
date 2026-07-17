#!/usr/bin/env python3
"""Official Home Assistant configuration validator using the actual HA package.

This leverages Home Assistant's own validation tools for the most
accurate results.
"""

import argparse
import re
import subprocess
import sys

from tools.common import get_env_int
from tools.validators.base import ValidatorBase


class HAOfficialValidator(ValidatorBase):
    """Validates Home Assistant configuration using the official HA package.

    This validator depends on the installed HA version and Python packages,
    not just config files. It declares no file dependencies so the caching
    layer never caches it.
    """

    validator_name = "Home Assistant configuration"

    def __init__(
        self, config_dir: str = "config", quiet: bool = False, summary: bool = False
    ):
        """Initialize validator and timeout configuration."""
        super().__init__(config_dir, quiet=quiet, summary=summary)
        self.validation_timeout = self._get_timeout("HA_VALIDATION_TIMEOUT", 120)

    def file_deps(self) -> list[str]:
        """Return an empty list — result depends on HA environment, not files."""
        return []

    def _get_timeout(self, env_name: str, default: int) -> int:
        """Read timeout env vars with validation."""
        timeout, warning = get_env_int(env_name, default)
        if warning:
            self.warnings.append(warning)
        return timeout

    def run_ha_check_config(self) -> bool:
        """Run Home Assistant's official check_config script."""
        try:
            # Use the hass command to check configuration
            cmd = [
                sys.executable,
                "-m",
                "homeassistant",
                "--config",
                str(self.config_dir),
                "--script",
                "check_config",
            ]

            # Run the command
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.validation_timeout,
            )

            # Parse the output
            self.parse_check_config_output(result.stdout, result.stderr)

            # Return success if exit code is 0. HA's "Successful config (partial)"
            # exits 0; on exit 0 demote any parsed errors to warnings so they stay
            # visible without failing CI (per AGENTS.md "exit 0 partial = pass").
            passed = result.returncode == 0
            if passed and self.errors:
                self.warnings.extend(self.errors)
                self.errors.clear()
            return passed

        except subprocess.TimeoutExpired:
            self.errors.append(
                "Home Assistant configuration check timed out "
                f"after {self.validation_timeout} seconds"
            )
            return False
        except FileNotFoundError:
            self.errors.append(
                "Home Assistant not found. "
                "Please install with: pip install homeassistant"
            )
            return False
        except (subprocess.SubprocessError, OSError) as e:
            self.errors.append(f"Failed to run Home Assistant config check: {e}")
            return False

    _BENIGN_PACKAGE_MARKERS = (
        "unable to install package",
        "no solution found when resolving",
        "requirements are unsatisfiable",
        "requirements for",
    )

    def _has_benign_package_context(self, stdout: str, stderr: str) -> bool:
        blob = (stdout + "\n" + stderr).lower()
        return any(m in blob for m in self._BENIGN_PACKAGE_MARKERS)

    def is_ignorable_message(self, line: str) -> bool:
        """Check if a message can be safely ignored (non-critical warnings).

        RuntimeError/^^^ suppression is handled contextually in
        parse_check_config_output (M12) — not here.
        """
        ignorable_patterns = [
            # TurboJPEG library warnings — not needed for config validation
            "turbojpeg",
            "libturbojpeg",
            "Camera snapshot performance will be sub-optimal",
            "Unable to locate turbojpeg library",
            "TurboJPEGSingleton",
            # Blueprint selector warnings for newer HA features
            "selector']['reorder']",
            # Python traceback header — not an error by itself
            "Traceback (most recent call last):",
            # Package installation failures in local validation environment.
            # Not config errors — integration packages are installed at runtime
            # on the real HA server.
            "Unable to install package",
            "No solution found when resolving",
            "requirements are unsatisfiable",
            "Requirements for",
            "could not be loaded",
        ]
        line_lower = line.lower()
        return any(pattern.lower() in line_lower for pattern in ignorable_patterns)

    def is_ignorable_traceback_line(
        self, line: str, *, benign_ctx: bool = False
    ) -> bool:
        """Check if line is part of a Python traceback we can ignore.

        Only suppresses ``File ... .py`` lines when *benign_ctx* is set
        (i.e. the surrounding output contains a known-benign package-install
        marker). Without that context, traceback lines are real errors.

        ``benign_ctx`` defaults to ``False`` so existing callers that invoke
        ``is_ignorable_traceback_line(line)`` without the keyword continue to
        get the strict (non-suppressing) behaviour.
        """
        return benign_ctx and line.strip().startswith("File ") and ".py" in line

    def parse_check_config_output(self, stdout: str, stderr: str):
        """Parse Home Assistant check_config output."""
        benign_ctx = self._has_benign_package_context(stdout, stderr)

        # Parse stdout
        if stdout:
            for line in stdout.split("\n"):
                line = line.strip()
                if not line:
                    continue

                # Skip ignorable messages (turbojpeg, Traceback header, etc.)
                if self.is_ignorable_message(line):
                    continue

                # M12: scope RuntimeError/^^^ suppression to benign context.
                if benign_ctx:
                    if "runtimeerror:" in line.lower() or line.strip() == "^^^":
                        continue
                    if self.is_ignorable_traceback_line(line, benign_ctx=True):
                        continue

                # Look for specific patterns
                if (
                    "Testing configuration at" in line
                    or "Configuration check successful!" in line
                ):
                    self.info.append(f"HA Check: {line}")
                elif m := re.search(r"(\d+)\s+errors?\s+found", line, re.I):
                    if m.group(1) == "0":
                        self.info.append(f"HA Check: {line}")
                    else:
                        self.errors.append(f"HA Check: {line}")
                elif re.match(r"^\W*(ERROR|Error|RuntimeError)\b", line):
                    self.errors.append(f"HA Check: {line}")
                elif re.match(r"^\W*(WARNING|Warning)\b", line):
                    self.warnings.append(f"HA Check: {line}")
                else:
                    # Include other informational lines
                    if line and not line.startswith("INFO:"):
                        self.info.append(f"HA Check: {line}")

        # Parse stderr for actual errors
        if stderr:
            # M11: severity indicators that mark a line as a real error regardless
            # of any benign substring it also contains.
            error_indicators = ("error", "fail", "fatal", "exception", "traceback")
            benign_any = ["debug", "info:", "starting"]
            benign_phrases = [
                "voluptuous",
                "setup of domain",
                "setup of platform",
                "loading",
                "initialized",
            ]

            for line in stderr.split("\n"):
                line = line.strip()
                if not line:
                    continue
                line_lower = line.lower()

                # Real-error lines survive even if they also mention a benign word.
                if any(ind in line_lower for ind in error_indicators):
                    self.errors.append(f"HA Error: {line}")
                    continue

                # Pure debug/info noise — suppress.
                if any(x in line_lower for x in benign_any):
                    continue
                if any(x in line_lower for x in benign_phrases):
                    continue

                # Anything else is treated as an error (unchanged behaviour).
                self.errors.append(f"HA Error: {line}")

    def _validate(self) -> bool:
        """Run complete validation using Home Assistant."""
        # Check if configuration.yaml exists
        config_file = self.config_dir / "configuration.yaml"
        if not config_file.exists():
            self.errors.append("configuration.yaml not found")
            return False

        # Run the official Home Assistant validation
        return self.run_ha_check_config()


def main() -> int:
    """Run Home Assistant configuration validation from command line."""
    parser = argparse.ArgumentParser(
        description=(
            "Validate Home Assistant configuration using the official HA package."
        )
    )
    parser.add_argument(
        "config_dir",
        nargs="?",
        default="config",
        help="Path to the config directory (default: config)",
    )
    args = parser.parse_args()

    validator = HAOfficialValidator(args.config_dir)
    is_valid = validator.validate_all()
    validator.print_results()

    return 0 if is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
