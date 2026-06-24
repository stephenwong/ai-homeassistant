#!/usr/bin/env python3
"""Service reference validator for Home Assistant configuration files.

Validates that all ``service:``/``action:`` targets in automations and scripts
correspond to loaded services on the Home Assistant instance. Degrades to a
format-only check when the HA API is unreachable.
"""

from __future__ import annotations

import argparse
import re
from typing import Any

from tools.common import HARequestError, ValidatorBase
from tools.ha.client import HAClient

_SERVICE_RE = re.compile(r"^[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*$")
_STEP_SERVICE_KEYS = ("action", "service")


class ServiceValidator(ValidatorBase):
    """Validates service references in automation/script steps."""

    validator_name = "Service references"

    def file_deps(self) -> list[str]:
        return []

    @staticmethod
    def _looks_dynamic(value: str) -> bool:
        return (
            value.startswith("!")
            or ("{{" in value and "}}" in value)
            or ("{%" in value and "%}" in value)
        )

    @classmethod
    def _extract_services(
        cls, data: Any, path: str, out: list[tuple[str, str]]
    ) -> None:
        if isinstance(data, dict):
            for k, v in data.items():
                p = f"{path}.{k}" if path else str(k)
                if k in _STEP_SERVICE_KEYS and isinstance(v, str):
                    if not cls._looks_dynamic(v):
                        out.append((v, p))
                else:
                    cls._extract_services(v, p, out)
        elif isinstance(data, list):
            for i, item in enumerate(data):
                cls._extract_services(item, f"{path}[{i}]", out)

    def _get_services(self) -> set[str] | None:
        try:
            client = HAClient.from_env()
        except HARequestError as e:
            self.info.append(f"Live service check skipped: {e}")
            return None
        try:
            catalog = client.get_json("/api/services")
        except HARequestError as e:
            self.info.append(f"Live service check skipped: {e}")
            return None
        if catalog is None:
            self.info.append(
                "Live service check skipped: null response from /api/services"
            )
            return None
        valid: set[str] = set()
        for entry in catalog:
            domain = entry.get("domain")
            for svc in entry.get("services") or {}:
                if domain and svc:
                    valid.add(f"{domain}.{svc}")
        return valid

    def validate_all(self) -> bool:
        if not self.config_dir.exists():
            self.errors.append(f"Config directory {self.config_dir} does not exist")
            return False

        found: list[tuple[str, str]] = []
        all_ok = True
        for fp in self.get_yaml_files():
            if fp.name == "secrets.yaml":
                continue
            data, ok = self.load_yaml_checked(fp)
            if not ok:
                all_ok = False
                continue
            if data is not None:
                self._extract_services(data, fp.name, found)

        if not found:
            return all_ok

        valid = self._get_services()

        for svc, path in sorted(set(found)):
            if "." not in svc:
                self.info.append(
                    f"{path}: Ignoring non-domain value '{svc}' (service reference?)"
                )
            elif not _SERVICE_RE.fullmatch(svc):
                self.errors.append(f"{path}: Malformed service '{svc}'")
                all_ok = False
            elif valid is not None and svc not in valid:
                self.warnings.append(
                    f"{path}: Unknown service '{svc}' (service not loaded?)"
                )

        return all_ok


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate service references in HA config."
    )
    parser.add_argument(
        "config_dir",
        nargs="?",
        default="config",
        help="Path to the config directory (default: config)",
    )
    args = parser.parse_args()
    v = ServiceValidator(args.config_dir)
    is_valid = v.validate_all()
    v.print_results()
    raise SystemExit(0 if is_valid else 1)


if __name__ == "__main__":
    main()
