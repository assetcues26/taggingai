"""Tests for pure utility functions in function_app."""

from __future__ import annotations

import json

import pytest


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        (42, 42),
        ("1001, ", 1001),
        ("abc", None),
        ("", None),
    ],
)
def test_to_int_or_none(function_app, value, expected):
    assert function_app.to_int_or_none(value) == expected


@pytest.mark.parametrize(
    ("detected", "user", "status", "percent"),
    [
        ("00123", "00123", "Y", 100),
        ("00123", "123", "N", 0),
        ("UNREADABLE", "00123", "N", 0),
        (" unreadable ", "00123", "N", 0),
        (None, "00123", "N", 0),
        ("123", None, "N", 0),
    ],
)
def test_compare_tag_numbers(function_app, detected, user, status, percent):
    match_status, match_percent = function_app.compare_tag_numbers(
        detected, user, request_id="test"
    )
    assert match_status == status
    assert match_percent == percent


@pytest.mark.parametrize(
    ("value", "expected_position"),
    [
        ({"position": "top-left"}, "top-left"),
        ({"position": ""}, None),
        ("bottom-right", "bottom-right"),
        (None, None),
        (123, "123"),
    ],
)
def test_format_barcode_position(function_app, value, expected_position):
    result = function_app.format_barcode_position(value)
    assert result == {"position": expected_position}


def test_create_error_response_shape(function_app):
    response = function_app.create_error_response(
        "Invalid multipart request",
        status_code=400,
        request_id="abc123",
    )
    assert response.status_code == 400
    assert response.headers["X-Request-ID"] == "abc123"

    payload = json.loads(response.get_body())
    assert payload["success"] is False
    assert payload["error"]["message"] == "Invalid multipart request"
    assert payload["error"]["code"] == 400
    assert payload["error"]["request_id"] == "abc123"


def test_call_gemini_with_retry_blocks_overlong_prompt(function_app):
    prompt = "x" * (function_app.MAX_PROMPT_LENGTH + 1)
    result = function_app.call_gemini_with_retry(None, prompt)
    assert result == {"error": "PROMPT_TOO_LONG"}
