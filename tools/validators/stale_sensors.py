#!/usr/bin/env python3
"""Stale sensor diagnostic validator for Home Assistant.

Queries the live HA REST API for states, filters out disabled/hidden entities and
virtual platforms using the local core.entity_registry, and identifies sensors
whose last update or radio check-in exceeds the configured threshold.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import UTC, datetime
from typing import Any

from tools.common import HARequestError, ValidatorBase, load_env_file
from tools.ha.client import HAClient


class StaleSensorValidator(ValidatorBase):
    """Validates that active sensors are updating and have not gone stale."""

    validator_name = "Stale sensors"

    def __init__(
        self,
        config_dir: str = "config",
        quiet: bool = False,
        threshold_hours: int = 24,
        only_domains: set[str] | None = None,
        exclude_platforms: set[str] | None = None,
        ignore_restored: bool = False,
    ):
        """Initialize the StaleSensorValidator.

        Args:
            config_dir: Configuration directory path.
            quiet: If True, suppress stdout printing on success.
            threshold_hours: Inactivity limit in hours before triggering stale state.
            only_domains: Domains to analyze (e.g., {'sensor'}).
            exclude_platforms: Integration platforms to ignore (e.g., {'template'}).
            ignore_restored: If True, restored entities at startup won't be flagged.
        """
        super().__init__(config_dir, quiet=quiet)
        self.threshold_hours = threshold_hours
        self.only_domains = only_domains if only_domains is not None else {"sensor"}

        default_exclude_platforms = {
            "template",
            "group",
            "derivative",
            "utility_meter",
            "min_max",
            "threshold",
            "integration",
            "history_stats",
            "filter",
        }
        self.exclude_platforms = (
            exclude_platforms
            if exclude_platforms is not None
            else default_exclude_platforms
        )
        self.ignore_restored = ignore_restored

    def file_deps(self) -> list[str]:
        """Return empty list to completely skip validation caching.

        Staleness is a time-sensitive live check and must never be cached.
        """
        return []

    def _get_current_time(self) -> datetime:
        """Get the current UTC time. Easy to mock in unit tests."""
        return datetime.now(UTC)

    def _load_registry(self) -> dict[str, Any] | None:
        """Load and parse the local entity registry with retry-on-failure."""
        registry_file = self.config_dir / ".storage" / "core.entity_registry"
        if not registry_file.exists():
            self.info.append(
                f"Entity registry not found at {registry_file}. "
                "Falling back to state-only analysis."
            )
            return None

        for attempt in range(2):
            try:
                with open(registry_file, encoding="utf-8") as f:
                    data = json.load(f)
                    return {
                        entity["entity_id"]: entity
                        for entity in data.get("data", {}).get("entities", [])
                    }
            except Exception as e:
                if attempt == 0:
                    time.sleep(0.1)
                    continue
                self.warnings.append(
                    f"Failed to read entity registry: {e}. "
                    "Falling back to state-only analysis."
                )
                return None
        return None

    def parse_timestamp(self, value: Any) -> datetime | None:
        """Parse string or epoch numeric timestamps into offset-aware UTC datetimes."""
        if value is None or isinstance(value, bool):
            return None

        # 1. Numeric epoch timestamps (float/int)
        if isinstance(value, (int, float)):
            try:
                # Normalise milliseconds to seconds
                if value > 1e11:
                    value = value / 1000.0
                return datetime.fromtimestamp(value, tz=UTC)
            except Exception as e:
                self.warnings.append(
                    f"Failed to parse numeric timestamp '{value}': {e}"
                )
                return None

        # 2. String timestamps
        if isinstance(value, str):
            # Normalise 'Z' suffix to '+00:00' for backward compatibility
            if value.endswith("Z"):
                value = value[:-1] + "+00:00"
            try:
                dt = datetime.fromisoformat(value)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
                return dt
            except ValueError:
                # Check if it is a string representation of a number
                try:
                    val_float = float(value)
                    if val_float > 1e11:
                        val_float = val_float / 1000.0
                    return datetime.fromtimestamp(val_float, tz=UTC)
                except ValueError:
                    pass
                self.warnings.append(f"Failed to parse string timestamp '{value}'")
                return None

        return None

    def validate_all(self) -> bool:
        """Query Home Assistant for stale sensors.

        Returns True under all conditions to ensure deployment is not blocked,
        populating warnings/errors list with diagnostic details.
        """
        # Fast skip in CI/CD environments
        if os.getenv("CI") == "true":
            self.info.append(
                "Skipped stale sensor validation: Running in CI environment."
            )
            return True

        load_env_file()
        url = os.getenv("HA_URL")
        token = os.getenv("HA_TOKEN")

        if not url or not token:
            self.info.append(
                "Skipped stale sensor validation: HA_URL or HA_TOKEN not set."
            )
            return True

        # Fetch states from HA API with a short 2-second timeout
        try:
            client = HAClient(url, token, timeout=2)
            states = client.get_json("/api/states")
        except HARequestError as e:
            self.info.append(f"Skipped stale sensor validation: API unreachable - {e}")
            return True

        if not isinstance(states, list):
            self.info.append(
                "Skipped stale sensor validation: invalid API states format."
            )
            return True

        registry = self._load_registry()
        current_time = self._get_current_time()

        for state in states:
            if not isinstance(state, dict):
                continue

            entity_id = state.get("entity_id")
            if not entity_id or "." not in entity_id:
                continue

            domain, _ = entity_id.split(".", 1)
            if domain not in self.only_domains:
                continue

            # Look up entity registry definitions if available
            reg_entry = registry.get(entity_id) if registry else None
            if reg_entry:
                # Exclude disabled and hidden entities
                if reg_entry.get("disabled_by") is not None:
                    continue
                if reg_entry.get("hidden_by") is not None:
                    continue

                # Exclude virtual / non-hardware platforms
                platform = reg_entry.get("platform")
                if platform in self.exclude_platforms:
                    continue

            # Check if startup restoration is active
            attrs = state.get("attributes") or {}
            if attrs.get("restored") is True:
                if not self.ignore_restored:
                    self.warnings.append(
                        f"{entity_id}: Entity has 'restored' status at HA startup. "
                        "Real hardware state is unknown."
                    )
                continue

            # Heartbeat check: Z2M or custom attributes represent
            # actual radio communication time.
            # Binary sensors are only validated if a heartbeat attribute
            # is explicitly present.
            heartbeat_ts = None
            for key in ("last_seen", "last_reported"):
                val = attrs.get(key)
                parsed = self.parse_timestamp(val)
                if parsed and (heartbeat_ts is None or parsed > heartbeat_ts):
                    heartbeat_ts = parsed

            if domain == "binary_sensor" and heartbeat_ts is None:
                # Skip binary sensors without device heartbeats
                # to avoid rare-event false positives.
                continue

            # Determine baseline timestamp to compare
            baseline_ts = heartbeat_ts
            if baseline_ts is None:
                last_updated_str = state.get("last_updated")
                baseline_ts = self.parse_timestamp(last_updated_str)

            if baseline_ts is None:
                continue

            # Calculate difference
            delta = current_time - baseline_ts
            elapsed_hours = delta.total_seconds() / 3600.0

            if elapsed_hours > self.threshold_hours:
                self.warnings.append(
                    f"{entity_id}: Stale state detected. Last update was "
                    f"{elapsed_hours:.1f} hours ago (limit: {self.threshold_hours}h)."
                )

        return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify active HA sensors are reporting updates."
    )
    parser.add_argument(
        "config_dir",
        nargs="?",
        default="config",
        help="Path to the config directory (default: config)",
    )
    args = parser.parse_args()
    v = StaleSensorValidator(args.config_dir)
    is_valid = v.validate_all()
    v.print_results()
    raise SystemExit(0 if is_valid else 1)


if __name__ == "__main__":
    main()
