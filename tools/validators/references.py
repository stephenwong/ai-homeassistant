#!/usr/bin/env python3
"""Entity and device reference validator for Home Assistant configuration files.

Validates that all entity references in configuration files actually exist.
"""

import argparse
import concurrent.futures
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

    _OBJECT_ID_RE = re.compile(r"^[a-z0-9_]+$")

    # Built-in entities that always exist in HA but may not be in the registry
    # zone.home is a special, pre-defined, non-deletable zone
    # See: https://www.home-assistant.io/integrations/zone/
    BUILTIN_ENTITIES = {"sun.sun", "zone.home"}

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

    def __init__(self, config_dir: str = "config", quiet: bool = False):
        """Initialize the ReferenceValidator."""
        super().__init__(config_dir, quiet=quiet)
        self.storage_dir = self.config_dir / ".storage"

        # Cache for loaded registries
        self._entities: dict[str, Any] | None = None
        self._devices: dict[str, Any] | None = None
        self._areas: dict[str, Any] | None = None
        self._restore_entities: set[str] | None = None
        self._config_defined_entities: set[str] | None = None

    @classmethod
    def _slugify_object_id(cls, value: str) -> str:
        """Best-effort HA-like slugify for deriving object_ids from names."""
        slug = value.strip().lower()
        slug = re.sub(r"[^a-z0-9_]+", "_", slug)
        slug = re.sub(r"_+", "_", slug)
        return slug.strip("_")

    @classmethod
    def _is_valid_object_id(cls, value: str) -> bool:
        """Check if a string is a valid HA object ID."""
        return bool(cls._OBJECT_ID_RE.fullmatch(value))

    @classmethod
    def _is_valid_entity_id(cls, value: str) -> bool:
        """Check if a string is a valid HA entity ID (domain.object_id)."""
        if "." not in value:
            return False
        domain, object_id = value.split(".", 1)
        return (
            bool(domain)
            and cls._is_valid_object_id(domain)
            and cls._is_valid_object_id(object_id)
        )

    def load_restore_state_entities(self) -> set[str]:
        """Load entity_ids from restore state storage (diagnostic only).

        Restore state can contain stale entries and is not authoritative.
        Used only for diagnostic warnings.
        """
        if self._restore_entities is not None:
            return self._restore_entities

        restore_file = self.storage_dir / "core.restore_state"
        if not restore_file.exists():
            self._restore_entities = set()
            return self._restore_entities

        try:
            with open(restore_file, encoding="utf-8") as f:
                payload = json.load(f)
        except Exception as e:
            self.warnings.append(f"Failed to load restore state: {e}")
            self._restore_entities = set()
            return self._restore_entities

        items = payload.get("data", [])
        entities: set[str] = set()
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                state = item.get("state")
                if not isinstance(state, dict):
                    continue
                entity_id = state.get("entity_id")
                if isinstance(entity_id, str) and self._is_valid_entity_id(entity_id):
                    entities.add(entity_id)

        self._restore_entities = entities
        return self._restore_entities

    def get_config_defined_entities(self) -> set[str]:
        """Extract entities defined in config files (not in entity registry)."""
        if self._config_defined_entities is not None:
            return self._config_defined_entities

        entities: set[str] = set()
        entities.update(self.BUILTIN_ENTITIES)

        # Load configuration.yaml once; share with both extraction methods that need it.
        config_data = self._load_config_yaml()

        # Run all five file reads concurrently (each targets a different file).
        with concurrent.futures.ThreadPoolExecutor() as executor:
            f_config = executor.submit(self._extract_from_configuration, config_data)
            f_auto = executor.submit(self._extract_automation_entities)
            f_script = executor.submit(self._extract_script_entities)
            f_scene = executor.submit(self._extract_scene_entities)
            f_zone = executor.submit(self._extract_zone_entities, config_data)

        config_entities = f_config.result()
        automation_entities = f_auto.result()
        script_entities = f_script.result()
        scene_entities = f_scene.result()
        zone_entities = f_zone.result()

        entities.update(config_entities)
        entities.update(automation_entities)
        entities.update(script_entities)
        entities.update(scene_entities)
        entities.update(zone_entities)

        self.info.append(
            "Config-defined entities: "
            f"{len(entities)} total "
            f"(builtin={len(self.BUILTIN_ENTITIES)}, "
            f"configuration={len(config_entities)}, "
            f"automations={len(automation_entities)}, "
            f"scripts={len(script_entities)}, "
            f"scenes={len(scene_entities)}, "
            f"zones={len(zone_entities)})"
        )

        self._config_defined_entities = entities
        return self._config_defined_entities

    def _load_config_yaml(self) -> dict | None:
        """Load and parse configuration.yaml once; shared across extraction methods."""
        config_file = self.config_dir / "configuration.yaml"
        if not config_file.exists():
            return None
        try:
            with open(config_file, encoding="utf-8") as f:
                data = yaml.load(f, Loader=HAYamlLoader)
            return data if isinstance(data, dict) else None
        except (OSError, yaml.YAMLError, TypeError, ValueError) as e:
            self._record_extraction_warning(config_file, e)
            return None

    def _record_extraction_warning(self, source: Path, error: Exception) -> None:
        """Record entity extraction errors without hiding them."""
        self.warnings.append(
            f"{source}: Failed to extract entity definitions - {error}"
        )

    def _extract_from_configuration(self, config_data: dict | None) -> set[str]:
        """Extract entities defined in configuration.yaml from pre-loaded data."""
        entities: set[str] = set()

        if not isinstance(config_data, dict):
            return entities

        # Extract group entities
        if "group" in config_data and isinstance(config_data["group"], dict):
            for group_name in config_data["group"]:
                if isinstance(group_name, str) and self._is_valid_object_id(group_name):
                    entities.add(f"group.{group_name}")

        # Extract input helpers
        for input_type in [
            "input_boolean",
            "input_number",
            "input_text",
            "input_select",
            "input_datetime",
            "input_button",
        ]:
            if input_type in config_data and isinstance(config_data[input_type], dict):
                for name in config_data[input_type]:
                    if isinstance(name, str) and self._is_valid_object_id(name):
                        entities.add(f"{input_type}.{name}")

        # Extract template entities
        if "template" in config_data:
            template_data = config_data["template"]
            if isinstance(template_data, list):
                for item in template_data:
                    entities.update(self._extract_template_entities(item))
            elif isinstance(template_data, dict):
                entities.update(self._extract_template_entities(template_data))

        # Extract platform-based sensors/binary_sensors
        for sensor_type in ["sensor", "binary_sensor"]:
            if sensor_type in config_data:
                sensor_data = config_data[sensor_type]
                if isinstance(sensor_data, list):
                    for item in sensor_data:
                        if isinstance(item, dict) and (
                            "platform" in item and item["platform"] == "template"
                        ):
                            sensors = item.get("sensors", {})
                            for name in sensors:
                                if isinstance(name, str) and self._is_valid_object_id(
                                    name
                                ):
                                    entities.add(f"{sensor_type}.{name}")

        return entities

    def _extract_template_entities(self, template_config: Any) -> set[str]:
        """Extract entity names from template configuration.

        Per HA docs: default_entity_id controls automatic entity_id generation.
        unique_id exists to allow changing entity_id in the UI - it's NOT the entity_id.
        See: https://www.home-assistant.io/integrations/template/
        """
        entities: set[str] = set()

        if not isinstance(template_config, dict):
            return entities

        for entity_type in [
            "sensor",
            "binary_sensor",
            "switch",
            "light",
            "number",
            "select",
            "button",
        ]:
            if entity_type in template_config:
                type_data = template_config[entity_type]
                if isinstance(type_data, list):
                    for item in type_data:
                        if isinstance(item, dict):
                            default_entity_id = item.get("default_entity_id")
                            name = item.get("name", "")
                            if default_entity_id:
                                default_entity_id = str(default_entity_id)
                                if "." in default_entity_id:
                                    if self._is_valid_entity_id(default_entity_id):
                                        entities.add(default_entity_id)
                                elif self._is_valid_object_id(default_entity_id):
                                    entities.add(f"{entity_type}.{default_entity_id}")
                            elif name:
                                object_id = self._slugify_object_id(str(name))
                                if object_id:
                                    entities.add(f"{entity_type}.{object_id}")

        return entities

    def _extract_automation_entities(self) -> set[str]:
        """Extract automation entities from automations.yaml.

        Per HA docs: The 'id' field is a unique identifier for UI customization -
        it is NOT the entity_id. Entity_id is derived from alias (friendly name).
        See: https://www.home-assistant.io/docs/automation/yaml/
        """
        entities: set[str] = set()
        automations_file = self.config_dir / "automations.yaml"

        if automations_file.exists():
            try:
                with open(automations_file, encoding="utf-8") as f:
                    data = yaml.load(f, Loader=HAYamlLoader)
                    if isinstance(data, list):
                        for automation in data:
                            if isinstance(automation, dict):
                                alias = automation.get("alias", "")
                                if alias:
                                    object_id = self._slugify_object_id(str(alias))
                                    if object_id:
                                        entities.add(f"automation.{object_id}")
                                elif automation.get("id"):
                                    object_id = self._slugify_object_id(
                                        str(automation["id"])
                                    )
                                    if object_id:
                                        entities.add(f"automation.{object_id}")
            except (OSError, yaml.YAMLError, TypeError, ValueError) as e:
                self._record_extraction_warning(automations_file, e)

        return entities

    def _extract_script_entities(self) -> set[str]:
        """Extract script entities from scripts.yaml."""
        entities: set[str] = set()
        scripts_file = self.config_dir / "scripts.yaml"

        if scripts_file.exists():
            try:
                with open(scripts_file, encoding="utf-8") as f:
                    data = yaml.load(f, Loader=HAYamlLoader)
                    if isinstance(data, dict):
                        for script_name in data:
                            if isinstance(
                                script_name, str
                            ) and self._is_valid_object_id(script_name):
                                entities.add(f"script.{script_name}")
            except (OSError, yaml.YAMLError, TypeError, ValueError) as e:
                self._record_extraction_warning(scripts_file, e)

        return entities

    def _extract_scene_entities(self) -> set[str]:
        """Extract scene entities from scenes.yaml.

        Like automations, the 'id' field is for UI customization,
        not the entity_id. Entity_id is derived from friendly name.
        """
        entities: set[str] = set()
        scenes_file = self.config_dir / "scenes.yaml"

        if scenes_file.exists():
            try:
                with open(scenes_file, encoding="utf-8") as f:
                    data = yaml.load(f, Loader=HAYamlLoader)
                    if isinstance(data, list):
                        for scene in data:
                            if isinstance(scene, dict):
                                name = scene.get("name", "")
                                if name:
                                    object_id = self._slugify_object_id(str(name))
                                    if object_id:
                                        entities.add(f"scene.{object_id}")
            except (OSError, yaml.YAMLError, TypeError, ValueError) as e:
                self._record_extraction_warning(scenes_file, e)

        return entities

    def _extract_zone_entities(self, config_data: dict | None) -> set[str]:
        """Extract zone entities from configuration and storage.

        Zones can be defined in configuration.yaml or via the UI (.storage/core.zone).
        zone.home is handled separately as a built-in entity.
        """
        entities: set[str] = set()

        # Extract from pre-loaded configuration.yaml data
        if isinstance(config_data, dict) and "zone" in config_data:
            zone_data = config_data["zone"]
            if isinstance(zone_data, list):
                for zone in zone_data:
                    if isinstance(zone, dict):
                        name = zone.get("name", "")
                        if name:
                            object_id = self._slugify_object_id(str(name))
                            if object_id:
                                entities.add(f"zone.{object_id}")

        # Extract from storage (UI-configured zones)
        zone_storage = self.storage_dir / "core.zone"
        if zone_storage.exists():
            try:
                with open(zone_storage, encoding="utf-8") as f:
                    data = json.load(f)
                    items = data.get("data", {}).get("items", [])
                    for item in items:
                        if isinstance(item, dict):
                            name = item.get("name", "")
                            if name:
                                object_id = self._slugify_object_id(str(name))
                                if object_id:
                                    entities.add(f"zone.{object_id}")
            except (OSError, json.JSONDecodeError, TypeError, ValueError) as e:
                self._record_extraction_warning(zone_storage, e)

        return entities

    def load_entity_registry(self) -> dict[str, Any]:
        """Load and cache entity registry."""
        if self._entities is None:
            registry_file = self.storage_dir / "core.entity_registry"
            if not registry_file.exists():
                self.errors.append(f"Entity registry not found: {registry_file}")
                self._entities = {}
                return {}

            try:
                with open(registry_file, encoding="utf-8") as f:
                    data = json.load(f)
                    self._entities = {
                        entity["entity_id"]: entity
                        for entity in data.get("data", {}).get("entities", [])
                    }
            except Exception as e:
                self.errors.append(f"Failed to load entity registry: {e}")
                self._entities = {}
                return {}

        return self._entities

    def load_device_registry(self) -> dict[str, Any]:
        """Load and cache device registry."""
        if self._devices is None:
            registry_file = self.storage_dir / "core.device_registry"
            if not registry_file.exists():
                self.errors.append(f"Device registry not found: {registry_file}")
                self._devices = {}
                return {}

            try:
                with open(registry_file, encoding="utf-8") as f:
                    data = json.load(f)
                    self._devices = {
                        device["id"]: device
                        for device in data.get("data", {}).get("devices", [])
                    }
            except Exception as e:
                self.errors.append(f"Failed to load device registry: {e}")
                self._devices = {}
                return {}

        return self._devices

    def load_area_registry(self) -> dict[str, Any]:
        """Load and cache area registry."""
        if self._areas is None:
            registry_file = self.storage_dir / "core.area_registry"
            if not registry_file.exists():
                self.warnings.append(f"Area registry not found: {registry_file}")
                self._areas = {}
                return {}

            try:
                with open(registry_file, encoding="utf-8") as f:
                    data = json.load(f)
                    self._areas = {
                        area["id"]: area
                        for area in data.get("data", {}).get("areas", [])
                    }
            except Exception as e:
                self.warnings.append(f"Failed to load area registry: {e}")
                self._areas = {}
                return {}

        return self._areas

    def is_uuid_format(self, value: str) -> bool:
        """Check if a string matches UUID format (32 hex characters)."""
        # UUID format: 8-4-4-4-12 hex digits, but HA often stores without hyphens
        uuid_pattern = r"^[a-f0-9]{32}$"
        return bool(re.match(uuid_pattern, value))

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

        for pattern in self._TEMPLATE_PATTERNS:
            for match in pattern.findall(template):
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
                            if (
                                isinstance(area, str)
                                and not area.startswith("!")
                                and not self.is_template(area)
                            ):
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
        if self.quiet:
            return

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
