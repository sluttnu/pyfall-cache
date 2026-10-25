import json
from typing import Any

import httpx

from app.config import settings


class ScryfallClient:
    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or settings.scryfall_api_base).rstrip("/")

    async def fetch(self, method: str, path: str, params: dict[str, Any] | None = None) -> tuple[int, dict[str, Any] | list[Any] | str, str]:
        url = f"{self.base_url}{path}"
        headers = {"Accept": "application/json"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method=method.upper(),
                url=url,
                params=params or {},
                headers=headers,
            )

        content_type = response.headers.get("content-type", "application/json")
        try:
            payload = response.json()
        except Exception:
            payload = response.text

        return response.status_code, payload, content_type