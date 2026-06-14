"""Tests for Gemini inline content builders."""

from __future__ import annotations

from gemini_content import build_gemini_content, inline_image_part


def test_inline_image_part_uses_gemini_inline_data_shape():
    payload = b"fake-image-bytes"
    part = inline_image_part(payload, "image/png")

    assert part == {
        "inline_data": {
            "mime_type": "image/png",
            "data": payload,
        }
    }


def test_build_gemini_content_orders_prompt_before_images():
    barcode = (b"barcode", "image/jpeg")
    asset = (b"asset", "image/webp")

    content = build_gemini_content("analyze this", [barcode, asset])

    assert content[0] == "analyze this"
    assert content[1]["inline_data"]["data"] == b"barcode"
    assert content[2]["inline_data"]["mime_type"] == "image/webp"
