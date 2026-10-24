from __future__ import annotations

import json

import redis.asyncio as redis
from fastapi import Body, Depends, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
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


@app.get("/")
@app.get("/tester")
async def index() -> HTMLResponse:
    html = """
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Pyfall Cache Endpoint Tester</title>
    <style>
      :root {
        --bg: #111827;
        --panel: #1f2937;
        --panel-alt: #0f172a;
        --text: #e5e7eb;
        --muted: #9ca3af;
        --accent: #60a5fa;
        --ok: #22c55e;
        --warn: #f59e0b;
        --error: #ef4444;
        --border: #374151;
      }

      * { box-sizing: border-box; }

      body {
        margin: 0;
        font-family: Arial, Helvetica, sans-serif;
        background: var(--bg);
        color: var(--text);
      }

      .container {
        max-width: 1200px;
        margin: 0 auto;
        padding: 24px;
      }

      h1 {
        margin-top: 0;
      }

      .controls {
        display: flex;
        gap: 12px;
        flex-wrap: wrap;
        margin: 20px 0;
      }

      button {
        background: var(--accent);
        color: #08111d;
        border: none;
        border-radius: 8px;
        padding: 10px 16px;
        font-weight: bold;
        cursor: pointer;
      }

      button.secondary {
        background: #374151;
        color: var(--text);
      }

      .panel {
        background: var(--panel);
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 14px;
        margin-bottom: 16px;
      }

      .panel h2 {
        margin: 0 0 10px;
        font-size: 1.1rem;
      }

      .status {
        display: inline-block;
        font-size: 0.8rem;
        padding: 3px 8px;
        border-radius: 999px;
        margin-left: 10px;
        vertical-align: middle;
      }

      .status.success { background: rgba(34, 197, 94, 0.2); color: var(--ok); }
      .status.error { background: rgba(239, 68, 68, 0.2); color: var(--error); }
      .status.warn { background: rgba(245, 158, 11, 0.2); color: var(--warn); }

      pre {
        margin: 0;
        white-space: pre-wrap;
        word-break: break-word;
        background: var(--panel-alt);
        border: 1px solid var(--border);
        border-radius: 8px;
        padding: 14px;
        color: #dbeafe;
        font-size: 13px;
        line-height: 1.45;
        overflow: auto;
      }

      .muted {
        color: var(--muted);
      }

      .endpoint-row {
        margin-top: 12px;
        border-top: 1px solid var(--border);
        padding-top: 12px;
      }

      .endpoint-row:first-child {
        margin-top: 0;
        border-top: none;
        padding-top: 0;
      }

      details.endpoint-row {
        background: var(--panel);
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 12px 14px 0;
        margin-bottom: 16px;
      }

      details.endpoint-row summary {
        cursor: pointer;
        list-style: none;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        padding-bottom: 12px;
        font-weight: 600;
      }

      details.endpoint-row summary::-webkit-details-marker {
        display: none;
      }

      details.endpoint-row pre {
        margin: 0 0 12px;
      }
    </style>
  </head>
  <body>
    <div class="container">
      <h1>Pyfall Cache Endpoint Tester</h1>

      <div class="controls">
        <button id="run-all">Run all endpoints</button>
        <button id="clear" class="secondary">Clear output</button>
      </div>

      <div class="panel">
        <h2>Settings</h2>
        <div class="muted">Base URL: <strong id="base-url">https://scryfall.slutt.nu</strong></div>
      </div>

      <div id="output"></div>
    </div>

    <script>
      const BASE_URL = 'https://scryfall.slutt.nu';
      const output = document.getElementById('output');

      function escapeHtml(value) {
        return String(value)
          .replace(/&/g, '&amp;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;')
          .replace(/\"/g, '&quot;')
          .replace(/'/g, '&#039;');
      }

      function addSection(title, content, status = 'warn') {
        const details = document.createElement('details');
        details.className = 'endpoint-row';
        details.open = false;

        const summary = document.createElement('summary');
        summary.innerHTML = `
          <span>${escapeHtml(title)}</span>
          <span class="status ${status}">${status.toUpperCase()}</span>
        `;

        const pre = document.createElement('pre');
        pre.textContent = typeof content === 'string' ? content : pretty(content);

        details.appendChild(summary);
        details.appendChild(pre);
        output.appendChild(details);
      }

      function clearOutput() {
        output.innerHTML = '';
      }

      async function fetchJson(url, options = {}) {
        const res = await fetch(url, {
          ...options,
          headers: {
            Accept: 'application/json',
            ...(options.headers || {}),
          },
        });

        const text = await res.text();
        let payload = text;
        try {
          payload = JSON.parse(text);
        } catch (error) {
          // keep raw text if not JSON
        }

        return {
          ok: res.ok,
          status: res.status,
          statusText: res.statusText,
          redirected: res.redirected,
          url: res.url,
          headers: Object.fromEntries(res.headers.entries()),
          payload,
          text,
        };
      }

      function pretty(value) {
        if (typeof value === 'string') return value;
        return JSON.stringify(value, null, 2);
      }

      async function runAllEndpoints() {
        clearOutput();

        function saveSection(name, result, status) {
          const summary = typeof result === 'string' ? result : pretty(result);
          addSection(name, summary, status);
        }

        addSection('INFO', `Base URL: ${BASE_URL}\nTesting all public endpoints...`, 'warn');

        const health = await fetchJson(`${BASE_URL}/health`);
        saveSection('GET /health', { status: health.status, body: health.payload }, health.ok ? 'success' : 'error');

        const setList = await fetchJson(`${BASE_URL}/sets`);
        if (setList.ok && Array.isArray(setList.payload?.data)) {
          saveSection('GET /sets', { status: setList.status, body: setList.payload }, 'success');
        } else {
          saveSection('GET /sets', { status: setList.status, body: setList.payload }, 'error');
        }

        let setRef = null;
        let setInfo = null;
        if (setList.ok && Array.isArray(setList.payload?.data) && setList.payload.data.length > 0) {
          setInfo = setList.payload.data[0];
          setRef = setInfo.code || setInfo.id || 'war';
          const setByRef = await fetchJson(`${BASE_URL}/sets/${encodeURIComponent(setRef)}`);
          saveSection(`GET /sets/{set_ref} (${setRef})`, { status: setByRef.status, body: setByRef.payload }, setByRef.ok ? 'success' : 'error');
        }

        if (setInfo && (setInfo.tcgplayer_id || setInfo.id)) {
          const tcgplayerId = setInfo.tcgplayer_id || setInfo.id;
          const setByTcg = await fetchJson(`${BASE_URL}/sets/tcgplayer/${encodeURIComponent(String(tcgplayerId))}`);
          saveSection(`GET /sets/tcgplayer/{tcgplayer_id} (${tcgplayerId})`, { status: setByTcg.status, body: setByTcg.payload }, setByTcg.ok ? 'success' : 'error');
        }

        const manifest = await fetchJson(`${BASE_URL}/cards/manifest`);
        saveSection('GET /cards/manifest', { status: manifest.status, body: manifest.payload }, manifest.ok ? 'success' : 'error');

        const search = await fetchJson(`${BASE_URL}/cards/search?q=${encodeURIComponent('lightning bolt')}&page=1&page_size=3`);
        saveSection('GET /cards/search?q=lightning+bolt', { status: search.status, body: search.payload }, search.ok ? 'success' : 'error');

        const named = await fetchJson(`${BASE_URL}/cards/named?fuzzy=${encodeURIComponent('lightning bolt')}`);
        saveSection('GET /cards/named?fuzzy=lightning+bolt', { status: named.status, body: named.payload }, named.ok ? 'success' : 'error');

        const autocomplete = await fetchJson(`${BASE_URL}/cards/autocomplete?q=${encodeURIComponent('lig')}`);
        saveSection('GET /cards/autocomplete?q=lig', { status: autocomplete.status, body: autocomplete.payload }, autocomplete.ok ? 'success' : 'error');

        const randomCard = await fetchJson(`${BASE_URL}/cards/random`);
        saveSection('GET /cards/random', { status: randomCard.status, body: randomCard.payload }, randomCard.ok ? 'success' : 'error');

        let card = null;
        let cardId = null;
        let setCode = null;
        let collectorNumber = null;

        if (search.ok && search.payload && Array.isArray(search.payload.data) && search.payload.data.length > 0) {
          card = search.payload.data[0];
        } else if (named.ok && named.payload && named.payload.id) {
          card = named.payload;
        } else if (randomCard.ok && randomCard.payload && randomCard.payload.id) {
          card = randomCard.payload;
        }

        if (card) {
          cardId = card.id;
          setCode = card.set || card.set_code || null;
          collectorNumber = card.collector_number || null;

          const cardById = await fetchJson(`${BASE_URL}/cards/${encodeURIComponent(cardId)}`);
          saveSection(`GET /cards/{card_id} (${cardId})`, { status: cardById.status, body: cardById.payload }, cardById.ok ? 'success' : 'error');

          const image = await fetchJson(`${BASE_URL}/cards/${encodeURIComponent(cardId)}/image`, { redirect: 'manual' });
          saveSection(`GET /cards/{card_id}/image (${cardId})`, {
            status: image.status,
            redirected: image.redirected,
            location: image.headers.location || null,
            finalUrl: image.url,
            payload: image.payload,
          }, image.ok || image.status === 302 || image.status === 307 ? 'success' : 'error');

          const art = await fetchJson(`${BASE_URL}/cards/${encodeURIComponent(cardId)}/art`, { redirect: 'manual' });
          saveSection(`GET /cards/{card_id}/art (${cardId})`, {
            status: art.status,
            redirected: art.redirected,
            location: art.headers.location || null,
            finalUrl: art.url,
            payload: art.payload,
          }, art.ok || art.status === 302 || art.status === 307 ? 'success' : 'error');
        }

        if (setCode && collectorNumber) {
          const setCard = await fetchJson(`${BASE_URL}/cards/${encodeURIComponent(setCode)}/${encodeURIComponent(String(collectorNumber))}`);
          saveSection(`GET /cards/{code}/{number} (${setCode}/${collectorNumber})`, { status: setCard.status, body: setCard.payload }, setCard.ok ? 'success' : 'error');
        }

        if (card && card.multiverse_ids && card.multiverse_ids.length > 0) {
          const multiverseId = card.multiverse_ids[0];
          const multiverse = await fetchJson(`${BASE_URL}/cards/multiverse/${encodeURIComponent(String(multiverseId))}`);
          saveSection(`GET /cards/multiverse/{multiverse_id} (${multiverseId})`, { status: multiverse.status, body: multiverse.payload }, multiverse.ok ? 'success' : 'error');
        }

        if (card && card.mtgo_id) {
          const mtgo = await fetchJson(`${BASE_URL}/cards/mtgo/${encodeURIComponent(String(card.mtgo_id))}`);
          saveSection(`GET /cards/mtgo/{mtgo_id} (${card.mtgo_id})`, { status: mtgo.status, body: mtgo.payload }, mtgo.ok ? 'success' : 'error');
        }

        if (card && card.arena_id) {
          const arena = await fetchJson(`${BASE_URL}/cards/arena/${encodeURIComponent(String(card.arena_id))}`);
          saveSection(`GET /cards/arena/{arena_id} (${card.arena_id})`, { status: arena.status, body: arena.payload }, arena.ok ? 'success' : 'error');
        }

        if (card && card.tcgplayer_id) {
          const tcg = await fetchJson(`${BASE_URL}/cards/tcgplayer/${encodeURIComponent(String(card.tcgplayer_id))}`);
          saveSection(`GET /cards/tcgplayer/{tcgplayer_id} (${card.tcgplayer_id})`, { status: tcg.status, body: tcg.payload }, tcg.ok ? 'success' : 'error');
        }

        if (card && card.cardmarket_id) {
          const cardmarket = await fetchJson(`${BASE_URL}/cards/cardmarket/${encodeURIComponent(String(card.cardmarket_id))}`);
          saveSection(`GET /cards/cardmarket/{cardmarket_id} (${card.cardmarket_id})`, { status: cardmarket.status, body: cardmarket.payload }, cardmarket.ok ? 'success' : 'error');
        }

        if (card && card.id) {
          const identifiersPayload = {
            identifiers: [
              { id: card.id },
              ...(card.multiverse_ids ? [{ multiverse_id: card.multiverse_ids[0] }] : []),
            ],
          };

          const collection = await fetchJson(`${BASE_URL}/cards/collection`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(identifiersPayload),
          });
          saveSection('POST /cards/collection', { status: collection.status, body: collection.payload }, collection.ok ? 'success' : 'error');
        }

        if (!card) {
          addSection('NOTE', 'No card data was available from the test queries, so some card-specific routes were skipped.', 'warn');
        }

        addSection('DONE', 'All requested checks have been attempted.', 'success');
      }

      document.getElementById('run-all').addEventListener('click', runAllEndpoints);
      document.getElementById('clear').addEventListener('click', () => clearOutput());
      clearOutput();
      addSection('READY', 'Click “Run all endpoints” to fetch and print the returned values.', 'warn');
    </script>
  </body>
</html>
    """
    return HTMLResponse(content=html)


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
        await redis_client.set(query_key, json.dumps(results), ex=settings.query_cache_ttl_seconds)

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
