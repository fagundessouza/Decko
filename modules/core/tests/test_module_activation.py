"""Ativação de módulo por empresa.

O requisito central do produto é a empresa receber só o que contratou. Estes testes provam
que a recusa acontece no servidor, que ter a permissão não basta, e que o núcleo continua
alcançável — senão não haveria como autenticar para contratar nada.

Decisão: ``docs/adr/0004-ativacao-de-modulo-por-empresa.md``.
"""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from decko.db import SessionFactory, bind_tenant
from decko.main import create_app
from decko_modules.core import activation
from decko_modules.core.cli import _bootstrap
from decko_modules.core.models import RolePermission, Tenant

PASSWORD = "senha-local-de-teste-123"
CORE = "/api/v1/core"
AGRO = "/api/v1/agro"


@dataclass
class Company:
    tenant_id: uuid.UUID
    token: str
    slug: str
    email: str


async def _create(client: AsyncClient, *, modules: list[str]) -> Company:
    suffix = uuid.uuid4().hex[:8]
    slug = f"teste-{suffix}"
    email = f"admin-{suffix}@teste-decko.com.br"

    async with SessionFactory() as session, session.begin():
        tenant, _user, _granted = await _bootstrap(
            session,
            tenant_name="Empresa de Teste",
            tenant_slug=slug,
            admin_email=email,
            admin_name="Administrador",
            password=PASSWORD,
            modules=modules,
        )
        tenant_id = tenant.id

    login = await client.post(
        f"{CORE}/auth/login",
        json={"tenant_slug": slug, "email": email, "password": PASSWORD},
    )
    assert login.status_code == 200, login.text
    return Company(tenant_id=tenant_id, token=login.json()["access_token"], slug=slug, email=email)


def _auth(company: Company) -> dict[str, str]:
    return {"Authorization": f"Bearer {company.token}"}


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    created: list[uuid.UUID] = []
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as http:
        http.created = created  # type: ignore[attr-defined]
        try:
            yield http
        finally:
            async with SessionFactory() as session, session.begin():
                for tenant_id in created:
                    await session.execute(delete(Tenant).where(Tenant.id == tenant_id))


async def _company(client: AsyncClient, *, modules: list[str]) -> Company:
    company = await _create(client, modules=modules)
    client.created.append(company.tenant_id)  # type: ignore[attr-defined]
    return company


async def test_module_not_contracted_is_unreachable(client: AsyncClient) -> None:
    company = await _company(client, modules=[])

    response = await client.get(f"{AGRO}/clients", headers=_auth(company))

    # 404 e não 403: para quem não contratou, o módulo não faz parte do sistema.
    assert response.status_code == 404
    assert "agro" in response.json()["detail"]


async def test_having_the_permission_is_not_enough(client: AsyncClient) -> None:
    """O administrador recebe as permissões de todos os módulos instalados.

    Se a permissão bastasse, a barreira não existiria — é por isso que este teste é
    separado do anterior.
    """
    company = await _company(client, modules=[])

    session = await client.get(f"{CORE}/auth/me", headers=_auth(company))
    assert "agro.client.read" in session.json()["permissions"]

    response = await client.get(f"{AGRO}/clients", headers=_auth(company))
    assert response.status_code == 404


async def test_contracted_module_is_reachable(client: AsyncClient) -> None:
    company = await _company(client, modules=["agro"])

    response = await client.get(f"{AGRO}/clients", headers=_auth(company))

    assert response.status_code == 200
    assert response.json() == []


async def test_core_works_without_any_activation(client: AsyncClient) -> None:
    """O núcleo é obrigatório: exigir ativação para conferir ativação não fecha."""
    company = await _company(client, modules=[])

    response = await client.get(f"{CORE}/auth/me", headers=_auth(company))

    assert response.status_code == 200


async def test_session_reports_the_active_modules(client: AsyncClient) -> None:
    company = await _company(client, modules=["agro"])

    body = (await client.get(f"{CORE}/auth/me", headers=_auth(company))).json()

    assert body["active_modules"] == ["agro"]


async def test_catalog_shows_what_is_installed_and_what_is_active(
    client: AsyncClient,
) -> None:
    company = await _company(client, modules=[])

    modules = (await client.get(f"{CORE}/modules", headers=_auth(company))).json()
    by_name = {module["name"]: module for module in modules}

    assert by_name["core"]["required"] is True
    assert by_name["core"]["active"] is True
    assert by_name["agro"]["required"] is False
    assert by_name["agro"]["active"] is False


async def test_activating_opens_the_module(client: AsyncClient) -> None:
    company = await _company(client, modules=[])
    assert (await client.get(f"{AGRO}/clients", headers=_auth(company))).status_code == 404

    activated = await client.post(f"{CORE}/modules/agro/activate", headers=_auth(company))
    assert activated.status_code == 200
    assert [m["name"] for m in activated.json()] == ["agro"]
    assert activated.json()[0]["active"] is True

    assert (await client.get(f"{AGRO}/clients", headers=_auth(company))).status_code == 200


async def test_deactivating_closes_the_module_again(client: AsyncClient) -> None:
    company = await _company(client, modules=["agro"])
    assert (await client.get(f"{AGRO}/clients", headers=_auth(company))).status_code == 200

    await client.delete(f"{CORE}/modules/agro/activate", headers=_auth(company))

    assert (await client.get(f"{AGRO}/clients", headers=_auth(company))).status_code == 404


async def test_activating_twice_is_not_an_error(client: AsyncClient) -> None:
    """Contratar de novo o que já se tem deve continuar funcionando, não falhar."""
    company = await _company(client, modules=["agro"])

    again = await client.post(f"{CORE}/modules/agro/activate", headers=_auth(company))

    assert again.status_code == 200
    assert again.json()[0]["active"] is True


async def test_the_core_cannot_be_deactivated(client: AsyncClient) -> None:
    company = await _company(client, modules=[])

    response = await client.delete(f"{CORE}/modules/core/activate", headers=_auth(company))

    assert response.status_code == 409


async def test_a_module_that_is_not_installed_does_not_exist(client: AsyncClient) -> None:
    company = await _company(client, modules=[])

    response = await client.post(f"{CORE}/modules/supermercado/activate", headers=_auth(company))

    assert response.status_code == 404


async def test_activation_of_one_company_does_not_reach_another(
    client: AsyncClient,
) -> None:
    com_agro = await _company(client, modules=["agro"])
    sem_agro = await _company(client, modules=[])

    assert (await client.get(f"{AGRO}/clients", headers=_auth(com_agro))).status_code == 200
    assert (await client.get(f"{AGRO}/clients", headers=_auth(sem_agro))).status_code == 404

    async with SessionFactory() as session, session.begin():
        await bind_tenant(session, sem_agro.tenant_id)
        assert await activation.active_modules(session, sem_agro.tenant_id) == []


async def test_activating_brings_what_the_module_depends_on(client: AsyncClient) -> None:
    """Quem contrata escolhe o que quer fazer, não a árvore técnica por baixo."""
    company = await _company(client, modules=[])

    activated = await client.post(f"{CORE}/modules/comercial/activate", headers=_auth(company))

    assert activated.status_code == 200
    # O core é dependência, mas é obrigatório: já vale como ativo e não ganha linha.
    assert [module["name"] for module in activated.json()] == ["comercial"]


async def test_the_catalogue_describes_each_module(client: AsyncClient) -> None:
    """A vitrine se monta a partir do manifesto, não de uma lista escrita na interface."""
    company = await _company(client, modules=[])

    modules = (await client.get(f"{CORE}/modules", headers=_auth(company))).json()
    by_name = {module["name"]: module for module in modules}

    assert by_name["comercial"]["category"]
    assert by_name["comercial"]["summary"]
    assert by_name["comercial"]["depends"] == ["core"]


async def test_installing_later_grants_the_module_permissions(client: AsyncClient) -> None:
    """Instalar depois do cadastro precisa deixar o módulo utilizável, não só montado.

    O papel de administrador é montado no bootstrap a partir dos módulos que existiam
    naquele momento. A empresa cadastrada antes de o módulo existir não tinha como receber
    as permissões dele, e instalar entregava um menu que abre numa tela de "permissão
    necessária". Aqui a situação é reproduzida tirando as permissões do papel.
    """
    company = await _company(client, modules=[])

    async with SessionFactory() as session, session.begin():
        await bind_tenant(session, company.tenant_id)
        await session.execute(
            delete(RolePermission).where(RolePermission.permission.like("comercial.%"))
        )

    # O token carrega as permissões de quando foi emitido, então a conferência precisa de
    # um login novo — que é também o que acontece na vida real.
    async def permissoes() -> list[str]:
        login = await client.post(
            f"{CORE}/auth/login",
            json={"tenant_slug": company.slug, "email": company.email, "password": PASSWORD},
        )
        assert login.status_code == 200, login.text
        token = {"Authorization": f"Bearer {login.json()['access_token']}"}
        me = await client.get(f"{CORE}/auth/me", headers=token)
        return list(me.json()["permissions"])

    assert not [p for p in await permissoes() if p.startswith("comercial.")]

    activated = await client.post(f"{CORE}/modules/comercial/activate", headers=_auth(company))
    assert activated.status_code == 200, activated.text

    assert "comercial.produto.read" in await permissoes()
