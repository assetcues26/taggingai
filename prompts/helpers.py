"""Shared helpers for building Gemini prompts."""

from __future__ import annotations

_EMPTY_DESCRIPTION_VALUES = frozenset({"N/A", "NA", "NULL", "NONE", ""})


def normalize_description(description: str | None) -> str:
    """Normalize user description; treat N/A-style values as empty."""
    text = str(description or "").strip()
    if text.upper() in _EMPTY_DESCRIPTION_VALUES:
        return ""
    return text


def format_description_for_phase1(description: str) -> str:
    return description if description else "(empty)"


def format_description_for_name_match(description: str) -> str:
    return description if description else "(empty - validation based on name only)"


def format_user_cost(user_cost) -> str:
    return str(user_cost) if user_cost is not None else "(not provided)"
