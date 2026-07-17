#!/usr/bin/env python3
"""Entity and device reference validator for Home Assistant configuration files.

Validates that all entity references in configuration files actually exist.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, TypedDict

from tools.common import resolve_summary
from tools.validators.base import ValidatorBase
from tools.validators.entity_definitions import EntityDefinitionExtractor

_TEMPLATE_PATTERNS = [
    re.compile(p)
    for p in [
        r"states\('([^']+)'\)",
        r'states\("([^"]+)"\)',
        r"states\.([a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*)",
        r"is_state\('([^']+)'",
        r'is_state\("([^"]+)"',
        r"state_attr\('([^']+)'",
        r'state_attr\("([^"]+)"',
    ]
]


class DomainSummary(TypedDict):
    """Type definition for domain summary dictionary."""

    count: int
    enabled: int
    disabled: int
    examples: list[str]


class ReferenceValidator(ValidatorBase):
    """Validates entity and device references in Home Assistant config."""

    validator_name = "Entity/device references"

    # Special keywords that are not entity IDs
    SPECIAL_KEYWORDS = {"all", "none"}

    def __init__(
        self, config_dir: str = "config", quiet: bool = False, summary: bool = False
    ):
        """Initialize the ReferenceValidator."""
        super().__init__(config_dir, quiet=quiet, summary=summary)
        self.storage_dir = self.config_dir / ".storage"

        # Cache for loaded registries
        self._entities: dict[str, Any] | None = None
        self._devices: dict[str, Any] | None = None
        self._areas: dict[str, Any] | None = None

        self._definitions = EntityDefinitionExtractor(
            self.config_dir, self.storage_dir, self.warnings, self.info
        )

    def file_deps(self) -> list[str]:
        return [
            "*.yaml",
            "*.yml",
            ".storage/core.entity_registry",
            ".storage/core.device_registry",
            ".storage/core.area_registry",
            ".storage/core.zone",
            ".storage/core.restore_state",
        ]

    def load_restore_state_entities(self) -> set[str]:
        """Load entity_ids from restore state storage (diagnostic only).

        Delegates to EntityDefinitionExtractor.
        """
        return self._definitions.load_restore_state_entities()

    def get_config_defined_entities(self) -> set[str]:
        """Extract entities defined in config files (not in entity registry).

        Delegates to EntityDefinitionExtractor.
        """
        return self._definitions.get_config_defined_entities()

    def _load_registry(
        self,
        filename: str,
        list_key: str,
        key_field: str,
        cache_attr: str,
        missing_bucket: str,
        label: str,
    ) -> dict[str, Any]:
        """Load and cache a HA registry JSON file.

        Args:
            filename: Relative path under storage_dir (e.g. 'core.entity_registry').
            list_key: Key in ``data.data[list_key]`` holding the items.
            key_field: Item field to use as the result-dict key.
            cache_attr: Instance attribute name for caching (e.g. '_entities').
            missing_bucket: 'errors' or 'warnings' — which bucket to use for
                missing/parse-failure messages.
            label: Human-readable label for error messages (e.g. 'Entity registry').
        """
        cached = getattr(self, cache_attr)
        if cached is not None:
            return cached
        registry_file = self.storage_dir / filename
        bucket = getattr(self, missing_bucket)

        if not registry_file.exists():
            bucket.append(f"{label} not found: {registry_file}")
            setattr(self, cache_attr, {})
            return {}

        try:
            with open(registry_file, encoding="utf-8") as f:
                data = json.load(f)
            result = {
                item[key_field]: item for item in data.get("data", {}).get(list_key, [])
            }
        except (
            OSError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
            AttributeError,
        ) as e:
            bucket.append(f"Failed to load {label.lower()}: {e}")
            setattr(self, cache_attr, {})
            return {}

        setattr(self, cache_attr, result)
        return result

    def load_entity_registry(self) -> dict[str, Any]:
        """Load and cache entity registry."""
        return self._load_registry(
            "core.entity_registry",
            "entities",
            "entity_id",
            "_entities",
            "errors",
            "Entity registry",
        )

    def load_device_registry(self) -> dict[str, Any]:
        """Load and cache device registry."""
        return self._load_registry(
            "core.device_registry",
            "devices",
            "id",
            "_devices",
            "errors",
            "Device registry",
        )

    def load_area_registry(self) -> dict[str, Any]:
        """Load and cache area registry."""
        return self._load_registry(
            "core.area_registry",
            "areas",
            "id",
            "_areas",
            "warnings",
            "Area registry",
        )

    def is_uuid_format(self, value: str) -> bool:
        """Check if a string matches UUID format (32 hex characters)."""
        # UUID format: 8-4-4-4-12 hex digits, but HA often stores without hyphens
        return bool(re.fullmatch(r"[a-f0-9]{32}", value))

    def is_template(self, value: str) -> bool:
        """Check if value is a Jinja2 template expression."""
        # Match template expressions like {{ ... }} or {% ... %}
        return bool(re.search(r"\{\{.*?\}\}|\{%.*?%\}", value))

    def should_skip_entity_validation(self, value: str) -> bool:
        """Check if entity reference should be skipped during validation."""
        return (
            value.startswith("!")  # HA tags like !input, !secret
            or self.is_uuid_format(value)  # UUID format (device-based)
            or self.is_template(value)  # Template expressions
            or value in self.SPECIAL_KEYWORDS  # Special keywords like "all", "none"
        )

    def extract_entity_references(self, data: Any) -> set[str]:
        """Extract entity references from configuration data."""
        entities = set()

        if isinstance(data, dict):
            for key, value in data.items():
                # Common entity reference keys
                if key in ["entity_id", "entity_ids", "entities"]:
                    if isinstance(value, str):
                        if not self.should_skip_entity_validation(value):
                            entities.add(value)
                    elif isinstance(value, list):
                        for entity in value:
                            if isinstance(
                                entity, str
                            ) and not self.should_skip_entity_validation(entity):
                                entities.add(entity)
                    elif isinstance(value, dict):
                        for entity_id in value:
                            if isinstance(
                                entity_id, str
                            ) and not self.should_skip_entity_validation(entity_id):
                                entities.add(entity_id)

                # Device/area IDs — handled by separate extractors
                elif key in ["device_id", "device_ids", "area_id", "area_ids"]:
                    pass

                # Service data might contain entity references
                elif key == "data" and isinstance(value, dict):
                    entities.update(self.extract_entity_references(value))

                # Templates might contain entity references
                elif isinstance(value, str) and any(
                    x in value for x in ["state_attr(", "states(", "is_state("]
                ):
                    entities.update(self.extract_entities_from_template(value))

                # Recursive search
                else:
                    entities.update(self.extract_entity_references(value))

        elif isinstance(data, list):
            for item in data:
                entities.update(self.extract_entity_references(item))

        return entities

    def extract_entities_from_template(self, template: str) -> set[str]:
        """Extract entity references from Jinja2 templates."""
        entities = set()

        for pattern in _TEMPLATE_PATTERNS:
            for match in pattern.findall(template):
                if "." in match and len(match.split(".")) == 2:
                    entities.add(match)

        return entities

    def _extract_id_references(self, data: Any, keys: set[str]) -> set[str]:
        """Extract references for any of *keys* (e.g. {'device_id', 'device_ids'})."""
        refs: set[str] = set()
        if isinstance(data, dict):
            for key, value in data.items():
                if key in keys:
                    if isinstance(value, str):
                        if not value.startswith("!") and not self.is_template(value):
                            refs.add(value)
                    elif isinstance(value, list):
                        for item in value:
                            if (
                                isinstance(item, str)
                                and not item.startswith("!")
                                and not self.is_template(item)
                            ):
                                refs.add(item)
                else:
                    refs.update(self._extract_id_references(value, keys))
        elif isinstance(data, list):
            for item in data:
                refs.update(self._extract_id_references(item, keys))
        return refs

    def extract_device_references(self, data: Any) -> set[str]:
        """Extract device references from configuration data."""
        return self._extract_id_references(data, {"device_id", "device_ids"})

    def extract_area_references(self, data: Any) -> set[str]:
        """Extract area references from configuration data."""
        return self._extract_id_references(data, {"area_id", "area_ids"})

    def extract_entity_registry_ids(self, data: Any) -> set[str]:
        """Extract entity registry UUID references from configuration data."""
        entity_registry_ids = set()

        if isinstance(data, dict):
            for key, value in data.items():
                if key in ("entity_id", "entity_ids"):
                    candidates = (
                        [value]
                        if isinstance(value, str)
                        else (value if isinstance(value, list) else [])
                    )
                    for cand in candidates:
                        if isinstance(cand, str) and self.is_uuid_format(cand):
                            entity_registry_ids.add(cand)
                else:
                    entity_registry_ids.update(self.extract_entity_registry_ids(value))
        elif isinstance(data, list):
            for item in data:
                entity_registry_ids.update(self.extract_entity_registry_ids(item))

        return entity_registry_ids

    def get_entity_registry_id_mapping(self) -> dict[str, str]:
        """Get mapping from entity registry ID to entity_id."""
        entities = self.load_entity_registry()
        return {
            entity_data["id"]: entity_data["entity_id"]
            for entity_data in entities.values()
            if "id" in entity_data
        }

    def validate_file_references(self, file_path: Path) -> bool:
        """Validate all references in a single file."""
        if file_path.name == "secrets.yaml":
            return True  # Skip secrets file

        data, ok = self.load_yaml_checked(file_path)
        if not ok:
            return False

        if data is None:
            return True  # Empty file is valid

        # Extract references
        entity_refs = self.extract_entity_references(data)
        device_refs = self.extract_device_references(data)
        area_refs = self.extract_area_references(data)
        entity_registry_ids = self.extract_entity_registry_ids(data)

        # Load registries
        entities = self.load_entity_registry()
        devices = self.load_device_registry()
        areas = self.load_area_registry()
        entity_id_mapping = self.get_entity_registry_id_mapping()

        # Get config-defined entities and restore state for diagnostics
        config_entities = self.get_config_defined_entities()
        restore_entities = self.load_restore_state_entities()

        all_valid = True

        # Validate entity references (normal entity_id format)
        for entity_id in entity_refs:
            # Skip UUID-format entity IDs, they're handled separately
            if self.is_uuid_format(entity_id):
                continue

            # Check if entity exists in registry
            if entity_id in entities:
                if entities[entity_id].get("disabled_by") is not None:
                    self.warnings.append(
                        f"{file_path}: References disabled entity '{entity_id}'"
                    )
                continue

            # Check if entity is defined in config files
            if entity_id in config_entities:
                continue

            # Diagnostic: note if found in restore state (but still fail)
            if entity_id in restore_entities:
                self.warnings.append(
                    f"{file_path}: Entity '{entity_id}' not in registry "
                    "but found in restore state"
                )

            self.errors.append(f"{file_path}: Unknown entity '{entity_id}'")
            all_valid = False

        # Validate entity registry ID references (UUID format)
        for registry_id in entity_registry_ids:
            if registry_id not in entity_id_mapping:
                self.errors.append(
                    f"{file_path}: Unknown entity registry ID '{registry_id}'"
                )
                all_valid = False
            else:
                # Check if the mapped entity is disabled
                actual_entity_id = entity_id_mapping[registry_id]
                if actual_entity_id in entities:
                    entity_data = entities[actual_entity_id]
                    if entity_data.get("disabled_by") is not None:
                        self.warnings.append(
                            f"{file_path}: Entity registry ID '{registry_id}' "
                            f"references disabled entity '{actual_entity_id}'"
                        )

        # Validate device references
        for device_id in device_refs:
            if device_id not in devices:
                self.errors.append(f"{file_path}: Unknown device '{device_id}'")
                all_valid = False

        # Validate area references
        for area_id in area_refs:
            if area_id not in areas:
                self.warnings.append(f"{file_path}: Unknown area '{area_id}'")

        return all_valid

    def _validate(self) -> bool:
        """Validate all references in the config directory."""
        yaml_files = self.get_yaml_files()
        if not yaml_files:
            self.warnings.append("No YAML files found in config directory")
            return True

        all_valid = True

        for file_path in yaml_files:
            if not self.validate_file_references(file_path):
                all_valid = False

        return all_valid

    def get_entity_summary(self) -> dict[str, DomainSummary]:
        """Get summary of available entities by domain."""
        entities = self.load_entity_registry()

        summary: dict[str, DomainSummary] = {}
        for entity_id, entity_data in entities.items():
            domain = entity_id.split(".")[0]
            if domain not in summary:
                summary[domain] = {
                    "count": 0,
                    "enabled": 0,
                    "disabled": 0,
                    "examples": [],
                }

            summary[domain]["count"] += 1
            if entity_data.get("disabled_by") is None:
                summary[domain]["enabled"] += 1
            else:
                summary[domain]["disabled"] += 1

            # Add some examples
            if len(summary[domain]["examples"]) < 3:
                summary[domain]["examples"].append(entity_id)

        return summary

    def print_results(self):
        """Print validation results with entity summary."""
        if self.quiet:
            return

        if self.summary:
            if self.errors:
                print("FAIL Entity/device references")
                for err in self.errors:
                    print(f"  ERROR: {err}", file=sys.stderr)
                for warn in self.warnings:
                    print(f"  WARN: {warn}", file=sys.stderr)
            elif self.warnings:
                print("PASS Entity/device references (with warnings)")
                for warn in self.warnings:
                    print(f"  WARN: {warn}", file=sys.stderr)
            else:
                print("PASS Entity/device references")
            return

        super().print_results()

        # Print entity summary
        summary = self.get_entity_summary()
        if summary:
            print("AVAILABLE ENTITIES BY DOMAIN:", file=sys.stderr)
            for domain, info in sorted(summary.items()):
                enabled_count = info["enabled"]
                disabled_count = info["disabled"]
                print(
                    f"  {domain}: {enabled_count} enabled, {disabled_count} disabled",
                    file=sys.stderr,
                )
                if info["examples"]:
                    print(
                        f"    Examples: {', '.join(info['examples'])}", file=sys.stderr
                    )
            print(file=sys.stderr)


def main() -> int:
    """Run entity and device reference validation from command line."""
    parser = argparse.ArgumentParser(
        description="Validate entity and device references in Home Assistant config."
    )
    parser.add_argument(
        "config_dir",
        nargs="?",
        default="config",
        help="Path to the config directory (default: config)",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Compact output; auto-detected when stdout is not a TTY",
    )
    parser.add_argument(
        "--no-summary",
        action="store_true",
        help="Force verbose output even when stdout is piped",
    )
    args = parser.parse_args()

    summary = resolve_summary(args)

    validator = ReferenceValidator(args.config_dir, summary=summary)
    is_valid = validator.validate_all()
    validator.print_results()

    return 0 if is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
