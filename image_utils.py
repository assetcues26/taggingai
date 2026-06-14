"""Image validation and resizing for direct binary uploads."""

from __future__ import annotations

import logging
from io import BytesIO

from PIL import Image

MAX_IMAGE_SIZE_MB = 10
MAX_IMAGE_BYTES = MAX_IMAGE_SIZE_MB * 1024 * 1024

_FORMAT_TO_MIME = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
    "GIF": "image/gif",
    "BMP": "image/bmp",
    "TIFF": "image/tiff",
}


def validate_image_size(image_bytes: bytes, max_size_mb: int = MAX_IMAGE_SIZE_MB) -> None:
    """Reject images larger than the configured limit."""
    max_bytes = max_size_mb * 1024 * 1024
    if len(image_bytes) > max_bytes:
        raise ValueError(f"Image size exceeds {max_size_mb}MB limit")


def detect_mime_type(
    image_bytes: bytes,
    upload_content_type: str | None = None,
    filename: str | None = None,
) -> str:
    """Resolve a MIME type from upload metadata or image bytes."""
    if upload_content_type:
        normalized = upload_content_type.split(";", 1)[0].strip().lower()
        if normalized.startswith("image/"):
            return normalized

    if filename and "." in filename:
        extension = filename.rsplit(".", 1)[-1].lower()
        extension_map = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "webp": "image/webp",
            "gif": "image/gif",
            "bmp": "image/bmp",
            "tif": "image/tiff",
            "tiff": "image/tiff",
        }
        if extension in extension_map:
            return extension_map[extension]

    with Image.open(BytesIO(image_bytes)) as image:
        return _FORMAT_TO_MIME.get((image.format or "JPEG").upper(), "image/jpeg")


def validate_barcode_image_quality(image, request_id=""):
    """
    Validate barcode image quality for OCR accuracy.
    Returns: (is_valid, warning_message)
    """
    try:
        min_width = 200
        min_height = 200

        if image.width < min_width or image.height < min_height:
            warning = (
                f"Barcode image resolution too low ({image.width}x{image.height}). "
                f"Minimum {min_width}x{min_height} recommended for accurate reading."
            )
            logging.warning(f"[{request_id}] {warning}")
            return False, warning

        if image.width < 400 and image.height < 400:
            warning = (
                f"Barcode image may be too small ({image.width}x{image.height}). "
                "Higher resolution recommended for maximum accuracy."
            )
            logging.warning(f"[{request_id}] {warning}")

        return True, None

    except Exception as e:
        logging.error(f"[{request_id}] Image quality validation error: {e}")
        return True, None


def resize_image_if_needed(
    image_bytes: bytes,
    max_width: int = 1920,
    max_height: int = 1080,
    request_id: str = "",
    is_barcode: bool = False,
    mime_type: str | None = None,
) -> tuple[bytes, str]:
    """
    Validate and optionally resize uploaded image bytes.
    Returns processed bytes and MIME type for Gemini.
    """
    validate_image_size(image_bytes)
    resolved_mime = mime_type or detect_mime_type(image_bytes)

    try:
        logging.info(f"[{request_id}] Checking image dimensions...")

        with Image.open(BytesIO(image_bytes)) as image:
            if is_barcode:
                is_valid, warning = validate_barcode_image_quality(image, request_id)
                if not is_valid:
                    raise ValueError(warning)

            if image.width <= max_width and image.height <= max_height:
                logging.info(f"[{request_id}] Image is within size limits. No resizing needed.")
                return image_bytes, resolved_mime

            logging.info(
                f"[{request_id}] Image ({image.width}x{image.height}) exceeds max dimensions. Resizing..."
            )
            image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)

            output_format = image.format if image.format in {"JPEG", "PNG", "WEBP"} else "JPEG"
            with BytesIO() as output_buffer:
                image.save(output_buffer, format=output_format, optimize=True)
                processed = output_buffer.getvalue()

            processed_mime = _FORMAT_TO_MIME.get(output_format, "image/jpeg")
            logging.info(f"[{request_id}] Image resized successfully with optimized memory usage.")
            return processed, processed_mime

    except ValueError:
        raise
    except Exception as e:
        logging.error(f"[{request_id}] Optimized image processing failed: {e}")
        raise ValueError(f"Invalid, corrupted, or oversized image provided: {e}") from e
