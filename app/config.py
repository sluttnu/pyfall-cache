from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: str = "production"
    app_port: int = 8080

    redis_url: str = "redis://redis:6379/0"
    database_url: str = "postgresql+psycopg://scryfall:scryfall@postgres:5432/scryfall"

    scryfall_api_base: str = "https://api.scryfall.com"
    scryfall_rate_limit_per_second: int = 10

    query_cache_ttl_seconds: int = 86400
    card_cache_ttl_seconds: int = 86400
    card_db_batch_size: int = 75

    default_cache_ttl_seconds: int = 3600


settings = Settings()