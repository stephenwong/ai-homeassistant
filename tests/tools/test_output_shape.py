"""Tests for tools/output_shape.py — shared JSON output-shaping helper."""

import pytest

from tools.output_shape import ABBREV_MAP, apply_output_shape


class TestNoOp:
    def test_no_kwargs_returns_unchanged(self):
        data = [{"a": 1}, {"b": 2}]
        assert apply_output_shape(data) is data

    def test_none_explicit_returns_unchanged(self):
        data = {"x": 1}
        assert apply_output_shape(data, first=None, pick=None, max_chars=None) is data


class TestFirst:
    def test_list_slice(self):
        data = [{"id": i} for i in range(10)]
        assert apply_output_shape(data, first=3) == [{"id": 0}, {"id": 1}, {"id": 2}]

    def test_dict_slice(self):
        data = {"a": 1, "b": 2, "c": 3, "d": 4}
        result = apply_output_shape(data, first=2)
        assert len(result) == 2

    def test_scalar_wraps_in_list(self):
        assert apply_output_shape(42, first=3) == [42]

    def test_overcount_clamps(self):
        data = [{"id": i} for i in range(3)]
        assert len(apply_output_shape(data, first=999)) == 3

    def test_empty_list(self):
        assert apply_output_shape([], first=5) == []

    def test_empty_dict(self):
        assert apply_output_shape({}, first=5) == {}

    def test_none_no_change(self):
        data = [1, 2, 3]
        assert apply_output_shape(data, first=None) is data


class TestPick:
    def test_list_of_dicts(self):
        data = [
            {"entity_id": "sensor.a", "state": "on", "attributes": {"x": 1}},
            {"entity_id": "sensor.b", "state": "off", "attributes": {"x": 0}},
        ]
        assert apply_output_shape(data, pick="entity_id,state") == [
            {"entity_id": "sensor.a", "state": "on"},
            {"entity_id": "sensor.b", "state": "off"},
        ]

    def test_missing_keys_omitted(self):
        data = [{"entity_id": "sensor.a", "state": "on"}]
        assert apply_output_shape(data, pick="entity_id,nonexistent") == [
            {"entity_id": "sensor.a"}
        ]

    def test_single_dict(self):
        data = {"entity_id": "sensor.a", "state": "on", "extra": "x"}
        assert apply_output_shape(data, pick="state") == {"state": "on"}

    def test_non_dict_items_pass_through(self):
        data = [42, {"entity_id": "sensor.a"}]
        assert apply_output_shape(data, pick="entity_id") == [
            42,
            {"entity_id": "sensor.a"},
        ]

    def test_empty_string_no_change(self):
        data = [{"a": 1}]
        assert apply_output_shape(data, pick="") == [{"a": 1}]

    def test_whitespace_around_fields(self):
        data = [{"entity_id": "sensor.a", "state": "on"}]
        assert apply_output_shape(data, pick=" entity_id , state ") == [
            {"entity_id": "sensor.a", "state": "on"}
        ]

    def test_scalar_passes_through(self):
        assert apply_output_shape(42, pick="state") == 42


class TestAbbrev:
    def test_renames_known_keys(self):
        data = [
            {
                "entity_id": "sensor.a",
                "state": "on",
                "attributes": {},
                "context": {"id": "x"},
                "last_changed": "t1",
                "last_updated": "t2",
            }
        ]
        assert apply_output_shape(data, abbrev=True) == [
            {
                "e": "sensor.a",
                "s": "on",
                "at": {},
                "ctx": {"id": "x"},
                "lc": "t1",
                "lu": "t2",
            }
        ]

    def test_unknown_keys_pass_through(self):
        assert apply_output_shape(
            [{"entity_id": "sensor.a", "custom": 42}], abbrev=True
        ) == [{"e": "sensor.a", "custom": 42}]

    def test_single_dict(self):
        assert apply_output_shape(
            {"entity_id": "sensor.a", "state": "on"}, abbrev=True
        ) == {"e": "sensor.a", "s": "on"}

    def test_scalar_passes_through(self):
        assert apply_output_shape(42, abbrev=True) == 42

    def test_abbrev_map_contents(self):
        assert ABBREV_MAP["entity_id"] == "e"
        assert ABBREV_MAP["state"] == "s"

    def test_non_dict_in_list_passes_through(self):
        assert apply_output_shape([42, {"entity_id": "a"}], abbrev=True) == [
            42,
            {"e": "a"},
        ]


class TestMaxChars:
    def test_truncates_list_with_marker(self):
        data = [{"id": i, "data": "x" * 50} for i in range(20)]
        result = apply_output_shape(data, max_chars=200)
        assert isinstance(result, list)
        assert result[-1].get("_truncated") is True
        assert result[-1]["total"] == 20

    def test_zero_disables(self):
        data = [{"id": i} for i in range(5)]
        assert apply_output_shape(data, max_chars=0) == data

    def test_negative_disables(self):
        data = [{"id": i} for i in range(5)]
        assert apply_output_shape(data, max_chars=-1) == data

    def test_small_data_unchanged(self):
        data = [{"id": 1}]
        assert apply_output_shape(data, max_chars=500) == [{"id": 1}]

    def test_non_list_passes_through(self):
        data = {"big": "x" * 1000}
        # dict is not truncated structurally
        result = apply_output_shape(data, max_chars=10)
        assert result == data

    def test_output_fits_under_limit(self):
        data = [{"data": "x" * 100} for _ in range(10)]
        result = apply_output_shape(data, max_chars=300)
        serialized = pytest.importorskip("json").dumps(result)
        assert len(serialized) <= 300

    def test_only_marker_fits(self):
        """When every item is larger than max_chars, return just the marker."""
        data = [{"very_long_key_" * 50: "x"}]
        result = apply_output_shape(data, max_chars=20)
        assert result == [{"_truncated": True, "shown": 0, "total": 1}]


class TestOrdering:
    """Transforms apply in order: first → pick → abbrev → max_chars."""

    def test_first_then_pick(self):
        data = [
            {"entity_id": "sensor.a", "state": "on"},
            {"entity_id": "sensor.b", "state": "off"},
            {"entity_id": "sensor.c", "state": "unknown"},
        ]
        assert apply_output_shape(data, first=2, pick="state") == [
            {"state": "on"},
            {"state": "off"},
        ]

    def test_pick_then_abbrev(self):
        data = [{"entity_id": "sensor.a", "state": "on", "attributes": {}}]
        assert apply_output_shape(data, pick="entity_id,state", abbrev=True) == [
            {"e": "sensor.a", "s": "on"}
        ]

    def test_first_then_abbrev(self):
        data = [
            {"entity_id": "sensor.a", "state": "on"},
            {"entity_id": "sensor.b", "state": "off"},
        ]
        assert apply_output_shape(data, first=1, abbrev=True) == [
            {"e": "sensor.a", "s": "on"}
        ]

    def test_first_pick_abbrev_maxchars(self):
        data = [
            {"entity_id": f"sensor.{i}", "state": str(i), "attributes": {"x": i}}
            for i in range(50)
        ]
        result = apply_output_shape(
            data, first=20, pick="entity_id,state", abbrev=True, max_chars=100
        )
        assert isinstance(result, list)
        assert result[-1].get("_truncated") is True
