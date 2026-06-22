"""Safe round-trip YAML editing using ruamel.yaml.

Preserves comments, formatting, and key ordering through load/dump cycles.
Works with both list-based (automations.yaml, scenes.yaml) and dict-based
(scripts.yaml) Home Assistant YAML files.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Callable
from pathlib import Path

from ruamel.yaml import YAML


class ValidationError(Exception):
    """Raised when a validation check fails during atomic save."""


class YAMLEditor:
    """Load and dump YAML files preserving formatting, comments, and ordering."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._yaml = YAML()
        self._yaml.preserve_quotes = True
        self._yaml.indent(mapping=2, sequence=4, offset=2)
        self._data: list | dict | None = None

    def load(self):
        """Load a YAML file, preserving structure.

        Returns:
            The parsed YAML data (list, dict, or None for empty).
            Raises FileNotFoundError if the path does not exist.
        """
        with open(self.path, encoding="utf-8") as f:
            self._data = self._yaml.load(f)
        return self._data

    def _ensure_loaded(self):
        """Lazy-load the file if not already loaded.

        If the file does not exist, ``self._data`` stays ``None``.
        """
        if self._data is None:
            with contextlib.suppress(FileNotFoundError):
                self.load()

    def save(self, validator: Callable[[Path], bool] | None = None) -> None:
        """Save in-memory state to the original file.

        If *validator* is provided, the data is first written to a temporary
        file and the validator is called on it.  On success the temp file is
        atomically renamed over the target; on failure a ``ValidationError``
        is raised and the original file is untouched.
        """
        if self._data is None:
            return

        if validator is not None:
            self._atomic_save(validator)
        else:
            self.dump(self._data, self.path)

    def _atomic_save(self, validator: Callable[[Path], bool]) -> None:
        """Write to a temp file, validate, then atomically rename."""
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            self.dump(self._data, tmp)
            if not validator(tmp):
                raise ValidationError("Atomic save aborted: validation failed")
            os.replace(tmp, self.path)
        finally:
            if tmp.exists():
                tmp.unlink()

    def dump(self, data, path: Path) -> None:
        """Write YAML data to a file path."""
        with open(path, "w", encoding="utf-8") as f:
            self._yaml.dump(data, f)

    def dump_to(self, data, stream) -> None:
        """Write YAML data to an open stream (e.g. sys.stdout)."""
        self._yaml.dump(data, stream)

    # ------------------------------------------------------------------
    # Automation list helpers (automations.yaml and scenes.yaml)
    # ------------------------------------------------------------------

    def _require_list(self, operation: str) -> None:
        """Raise TypeError if data is not a list (e.g. scripts.yaml)."""
        self._ensure_loaded()
        if not isinstance(self._data, list):
            raise TypeError(
                f"Cannot {operation} on {self.path.name}: "
                f"expected a list, got {type(self._data).__name__}"
            )

    def _require_dict(self, operation: str) -> None:
        """Raise TypeError if data is not a dict."""
        self._ensure_loaded()
        if not isinstance(self._data, dict):
            raise TypeError(
                f"Cannot {operation} on {self.path.name}: "
                f"expected a dict, got {type(self._data).__name__}"
            )

    def find_automation(self, alias: str) -> int | None:
        """Return the index of an automation by alias, or None if not found."""
        self._ensure_loaded()
        if not isinstance(self._data, list):
            return None
        for i, item in enumerate(self._data):
            if isinstance(item, dict) and item.get("alias") == alias:
                return i
        return None

    def find_script(self, key: str) -> bool:
        """Return True if a script key exists in a dict-based file."""
        self._ensure_loaded()
        if not isinstance(self._data, dict):
            return False
        return key in self._data

    def add_automation(self, automation: dict) -> None:
        """Append an automation dict to the list. Does NOT save.

        Raises TypeError if the loaded data is not a list.
        """
        self._ensure_loaded()
        if self._data is None:
            self._data = []
        self._require_list("add automation")
        self._data.append(automation)

    def add_script(self, key: str, script: dict) -> None:
        """Add a script entry to a dict-based file. Does NOT save.

        Raises TypeError if the loaded data is not a dict.
        Raises ValueError if the key already exists.
        """
        self._ensure_loaded()
        if self._data is None:
            self._data = {}
        self._require_dict("add script")
        if key in self._data:
            raise ValueError(f"Script '{key}' already exists")
        self._data[key] = script

    def update_automation(self, alias: str, updates: dict) -> None:
        """Merge updates into an automation found by alias. Does NOT save.

        Raises TypeError if data is not a list.
        Raises ValueError if the alias is not found.
        """
        self._require_list("update automation")
        idx = self.find_automation(alias)
        if idx is None:
            raise ValueError(f"Automation with alias '{alias}' not found")
        target = self._data[idx]
        if isinstance(target, dict):
            target.update(updates)

    def update_script(self, key: str, updates: dict) -> None:
        """Merge updates into a script entry. Does NOT save.

        Raises TypeError if data is not a dict.
        Raises ValueError if the key is not found.
        """
        self._require_dict("update script")
        if key not in self._data:
            raise ValueError(f"Script '{key}' not found")
        target = self._data[key]
        if isinstance(target, dict):
            target.update(updates)

    def remove_automation(self, alias: str) -> None:
        """Remove an automation by alias. Does NOT save.

        Raises TypeError if data is not a list.
        Raises ValueError if the alias is not found.
        """
        self._require_list("remove automation")
        idx = self.find_automation(alias)
        if idx is None:
            raise ValueError(f"Automation with alias '{alias}' not found")
        self._data.pop(idx)

    def remove_script(self, key: str) -> None:
        """Remove a script entry. Does NOT save.

        Raises TypeError if data is not a dict.
        Raises ValueError if the key is not found.
        """
        self._require_dict("remove script")
        if key not in self._data:
            raise ValueError(f"Script '{key}' not found")
        del self._data[key]
