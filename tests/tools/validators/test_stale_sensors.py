"""Unit tests for stale_sensors.py — Stale Sensor Diagnostic Scanner."""

import json
import os
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from tools.common import HARequestError
from tools.validators.stale_sensors import StaleSensorValidator


@pytest.fixture(autouse=True)
def patch_load_env():
    """Prevent loading real .env files during test runs."""
    with patch("tools.ha.client.load_env_file") as mock_load:
        yield mock_load


@pytest.fixture(autouse=True)
def setup_env():
    """Set up default environment variables for testing."""
    # Ensure staleness-related env vars are isolated from the real environment
    env = {
        "HA_URL": "http://localhost:8123",
        "HA_TOKEN": "mock_token",
    }
    if "CI" in os.environ:
        env["CI"] = "false"
    for key in ("HA_STALE_FAIL", "HA_STALE_TIMEOUT"):
        if key in os.environ:
            env[key] = "false"
    with patch.dict("os.environ", env):
        yield


@pytest.fixture
def config_dir(tmp_path):
    """Temporary configuration directory containing mock storage registry."""
    storage_dir = tmp_path / ".storage"
    storage_dir.mkdir()
    return tmp_path


def _write_entity_registry(config_dir, entities_list):
    """Helper to write mock core.entity_registry."""
    registry_file = config_dir / ".storage" / "core.entity_registry"
    data = {
        "version": 1,
        "minor_version": 1,
        "key": "core.entity_registry",
        "data": {"entities": entities_list},
    }
    with open(registry_file, "w", encoding="utf-8") as f:
        json.dump(data, f)


def _mock_states(states_list) -> MagicMock:
    """Helper to mock HA API client response."""
    client = MagicMock()
    client.get_json.return_value = states_list
    return client


def _mock_offline() -> MagicMock:
    """Helper to mock unreachable HA API."""
    client = MagicMock()
    # Mocking HAClient instantiation behavior
    # When HAClient is constructed, it might raise HARequestError or during get_json.
    # To mock both, we can make the constructor raise it or get_json raise it.
    client.get_json.side_effect = HARequestError("API Connection Timeout")
    return client


def test_file_deps_empty():
    """StaleSensorValidator should return empty file dependencies to bypass caching."""
    v = StaleSensorValidator()
    assert v.file_deps() == []


def test_api_offline_degrades_gracefully(config_dir):
    """If the HA API is offline, the validator logs info and returns True."""
    mock_client = _mock_offline()
    with patch("tools.validators.stale_sensors.HAClient", return_value=mock_client):
        v = StaleSensorValidator(str(config_dir))
        assert v.validate_all() is True
        assert any(
            "skipped" in info or "offline" in info or "unreachable" in info
            for info in v.info
        )


def test_stale_sensor_detected(config_dir):
    """Active sensor that has not updated for > 24 hours triggers warning."""
    _write_entity_registry(
        config_dir,
        [
            {
                "entity_id": "sensor.test_temp",
                "platform": "zha",
                "disabled_by": None,
                "hidden_by": None,
            }
        ],
    )
    # Mock states: test_temp last_updated is 25 hours ago
    mock_client = _mock_states(
        [
            {
                "entity_id": "sensor.test_temp",
                "state": "21.5",
                "last_updated": "2026-06-24T20:00:00+00:00",
                "attributes": {},
            }
        ]
    )
    with patch("tools.validators.stale_sensors.HAClient", return_value=mock_client):
        v = StaleSensorValidator(str(config_dir))
        # Freeze target current time to 2026-06-25 21:00:00 UTC (25 hours later)
        v._get_current_time = MagicMock(
            return_value=datetime(2026, 6, 25, 21, 0, 0, tzinfo=UTC)
        )
        assert v.validate_all() is True
        assert any("sensor.test_temp" in w and "stale" in w.lower() for w in v.warnings)


def test_healthy_sensor_ignored(config_dir):
    """Active sensor that updated recently is ignored."""
    _write_entity_registry(
        config_dir,
        [
            {
                "entity_id": "sensor.test_temp",
                "platform": "zha",
                "disabled_by": None,
                "hidden_by": None,
            }
        ],
    )
    # Mock states: last_updated is 1 hour ago
    mock_client = _mock_states(
        [
            {
                "entity_id": "sensor.test_temp",
                "state": "21.5",
                "last_updated": "2026-06-25T20:00:00+00:00",
                "attributes": {},
            }
        ]
    )
    with patch("tools.validators.stale_sensors.HAClient", return_value=mock_client):
        v = StaleSensorValidator(str(config_dir))
        v._get_current_time = MagicMock(
            return_value=datetime(2026, 6, 25, 21, 0, 0, tzinfo=UTC)
        )
        assert v.validate_all() is True
        assert len(v.warnings) == 0


def test_unavailable_state_flagged_immediately(config_dir):
    """M27: a sensor in unavailable/unknown state must surface at once,
    not wait for threshold_hours to elapse."""
    _write_entity_registry(
        config_dir,
        [
            {
                "entity_id": "sensor.dead_battery",
                "platform": "zha",
                "disabled_by": None,
                "hidden_by": None,
            }
        ],
    )
    fresh_now = datetime(2026, 6, 25, 21, 0, 0, tzinfo=UTC)
    mock_client = _mock_states(
        [
            {
                "entity_id": "sensor.dead_battery",
                "state": "unavailable",
                "last_updated": fresh_now.isoformat(),
                "attributes": {},
            }
        ]
    )
    with (
        patch("tools.validators.stale_sensors.HAClient", return_value=mock_client),
        patch.object(StaleSensorValidator, "_get_current_time", return_value=fresh_now),
    ):
        v = StaleSensorValidator(str(config_dir))
        v.validate_all()
    assert any(
        "unavailable" in w or "unknown" in w or "not reporting" in w for w in v.warnings
    ), "unavailable state must surface immediately"
    assert "sensor.dead_battery" in v.stale_entities


def test_parse_timestamp_handles_positive_offset_aest():
    """M27: a +10:00 (AEST) offset must be parsed and normalised to UTC
    correctly so elapsed-hours math is right."""
    from datetime import timedelta

    v = StaleSensorValidator()
    parsed = v.parse_timestamp("2026-07-17T08:00:00+10:00")
    assert parsed is not None
    assert parsed.utcoffset() == timedelta(hours=10)
    now_utc = datetime(2026, 7, 16, 22, 0, 0, tzinfo=UTC)
    delta_hours = (now_utc - parsed).total_seconds() / 3600.0
    assert delta_hours == 0.0


def test_disabled_or_hidden_sensor_ignored(config_dir):
    """Disabled or hidden entities are excluded from staleness checks."""
    _write_entity_registry(
        config_dir,
        [
            {
                "entity_id": "sensor.disabled_temp",
                "platform": "zha",
                "disabled_by": "user",
                "hidden_by": None,
            },
            {
                "entity_id": "sensor.hidden_temp",
                "platform": "zha",
                "disabled_by": None,
                "hidden_by": "user",
            },
        ],
    )
    mock_client = _mock_states(
        [
            {
                "entity_id": "sensor.disabled_temp",
                "state": "21.5",
                "last_updated": "2026-06-24T20:00:00+00:00",
                "attributes": {},
            },
            {
                "entity_id": "sensor.hidden_temp",
                "state": "22.0",
                "last_updated": "2026-06-24T20:00:00+00:00",
                "attributes": {},
            },
        ]
    )
    with patch("tools.validators.stale_sensors.HAClient", return_value=mock_client):
        v = StaleSensorValidator(str(config_dir))
        v._get_current_time = MagicMock(
            return_value=datetime(2026, 6, 25, 21, 0, 0, tzinfo=UTC)
        )
        assert v.validate_all() is True
        assert len(v.warnings) == 0


def test_virtual_platform_ignored(config_dir):
    """Template/group/utility_meter platform entities are ignored."""
    _write_entity_registry(
        config_dir,
        [
            {
                "entity_id": "sensor.template_temp",
                "platform": "template",
                "disabled_by": None,
                "hidden_by": None,
            },
            {
                "entity_id": "sensor.group_temp",
                "platform": "group",
                "disabled_by": None,
                "hidden_by": None,
            },
        ],
    )
    mock_client = _mock_states(
        [
            {
                "entity_id": "sensor.template_temp",
                "state": "21.5",
                "last_updated": "2026-06-24T20:00:00+00:00",
                "attributes": {},
            },
            {
                "entity_id": "sensor.group_temp",
                "state": "22.0",
                "last_updated": "2026-06-24T20:00:00+00:00",
                "attributes": {},
            },
        ]
    )
    with patch("tools.validators.stale_sensors.HAClient", return_value=mock_client):
        v = StaleSensorValidator(str(config_dir))
        v._get_current_time = MagicMock(
            return_value=datetime(2026, 6, 25, 21, 0, 0, tzinfo=UTC)
        )
        assert v.validate_all() is True
        assert len(v.warnings) == 0


def test_restored_entity_flagged(config_dir):
    """Restored entities are flagged as stale immediately."""
    _write_entity_registry(
        config_dir,
        [
            {
                "entity_id": "sensor.restored_temp",
                "platform": "mqtt",
                "disabled_by": None,
                "hidden_by": None,
            }
        ],
    )
    # Restored: True in attributes, but last_updated is 5 mins ago (HA startup time)
    mock_client = _mock_states(
        [
            {
                "entity_id": "sensor.restored_temp",
                "state": "21.5",
                "last_updated": "2026-06-25T20:55:00+00:00",
                "attributes": {"restored": True},
            }
        ]
    )
    with patch("tools.validators.stale_sensors.HAClient", return_value=mock_client):
        v = StaleSensorValidator(str(config_dir))
        v._get_current_time = MagicMock(
            return_value=datetime(2026, 6, 25, 21, 0, 0, tzinfo=UTC)
        )
        assert v.validate_all() is True
        assert any(
            "sensor.restored_temp" in w and "restored" in w.lower() for w in v.warnings
        )


def test_custom_heartbeat_timestamp(config_dir):
    """Zigbee last_seen attribute is checked if present, catching hidden staleness."""
    _write_entity_registry(
        config_dir,
        [
            {
                "entity_id": "sensor.z2m_temp",
                "platform": "mqtt",
                "disabled_by": None,
                "hidden_by": None,
            }
        ],
    )
    # last_updated is fresh, but last_seen (heartbeat) attribute is stale
    mock_client = _mock_states(
        [
            {
                "entity_id": "sensor.z2m_temp",
                "state": "21.5",
                "last_updated": "2026-06-25T20:55:00+00:00",
                "attributes": {"last_seen": "2026-06-24T20:00:00Z"},
            }
        ]
    )
    with patch("tools.validators.stale_sensors.HAClient", return_value=mock_client):
        v = StaleSensorValidator(str(config_dir))
        v._get_current_time = MagicMock(
            return_value=datetime(2026, 6, 25, 21, 0, 0, tzinfo=UTC)
        )
        assert v.validate_all() is True
        assert any("sensor.z2m_temp" in w and "stale" in w.lower() for w in v.warnings)


def test_numeric_heartbeat_timestamp(config_dir):
    """Validator parses integer/float epochs in heartbeats."""
    _write_entity_registry(
        config_dir,
        [
            {
                "entity_id": "sensor.numeric_temp",
                "platform": "mqtt",
                "disabled_by": None,
                "hidden_by": None,
            }
        ],
    )
    # epoch seconds representation
    mock_client = _mock_states(
        [
            {
                "entity_id": "sensor.numeric_temp",
                "state": "21.5",
                "last_updated": "2026-06-25T20:55:00+00:00",
                "attributes": {"last_reported": 1782331200},  # epoch seconds
            }
        ]
    )
    with patch("tools.validators.stale_sensors.HAClient", return_value=mock_client):
        v = StaleSensorValidator(str(config_dir))
        v._get_current_time = MagicMock(
            return_value=datetime.fromtimestamp(1782421200, tz=UTC)
        )
        assert v.validate_all() is True
        assert any(
            "sensor.numeric_temp" in w and "stale" in w.lower() for w in v.warnings
        )


def test_ci_environment_skips_validation(config_dir):
    """Skipping checking and returning True in CI environment to avoid hangs."""
    mock_client = _mock_states([])
    with (
        patch("tools.validators.stale_sensors.HAClient", return_value=mock_client),
        patch("os.getenv", side_effect=lambda k, d=None: "true" if k == "CI" else d),
    ):
        v = StaleSensorValidator(str(config_dir))
        assert v.validate_all() is True
        assert any("CI environment" in info for info in v.info)


def test_missing_registry_fallback(config_dir):
    """Missing registry file degrades gracefully to states-only check."""
    # We do NOT write core.entity_registry to config_dir, so it's missing.
    mock_client = _mock_states(
        [
            {
                "entity_id": "sensor.unknown_temp",
                "state": "21.5",
                "last_updated": "2026-06-24T20:00:00+00:00",
                "attributes": {},
            }
        ]
    )
    with patch("tools.validators.stale_sensors.HAClient", return_value=mock_client):
        v = StaleSensorValidator(str(config_dir))
        v._get_current_time = MagicMock(
            return_value=datetime(2026, 6, 25, 21, 0, 0, tzinfo=UTC)
        )
        assert v.validate_all() is True
        assert any(
            "sensor.unknown_temp" in w and "stale" in w.lower() for w in v.warnings
        )
        assert any(
            "missing" in info.lower() or "fallback" in info.lower() for info in v.info
        )


def test_retry_on_registry_read_failure(config_dir):
    """Validator retries once if registry read fails with JSONDecodeError."""
    # We will write invalid json, and patch open or json.load to fail
    # on first call but succeed on second retry.
    _write_entity_registry(
        config_dir,
        [
            {
                "entity_id": "sensor.test_temp",
                "platform": "zha",
                "disabled_by": None,
                "hidden_by": None,
            }
        ],
    )

    # Let's mock open/json.load behavior.
    mock_client = _mock_states(
        [
            {
                "entity_id": "sensor.test_temp",
                "state": "21.5",
                "last_updated": "2026-06-24T20:00:00+00:00",
                "attributes": {},
            }
        ]
    )

    call_count = 0
    original_json_load = json.load

    def mock_json_load(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise json.JSONDecodeError("Expecting value", "", 0)
        return original_json_load(*args, **kwargs)

    with (
        patch("tools.validators.stale_sensors.HAClient", return_value=mock_client),
        patch("json.load", side_effect=mock_json_load),
        patch("time.sleep") as mock_sleep,
    ):
        v = StaleSensorValidator(str(config_dir))
        v._get_current_time = MagicMock(
            return_value=datetime(2026, 6, 25, 21, 0, 0, tzinfo=UTC)
        )
        assert v.validate_all() is True
        assert any("sensor.test_temp" in w for w in v.warnings)
        assert call_count == 2
        mock_sleep.assert_called_once_with(0.1)


def test_ha_stale_timeout_env_overrides_default(config_dir):
    """HA_STALE_TIMEOUT env var overrides the default 2-second timeout."""
    with patch("tools.validators.stale_sensors.HAClient") as mock_class:
        inst = MagicMock()
        inst.get_json.return_value = []
        mock_class.return_value = inst
        with patch.dict("os.environ", {"HA_STALE_TIMEOUT": "9"}):
            v = StaleSensorValidator(str(config_dir))
            v.validate_all()
            mock_class.assert_called_once()
            assert mock_class.call_args.kwargs["timeout"] == 9


def test_fail_on_stale_mode_returns_false_when_stale(config_dir):
    """fail_on_stale=True + stale sensors → validate_all returns False."""
    _write_entity_registry(
        config_dir,
        [
            {
                "entity_id": "sensor.test_temp",
                "platform": "zha",
                "disabled_by": None,
                "hidden_by": None,
            }
        ],
    )
    mock_client = _mock_states(
        [
            {
                "entity_id": "sensor.test_temp",
                "state": "21.5",
                "last_updated": "2026-06-24T20:00:00+00:00",
                "attributes": {},
            }
        ]
    )
    with patch("tools.validators.stale_sensors.HAClient", return_value=mock_client):
        v = StaleSensorValidator(str(config_dir), fail_on_stale=True)
        v._get_current_time = MagicMock(
            return_value=datetime(2026, 6, 25, 21, 0, 0, tzinfo=UTC)
        )
        assert v.validate_all() is False
        assert any("failed" in e.lower() for e in v.errors)


def test_fail_on_stale_off_keeps_diagnostic(config_dir):
    """fail_on_stale=False (default) returns True even when stale."""
    _write_entity_registry(
        config_dir,
        [
            {
                "entity_id": "sensor.test_temp",
                "platform": "zha",
                "disabled_by": None,
                "hidden_by": None,
            }
        ],
    )
    mock_client = _mock_states(
        [
            {
                "entity_id": "sensor.test_temp",
                "state": "21.5",
                "last_updated": "2026-06-24T20:00:00+00:00",
                "attributes": {},
            }
        ]
    )
    with patch("tools.validators.stale_sensors.HAClient", return_value=mock_client):
        v = StaleSensorValidator(str(config_dir), fail_on_stale=False)
        v._get_current_time = MagicMock(
            return_value=datetime(2026, 6, 25, 21, 0, 0, tzinfo=UTC)
        )
        assert v.validate_all() is True
        assert any("sensor.test_temp" in w for w in v.warnings)


def test_fail_on_stale_no_stale_returns_true(config_dir):
    """fail_on_stale=True with no stale sensors returns True."""
    _write_entity_registry(
        config_dir,
        [
            {
                "entity_id": "sensor.test_temp",
                "platform": "zha",
                "disabled_by": None,
                "hidden_by": None,
            }
        ],
    )
    mock_client = _mock_states(
        [
            {
                "entity_id": "sensor.test_temp",
                "state": "21.5",
                "last_updated": "2026-06-25T20:00:00+00:00",
                "attributes": {},
            }
        ]
    )
    with patch("tools.validators.stale_sensors.HAClient", return_value=mock_client):
        v = StaleSensorValidator(str(config_dir), fail_on_stale=True)
        v._get_current_time = MagicMock(
            return_value=datetime(2026, 6, 25, 21, 0, 0, tzinfo=UTC)
        )
        assert v.validate_all() is True
        assert len(v.warnings) == 0


def test_fail_on_stale_env_var_picked_up_after_load_env(config_dir, monkeypatch):
    """HA_STALE_FAIL env var is read after load_env_file() in validate_all()."""
    monkeypatch.setenv("HA_URL", "http://localhost:8123")
    monkeypatch.setenv("HA_TOKEN", "mock_token")
    _write_entity_registry(
        config_dir,
        [
            {
                "entity_id": "sensor.test_temp",
                "platform": "zha",
                "disabled_by": None,
                "hidden_by": None,
            }
        ],
    )
    mock_client = _mock_states(
        [
            {
                "entity_id": "sensor.test_temp",
                "state": "21.5",
                "last_updated": "2026-06-24T20:00:00+00:00",
                "attributes": {},
            }
        ]
    )
    with patch("tools.validators.stale_sensors.HAClient", return_value=mock_client):
        v = StaleSensorValidator(str(config_dir))
        monkeypatch.setenv("HA_STALE_FAIL", "true")
        v._get_current_time = MagicMock(
            return_value=datetime(2026, 6, 25, 21, 0, 0, tzinfo=UTC)
        )
        assert v.fail_on_stale is False
        assert v.validate_all() is False
        assert any("failed" in e.lower() for e in v.errors)


def test_naive_datetime_handling():
    """Validator parses naive ISO strings and treats them as UTC timezone-aware."""
    v = StaleSensorValidator()
    # Naive ISO format string (no timezone info)
    dt = v.parse_timestamp("2026-06-25T20:00:00")
    assert dt is not None
    assert dt.tzinfo == UTC
    assert dt.hour == 20


def test_boolean_handling_in_parse_timestamp():
    """Validator ignores boolean values in parse_timestamp."""
    v = StaleSensorValidator()
    assert v.parse_timestamp(True) is None
    assert v.parse_timestamp(False) is None


def test_malformed_registry_json(config_dir):
    """Validator falls back gracefully if registry JSON is malformed list."""
    registry_file = config_dir / ".storage" / "core.entity_registry"
    # Write a JSON list instead of a dict mapping
    with open(registry_file, "w", encoding="utf-8") as f:
        f.write("[]")

    mock_client = _mock_states(
        [
            {
                "entity_id": "sensor.test_temp",
                "state": "21.5",
                "last_updated": "2026-06-24T20:00:00+00:00",
                "attributes": {},
            }
        ]
    )

    with patch("tools.validators.stale_sensors.HAClient", return_value=mock_client):
        v = StaleSensorValidator(str(config_dir))
        v._get_current_time = MagicMock(
            return_value=datetime(2026, 6, 25, 21, 0, 0, tzinfo=UTC)
        )
        assert v.validate_all() is True
        # Verify fallback warning was logged (first warning is the
        # registry load failure)
        assert any(
            "fallback" in w.lower() or "failed to read" in w.lower() for w in v.warnings
        )
        # Verify stale sensor detection still worked
        assert any("sensor.test_temp" in w for w in v.warnings)


def test_main_dispatch_with_ci_short_circuit(monkeypatch):
    """main() returns 0 when CI=true short-circuits stale sensor validation."""
    from tools.validators.stale_sensors import main

    monkeypatch.setenv("CI", "true")
    monkeypatch.setattr("sys.argv", ["stale_sensors", "config"])
    assert main() == 0


# ── Timestamp parsing variants (covers 128-129, 148-156, 159) ──────────


def test_parse_timestamp_milliseconds_epoch():
    """parse_timestamp normalises ms-epoch timestamps by dividing by 1000."""
    v = StaleSensorValidator()
    result = v.parse_timestamp(1782331200000)
    assert result == datetime.fromtimestamp(1782331200, tz=UTC)


def test_parse_timestamp_numeric_string():
    """parse_timestamp handles numeric strings via float conversion."""
    v = StaleSensorValidator()
    assert v.parse_timestamp("1782331200") == datetime.fromtimestamp(1782331200, tz=UTC)


def test_parse_timestamp_ms_string():
    """Millisecond epoch as a string is normalised by dividing by 1000."""
    v = StaleSensorValidator()
    result = v.parse_timestamp("1782331200000")
    assert result == datetime.fromtimestamp(1782331200, tz=UTC)


def test_parse_timestamp_malformed_string_appends_warning():
    """A non-numeric, non-ISO string appends a warning and returns None."""
    v = StaleSensorValidator()
    assert v.parse_timestamp("not a date") is None
    assert any("Failed to parse" in w for w in v.warnings)


def test_parse_timestamp_unsupported_type_returns_none():
    """parse_timestamp returns None for list/dict values."""
    v = StaleSensorValidator()
    assert v.parse_timestamp([1, 2]) is None
    assert v.parse_timestamp({"nested": True}) is None


# ── Invalid HA_STALE_TIMEOUT (covers 194) ──────────────────────────────


def test_missing_ha_url_token_skips_gracefully(config_dir):
    """When HA_URL or HA_TOKEN are not set, skip with info and return True."""
    with patch.dict("os.environ", {}, clear=True):
        v = StaleSensorValidator(str(config_dir))
        assert v.validate_all() is True
        assert any("not set" in i for i in v.info)


def test_invalid_ha_stale_timeout_warns(config_dir):
    """Non-integer HA_STALE_TIMEOUT logs an info warning with the default fallback."""
    with patch("tools.validators.stale_sensors.HAClient") as mock_class:
        inst = MagicMock()
        inst.get_json.return_value = []
        mock_class.return_value = inst
        with patch.dict("os.environ", {"HA_STALE_TIMEOUT": "notanint"}):
            v = StaleSensorValidator(str(config_dir))
            v.validate_all()
            assert any("must be an integer" in i for i in v.info)


# ── API shape-guard continue paths (covers 203-206, 213, 217, 221, 270) ──


def test_states_not_list_is_skipped(config_dir):
    """When /api/states returns a dict instead of a list, skip with info."""
    client = MagicMock()
    client.get_json.return_value = {}
    with patch("tools.validators.stale_sensors.HAClient", return_value=client):
        v = StaleSensorValidator(str(config_dir))
        assert v.validate_all() is True
        assert any("invalid API states format" in i for i in v.info)


def test_non_dict_state_entry_skipped(config_dir):
    """Non-dict items in the states list are skipped (continue at 213)."""
    with patch(
        "tools.validators.stale_sensors.HAClient",
        return_value=_mock_states(["oops", 42]),
    ):
        assert StaleSensorValidator(str(config_dir)).validate_all() is True


def test_dotless_entity_id_skipped(config_dir):
    """State entries without a '.' in entity_id are skipped (continue at 217)."""
    states = [
        {
            "entity_id": "no_dot",
            "last_updated": "2026-06-24T20:00:00+00:00",
            "attributes": {},
        }
    ]
    with patch(
        "tools.validators.stale_sensors.HAClient",
        return_value=_mock_states(states),
    ):
        assert StaleSensorValidator(str(config_dir)).validate_all() is True


def test_non_sensor_domain_skipped(config_dir):
    """States with domains not in only_domains are skipped (continue at 221)."""
    states = [
        {
            "entity_id": "light.x",
            "last_updated": "2026-06-24T20:00:00+00:00",
            "attributes": {},
        }
    ]
    with patch(
        "tools.validators.stale_sensors.HAClient",
        return_value=_mock_states(states),
    ):
        assert StaleSensorValidator(str(config_dir)).validate_all() is True


def test_sensor_with_unparseable_baseline_skipped(config_dir):
    """sensor.x with garbage last_updated yields no baseline → continue (270)."""
    states = [
        {
            "entity_id": "sensor.x",
            "last_updated": "garbage",
            "attributes": {},
        }
    ]
    with patch(
        "tools.validators.stale_sensors.HAClient",
        return_value=_mock_states(states),
    ):
        assert StaleSensorValidator(str(config_dir)).validate_all() is True


# ── Binary sensor without heartbeat (covers 261) ───────────────────────
# NOTE: Must override only_domains={"binary_sensor"} so the entity is not
# filtered out at line 221 before reaching the heartbeat check at 258-261.


def test_binary_sensor_without_heartbeat_skipped(config_dir):
    """binary_sensor without last_seen/last_reported → continue (261)."""
    states = [
        {
            "entity_id": "binary_sensor.x",
            "last_updated": "2026-06-24T20:00:00+00:00",
            "attributes": {},
        }
    ]
    with patch(
        "tools.validators.stale_sensors.HAClient",
        return_value=_mock_states(states),
    ):
        v = StaleSensorValidator(str(config_dir), only_domains={"binary_sensor"})
        assert v.validate_all() is True


def test_fail_on_stale_ignores_non_staleness_warnings(config_dir):
    """A registry-read failure (warning) with fresh sensors must NOT trip fail mode."""
    (config_dir / ".storage" / "core.entity_registry").write_text("{ not valid json")
    fresh = [
        {
            "entity_id": "sensor.ok",
            "state": "1",
            "last_updated": "2026-07-17T00:00:00+00:00",
            "attributes": {},
        }
    ]
    mock_client = _mock_states(fresh)
    with (
        patch("tools.validators.stale_sensors.HAClient", return_value=mock_client),
        patch.object(
            StaleSensorValidator,
            "_get_current_time",
            return_value=datetime(2026, 7, 17, 0, 0, 10, tzinfo=UTC),
        ),
    ):
        v = StaleSensorValidator(
            str(config_dir), fail_on_stale=True, threshold_hours=24
        )
        assert v.validate_all() is True
    assert len(v.warnings) >= 1
    assert len(v.errors) == 0


def test_fail_on_stale_trips_on_real_stale_sensor(config_dir):
    """A genuinely stale sensor with fail_on_stale=True must fail (return False)."""
    _write_entity_registry(
        config_dir,
        [
            {"entity_id": "sensor.stale", "platform": "zha", "disabled_by": None},
        ],
    )
    stale = [
        {
            "entity_id": "sensor.stale",
            "state": "1",
            "last_updated": "2026-07-15T00:00:00+00:00",
            "attributes": {},
        }
    ]
    mock_client = _mock_states(stale)
    with (
        patch("tools.validators.stale_sensors.HAClient", return_value=mock_client),
        patch.object(
            StaleSensorValidator,
            "_get_current_time",
            return_value=datetime(2026, 7, 17, 0, 0, 0, tzinfo=UTC),
        ),
    ):
        v = StaleSensorValidator(
            str(config_dir), fail_on_stale=True, threshold_hours=24
        )
        assert v.validate_all() is False
    assert any("Stale sensor check failed" in e for e in v.errors)
