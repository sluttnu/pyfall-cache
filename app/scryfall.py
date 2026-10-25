from __future__ import annotations

import hashlib
import time
from typing import Any

import httpx

from app.config import get_settings

settings = get_settings()

client = httpx.AsyncClient(timeout=30.0)

_last_request_at = 0.0
_min_interval = 1.0 / settings.scryfall_rate_limit_per_second


async def rate_limited_get(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    global _last_request_at

    now = time.monotonic()
    elapsed = now - _last_request_at
    if elapsed < _min_interval:
        time.sleep(_min_interval - elapsed)
    _last_request_at = time.monotonic()

    response = await client.get(f"{settings.scryfall_api_base}{url}", params=params)
    response.raise_for_status()
    return response.json()


def resolve_image_url(card: dict[str, Any], version: str = "large") -> str | None:
    if not isinstance(card, dict):
        return None

    image_uris = card.get("image_uris") or {}
    if image_uris.get(version):
        return image_uris[version]

    for face in card.get("card_faces") or []:
        face_images = face.get("image_uris") or {}
        if face_images.get(version):
            return face_images[version]

    # fallback for common image sizes
    for key in ("normal", "large", "png", "art_crop", "border_crop"):
        if image_uris.get(key):
            return image_uris[key]

    return None


def resolve_art_url(card: dict[str, Any], version: str = "art_crop") -> str | None:
    return resolve_image_url(card, version=version)


async def get_sets() -> dict[str, Any]:
    return await rate_limited_get("/sets")


async def get_set(set_ref: str) -> dict[str, Any] | None:
    try:
        return await rate_limited_get(f"/sets/{set_ref}")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return None
        raise


async def get_set_by_tcgplayer(tcgplayer_id: str) -> dict[str, Any] | None:
    try:
        return await rate_limited_get(f"/sets/tcgplayer/{tcgplayer_id}")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return None
        raise


async def get_cards_manifest() -> dict[str, Any]:
    sets_payload = await get_sets()
    return {
        "object": "manifest",
        "data": {
            "sets": sets_payload.get("data", []),
        },
    }


async def search_cards(query: str, page: int = 1, page_size: int = 100) -> dict[str, Any]:
    params = {"q": query, "page": page, "page_size": page_size}
    return await rate_limited_get("/cards/search", params=params)


async def get_card_by_name(name: str, exact: bool = False) -> dict[str, Any] | None:
    params = {"exact": name} if exact else {"fuzzy": name}
    try:
        return await rate_limited_get("/cards/named", params=params)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return None
        raise


async def get_card_by_id(card_id: str) -> dict[str, Any] | None:
    try:
        return await rate_limited_get(f"/cards/{card_id}")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return None
        raise


async def get_card_by_set_code_number(code: str, number: str, lang: str | None = None) -> dict[str, Any] | None:
    path = f"/cards/{code}/{number}"
    if lang:
        path = f"{path}/{lang}"
    try:
        return await rate_limited_get(path)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return None
        raise


async def get_card_by_multiverse(multiverse_id: str) -> dict[str, Any] | None:
    try:
        return await rate_limited_get(f"/cards/multiverse/{multiverse_id}")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return None
        raise


async def get_card_by_mtgo(mtgo_id: str) -> dict[str, Any] | None:
    try:
        return await rate_limited_get(f"/cards/mtgo/{mtgo_id}")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return None
        raise


async def get_card_by_arena(arena_id: str) -> dict[str, Any] | None:
    try:
        return await rate_limited_get(f"/cards/arena/{arena_id}")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return None
        raise


async def get_card_by_tcgplayer(tcgplayer_id: str) -> dict[str, Any] | None:
    try:
        return await rate_limited_get(f"/cards/tcgplayer/{tcgplayer_id}")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return None
        raise


async def get_card_by_cardmarket(cardmarket_id: str) -> dict[str, Any] | None:
    try:
        return await rate_limited_get(f"/cards/cardmarket/{cardmarket_id}")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return None
        raise


async def get_cards_by_ids(ids: list[str]) -> list[dict[str, Any]]:
    if not ids:
        return []

    payload = {"identifiers": [{"id": card_id} for card_id in ids]}
    response = await client.post(f"{settings.scryfall_api_base}/cards/collection", json=payload)
    response.raise_for_status()
    data = response.json()
    return data.get("data", [])


async def autocomplete(prefix: str) -> dict[str, Any]:
    return await rate_limited_get("/cards/autocomplete", {"q": prefix})


async def get_random_card() -> dict[str, Any] | None:
    try:
        return await rate_limited_get("/cards/random")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return None
        raise


def hash_query(query: str) -> str:
    return hashlib.sha256(query.strip().encode("utf-8")).hexdigest()