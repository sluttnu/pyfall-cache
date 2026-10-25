import json
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import redis
from sqlalchemy.orm import Session

from app.config import settings
from app.database import CacheEntry, SessionLocal


redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_key(method: str, path: str, query: str) -> str:
    return f"{method.upper()}:{path}:{query or ''}"


def get_hot_cache(method: str, path: str, query: str) -> tuple[bool, Any | None]:
    key = normalize_key(method, path, query)
    cached = redis_client.get(key)
    if cached is None:
        return False, None
    try:
        return True, json.loads(cached)
    except Exception:
        return False, None


def set_hot_cache(method: str, path: str, query: str, payload: Any, ttl_seconds: int) -> None:
    key = normalize_key(method, path, query)
    redis_client.setex(key, ttl_seconds, json.dumps(payload, separators=(",", ":")))


def get_cold_cache(method: str, path: str, query: str) -> tuple[bool, Any | None]:
    key = normalize_key(method, path, query)
    db: Session = SessionLocal()
    try:
        entry = db.query(CacheEntry).filter(CacheEntry.key == key).one_or_none()
        if entry is None:
            return False, None

        expires_at = datetime.fromisoformat(entry.expires_at.replace("Z", "+00:00"))
        if expires_at <= utc_now():
            db.delete(entry)
            db.commit()
            return False, None

        return True, json.loads(entry.response)
    finally:
        db.close()


def set_cold_cache(method: str, path: str, query: str, payload: Any, status_code: int, content_type: str, ttl_seconds: int) -> None:
    key = normalize_key(method, path, query)
    created_at = utc_now().isoformat().replace("+00:00", "Z")
    expires_at = (utc_now() + timedelta(seconds=ttl_seconds)).isoformat().replace("+00:00", "Z")

    db: Session = SessionLocal()
    try:
        entry = db.query(CacheEntry).filter(CacheEntry.key == key).one_or_none()
        if entry is None:
            entry = CacheEntry(
                key=key,
                response=json.dumps(payload, separators=(",", ":")),
                status_code=status_code,
                content_type=content_type,
                created_at=created_at,
                expires_at=expires_at,
            )
            db.add(entry)
        else:
            entry.response = json.dumps(payload, separators=(",", ":"))
            entry.status_code = status_code
            entry.content_type = content_type
            entry.created_at = created_at
            entry.expires_at = expires_at
        db.commit()
    finally:
        db.close()