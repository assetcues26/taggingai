"""FastAPI entrypoint for Vercel and local HTTP testing."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

app = FastAPI(title="Tagging AI Asset Analysis")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


class _HttpRequestAdapter:
    """Minimal adapter so shared handler code accepts FastAPI requests."""

    def __init__(self, body: bytes, headers: dict[str, str]):
        self._body = body
        self.headers = headers

    def get_body(self) -> bytes:
        return self._body


def _azure_response_to_fastapi(azure_response) -> Response:
    body = azure_response.get_body()
    payload = body if isinstance(body, (bytes, bytearray)) else str(body or "").encode("utf-8")
    response_headers = dict(azure_response.headers or {})
    response_headers.setdefault("Content-Type", azure_response.mimetype or "application/json")
    return Response(
        content=payload,
        status_code=azure_response.status_code,
        headers=response_headers,
        media_type=azure_response.mimetype or "application/json",
    )


@app.get("/")
async def root() -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "tagging-ai"})


@app.get("/api/asset_analysis")
async def asset_analysis_health() -> JSONResponse:
    return JSONResponse(
        {
            "status": "ok",
            "endpoint": "/api/asset_analysis",
            "method": "POST",
            "content_type": "multipart/form-data",
        }
    )


@app.post("/api/asset_analysis")
async def asset_analysis(request: Request) -> Response:
    body = await request.body()
    headers = {key: value for key, value in request.headers.items()}

    try:
        from function_app import process_asset_analysis  # noqa: PLC0415

        azure_response = process_asset_analysis(_HttpRequestAdapter(body, headers))
        if azure_response is None:
            return JSONResponse(
                {"success": False, "error": {"message": "Handler returned no response"}},
                status_code=500,
            )
        return _azure_response_to_fastapi(azure_response)
    except Exception as exc:
        return JSONResponse(
            {"success": False, "error": {"message": str(exc)}},
            status_code=500,
        )
