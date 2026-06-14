"""Parse multipart asset analysis requests with direct image uploads."""

from __future__ import annotations

import cgi
import io
import json
from dataclasses import dataclass
from typing import Any, Protocol

from image_utils import detect_mime_type

METADATA_FIELD_NAMES = (
    "assetid",
    "assetname",
    "description",
    "tagnumber",
    "assetnumber",
    "assetclassid",
    "assettaggingdetailid",
    "assetclassname",
    "categoryid",
    "categoryname",
    "subcategoryid",
    "subcategoryname",
    "makemodelname",
    "companyid",
    "company",
    "makemodelid",
    "customerid",
    "cost",
    "acquisitiondate",
)


@dataclass(frozen=True)
class UploadedImage:
    data: bytes
    mime_type: str
    filename: str | None = None


@dataclass(frozen=True)
class ParsedAssetAnalysisRequest:
    metadata: dict[str, Any]
    asset_image: UploadedImage | None = None
    barcode_image: UploadedImage | None = None


class RequestParseError(ValueError):
    """Raised when the incoming HTTP request cannot be parsed."""


class HttpRequestLike(Protocol):
    headers: dict[str, str]

    def get_body(self) -> bytes: ...


def _parse_multipart(
    body: bytes, content_type: str
) -> tuple[dict[str, str], dict[str, tuple[bytes, str | None, str | None]]]:
    """Parse multipart/form-data into text fields and uploaded files."""
    environ = {
        "REQUEST_METHOD": "POST",
        "CONTENT_TYPE": content_type,
        "CONTENT_LENGTH": str(len(body)),
    }
    form = cgi.FieldStorage(fp=io.BytesIO(body), environ=environ, keep_blank_values=True)

    fields: dict[str, str] = {}
    files: dict[str, tuple[bytes, str | None, str | None]] = {}

    if not form.list:
        return fields, files

    for item in form.list:
        if item.filename:
            files[item.name] = (
                item.file.read(),
                item.type or None,
                item.filename or None,
            )
        elif item.name:
            fields[item.name] = item.value

    return fields, files


def _coerce_metadata(fields: dict[str, str]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}

    for key in METADATA_FIELD_NAMES:
        if key not in fields:
            continue
        value = fields[key]
        if value == "":
            metadata[key] = None
            continue
        if key == "assetclassid":
            try:
                metadata[key] = int(value)
            except ValueError:
                metadata[key] = value
            continue
        metadata[key] = value

    return metadata


def _build_uploaded_image(
    name: str,
    payload: tuple[bytes, str | None, str | None],
) -> UploadedImage:
    data, content_type, filename = payload
    if not data:
        raise RequestParseError(f"Uploaded file '{name}' is empty.")
    mime_type = detect_mime_type(data, upload_content_type=content_type, filename=filename)
    return UploadedImage(data=data, mime_type=mime_type, filename=filename)


def parse_asset_analysis_from_body(body: bytes, content_type: str) -> ParsedAssetAnalysisRequest:
    """Parse multipart/form-data body into metadata and uploaded images."""
    if "multipart/form-data" not in content_type.lower():
        raise RequestParseError(
            "Expected multipart/form-data with direct image uploads. "
            "Send assetimage and/or barcodeimage as file fields plus metadata as form fields."
        )

    if not body:
        raise RequestParseError("Request body is empty.")

    fields, files = _parse_multipart(body, content_type)

    if "metadata" in fields and fields["metadata"].strip():
        try:
            embedded = json.loads(fields["metadata"])
        except json.JSONDecodeError as exc:
            raise RequestParseError("Invalid JSON in 'metadata' form field.") from exc
        if not isinstance(embedded, dict):
            raise RequestParseError("'metadata' form field must be a JSON object.")
        embedded_fields = {
            key: "" if value is None else str(value) for key, value in embedded.items()
        }
        metadata = _coerce_metadata(embedded_fields)
        form_overrides = {key: value for key, value in fields.items() if key != "metadata"}
        metadata.update(_coerce_metadata(form_overrides))
    else:
        metadata = _coerce_metadata(fields)

    asset_image = None
    barcode_image = None

    if "assetimage" in files:
        asset_image = _build_uploaded_image("assetimage", files["assetimage"])
    if "barcodeimage" in files:
        barcode_image = _build_uploaded_image("barcodeimage", files["barcodeimage"])

    return ParsedAssetAnalysisRequest(
        metadata=metadata,
        asset_image=asset_image,
        barcode_image=barcode_image,
    )


def parse_asset_analysis_request(req: HttpRequestLike) -> ParsedAssetAnalysisRequest:
    """
    Parse POST /asset_analysis requests.

    Expected format:
      Content-Type: multipart/form-data
      - assetimage: file (optional)
      - barcodeimage: file (optional)
      - metadata fields as regular form fields (assetid, assetname, cost, etc.)
    """
    content_type = req.headers.get("Content-Type", "")
    return parse_asset_analysis_from_body(req.get_body(), content_type)
