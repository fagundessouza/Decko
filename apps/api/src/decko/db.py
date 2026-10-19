"""Acesso a banco e aplicação do isolamento por tenant.

Toda sessão entregue a um endpoint roda dentro de uma transação que define
``decko.tenant_id``. ``SET LOCAL`` limita o valor à transação, então uma conexão devolvida
ao pool nunca carrega o tenant da requisição anterior.
"""

from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from sqlalchemy import MetaData, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from decko.config import get_settings
from decko.tenancy import TENANT_GUC, get_current_tenant

# Convenção de nomes explícita: sem ela, o Alembic gera migrações com nomes de constraint
# gerados pelo banco, que variam e tornam o downgrade pouco confiável.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base declarativa compartilhada. Módulos importam esta classe para que todas as
    tabelas fiquem no mesmo MetaData e o Alembic as enxergue."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


_settings = get_settings()

engine = create_async_engine(
    _settings.database_url,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=5,
)

SessionFactory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


async def bind_tenant(session: AsyncSession, tenant_id: UUID | None) -> None:
    """Define o tenant da transação em curso.

    Quando ``tenant_id`` é ``None``, o parâmetro recebe string vazia. As políticas tratam
    isso como "nenhuma linha visível", de modo que o padrão é negar.

    Chamada explicitamente pelo login, que só descobre a empresa depois de consultar a
    tabela ``tenant`` — a única sem RLS, justamente para permitir essa resolução.
    """
    value = str(tenant_id) if tenant_id is not None else ""
    await session.execute(
        text(f"SELECT set_config('{TENANT_GUC}', :tenant_id, true)"),
        {"tenant_id": value},
    )


async def apply_tenant_scope(session: AsyncSession) -> None:
    """Aplica o tenant do contexto da requisição à transação em curso."""
    await bind_tenant(session, get_current_tenant())


async def get_session() -> AsyncIterator[AsyncSession]:
    """Dependência do FastAPI. Commita se o endpoint retornar, desfaz se levantar."""
    async with SessionFactory() as session, session.begin():
        await apply_tenant_scope(session)
        yield session


async def check_connection() -> dict[str, Any]:
    async with engine.connect() as conn:
        version = await conn.scalar(text("SELECT version()"))
        user = await conn.scalar(text("SELECT current_user"))
        bypass = await conn.scalar(
            text("SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user")
        )
    return {"version": version, "user": user, "bypasses_rls": bypass}
