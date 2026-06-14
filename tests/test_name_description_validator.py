"""Tests for name/description sanity validation."""

from __future__ import annotations

from name_description_validator import apply_name_description_sanity_check


def test_rejects_laptop_name_with_printer_image():
    result = apply_name_description_sanity_check(
        user_asset_name="HP Laptop",
        user_description="HP Black and White Printer",
        image_analysis="HP Color LaserJet Pro multifunction printer with scanner.",
        detected_asset="HP Color LaserJet Pro printer",
        ai_result={
            "namedescriptionmatch": "Y",
            "namedescriptionmatchpercent": 100,
            "reasoning": "AI incorrectly approved",
        },
    )

    assert result["namedescriptionmatch"] == "N"
    assert result["namedescriptionmatchpercent"] <= 25
    assert "laptop" in result["reasoning"].lower()


def test_keeps_match_when_name_and_image_align():
    result = apply_name_description_sanity_check(
        user_asset_name="HP Printer",
        user_description="HP LaserJet",
        image_analysis="HP LaserJet multifunction printer.",
        detected_asset="HP LaserJet printer",
        ai_result={
            "namedescriptionmatch": "Y",
            "namedescriptionmatchpercent": 95,
            "reasoning": "Match",
        },
    )

    assert result["namedescriptionmatch"] == "Y"
    assert result["namedescriptionmatchpercent"] == 95
