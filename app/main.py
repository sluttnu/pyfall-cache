from __future__ import annotations

import json
from typing import Any

import redis.asyncio as redis
from fastapi import FastAPI, Query, HTTPException, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal, get_db, get_card_by_id, get_card_by_name, save_cards, get_query_cache, save_query_cache
from app.scryfall import search_cards, get_sets, get_card_by_id as fetch_scryfall_card_by_id, get_card_by_name as fetch_scryfall_card_by_name, autocomplete, hash_query

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
async def sets(db: Session = Depends(get_db)):
    key = "sets"
    cached = await redis_client.get(key)
    if cached:
        return JSONResponse(content=json.loads(cached))
    rows = db.execute("""
        SELECT raw_json
        FROM cards
        WHERE set_code IS NOT NULL
        LIMIT 1
    """).fetchall()
    if rows and rows[0][0]:
        return JSONResponse(content=rows[0][0])
    data = await get_sets()
    await redis_client.set(key, json.dumps(data), ex=settings.card_cache_ttl_seconds)
    return data

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
    if upstream.get("data"):
        save_cards(db, upstream["data"])
        save_query_cache(db, query_key, q, [str(card["id"]) for card in upstream["data"]])
        await redis_client.set(query_key, json.dumps([str(card["id"]) for card in upstream["data"]]), ex=settings.query_cache_ttl_seconds)
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

@app.get("/cards/autocomplete")
async def cards_autocomplete(q: str = Query(..., min_length=2)):
    return await autocomplete(q)
