"""Tests for prompt helper utilities."""

from __future__ import annotations

import pytest

from prompts.helpers import (
    format_description_for_name_match,
    format_description_for_phase1,
    format_user_cost,
    normalize_description,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, ""),
        ("", ""),
        ("  ", ""),
        ("N/A", ""),
        ("na", ""),
        ("NULL", ""),
        ("  Valid description  ", "Valid description"),
    ],
)
def test_normalize_description(raw, expected):
    assert normalize_description(raw) == expected


def test_format_description_for_phase1():
    assert format_description_for_phase1("") == "(empty)"
    assert format_description_for_phase1("Dell laptop") == "Dell laptop"


def test_format_description_for_name_match():
    assert format_description_for_name_match("") == "(empty - validation based on name only)"
    assert format_description_for_name_match("Office chair") == "Office chair"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "(not provided)"),
        (50000, "50000"),
        ("12,500", "12,500"),
    ],
)
def test_format_user_cost(value, expected):
    assert format_user_cost(value) == expected
