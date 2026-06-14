"""Phase 2 subcategory and make/model validation prompt."""

from __future__ import annotations

from prompts._loader import load_template

_TEMPLATE = load_template("phase2_subcat_model.txt")
_EMPTY_VALUES = frozenset({"N/A", "NA", "NULL", "NONE", ""})


def _format_field(value: str | None, empty_label: str) -> str:
    text = str(value or "").strip()
    if text.upper() in _EMPTY_VALUES:
        return empty_label
    return text


def build_phase2_subcat_model_prompt(
    categoryname: str,
    user_subcategory: str,
    user_makemodel: str,
    detected_asset: str,
    image_analysis: str,
) -> str:
    """Build the Gemini Phase 2 subcategory/make-model validation prompt."""
    return _TEMPLATE.substitute(
        categoryname=_format_field(categoryname, "(not provided)"),
        user_subcategory=_format_field(user_subcategory, "(not provided)"),
        user_makemodel=_format_field(user_makemodel, "(not provided)"),
        detected_asset=_format_field(detected_asset, "(unknown)"),
        image_analysis=_format_field(image_analysis, "(no image analysis available)"),
    )
