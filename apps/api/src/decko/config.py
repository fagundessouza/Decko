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
    # Conferir a senha escolhida contra vazamentos conhecidos. Desligar é para instalação
    # sem internet, onde a consulta é latência garantida sem resposta possível — ver
    # docs/adr/0011-senha-conhecidamente-vazada.md.
    breach_check_enabled: bool = True
    access_token_ttl_seconds: int = 900
    refresh_token_ttl_seconds: int = 60 * 60 * 24 * 14

    # Origens que podem chamar a API de outro domínio, separadas por vírgula.
    #
    # Vazio é o padrão, e quer dizer **nenhuma**: com front e API atrás do mesmo domínio —
    # ou atrás do proxy do Vite em desenvolvimento — não há requisição entre origens, e
    # ligar CORS sem precisar só amplia a superfície.
    cors_origins: str = ""

    # Conexões que a aplicação mantém com o banco. Era fixo em código, escolhido quando
    # havia uma empresa; vira configuração porque o número certo depende da máquina e da
    # quantidade de inquilinos — ver docs/adr/0015-modo-de-implantacao-e-licenca.md.
    #
    # Cada conexão custa memória **no PostgreSQL**, não só aqui: aumentar sem olhar o
    # `max_connections` do servidor troca um limite por outro.
    db_pool_size: int = 10
    db_max_overflow: int = 5

    @property
    def allowed_origins(self) -> list[str]:
        """As origens, separadas e sem espaço em branco."""
        return [origem.strip() for origem in self.cors_origins.split(",") if origem.strip()]

    @property
    def modules_dir(self) -> Path:
        return REPO_ROOT / "modules"

    @property
    def profiles_dir(self) -> Path:
        return REPO_ROOT / "profiles"

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
