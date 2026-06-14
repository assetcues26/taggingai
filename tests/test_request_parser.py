"""Tests for multipart request parsing."""

from __future__ import annotations

import json
from io import BytesIO

import pytest
from PIL import Image

from request_parser import RequestParseError, parse_asset_analysis_request


class FakeHttpRequest:
    def __init__(self, body: bytes, content_type: str):
        self._body = body
        self.headers = {"Content-Type": content_type}

    def get_body(self) -> bytes:
        return self._body


def _build_multipart(
    fields: dict[str, str], files: dict[str, tuple[bytes, str, str]]
) -> tuple[bytes, str]:
    boundary = "----cursor-test-boundary"
    body = BytesIO()

    for name, value in fields.items():
        body.write(f"--{boundary}\r\n".encode())
        body.write(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        body.write(f"{value}\r\n".encode())

    for name, (content, mime_type, filename) in files.items():
        body.write(f"--{boundary}\r\n".encode())
        body.write(
            (
                f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
                f"Content-Type: {mime_type}\r\n\r\n"
            ).encode()
        )
        body.write(content)
        body.write(b"\r\n")

    body.write(f"--{boundary}--\r\n".encode())
    content_type = f"multipart/form-data; boundary={boundary}"
    return body.getvalue(), content_type


def _jpeg_bytes() -> bytes:
    image = Image.new("RGB", (400, 400), color="white")
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def test_parse_asset_analysis_request_reads_files_and_fields():
    jpeg = _jpeg_bytes()
    body, content_type = _build_multipart(
        {
            "assetname": "Dell Laptop",
            "tagnumber": "00123",
            "cost": "65000",
        },
        {
            "assetimage": (jpeg, "image/jpeg", "asset.jpg"),
            "barcodeimage": (jpeg, "image/jpeg", "barcode.png"),
        },
    )

    parsed = parse_asset_analysis_request(FakeHttpRequest(body, content_type))

    assert parsed.metadata["assetname"] == "Dell Laptop"
    assert parsed.metadata["tagnumber"] == "00123"
    assert parsed.metadata["cost"] == "65000"
    assert parsed.asset_image is not None
    assert parsed.barcode_image is not None
    assert parsed.asset_image.mime_type == "image/jpeg"


def test_parse_asset_analysis_request_rejects_json_body():
    request = FakeHttpRequest(b'{"assetname":"Chair"}', "application/json")
    with pytest.raises(RequestParseError, match="multipart/form-data"):
        parse_asset_analysis_request(request)


def test_parse_asset_analysis_request_supports_metadata_json_field():
    jpeg = _jpeg_bytes()
    metadata = json.dumps({"assetname": "Office Chair", "company": "Generic"})
    body, content_type = _build_multipart(
        {"metadata": metadata, "tagnumber": "TAG-001"},
        {"assetimage": (jpeg, "image/jpeg", "asset.webp")},
    )

    parsed = parse_asset_analysis_request(FakeHttpRequest(body, content_type))

    assert parsed.metadata["assetname"] == "Office Chair"
    assert parsed.metadata["company"] == "Generic"
    assert parsed.metadata["tagnumber"] == "TAG-001"
