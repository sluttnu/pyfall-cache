from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.orm import sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


class CacheEntry(Base):
    __tablename__ = "cache_entries"

    key: Mapped[str] = mapped_column(primary_key=True)
    response: Mapped[str] = mapped_column()
    status_code: Mapped[int] = mapped_column(default=200)
    content_type: Mapped[str] = mapped_column(default="application/json")
    created_at: Mapped[str] = mapped_column(default="1970-01-01T00:00:00Z")
    expires_at: Mapped[str] = mapped_column(default="1970-01-01T00:00:00Z")


engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(
            text("""
            CREATE TABLE IF NOT EXISTS cache_entries (
                key TEXT PRIMARY KEY,
                response TEXT NOT NULL,
                status_code INTEGER NOT NULL DEFAULT 200,
                content_type TEXT NOT NULL DEFAULT 'application/json',
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
            """)
        )