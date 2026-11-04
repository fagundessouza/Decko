"""Acesso a banco e aplicação do isolamento por tenant.

Toda sessão entregue a um endpoint roda dentro de uma transação que define
``decko.tenant_id``. ``SET LOCAL`` limita o valor à transação, então uma conexão devolvida
ao pool nunca carrega o tenant da requisição anterior.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, MetaData, func, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

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


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class TenantMixin:
    """Marca a tabela como pertencente a uma empresa.

    Vive no host e não no módulo núcleo porque todo módulo precisa dela: se morasse em
    ``core``, cada módulo novo passaria a importar modelos de outro módulo, que é
    justamente o acoplamento que a arquitetura evita.

    A chave estrangeira aponta para ``tenant``, tabela do núcleo. O núcleo é dependência
    obrigatória de qualquer módulo, então isso não cria dependência nova.
    """

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenant.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


def primary_key() -> Mapped[uuid.UUID]:
    """Chave primária UUID. Repetida em toda tabela; existe para não repetir o detalhe."""
    return mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


_settings = get_settings()

engine = create_async_engine(
    _settings.database_url,
    echo=False,
    pool_pre_ping=True,
    pool_size=_settings.db_pool_size,
    max_overflow=_settings.db_max_overflow,
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
