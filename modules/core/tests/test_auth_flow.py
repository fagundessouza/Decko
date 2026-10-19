"""Ciclo completo de autenticação contra a API real e o banco real.

Diferente de test_tenant_isolation, aqui os dados precisam ser efetivados: os endpoints
abrem a própria sessão de banco, então não enxergariam uma transação que o teste mantém
aberta. A empresa criada é removida ao final.
"""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from decko.db import SessionFactory
from decko.main import create_app
from decko_modules.core.cli import _bootstrap
from decko_modules.core.models import Tenant

PASSWORD = "senha-local-de-teste-123"
BASE = "/api/v1/core"


@dataclass
class Fixture:
    tenant_id: uuid.UUID
    slug: str
    email: str


@pytest_asyncio.fixture
async def company() -> AsyncIterator[Fixture]:
    suffix = uuid.uuid4().hex[:8]
    slug = f"teste-{suffix}"
    # Domínio comum de propósito: TLDs reservados como .test e .local são recusados pela
    # validação de e-mail, que é o comportamento correto da aplicação.
    email = f"admin-{suffix}@teste-decko.com.br"

    async with SessionFactory() as session, session.begin():
        tenant, _user, _granted = await _bootstrap(
            session,
            tenant_name="Empresa de Teste",
            tenant_slug=slug,
            admin_email=email,
            admin_name="Administrador de Teste",
            password=PASSWORD,
        )
        tenant_id = tenant.id

    try:
        yield Fixture(tenant_id=tenant_id, slug=slug, email=email)
    finally:
        async with SessionFactory() as session, session.begin():
            await session.execute(delete(Tenant).where(Tenant.id == tenant_id))


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_login_returns_tokens_and_permissions(client: AsyncClient, company: Fixture) -> None:
    response = await client.post(
        f"{BASE}/auth/login",
        json={"tenant_slug": company.slug, "email": company.email, "password": PASSWORD},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0

    me = await client.get(
        f"{BASE}/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}
    )
    assert me.status_code == 200
    session = me.json()
    assert session["user"]["email"] == company.email
    assert session["tenant"]["slug"] == company.slug
    # O administrador recebe as permissões declaradas nos manifestos dos módulos.
    assert "core.user.create" in session["permissions"]


async def test_wrong_password_is_rejected(client: AsyncClient, company: Fixture) -> None:
    response = await client.post(
        f"{BASE}/auth/login",
        json={"tenant_slug": company.slug, "email": company.email, "password": "errada"},
    )
    assert response.status_code == 401


async def test_login_in_another_company_is_rejected(client: AsyncClient, company: Fixture) -> None:
    """O mesmo e-mail e senha não valem em outra empresa."""
    response = await client.post(
        f"{BASE}/auth/login",
        json={
            "tenant_slug": f"inexistente-{uuid.uuid4().hex[:8]}",
            "email": company.email,
            "password": PASSWORD,
        },
    )
    assert response.status_code == 401


async def test_refresh_rotates_and_invalidates_the_previous_token(
    client: AsyncClient, company: Fixture
) -> None:
    login = await client.post(
        f"{BASE}/auth/login",
        json={"tenant_slug": company.slug, "email": company.email, "password": PASSWORD},
    )
    first = login.json()["refresh_token"]

    rotated = await client.post(f"{BASE}/auth/refresh", json={"refresh_token": first})
    assert rotated.status_code == 200
    assert rotated.json()["refresh_token"] != first

    # Reaproveitar o token antigo precisa falhar: é isso que limita o dano de um vazamento.
    replay = await client.post(f"{BASE}/auth/refresh", json={"refresh_token": first})
    assert replay.status_code == 401


async def test_logout_revokes_the_refresh_token(client: AsyncClient, company: Fixture) -> None:
    login = await client.post(
        f"{BASE}/auth/login",
        json={"tenant_slug": company.slug, "email": company.email, "password": PASSWORD},
    )
    refresh_token = login.json()["refresh_token"]

    logout = await client.post(f"{BASE}/auth/logout", json={"refresh_token": refresh_token})
    assert logout.status_code == 204

    after = await client.post(f"{BASE}/auth/refresh", json={"refresh_token": refresh_token})
    assert after.status_code == 401


async def test_me_requires_authentication(client: AsyncClient) -> None:
    response = await client.get(f"{BASE}/auth/me")
    assert response.status_code == 401
