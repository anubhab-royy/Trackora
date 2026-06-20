"""Tests for SchemaVersion value object."""

from __future__ import annotations

import re
from dataclasses import FrozenInstanceError

import pytest

from trackora.core.schema_version import SchemaVersion


# ── from_string — valid cases ─────────────────────────────────────


class TestFromString:
    def test_from_string_valid(self) -> None:
        version = SchemaVersion.from_string("2.0.0")
        assert version.major == 2
        assert version.minor == 0
        assert version.patch == 0

    def test_from_string_minimum(self) -> None:
        version = SchemaVersion.from_string("0.0.0")
        assert version.major == 0
        assert version.minor == 0
        assert version.patch == 0

    def test_from_string_multi_digit(self) -> None:
        version = SchemaVersion.from_string("12.34.56")
        assert version.major == 12
        assert version.minor == 34
        assert version.patch == 56

    def test_from_string_large_numbers(self) -> None:
        version = SchemaVersion.from_string("999.888.777")
        assert version.major == 999
        assert version.minor == 888
        assert version.patch == 777


class TestFromStringInvalid:
    @pytest.mark.parametrize("invalid", [
        "2.0",         # missing patch
        "v2.0.0",      # v prefix
        "2.0.0.0",     # four parts
        "abc",         # non-numeric
        "",            # empty
        "2.0.0-alpha", # semver prerelease
        "2.0.0+build", # semver build
        ".0.0",        # leading dot
        "2..0",        # double dot
        "2.0.",        # trailing dot
        " 2.0.0",      # leading space
        "2.0.0 ",      # trailing space
    ])
    def test_from_string_invalid_format(self, invalid: str) -> None:
        with pytest.raises(ValueError, match="Invalid schema version"):
            SchemaVersion.from_string(invalid)

    @pytest.mark.parametrize("invalid", [
        "-1.0.0",
        "2.-1.0",
        "2.0.-1",
    ])
    def test_from_string_negative(self, invalid: str) -> None:
        with pytest.raises(ValueError, match="Invalid schema version"):
            SchemaVersion.from_string(invalid)


# ── is_valid_format ──────────────────────────────────────────────


class TestIsValidFormat:
    @pytest.mark.parametrize("valid", [
        "0.0.0",
        "1.0.0",
        "2.0.0",
        "1.1.0",
        "1.1.1",
        "12.34.56",
        "999.999.999",
    ])
    def test_valid_format_returns_true(self, valid: str) -> None:
        assert SchemaVersion.is_valid_format(valid) is True

    @pytest.mark.parametrize("invalid", [
        "2.0",
        "v2.0.0",
        "2.0.0.0",
        "abc",
        "",
        "2.0.0-alpha",
        "-1.0.0",
    ])
    def test_invalid_format_returns_false(self, invalid: str) -> None:
        assert SchemaVersion.is_valid_format(invalid) is False


# ── current_app_version ──────────────────────────────────────────


class TestCurrentAppVersion:
    def test_current_app_version_matches(self) -> None:
        from trackora import __version__
        expected = SchemaVersion.from_string(__version__)
        assert SchemaVersion.current_app_version() == expected

    def test_current_app_version_is_schema_version(self) -> None:
        version = SchemaVersion.current_app_version()
        assert isinstance(version, SchemaVersion)
        assert version.major >= 0
        assert version.minor >= 0
        assert version.patch >= 0


# ── string serialization ─────────────────────────────────────────


class TestStr:
    def test_str_representation(self) -> None:
        assert str(SchemaVersion(2, 0, 0)) == "2.0.0"
        assert str(SchemaVersion(1, 1, 0)) == "1.1.0"
        assert str(SchemaVersion(0, 0, 0)) == "0.0.0"
        assert str(SchemaVersion(12, 34, 56)) == "12.34.56"


class TestToDict:
    def test_to_dict(self) -> None:
        result = SchemaVersion(2, 0, 0).to_dict()
        assert result == {"major": 2, "minor": 0, "patch": 0}

    def test_to_dict_round_trip(self) -> None:
        original = SchemaVersion(1, 1, 0)
        d = original.to_dict()
        reconstructed = SchemaVersion(d["major"], d["minor"], d["patch"])
        assert reconstructed == original


# ── equality ─────────────────────────────────────────────────────


class TestEquality:
    def test_eq_same(self) -> None:
        assert SchemaVersion(2, 0, 0) == SchemaVersion(2, 0, 0)

    def test_eq_different_major(self) -> None:
        assert not (SchemaVersion(2, 0, 0) == SchemaVersion(1, 0, 0))

    def test_eq_different_minor(self) -> None:
        assert not (SchemaVersion(2, 0, 0) == SchemaVersion(2, 1, 0))

    def test_eq_different_patch(self) -> None:
        assert not (SchemaVersion(2, 0, 0) == SchemaVersion(2, 0, 1))

    def test_eq_with_non_version(self) -> None:
        assert not (SchemaVersion(2, 0, 0) == "2.0.0")

    def test_ne(self) -> None:
        assert SchemaVersion(2, 0, 0) != SchemaVersion(1, 0, 0)

    def test_ne_equal(self) -> None:
        assert not (SchemaVersion(2, 0, 0) != SchemaVersion(2, 0, 0))


# ── less than ────────────────────────────────────────────────────


class TestLessThan:
    def test_lt_major(self) -> None:
        assert SchemaVersion(1, 9, 9) < SchemaVersion(2, 0, 0)

    def test_lt_minor(self) -> None:
        assert SchemaVersion(2, 0, 0) < SchemaVersion(2, 1, 0)

    def test_lt_patch(self) -> None:
        assert SchemaVersion(2, 0, 0) < SchemaVersion(2, 0, 1)

    def test_lt_equal(self) -> None:
        assert not (SchemaVersion(2, 0, 0) < SchemaVersion(2, 0, 0))

    def test_lt_greater(self) -> None:
        assert not (SchemaVersion(2, 0, 0) < SchemaVersion(1, 0, 0))

    def test_le_less(self) -> None:
        assert SchemaVersion(1, 0, 0) <= SchemaVersion(2, 0, 0)

    def test_le_equal(self) -> None:
        assert SchemaVersion(2, 0, 0) <= SchemaVersion(2, 0, 0)

    def test_le_greater(self) -> None:
        assert not (SchemaVersion(2, 0, 0) <= SchemaVersion(1, 0, 0))

    def test_lt_with_non_version_not_implemented(self) -> None:
        result = SchemaVersion(2, 0, 0).__lt__("not a version")
        assert result is NotImplemented


# ── greater than ─────────────────────────────────────────────────


class TestGreaterThan:
    def test_gt_major(self) -> None:
        assert SchemaVersion(2, 0, 0) > SchemaVersion(1, 9, 9)

    def test_gt_minor(self) -> None:
        assert SchemaVersion(2, 1, 0) > SchemaVersion(2, 0, 0)

    def test_gt_patch(self) -> None:
        assert SchemaVersion(2, 0, 1) > SchemaVersion(2, 0, 0)

    def test_gt_equal(self) -> None:
        assert not (SchemaVersion(2, 0, 0) > SchemaVersion(2, 0, 0))

    def test_gt_less(self) -> None:
        assert not (SchemaVersion(1, 0, 0) > SchemaVersion(2, 0, 0))

    def test_ge_greater(self) -> None:
        assert SchemaVersion(2, 0, 0) >= SchemaVersion(1, 0, 0)

    def test_ge_equal(self) -> None:
        assert SchemaVersion(2, 0, 0) >= SchemaVersion(2, 0, 0)

    def test_ge_less(self) -> None:
        assert not (SchemaVersion(1, 0, 0) >= SchemaVersion(2, 0, 0))


# ── sorting ──────────────────────────────────────────────────────


class TestSorting:
    def test_sorting_ascending(self) -> None:
        unsorted = [
            SchemaVersion(2, 0, 0),
            SchemaVersion(1, 0, 0),
            SchemaVersion(1, 1, 0),
            SchemaVersion(2, 0, 1),
        ]
        expected = [
            SchemaVersion(1, 0, 0),
            SchemaVersion(1, 1, 0),
            SchemaVersion(2, 0, 0),
            SchemaVersion(2, 0, 1),
        ]
        assert sorted(unsorted) == expected

    def test_sorting_reverse(self) -> None:
        unsorted = [
            SchemaVersion(1, 0, 0),
            SchemaVersion(2, 0, 0),
        ]
        expected = [
            SchemaVersion(2, 0, 0),
            SchemaVersion(1, 0, 0),
        ]
        assert sorted(unsorted, reverse=True) == expected


# ── immutability ─────────────────────────────────────────────────


class TestImmutability:
    def test_cannot_modify_major(self) -> None:
        v = SchemaVersion(2, 0, 0)
        with pytest.raises(FrozenInstanceError):
            v.major = 3  # type: ignore[misc]

    def test_cannot_modify_minor(self) -> None:
        v = SchemaVersion(2, 0, 0)
        with pytest.raises(FrozenInstanceError):
            v.minor = 1  # type: ignore[misc]

    def test_cannot_modify_patch(self) -> None:
        v = SchemaVersion(2, 0, 0)
        with pytest.raises(FrozenInstanceError):
            v.patch = 1  # type: ignore[misc]


# ── hashable ─────────────────────────────────────────────────────


class TestHashable:
    def test_use_as_dict_key(self) -> None:
        mapping = {
            SchemaVersion(1, 0, 0): "old",
            SchemaVersion(2, 0, 0): "current",
        }
        assert mapping[SchemaVersion(1, 0, 0)] == "old"
        assert mapping[SchemaVersion(2, 0, 0)] == "current"

    def test_use_in_set(self) -> None:
        versions = {
            SchemaVersion(1, 0, 0),
            SchemaVersion(2, 0, 0),
            SchemaVersion(2, 0, 0),  # duplicate
        }
        assert len(versions) == 2

    def test_hash_consistent(self) -> None:
        v1 = SchemaVersion(2, 0, 0)
        v2 = SchemaVersion(2, 0, 0)
        assert hash(v1) == hash(v2)


# ── ordering protocol ────────────────────────────────────────────


class TestOrderingProtocol:
    def test_total_ordering_consistent(self) -> None:
        a = SchemaVersion(1, 0, 0)
        b = SchemaVersion(2, 0, 0)
        c = SchemaVersion(2, 0, 0)
        # Reflexive
        assert a <= a
        assert a >= a
        # Transitive
        assert a < b and b == c and a < c
        # Antisymmetric
        assert a <= b and b >= a
