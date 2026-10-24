from __future__ import annotations

import json

import redis.asyncio as redis
from fastapi import Body, Depends, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_card_by_id, get_card_by_name, get_db, get_query_cache, save_cards, save_query_cache
from app.scryfall import (
    autocomplete,
    get_card_by_arena,
    get_card_by_cardmarket,
    get_card_by_id as fetch_scryfall_card_by_id,
    get_card_by_multiverse,
    get_card_by_mtgo,
    get_card_by_name as fetch_scryfall_card_by_name,
    get_card_by_set_code_number,
    get_card_by_tcgplayer,
    get_cards_by_ids,
    get_cards_manifest,
    get_random_card,
    get_set,
    get_set_by_tcgplayer,
    get_sets,
    hash_query,
    pick_art_url,
    pick_image_url,
    search_cards,
)

settings = get_settings()
app = FastAPI(title="Pyfall Cache", version="0.1.0")
redis_client = redis.from_url(settings.redis_url, decode_responses=True)


@app.on_event("startup")
async def startup():
    from app.db import init_db

    init_db()


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/sets")
async def sets():
    key = "sets"
    cached = await redis_client.get(key)
    if cached:
        return JSONResponse(content=json.loads(cached))

    data = await get_sets()
    await redis_client.set(key, json.dumps(data), ex=settings.card_cache_ttl_seconds)
    return data


@app.get("/sets/{set_ref}")
async def set_by_ref(set_ref: str):
    data = await get_set(set_ref)
    if data is None:
        raise HTTPException(status_code=404, detail="Set not found")
    return data


@app.get("/sets/tcgplayer/{tcgplayer_id}")
async def set_by_tcgplayer(tcgplayer_id: str):
    data = await get_set_by_tcgplayer(tcgplayer_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Set not found")
    return data


@app.get("/cards/manifest")
async def cards_manifest():
    return await get_cards_manifest()


@app.get("/cards/search")
async def cards_search(
    q: str = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=250),
    db: Session = Depends(get_db),
):
    query_key = hash_query(f"{q}|{page}|{page_size}")
    cached_ids = get_query_cache(db, query_key)
    if cached_ids:
        cached_cards = []
        for card_id in cached_ids:
            card = get_card_by_id(db, card_id)
            if card:
                cached_cards.append(card)
        if cached_cards:
            return {
                "object": "list",
                "data": cached_cards,
                "has_more": False,
                "next_page": None,
                "total_cards": len(cached_cards),
            }

    upstream = await search_cards(q, page=page, page_size=page_size)
    cards = upstream.get("data", [])
    if cards:
        save_cards(db, cards)
        results = [str(card["id"]) for card in cards if isinstance(card, dict) and "id" in card]
        save_query_cache(db, query_key, q, results)
        await redis_client.set(
            query_key,
            json.dumps(results),
            ex=settings.query_cache_ttl_seconds,
        )

    return upstream


@app.get("/cards/named")
async def cards_named(
    fuzzy: str | None = None,
    exact: str | None = None,
    db: Session = Depends(get_db),
):
    name = fuzzy or exact
    if not name:
        raise HTTPException(status_code=400, detail="Provide fuzzy or exact")

    cached = get_card_by_name(db, name)
    if cached:
        return cached

    card = await fetch_scryfall_card_by_name(name, exact=bool(exact))
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")

    save_cards(db, [card])
    return card


@app.get("/cards/autocomplete")
async def cards_autocomplete(q: str = Query(..., min_length=2)):
    return await autocomplete(q)


@app.get("/cards/random")
async def cards_random():
    card = await get_random_card()
    if card is None:
        raise HTTPException(status_code=404, detail="No random card available")
    return card


@app.post("/cards/collection")
async def cards_collection(payload: dict = Body(...)):
    identifiers = payload.get("identifiers") or payload.get("ids") or []
    if not identifiers:
        raise HTTPException(status_code=400, detail="identifiers required")

    card_ids = []
    for item in identifiers:
        if isinstance(item, dict):
            if "id" in item:
                card_ids.append(str(item["id"]))
            elif "multiverse_id" in item:
                card_ids.append(str(item["multiverse_id"]))
        else:
            card_ids.append(str(item))

    data = await get_cards_by_ids(card_ids)
    return {"object": "list", "data": data}


@app.get("/cards/{code}/{number}")
@app.get("/cards/{code}/{number}/{lang}")
async def card_by_set_code_number(code: str, number: str, lang: str | None = None):
    card = await get_card_by_set_code_number(code, number, lang)
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")
    return card


@app.get("/cards/multiverse/{multiverse_id}")
async def card_by_multiverse(multiverse_id: str):
    card = await get_card_by_multiverse(multiverse_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")
    return card


@app.get("/cards/mtgo/{mtgo_id}")
async def card_by_mtgo(mtgo_id: str):
    card = await get_card_by_mtgo(mtgo_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")
    return card


@app.get("/cards/arena/{arena_id}")
async def card_by_arena(arena_id: str):
    card = await get_card_by_arena(arena_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")
    return card


@app.get("/cards/tcgplayer/{tcgplayer_id}")
async def card_by_tcgplayer(tcgplayer_id: str):
    card = await get_card_by_tcgplayer(tcgplayer_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")
    return card


@app.get("/cards/cardmarket/{cardmarket_id}")
async def card_by_cardmarket(cardmarket_id: str):
    card = await get_card_by_cardmarket(cardmarket_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")
    return card


@app.get("/cards/{card_id}")
async def card_by_id(card_id: str, db: Session = Depends(get_db)):
    cached = get_card_by_id(db, card_id)
    if cached:
        return cached

    card = await fetch_scryfall_card_by_id(card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")

    save_cards(db, [card])
    return card


@app.get("/cards/{card_id}/image")
async def card_image(card_id: str):
    card = await fetch_scryfall_card_by_id(card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")

    image_url = pick_image_url(card)
    if not image_url:
        raise HTTPException(status_code=404, detail="Card image not available")
    return RedirectResponse(url=image_url)


@app.get("/cards/{card_id}/art")
async def card_art(card_id: str):
    card = await fetch_scryfall_card_by_id(card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")

    art_url = pick_art_url(card)
    if not art_url:
        raise HTTPException(status_code=404, detail="Card art not available")
    return RedirectResponse(url=art_url)
