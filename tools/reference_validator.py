#!/usr/bin/env python3
"""Entity and device reference validator for Home Assistant configuration files.

Validates that all entity references in configuration files actually exist.
"""

import argparse
import json
import re
from pathlib import Path
from typing import Any, TypedDict

import yaml

from tools.common import HAYamlLoader, ValidatorBase


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

    # Built-in entities that always exist in HA but may not be in the registry
    BUILTIN_ENTITIES = {"sun.sun"}

    # Entities defined in YAML config (templates, etc.) won't appear in registry
    YAML_DEFINED_ENTITIES: set[str] = set()

    def __init__(self, config_dir: str = "config"):
        """Initialize the ReferenceValidator."""
        super().__init__(config_dir)
        self.storage_dir = self.config_dir / ".storage"

        # Cache for loaded registries
        self._entities: dict[str, Any] | None = None
        self._devices: dict[str, Any] | None = None
        self._areas: dict[str, Any] | None = None
        self._yaml_entities: set[str] | None = None

    def load_yaml_defined_entities(self) -> set[str]:
        """Extract entities defined in YAML templates and automations."""
        if self._yaml_entities is not None:
            return self._yaml_entities

        self._yaml_entities = set()

        # Extract template entities from configuration.yaml
        config_file = self.config_dir / "configuration.yaml"
        if config_file.exists():
            try:
                with open(config_file, encoding="utf-8") as f:
                    data = yaml.load(f, Loader=HAYamlLoader)

                if data and "template" in data:
                    templates = data["template"]
                    if isinstance(templates, list):
                        for template_block in templates:
                            if isinstance(template_block, dict):
                                # Check for various entity types in templates
                                for domain in [
                                    "binary_sensor",
                                    "sensor",
                                    "switch",
                                    "light",
                                ]:
                                    if domain in template_block:
                                        entities = template_block[domain]
                                        if isinstance(entities, list):
                                            for entity in entities:
                                                if (
                                                    isinstance(entity, dict)
                                                    and "name" in entity
                                                ):
                                                    # Convert name to entity_id
                                                    ent_name = entity["name"]
                                                    slug = ent_name.lower()
                                                    slug = slug.replace(" ", "_")
                                                    entity_id = f"{domain}.{slug}"
                                                    self._yaml_entities.add(entity_id)
            except Exception as e:
                self.warnings.append(
                    f"Failed to parse templates from configuration.yaml: {e}"
                )

        # Extract automation IDs from automations.yaml
        automations_file = self.config_dir / "automations.yaml"
        if automations_file.exists():
            try:
                with open(automations_file, encoding="utf-8") as f:
                    data = yaml.load(f, Loader=HAYamlLoader)

                if isinstance(data, list):
                    for automation in data:
                        if isinstance(automation, dict) and "id" in automation:
                            automation_id = automation["id"]
                            entity_id = f"automation.{automation_id}"
                            self._yaml_entities.add(entity_id)
            except Exception as e:
                self.warnings.append(f"Failed to parse automations.yaml: {e}")

        return self._yaml_entities

    def load_entity_registry(self) -> dict[str, Any]:
        """Load and cache entity registry."""
        if self._entities is None:
            registry_file = self.storage_dir / "core.entity_registry"
            if not registry_file.exists():
                self.errors.append(f"Entity registry not found: {registry_file}")
                return {}

            try:
                with open(registry_file) as f:
                    data = json.load(f)
                    self._entities = {
                        entity["entity_id"]: entity
                        for entity in data.get("data", {}).get("entities", [])
                    }
            except Exception as e:
                self.errors.append(f"Failed to load entity registry: {e}")
                return {}

        return self._entities

    def load_device_registry(self) -> dict[str, Any]:
        """Load and cache device registry."""
        if self._devices is None:
            registry_file = self.storage_dir / "core.device_registry"
            if not registry_file.exists():
                self.errors.append(f"Device registry not found: {registry_file}")
                return {}

            try:
                with open(registry_file) as f:
                    data = json.load(f)
                    self._devices = {
                        device["id"]: device
                        for device in data.get("data", {}).get("devices", [])
                    }
            except Exception as e:
                self.errors.append(f"Failed to load device registry: {e}")
                return {}

        return self._devices

    def load_area_registry(self) -> dict[str, Any]:
        """Load and cache area registry."""
        if self._areas is None:
            registry_file = self.storage_dir / "core.area_registry"
            if not registry_file.exists():
                self.warnings.append(f"Area registry not found: {registry_file}")
                return {}

            try:
                with open(registry_file) as f:
                    data = json.load(f)
                    self._areas = {
                        area["id"]: area
                        for area in data.get("data", {}).get("areas", [])
                    }
            except Exception as e:
                self.warnings.append(f"Failed to load area registry: {e}")
                return {}

        return self._areas

    def is_uuid_format(self, value: str) -> bool:
        """Check if a string matches UUID format (32 hex characters)."""
        # UUID format: 8-4-4-4-12 hex digits, but HA often stores without hyphens
        uuid_pattern = r"^[a-f0-9]{32}$"
        return bool(re.match(uuid_pattern, value))

    def is_template(self, value: str) -> bool:
        """Check if value is a Jinja2 template expression."""
        # Match template expressions like {{ ... }}
        return bool(re.search(r"\{\{.*?\}\}", value))

    def should_skip_entity_validation(self, value: str) -> bool:
        """Check if entity reference should be skipped during validation."""
        return (
            value.startswith("!")  # HA tags like !input, !secret
            or self.is_uuid_format(value)  # UUID format (device-based)
            or self.is_template(value)  # Template expressions
            or value in self.SPECIAL_KEYWORDS  # Special keywords like "all", "none"
        )

    def extract_entity_references(self, data: Any, path: str = "") -> set[str]:
        """Extract entity references from configuration data."""
        entities = set()

        if isinstance(data, dict):
            for key, value in data.items():
                current_path = f"{path}.{key}" if path else key

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

                # Device-related keys
                elif key in ["device_id", "device_ids"]:
                    # Device IDs are handled separately
                    pass

                # Area-related keys
                elif key in ["area_id", "area_ids"]:
                    # Area IDs are handled separately
                    pass

                # Service data might contain entity references
                elif key == "data" and isinstance(value, dict):
                    entities.update(self.extract_entity_references(value, current_path))

                # Templates might contain entity references
                elif isinstance(value, str) and any(
                    x in value for x in ["state_attr(", "states(", "is_state("]
                ):
                    entities.update(self.extract_entities_from_template(value))

                # Recursive search
                else:
                    entities.update(self.extract_entity_references(value, current_path))

        elif isinstance(data, list):
            for i, item in enumerate(data):
                current_path = f"{path}[{i}]" if path else f"[{i}]"
                entities.update(self.extract_entity_references(item, current_path))

        return entities

    def extract_entities_from_template(self, template: str) -> set[str]:
        """Extract entity references from Jinja2 templates."""
        entities = set()

        # Common patterns for entity references in templates
        patterns = [
            r"states\('([^']+)'\)",  # states('entity.id')
            r'states\("([^"]+)"\)',  # states("entity.id")
            # states.domain.entity
            r"states\.([a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*)",
            r"is_state\('([^']+)'",  # is_state('entity.id', ...)
            r'is_state\("([^"]+)"',  # is_state("entity.id", ...)
            r"state_attr\('([^']+)'",  # state_attr('entity.id', ...)
            r'state_attr\("([^"]+)"',  # state_attr("entity.id", ...)
        ]

        for pattern in patterns:
            matches = re.findall(pattern, template)
            for match in matches:
                # Validate entity ID format
                if "." in match and len(match.split(".")) == 2:
                    entities.add(match)

        return entities

    def extract_device_references(self, data: Any) -> set[str]:
        """Extract device references from configuration data."""
        devices = set()

        if isinstance(data, dict):
            for key, value in data.items():
                if key in ["device_id", "device_ids"]:
                    if isinstance(value, str):
                        # Skip blueprint inputs and other HA tags
                        if not value.startswith("!") and not self.is_template(value):
                            devices.add(value)
                    elif isinstance(value, list):
                        for device in value:
                            if (
                                isinstance(device, str)
                                and not device.startswith("!")
                                and not self.is_template(device)
                            ):
                                devices.add(device)
                else:
                    devices.update(self.extract_device_references(value))

        elif isinstance(data, list):
            for item in data:
                devices.update(self.extract_device_references(item))

        return devices

    def extract_area_references(self, data: Any) -> set[str]:
        """Extract area references from configuration data."""
        areas = set()

        if isinstance(data, dict):
            for key, value in data.items():
                if key in ["area_id", "area_ids"]:
                    if isinstance(value, str):
                        # Skip blueprint inputs and other HA tags
                        if not value.startswith("!") and not self.is_template(value):
                            areas.add(value)
                    elif isinstance(value, list):
                        for area in value:
                            if isinstance(area, str) and not area.startswith("!"):
                                areas.add(area)
                else:
                    areas.update(self.extract_area_references(value))

        elif isinstance(data, list):
            for item in data:
                areas.update(self.extract_area_references(item))

        return areas

    def extract_entity_registry_ids(self, data: Any) -> set[str]:
        """Extract entity registry UUID references from configuration data."""
        entity_registry_ids = set()

        if isinstance(data, dict):
            for key, value in data.items():
                # Look for entity_id fields containing UUIDs (device-based automations)
                if key == "entity_id" and isinstance(value, str):
                    if self.is_uuid_format(value):
                        entity_registry_ids.add(value)
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

        try:
            with open(file_path, encoding="utf-8") as f:
                data = yaml.load(f, Loader=HAYamlLoader)
        except Exception as e:
            self.errors.append(f"{file_path}: Failed to load YAML - {e}")
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

        all_valid = True

        # Validate entity references (normal entity_id format)
        yaml_entities = self.load_yaml_defined_entities()
        for entity_id in entity_refs:
            # Skip UUID-format entity IDs, they're handled separately
            if self.is_uuid_format(entity_id):
                continue

            # Skip built-in entities that are always present
            if entity_id in self.BUILTIN_ENTITIES:
                continue

            # Skip entities defined in YAML templates
            if entity_id in yaml_entities:
                continue

            if entity_id not in entities:
                # Check if it's a disabled entity
                disabled_entities = {
                    e["entity_id"]: e
                    for e in entities.values()
                    if e.get("disabled_by") is not None
                }

                if entity_id in disabled_entities:
                    self.warnings.append(
                        f"{file_path}: References disabled entity '{entity_id}'"
                    )
                else:
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

    def validate_all(self) -> bool:
        """Validate all references in the config directory."""
        if not self.config_dir.exists():
            self.errors.append(f"Config directory {self.config_dir} does not exist")
            return False

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
        super().print_results()

        # Print entity summary
        summary = self.get_entity_summary()
        if summary:
            print("AVAILABLE ENTITIES BY DOMAIN:")
            for domain, info in sorted(summary.items()):
                enabled_count = info["enabled"]
                disabled_count = info["disabled"]
                print(f"  {domain}: {enabled_count} enabled, {disabled_count} disabled")
                if info["examples"]:
                    print(f"    Examples: {', '.join(info['examples'])}")
            print()


def main():
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
    args = parser.parse_args()

    validator = ReferenceValidator(args.config_dir)
    is_valid = validator.validate_all()
    validator.print_results()

    raise SystemExit(0 if is_valid else 1)


if __name__ == "__main__":
    main()
