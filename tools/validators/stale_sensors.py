#!/usr/bin/env python3
"""Stale sensor diagnostic validator for Home Assistant.

Queries the live HA REST API for states, filters out disabled/hidden entities and
virtual platforms using the local core.entity_registry, and identifies sensors
whose last update or radio check-in exceeds the configured threshold.
"""

import json
import os
import time
from datetime import UTC, datetime
from typing import Any

from tools.common import HARequestError, get_env_int, load_env_file
from tools.ha.client import HAClient
from tools.validators._storage import load_storage_registry
from tools.validators.base import ValidatorBase

_EPOCH_MS_THRESHOLD = 1e11


class StaleSensorValidator(ValidatorBase):
    """Validates that active sensors are updating and have not gone stale."""

    validator_name = "Stale sensors"

    def __init__(
        self,
        config_dir: str = "config",
        quiet: bool = False,
        summary: bool = False,
        threshold_hours: int = 24,
        only_domains: set[str] | None = None,
        exclude_platforms: set[str] | None = None,
        ignore_restored: bool = False,
        fail_on_stale: bool = False,
        *,
        exclude_domains: set[str] | None = None,
    ):
        """Initialize the StaleSensorValidator.

        Args:
            config_dir: Configuration directory path.
            quiet: If True, suppress stdout printing on success.
            summary: If True, use compact output format.
            threshold_hours: Inactivity limit in hours before triggering stale state.
            only_domains: Domains to analyze (e.g., {'sensor'}).
            exclude_platforms: Integration platforms to ignore (e.g., {'template'}).
            exclude_domains: Domains to subtract from only_domains.
            ignore_restored: If True, restored entities at startup won't be flagged.
            fail_on_stale: If True, validator returns False when staleness is detected.
        """
        super().__init__(config_dir, quiet=quiet, summary=summary)
        self.threshold_hours = threshold_hours
        base_domains = only_domains if only_domains is not None else {"sensor"}
        self.only_domains = base_domains - (exclude_domains or set())
        self.fail_on_stale = fail_on_stale
        self.stale_entities: list[str] = []

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
        """Load and parse the local entity registry with retry-on-failure.

        Wraps :func:`tools.validators._storage.load_storage_registry` with a
        100ms retry loop (per ``AGENTS.md``: "Atomic writes to ``.storage/``
        can cause transient ``JSONDecodeError``. Retry (100ms sleep)").
        """
        registry_file = self.config_dir / ".storage" / "core.entity_registry"
        if not registry_file.exists():
            self.info.append(
                f"Entity registry not found at {registry_file}. "
                "Falling back to state-only analysis."
            )
            return None

        for attempt in range(2):
            try:
                return load_storage_registry(
                    registry_file, list_key="entities", key_field="entity_id"
                )
            except (
                OSError,
                json.JSONDecodeError,
                KeyError,
                TypeError,
                ValueError,
                AttributeError,
            ) as e:
                if attempt == 0:
                    time.sleep(0.1)
                    continue
                self.warnings.append(
                    f"Failed to read entity registry: {e}. "
                    "Falling back to state-only analysis."
                )
                return None
        return None  # pragma: no cover  # unreachable fallthrough

    def _parse_iso_string(self, s: str) -> datetime | None:
        """Parse an ISO-8601 string into an offset-aware datetime.

        Normalises a trailing ``Z`` to ``+00:00``, attaches UTC to naive
        datetimes, and returns ``None`` on parse failure (no warning —
        callers decide whether to warn).
        """
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt

    def _parse_epoch(self, value: float) -> datetime:
        """Parse a numeric epoch value, normalising milliseconds to seconds."""
        if value > _EPOCH_MS_THRESHOLD:
            value = value / 1000.0
        return datetime.fromtimestamp(value, tz=UTC)

    def parse_timestamp(self, value: Any) -> datetime | None:
        """Parse string or epoch numeric timestamps into offset-aware UTC datetimes."""
        if value is None or isinstance(value, bool):
            return None

        if isinstance(value, (int, float)):
            try:
                return self._parse_epoch(value)
            except (OverflowError, OSError, ValueError) as e:  # pragma: no cover
                self.warnings.append(
                    f"Failed to parse numeric timestamp '{value}': {e}"
                )
                return None

        if isinstance(value, str):
            dt = self._parse_iso_string(value)
            if dt is not None:
                return dt
            try:
                return self._parse_epoch(float(value))
            except ValueError:
                self.warnings.append(f"Failed to parse string timestamp '{value}'")
                return None

        return None

    def _validate(self) -> bool:
        """Query Home Assistant for stale sensors.

        Returns True when no staleness or when fail_on_stale is off (default).
        Returns False when fail_on_stale is True and stale sensors exist.
        Populates warnings/errors/info with diagnostic details.
        """
        # Fast skip in CI/CD environments
        if os.getenv("CI") == "true":
            self.info.append(
                "Skipped stale sensor validation: Running in CI environment."
            )
            return True

        load_env_file()
        if not self.fail_on_stale:
            self.fail_on_stale = os.getenv("HA_STALE_FAIL", "").strip().lower() in (
                "1",
                "true",
                "yes",
            )
        url = os.getenv("HA_URL")
        token = os.getenv("HA_TOKEN")

        if not url or not token:  # tested separately
            self.info.append(
                "Skipped stale sensor validation: HA_URL or HA_TOKEN not set."
            )
            return True

        # Fetch states from HA API with configurable timeout (env HA_STALE_TIMEOUT)
        timeout_val, warn = get_env_int("HA_STALE_TIMEOUT", 2)
        if warn:
            self.info.append(warn)
        try:
            client = HAClient(url, token, timeout=timeout_val)
            states = client.get_json("/api/states")
        except (HARequestError, OSError) as e:
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

            # M27: a sensor in unavailable/unknown/None state is not reporting —
            # surface immediately rather than waiting for threshold_hours.
            st_value = state.get("state")
            if st_value in ("unavailable", "unknown", None):
                self.warnings.append(
                    f"{entity_id}: State is {st_value!r} — device not reporting."
                )
                self.stale_entities.append(entity_id)
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
                # Prefer last_changed (value-change) over last_updated (attr-write).
                last_changed = state.get("last_changed")
                last_updated = state.get("last_updated")
                if last_changed and last_updated:
                    # Use whichever is older — value change before latest attr write
                    # is the stronger staleness signal.
                    try:
                        tc = self.parse_timestamp(last_changed)
                        tu = self.parse_timestamp(last_updated)
                        baseline_ts = min(tc, tu) if (tc and tu) else (tc or tu)
                    except Exception:
                        baseline_ts = self.parse_timestamp(last_updated)
                else:
                    baseline_ts = self.parse_timestamp(last_changed or last_updated)

            if baseline_ts is None:
                continue

            # Calculate difference
            delta = current_time - baseline_ts
            elapsed_hours = delta.total_seconds() / 3600.0

            if elapsed_hours > self.threshold_hours:
                self.stale_entities.append(entity_id)
                self.warnings.append(
                    f"{entity_id}: Stale state detected. Last update was "
                    f"{elapsed_hours:.1f} hours ago (limit: {self.threshold_hours}h)."
                )

        if self.fail_on_stale and self.stale_entities:
            self.errors.append(
                f"Stale sensor check failed: "
                f"{len(self.stale_entities)} stale sensor(s) detected (see warnings)"
            )
            return False

        return True


def main() -> int:
    """Verify active HA sensors are reporting updates."""
    return StaleSensorValidator.run_cli(
        "Verify active HA sensors are reporting updates."
    )


if __name__ == "__main__":
    raise SystemExit(main())
