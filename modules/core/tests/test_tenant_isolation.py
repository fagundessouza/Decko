"""Prova de que o isolamento entre empresas é imposto pelo PostgreSQL.

Estes testes rodam contra um PostgreSQL real, usando o mesmo papel da aplicação. Um mock
não serviria aqui: o que está sendo verificado é justamente o comportamento do banco.

Tudo é desfeito ao final de cada teste; nada é gravado.
"""

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from decko.db import SessionFactory, bind_tenant
from decko_modules.core.models import AuditLog, Tenant, User
from decko_modules.core.security import hash_password


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


async def _make_user(session: AsyncSession, tenant: Tenant, email: str) -> User:
    await bind_tenant(session, tenant.id)
    user = User(
        tenant_id=tenant.id,
        email=email,
        full_name="Operador de Teste",
        password_hash=hash_password("senha-de-teste-apenas-local"),
    )
    session.add(user)
    await session.flush()
    return user


async def test_app_role_does_not_bypass_rls(session: AsyncSession) -> None:
    """Se o papel da aplicação ignorasse RLS, todos os demais testes passariam à toa."""
    bypasses = await session.scalar(
        text("SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user")
    )
    assert bypasses is False


async def test_select_only_returns_current_tenant(session: AsyncSession) -> None:
    tenant_a = await _make_tenant(session, "alfa")
    tenant_b = await _make_tenant(session, "beta")
    user_a = await _make_user(session, tenant_a, "operador@alfa.test")
    await _make_user(session, tenant_b, "operador@beta.test")

    await bind_tenant(session, tenant_a.id)
    visible = (await session.execute(select(User.id))).scalars().all()

    assert visible == [user_a.id]


async def test_without_tenant_nothing_is_visible(session: AsyncSession) -> None:
    """Esquecer de definir o tenant não pode vazar dados — o padrão é não ver nada."""
    tenant = await _make_tenant(session, "gama")
    await _make_user(session, tenant, "operador@gama.test")

    await bind_tenant(session, None)
    count = await session.scalar(select(func.count()).select_from(User))

    assert count == 0


async def test_cannot_write_into_another_tenant(session: AsyncSession) -> None:
    """A cláusula WITH CHECK impede gravar linha carimbada com outra empresa."""
    tenant_a = await _make_tenant(session, "delta")
    tenant_b = await _make_tenant(session, "epsilon")

    await bind_tenant(session, tenant_a.id)
    session.add(
        User(
            tenant_id=tenant_b.id,
            email="intruso@delta.test",
            full_name="Intruso",
            password_hash=hash_password("senha-de-teste-apenas-local"),
        )
    )

    with pytest.raises(ProgrammingError):
        await session.flush()


async def test_audit_log_is_append_only(session: AsyncSession) -> None:
    tenant = await _make_tenant(session, "zeta")
    user = await _make_user(session, tenant, "operador@zeta.test")

    entry = AuditLog(tenant_id=tenant.id, user_id=user.id, action="login", entity="user_account")
    session.add(entry)
    await session.flush()

    # A política RESTRICTIVE faz o UPDATE não encontrar linha para alterar.
    result = await session.execute(
        text("UPDATE audit_log SET action = 'adulterado' WHERE id = :id"),
        {"id": entry.id},
    )
    assert result.rowcount == 0

    result = await session.execute(text("DELETE FROM audit_log WHERE id = :id"), {"id": entry.id})
    assert result.rowcount == 0
