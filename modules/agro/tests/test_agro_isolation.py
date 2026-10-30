"""O isolamento entre empresas vale para as tabelas deste módulo, não só para o núcleo.

Um módulo novo é exatamente onde o isolamento tende a ser esquecido: basta uma tabela sem
política para abrir uma brecha que nenhum teste do núcleo detectaria.
"""

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from decko.db import SessionFactory, bind_tenant
from decko_modules.agro.models import TENANT_SCOPED_TABLES, Aircraft, Client
from decko_modules.core.models import Tenant


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        await session.begin()
        try:
            yield session
        finally:
            await session.rollback()


async def _make_tenant(session: AsyncSession, slug: str) -> Tenant:
    tenant = Tenant(name=f"Empresa {slug}", slug=f"{slug}-{uuid.uuid4().hex[:8]}")
    session.add(tenant)
    await session.flush()
    return tenant


async def _make_client(session: AsyncSession, tenant: Tenant, cpf_cnpj: str) -> Client:
    await bind_tenant(session, tenant.id)
    client = Client(tenant_id=tenant.id, nome="Fazenda de Teste", cpf_cnpj=cpf_cnpj)
    session.add(client)
    await session.flush()
    return client


async def test_every_declared_table_has_a_policy(session: AsyncSession) -> None:
    """Confere a lista declarada no módulo contra o que o banco realmente aplica.

    É o teste que acusa uma tabela nova cuja política ficou de fora da migração.
    """
    rows = (
        await session.execute(
            text(
                "SELECT tablename FROM pg_policies "
                "WHERE policyname = 'tenant_isolation' AND tablename = ANY(:names)"
            ),
            {"names": list(TENANT_SCOPED_TABLES)},
        )
    ).scalars()
    assert set(rows) == set(TENANT_SCOPED_TABLES)


async def test_every_declared_table_forces_rls(session: AsyncSession) -> None:
    """Sem FORCE, o dono da tabela enxerga todas as empresas."""
    rows = (
        await session.execute(
            text(
                "SELECT relname FROM pg_class "
                "WHERE relname = ANY(:names) AND relrowsecurity AND relforcerowsecurity"
            ),
            {"names": list(TENANT_SCOPED_TABLES)},
        )
    ).scalars()
    assert set(rows) == set(TENANT_SCOPED_TABLES)


async def test_select_only_returns_current_tenant(session: AsyncSession) -> None:
    tenant_a = await _make_tenant(session, "agro-alfa")
    tenant_b = await _make_tenant(session, "agro-beta")
    client_a = await _make_client(session, tenant_a, "11111111111")
    await _make_client(session, tenant_b, "22222222222")

    await bind_tenant(session, tenant_a.id)
    visible = (await session.execute(select(Client.id))).scalars().all()

    assert visible == [client_a.id]


async def test_without_tenant_nothing_is_visible(session: AsyncSession) -> None:
    tenant = await _make_tenant(session, "agro-gama")
    await _make_client(session, tenant, "33333333333")

    await bind_tenant(session, None)
    count = await session.scalar(select(func.count()).select_from(Client))

    assert count == 0


async def test_cannot_write_into_another_tenant(session: AsyncSession) -> None:
    tenant_a = await _make_tenant(session, "agro-delta")
    tenant_b = await _make_tenant(session, "agro-epsilon")

    await bind_tenant(session, tenant_a.id)
    session.add(Aircraft(tenant_id=tenant_b.id, prefixo="PP-XXX"))

    with pytest.raises(ProgrammingError):
        await session.flush()
