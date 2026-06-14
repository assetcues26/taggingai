"""Tests for direct image upload utilities."""

from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from image_utils import (
    MAX_IMAGE_BYTES,
    detect_mime_type,
    resize_image_if_needed,
    validate_barcode_image_quality,
    validate_image_size,
)


def _image_bytes(width: int = 800, height: int = 600, fmt: str = "JPEG") -> bytes:
    image = Image.new("RGB", (width, height), color="white")
    buffer = BytesIO()
    image.save(buffer, format=fmt)
    return buffer.getvalue()


def test_validate_image_size_rejects_oversized():
    with pytest.raises(ValueError, match="exceeds 10MB"):
        validate_image_size(b"x" * (MAX_IMAGE_BYTES + 1))


def test_detect_mime_type_from_bytes():
    assert detect_mime_type(_image_bytes(fmt="PNG")) == "image/png"


def test_resize_image_if_needed_keeps_small_image():
    original = _image_bytes()
    processed, mime_type = resize_image_if_needed(original, request_id="test")
    assert processed == original
    assert mime_type == "image/jpeg"


def test_resize_image_if_needed_scales_large_image():
    original = _image_bytes(width=3000, height=2000)
    processed, _mime_type = resize_image_if_needed(original, request_id="test")
    assert processed != original

    with Image.open(BytesIO(processed)) as image:
        assert image.width <= 1920
        assert image.height <= 1080


def test_validate_barcode_image_quality_rejects_small_image():
    image = Image.new("RGB", (100, 100), color="white")
    is_valid, warning = validate_barcode_image_quality(image, request_id="test")
    assert is_valid is False
    assert warning is not None
