"""Identificação da empresa: o bloco que o Planejamento Operacional imprime no cabeçalho.

As permissões ``core.tenant.read`` e ``core.tenant.update`` estavam declaradas no
manifesto sem rota que as usasse, e os campos do cabeçalho nem existiam no modelo — o
documento saía com o bloco em branco. O que está sob teste é o caminho pela API, incluindo
a recusa de CNPJ com dígito verificador errado.
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

PERFIL = {
    "name": "AgroDrone Jatai",
    "cnpj": "12.345.678/0001-95",
    "registro_mapa": "GO-00123",
    "crea": "CREA-GO 56789",
    "cda": "CDA 4321",
    "inscricao_estadual": "10.987.654-3",
    "inscricao_municipal": "987654",
    "rodape": "Rua das Acacias, 100 - Jatai/GO - (64) 3631-0000",
}


@dataclass
class Company:
    tenant_id: uuid.UUID
    token: str

    @property
    def auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


async def _sign_up(http: AsyncClient, nome: str) -> Company:
    suffix = uuid.uuid4().hex[:8]
    slug = f"teste-{suffix}"
    email = f"admin-{suffix}@teste-decko.com.br"

    async with SessionFactory() as session, session.begin():
        tenant, _user, _granted = await _bootstrap(
            session,
            tenant_name=nome,
            tenant_slug=slug,
            admin_email=email,
            admin_name="Administrador de Teste",
            password=PASSWORD,
        )
        tenant_id = tenant.id

    login = await http.post(
        f"{BASE}/auth/login",
        json={"tenant_slug": slug, "email": email, "password": PASSWORD},
    )
    assert login.status_code == 200, login.text
    return Company(tenant_id=tenant_id, token=login.json()["access_token"])


@dataclass
class Scenario:
    client: AsyncClient
    first: Company
    second: Company


@pytest_asyncio.fixture
async def scenario() -> AsyncIterator[Scenario]:
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        first = await _sign_up(http, "Empresa de Teste")
        second = await _sign_up(http, "Concorrente de Teste")
        try:
            yield Scenario(client=http, first=first, second=second)
        finally:
            async with SessionFactory() as session, session.begin():
                await session.execute(
                    delete(Tenant).where(Tenant.id.in_([first.tenant_id, second.tenant_id]))
                )


async def test_the_profile_starts_empty(scenario: Scenario) -> None:
    """O bootstrap cria a empresa com nome e identificador; o resto é preenchido depois."""
    response = await scenario.client.get(f"{BASE}/tenant", headers=scenario.first.auth)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "Empresa de Teste"
    assert body["cnpj"] is None
    assert body["registro_mapa"] is None


async def test_the_header_block_is_saved_and_read_back(scenario: Scenario) -> None:
    saved = await scenario.client.put(f"{BASE}/tenant", headers=scenario.first.auth, json=PERFIL)
    assert saved.status_code == 200, saved.text

    read = await scenario.client.get(f"{BASE}/tenant", headers=scenario.first.auth)
    body = read.json()

    assert body["name"] == "AgroDrone Jatai"
    assert body["registro_mapa"] == "GO-00123"
    assert body["crea"] == "CREA-GO 56789"
    assert body["cda"] == "CDA 4321"
    assert body["inscricao_estadual"] == "10.987.654-3"
    assert body["inscricao_municipal"] == "987654"
    assert body["rodape"].startswith("Rua das Acacias")


async def test_the_cnpj_is_stored_without_its_mask(scenario: Scenario) -> None:
    response = await scenario.client.put(f"{BASE}/tenant", headers=scenario.first.auth, json=PERFIL)

    assert response.json()["cnpj"] == "12345678000195"


async def test_a_wrong_check_digit_is_refused(scenario: Scenario) -> None:
    """Mesma conferência do contratante: o CNPJ da empresa sai impresso no mesmo papel."""
    response = await scenario.client.put(
        f"{BASE}/tenant",
        headers=scenario.first.auth,
        json={**PERFIL, "cnpj": "12.345.678/0001-99"},
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["msg"] == (
        "CNPJ inválido: o dígito verificador não confere."
    )


async def test_an_alphanumeric_cnpj_is_accepted(scenario: Scenario) -> None:
    """Exemplo trabalhado da Receita — a conta está em apps/api/tests/test_documents.py."""
    response = await scenario.client.put(
        f"{BASE}/tenant",
        headers=scenario.first.auth,
        json={**PERFIL, "cnpj": "12.ABC.345/01DE-35"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["cnpj"] == "12ABC34501DE35"


async def test_the_cnpj_can_be_cleared(scenario: Scenario) -> None:
    """Quem digitou errado precisa conseguir apagar enquanto confere o papel."""
    await scenario.client.put(f"{BASE}/tenant", headers=scenario.first.auth, json=PERFIL)

    cleared = await scenario.client.put(
        f"{BASE}/tenant", headers=scenario.first.auth, json={**PERFIL, "cnpj": ""}
    )

    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["cnpj"] is None


async def test_each_company_edits_only_its_own(scenario: Scenario) -> None:
    """A empresa alterada vem do token, nunca do corpo do pedido."""
    await scenario.client.put(f"{BASE}/tenant", headers=scenario.first.auth, json=PERFIL)

    other = await scenario.client.get(f"{BASE}/tenant", headers=scenario.second.auth)

    assert other.json()["name"] == "Concorrente de Teste"
    assert other.json()["cnpj"] is None
    assert other.json()["id"] == str(scenario.second.tenant_id)


async def test_reading_the_profile_requires_authentication(scenario: Scenario) -> None:
    response = await scenario.client.get(f"{BASE}/tenant")

    assert response.status_code == 401


async def test_editing_the_profile_requires_authentication(scenario: Scenario) -> None:
    response = await scenario.client.put(f"{BASE}/tenant", json=PERFIL)

    assert response.status_code == 401
