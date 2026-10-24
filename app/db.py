from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import JSON, String, Text, DateTime, func, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings

settings = get_settings()
engine = create_engine(settings.database_url, future=True, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

class CardRecord(Base):
    __tablename__ = "cards"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, index=True)
    set_code: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    collector_number: Mapped[str | None] = mapped_column(String, nullable=True)
    rarity: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

class QueryCacheRecord(Base):
    __tablename__ = "query_cache"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    results: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def get_db() -> Session:
    db = SessionLocal()
    try:
        return db
    finally:
        pass


def get_card_by_id(db: Session, card_id: str) -> dict | None:
    row = db.execute(select(CardRecord).where(CardRecord.id == card_id)).scalar_one_or_none()
    if row is None:
        return None
    return row.raw_json


def get_card_by_name(db: Session, name: str) -> dict | None:
    row = db.execute(select(CardRecord).where(CardRecord.name == name)).scalar_one_or_none()
    if row is None:
        return None
    return row.raw_json


def save_cards(db: Session, cards: list[dict]) -> None:
    now = datetime.now(timezone.utc)
    for card in cards:
        if not isinstance(card, dict) or "id" not in card:
            continue

        card_id = str(card["id"])
        existing = db.execute(select(CardRecord).where(CardRecord.id == card_id)).scalar_one_or_none()
        if existing is None:
            db.add(CardRecord(
                id=card_id,
                name=card.get("name") or "",
                set_code=card.get("set"),
                collector_number=card.get("collector_number"),
                rarity=card.get("rarity"),
                raw_json=card,
                created_at=now,
                updated_at=now,
            ))
        else:
            existing.name = card.get("name") or existing.name
            existing.set_code = card.get("set")
            existing.collector_number = card.get("collector_number")
            existing.rarity = card.get("rarity")
            existing.raw_json = card
            existing.updated_at = now
    db.commit()


def get_query_cache(db: Session, key: str) -> list[str] | None:
    row = db.execute(select(QueryCacheRecord).where(QueryCacheRecord.key == key)).scalar_one_or_none()
    if row is None:
        return None

    created_at = row.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)

    expires_at = datetime.now(timezone.utc) - timedelta(seconds=settings.query_cache_ttl_seconds)
    if created_at < expires_at:
        db.delete(row)
        db.commit()
        return None

    return row.results


def save_query_cache(db: Session, key: str, query: str, results: list[str]) -> None:
    now = datetime.now(timezone.utc)
    existing = db.execute(select(QueryCacheRecord).where(QueryCacheRecord.key == key)).scalar_one_or_none()
    if existing is not None:
        existing.query = query
        existing.results = results
        existing.created_at = now
    else:
        db.add(QueryCacheRecord(
            key=key,
            query=query,
            results=results,
            created_at=now,
        ))
    db.commit()
