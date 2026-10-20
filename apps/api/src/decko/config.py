from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# src/decko/config.py -> src -> api -> apps -> raiz do repositório
REPO_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DECKO_",
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "development"
    debug: bool = False

    # Conexão da aplicação. Usa o papel decko_app, que está sujeito a RLS.
    database_url: str
    # Conexão das migrações. Usa o dono do schema; não é usada em tempo de requisição.
    migration_database_url: str

    secret_key: str
    access_token_ttl_seconds: int = 900
    refresh_token_ttl_seconds: int = 60 * 60 * 24 * 14

    @property
    def modules_dir(self) -> Path:
        return REPO_ROOT / "modules"

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
