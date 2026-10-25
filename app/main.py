import json
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

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
        return JSONResponse(content=hot_payload)

    cold_ok, cold_payload = get_cold_cache(method, base_path, query)
    if cold_ok:
        set_hot_cache(method, base_path, query, cold_payload, ttl)
        return JSONResponse(content=cold_payload)

    body = await request.body()
    upstream_params = params

    if body and body.strip():
        try:
            upstream_body = json.loads(body)
        except Exception:
            upstream_body = body.decode("utf-8", errors="replace")
    else:
        upstream_body = None

    status_code, payload, content_type = await client.fetch(method, base_path, upstream_params)

    if status_code >= 400:
        return JSONResponse(
            status_code=status_code,
            content=payload if isinstance(payload, dict) else {"detail": payload},
        )

    set_hot_cache(method, base_path, query, payload, ttl)
    set_cold_cache(method, base_path, query, payload, status_code, content_type, ttl)

    if isinstance(payload, (dict, list)):
        return JSONResponse(
            status_code=status_code,
            content=payload,
        )

    return Response(
        status_code=status_code,
        content=str(payload),
        media_type=content_type or "application/json",
    )