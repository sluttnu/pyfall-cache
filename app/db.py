from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Sequence

from sqlalchemy import JSON, String, Text, DateTime, func, select
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
    for card in cards:
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
            ))
        else:
            existing.name = card.get("name") or existing.name
            existing.set_code = card.get("set")
            existing.collector_number = card.get("collector_number")
            existing.rarity = card.get("rarity")
            existing.raw_json = card
    db.commit()

def get_query_cache(db: Session, key: str) -> list[str] | None:
    row = db.execute(select(QueryCacheRecord).where(QueryCacheRecord.key == key)).scalar_one_or_none()
    if row is None:
        return None
    if row.created_at < datetime.utcnow() - timedelta(seconds=settings.query_cache_ttl_seconds):
        db.delete(row)
        db.commit()
        return None
    return row.results

def save_query_cache(db: Session, key: str, query: str, results: list[str]) -> None:
    existing = db.execute(select(QueryCacheRecord).where(QueryCacheRecord.key == key)).scalar_one_or_none()
    if existing is not None:
        existing.query = query
        existing.results = results
        existing.created_at = datetime.utcnow()
    else:
        db.add(QueryCacheRecord(
            key=key,
            query=query,
            results=results,
            created_at=datetime.utcnow(),
        ))
    db.commit()
