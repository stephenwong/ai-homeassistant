#!/usr/bin/env python3
"""Duplicate automation ID detector for Home Assistant configuration files.

Checks automations.yaml for duplicate ``id`` values (which silently break
triggering and UI customization) and missing ``id`` fields.
"""

from __future__ import annotations

import argparse
import collections

from tools.common import ValidatorBase


class DuplicateIDValidator(ValidatorBase):
    """Validates that no two automations share the same ``id``."""

    validator_name = "Duplicate automation IDs"

    def file_deps(self) -> list[str]:
        return ["automations.yaml"]

    def _check_automations(self, automations: list, source: str) -> bool:
        """Walk a parsed automations list; flag duplicates and missing IDs.

        Args:
            automations: Parsed list of automation dictionaries.
            source: Label for error messages (e.g. file path).

        Returns:
            True when there are no duplicate-ID errors. Missing IDs are
            warnings and do not change the return value.
        """
        all_valid = True
        seen: dict[str, int] = collections.Counter()
        missing = 0

        for i, automation in enumerate(automations):
            if not isinstance(automation, dict):
                self.errors.append(f"{source}: Automation {i} must be a dictionary")
                all_valid = False
                continue

            aid = automation.get("id")
            if aid is None:
                missing += 1
                alias = automation.get("alias", f"#{i}")
                self.warnings.append(f"{source}: Automation '{alias}' missing 'id'")
            else:
                seen[str(aid)] += 1

        for aid, count in seen.items():
            if count > 1:
                self.errors.append(
                    f"{source}: Duplicate automation id '{aid}' used {count} times"
                )
                all_valid = False

        if missing:
            self.info.append(f"{source}: {missing} automation(s) missing 'id'")

        return all_valid

    def validate_all(self) -> bool:
        """Run duplicate-ID detection on automations.yaml."""
        if not self.config_dir.exists():
            self.errors.append(f"Config directory {self.config_dir} does not exist")
            return False

        automations_file = self.config_dir / "automations.yaml"
        if not automations_file.exists():
            return True  # nothing to check

        data, ok = self.load_yaml_checked(automations_file)
        if not ok:
            return False

        if data is None:
            return True  # empty file

        if not isinstance(data, list):
            self.errors.append(
                f"{automations_file}: Automations must be a list, "
                f"got {type(data).__name__}"
            )
            return False

        return self._check_automations(data, str(automations_file))


def main() -> None:
    """Run duplicate automation ID validation from command line."""
    parser = argparse.ArgumentParser(
        description="Detect duplicate and missing automation IDs."
    )
    parser.add_argument(
        "config_dir",
        nargs="?",
        default="config",
        help="Path to the config directory (default: config)",
    )
    args = parser.parse_args()

    validator = DuplicateIDValidator(args.config_dir)
    is_valid = validator.validate_all()
    validator.print_results()
    raise SystemExit(0 if is_valid else 1)


if __name__ == "__main__":
    main()
