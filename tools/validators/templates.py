#!/usr/bin/env python3
"""Jinja2 template linter for Home Assistant configuration files.

Renders every template string against HA's ``/api/template`` endpoint and
surfaces failures. Degrades to a brace-balance check when the HA API is
unreachable.
"""

from __future__ import annotations

import argparse
import re
from typing import Any

from tools.common import HARequestError, ValidatorBase
from tools.ha.client import HAClient

_TEMPLATE_RE = re.compile(r"\{\{.*?\}\}|\{%.*?%\}", re.DOTALL)
_RUNTIME_NAMES = frozenset(
    {
        "trigger",
        "this",
        "wait",
        "wait_for_trigger",
        "repeat",
        "condition_result",
        "loop_var",
        "index",
        "index0",
    }
)
_SYNTAX_SIGNATURES = (
    "syntax error",
    "expected token",
    "unexpected",
    "no filter named",
    "encountered unknown tag",
    "unrecognized",
)


class TemplateValidator(ValidatorBase):
    """Lints Jinja2 templates by rendering them against the live HA API."""

    validator_name = "Jinja2 templates"

    def file_deps(self) -> list[str]:
        return []

    @staticmethod
    def _is_template(s: str) -> bool:
        return bool(isinstance(s, str) and _TEMPLATE_RE.search(s))

    @staticmethod
    def _balanced(s: str) -> bool:
        return s.count("{{") == s.count("}}") and s.count("{%") == s.count("%}")

    @classmethod
    def _collect(cls, data: Any, path: str, out: list[tuple[str, str]]) -> None:
        if isinstance(data, dict):
            for k, v in data.items():
                cls._collect(v, f"{path}.{k}" if path else str(k), out)
        elif isinstance(data, list):
            for i, item in enumerate(data):
                cls._collect(item, f"{path}[{i}]", out)
        elif cls._is_template(data):
            out.append((path, data))

    @staticmethod
    def _render(client: HAClient, template: str) -> tuple[str, str]:
        try:
            resp = client.post("/api/template", json={"template": template})
        except HARequestError as e:
            return ("network", str(e))
        if resp.status_code == 200:
            return ("ok", resp.text)
        try:
            msg = resp.json().get("message", resp.text)
        except ValueError:
            msg = resp.text
        return ("error", msg)

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
                self._collect(data, fp.name, found)

        if not found:
            return all_ok

        try:
            client = HAClient.from_env()
        except HARequestError as e:
            self.info.append(f"Live template check skipped: {e}")
            client = None

        for path, tmpl in sorted(set(found)):
            if client is None:
                if not self._balanced(tmpl):
                    self.errors.append(
                        f"{path}: Unbalanced template braces (live check skipped)"
                    )
                    all_ok = False
                continue

            status, detail = self._render(client, tmpl)
            if status == "ok":
                continue
            if status == "network":
                self.warnings.append(
                    f"{path}: Template render failed (network): {detail}"
                )
                continue

            low = detail.lower()
            if any(sig in low for sig in _SYNTAX_SIGNATURES):
                self.errors.append(f"{path}: Template syntax error: {detail}")
                all_ok = False
            elif any(f"'{n}' is undefined" in low for n in _RUNTIME_NAMES):
                self.warnings.append(
                    f"{path}: Uses runtime context ({detail.splitlines()[0]})"
                )
            else:
                self.warnings.append(
                    f"{path}: Template render warning: {detail.splitlines()[0]}"
                )

        return all_ok


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Lint Jinja2 templates in HA config via the render API."
    )
    parser.add_argument(
        "config_dir",
        nargs="?",
        default="config",
        help="Path to the config directory (default: config)",
    )
    args = parser.parse_args()
    v = TemplateValidator(args.config_dir)
    is_valid = v.validate_all()
    v.print_results()
    raise SystemExit(0 if is_valid else 1)


if __name__ == "__main__":
    main()
