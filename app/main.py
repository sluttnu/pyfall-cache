import json
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from app.cache import (
    get_cold_cache,
    get_hot_cache,
    set_cold_cache,
    set_hot_cache,
)
from app.config import settings
from app.database import init_db
from app.scryfall_client import ScryfallClient

app = FastAPI(title="Scryfall Cache Proxy", version="1.0.0")

client = ScryfallClient(settings.scryfall_api_base)


def normalize_scryfall_error(status_code: int, payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict) and payload.get("object") == "error":
        return payload

    if isinstance(payload, dict):
        details = (
            payload.get("details")
            or payload.get("detail")
            or payload.get("message")
            or "No card found with the given ID or set code and collector number."
        )
        error = {
            "object": "error",
            "code": payload.get("code") or ("not_found" if status_code == 404 else "error"),
            "status": status_code,
            "details": details,
        }
        if "type" in payload:
            error["type"] = payload["type"]
        if "warnings" in payload:
            error["warnings"] = payload["warnings"]
        return error

    details = str(payload) if payload is not None else "No card found with the given ID or set code and collector number."
    return {
        "object": "error",
        "code": "not_found" if status_code == 404 else "error",
        "status": status_code,
        "details": details,
    }


@app.on_event("startup")
async def startup_event() -> None:
    init_db()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def proxy_all(request: Request, path: str) -> Response:
    method = request.method
    query = request.url.query
    base_path = f"/{path}" if not path.startswith("/") else path

    if not base_path or base_path == "/":
        base_path = "/"

    ttl = settings.default_cache_ttl_seconds
    if method == "GET":
        if "cards" in base_path or "search" in base_path:
            ttl = settings.card_cache_ttl_seconds
        else:
            ttl = settings.query_cache_ttl_seconds

    params = dict(request.query_params)
    key = f"{method}:{base_path}:{query}"

    hot_ok, hot_payload = get_hot_cache(method, base_path, query)
    if hot_ok:
        return JSONResponse(content=hot_payload) if isinstance(hot_payload, (dict, list)) else Response(content=str(hot_payload))

    cold_ok, cold_payload = get_cold_cache(method, base_path, query)
    if cold_ok:
        set_hot_cache(method, base_path, query, cold_payload, ttl)
        if isinstance(cold_payload, (dict, list)):
            return JSONResponse(content=cold_payload)
        return Response(content=str(cold_payload))

    body = await request.body()
    upstream_headers = {}
    content_type = request.headers.get("content-type")
    if content_type:
        upstream_headers["Content-Type"] = content_type
    if method == "GET" and not body:
        upstream_body = None
    else:
        upstream_body = body if body else None

    status_code, payload, content_type_value = await client.fetch(
        method,
        base_path,
        params=params,
        body=upstream_body,
        headers=upstream_headers,
    )

    if 300 <= status_code < 400 and isinstance(payload, str):
        return RedirectResponse(url=payload, status_code=status_code)

    if status_code >= 400:
        return JSONResponse(
            status_code=status_code,
            content=normalize_scryfall_error(status_code, payload),
        )

    set_hot_cache(method, base_path, query, payload, ttl)
    set_cold_cache(method, base_path, query, payload, status_code, content_type_value, ttl)

    if isinstance(payload, (dict, list)):
        return JSONResponse(status_code=status_code, content=payload)

    return Response(
        status_code=status_code,
        content=str(payload),
        media_type=content_type_value or "application/json",
    )
