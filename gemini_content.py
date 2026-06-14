"""Build Gemini inline multimodal request content."""

from __future__ import annotations

InlineImage = tuple[bytes, str]


def inline_image_part(image_bytes: bytes, mime_type: str) -> dict:
    """Return a Gemini Part using inline_data for fast single-request uploads."""
    return {"inline_data": {"mime_type": mime_type, "data": image_bytes}}


def build_gemini_content(prompt: str, inline_images: list[InlineImage] | None = None) -> list:
    """Build generate_content input: text prompt followed by inline image parts."""
    content: list = [prompt]
    if inline_images:
        for image_bytes, mime_type in inline_images:
            content.append(inline_image_part(image_bytes, mime_type))
    return content
