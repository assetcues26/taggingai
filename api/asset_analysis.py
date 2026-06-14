"""Vercel serverless entrypoint for POST /api/asset_analysis."""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from function_app import asset_analysis as run_asset_analysis  # noqa: E402


class _HttpRequestAdapter:
    """Minimal adapter so shared handler code accepts Vercel requests."""

    def __init__(self, body: bytes, headers: dict[str, str]):
        self._body = body
        self.headers = headers

    def get_body(self) -> bytes:
        return self._body


def _write_azure_response(handler: BaseHTTPRequestHandler, response) -> None:
    body = response.get_body()
    payload = body.encode("utf-8") if isinstance(body, str) else (body or b"")

    handler.send_response(response.status_code)
    handler.send_header("Content-Type", response.mimetype or "application/json")
    handler.send_header("Access-Control-Allow-Origin", "*")

    for key, value in (response.headers or {}).items():
        if key.lower() not in {"content-type", "content-length"}:
            handler.send_header(key, value)

    handler.send_header("Content-Length", str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)


class handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        payload = json.dumps(
            {
                "status": "ok",
                "endpoint": "/api/asset_analysis",
                "method": "POST",
                "content_type": "multipart/form-data",
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self) -> None:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0

        body = self.rfile.read(content_length) if content_length > 0 else b""
        headers = {key: self.headers[key] for key in self.headers}
        azure_response = run_asset_analysis(_HttpRequestAdapter(body, headers))
        _write_azure_response(self, azure_response)
