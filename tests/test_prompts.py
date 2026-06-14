"""Tests for prompt templates and builders."""

from __future__ import annotations

from pathlib import Path

from prompts import (
    GENERIC_SAFE_WORDS,
    MAX_PROMPT_LENGTH,
    build_name_description_match_prompt,
    build_phase1_vision_prompt,
    build_phase2_subcat_model_prompt,
)
from prompts._loader import load_template
from prompts.constants import GENERIC_SAFE_WORDS as CONST_GENERIC_WORDS


def test_template_files_exist():
    templates_dir = Path(__file__).resolve().parents[1] / "prompts" / "templates"
    assert (templates_dir / "phase1_vision.txt").is_file()
    assert (templates_dir / "name_description_match.txt").is_file()
    assert (templates_dir / "phase2_subcat_model.txt").is_file()


def test_templates_have_no_warning_emoji():
    templates_dir = Path(__file__).resolve().parents[1] / "prompts" / "templates"
    for path in templates_dir.glob("*.txt"):
        content = path.read_text(encoding="utf-8")
        assert "⚠" not in content
        assert "✅" not in content


def test_load_template_is_cached():
    first = load_template("phase1_vision.txt")
    second = load_template("phase1_vision.txt")
    assert first is second


def test_build_phase1_vision_prompt_substitutes_placeholders():
    prompt = build_phase1_vision_prompt(
        user_asset_name="Dell Latitude 5420",
        user_description="i5, 8GB RAM",
        user_cost=65000,
    )
    assert "Dell Latitude 5420" in prompt
    assert "i5, 8GB RAM" in prompt
    assert "65000" in prompt
    assert "$user_asset_name" not in prompt
    assert "$user_description" not in prompt
    assert "$user_cost" not in prompt
    assert len(prompt) <= MAX_PROMPT_LENGTH


def test_build_phase1_vision_prompt_handles_missing_optional_inputs():
    prompt = build_phase1_vision_prompt(
        user_asset_name="Office chair",
        user_description="",
        user_cost=None,
    )
    assert "(empty)" in prompt
    assert "(not provided)" in prompt


def test_build_name_description_match_prompt_substitutes_placeholders():
    prompt = build_name_description_match_prompt(
        user_asset_name="HP Laptop",
        user_description="",
        image_analysis="Silver laptop on desk with HP logo visible.",
    )
    assert "HP Laptop" in prompt
    assert "(empty - validation based on name only)" in prompt
    assert "Silver laptop on desk with HP logo visible." in prompt
    assert "$image_analysis" not in prompt


def test_generic_safe_words_exported():
    assert GENERIC_SAFE_WORDS == CONST_GENERIC_WORDS
    assert "laptop" in GENERIC_SAFE_WORDS


def test_build_phase2_subcat_model_prompt_substitutes_placeholders():
    prompt = build_phase2_subcat_model_prompt(
        categoryname="Printer",
        user_subcategory="Laptop",
        user_makemodel="HP PRINTER",
        detected_asset="HP Color LaserJet Pro printer",
        image_analysis="Multifunction laser printer with scanner on top.",
    )
    assert "Printer" in prompt
    assert "Laptop" in prompt
    assert "HP PRINTER" in prompt
    assert "HP Color LaserJet Pro printer" in prompt
    assert "Multifunction laser printer with scanner on top." in prompt
    assert "$user_subcategory" not in prompt
    assert len(prompt) <= MAX_PROMPT_LENGTH
