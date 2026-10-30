"""Trazer os itens iniciais pela vitrine.

A semente entra na contratação, e só nela (ADR 0010, decisão 3). Isso protege quem já
opera de receber linhas no catálogo sem pedir, e deixa de fora a empresa que instalou o
módulo antes de a semente existir. Esta é a porta pela qual ela pede.

O cenário dos testes é justamente aquela empresa: o módulo ativo, e nenhum item inicial.
"""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

# Importado pelo efeito: é a importação do pacote que registra o carregador de semente.
import decko_modules.comercial  # noqa: F401
from decko.db import SessionFactory, bind_tenant
from decko.main import create_app
from decko_modules.comercial.models import Unidade
from decko_modules.core.cli import _bootstrap
from decko_modules.core.models import SeedRecord, Tenant

CORE = "/api/v1/core"
PASSWORD = "senha-local-de-teste-123"


@dataclass
class Empresa:
    client: AsyncClient
    tenant_id: uuid.UUID
    token: str

    @property
    def auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


@pytest_asyncio.fixture
async def empresa() -> AsyncIterator[Empresa]:
    sufixo = uuid.uuid4().hex[:8]
    slug = f"vitrine-{sufixo}"
    email = f"admin-{sufixo}@teste-decko.com.br"

    async with SessionFactory() as session, session.begin():
        tenant, _user, _granted = await _bootstrap(
            session,
            tenant_name="Loja Antiga",
            tenant_slug=slug,
            admin_email=email,
            admin_name="Administrador",
            password=PASSWORD,
            modules=["comercial"],
        )
        tenant_id = tenant.id

    # Volta a empresa ao estado de quem instalou o módulo antes de a semente existir: o
    # módulo ativo, as unidades inexistentes e nenhum registro de semente.
    async with SessionFactory() as session, session.begin():
        await bind_tenant(session, tenant_id)
        await session.execute(delete(Unidade).where(Unidade.tenant_id == tenant_id))
        await session.execute(delete(SeedRecord).where(SeedRecord.tenant_id == tenant_id))

    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as http:
        login = await http.post(
            f"{CORE}/auth/login",
            json={"tenant_slug": slug, "email": email, "password": PASSWORD},
        )
        assert login.status_code == 200, login.text
        try:
            yield Empresa(client=http, tenant_id=tenant_id, token=login.json()["access_token"])
        finally:
            async with SessionFactory() as session, session.begin():
                await session.execute(delete(Tenant).where(Tenant.id == tenant_id))


async def _unidades(tenant_id: uuid.UUID) -> list[str]:
    async with SessionFactory() as session, session.begin():
        await bind_tenant(session, tenant_id)
        resultado = await session.execute(select(Unidade.nome).order_by(Unidade.nome))
        return list(resultado.scalars().all())


async def test_a_vitrine_diz_quais_modulos_tem_itens_iniciais(empresa: Empresa) -> None:
    """A tela não pode ter a lista escrita à mão: ela sairia de sincronia no módulo novo."""
    catalogo = await empresa.client.get(f"{CORE}/modules", headers=empresa.auth)

    por_nome = {module["name"]: module for module in catalogo.json()}
    assert por_nome["comercial"]["has_seed"] is True
    assert por_nome["agro"]["has_seed"] is False


async def test_trazer_os_itens_iniciais(empresa: Empresa) -> None:
    assert await _unidades(empresa.tenant_id) == []

    resposta = await empresa.client.post(f"{CORE}/modules/comercial/seed", headers=empresa.auth)

    assert resposta.status_code == 200, resposta.text
    assert sorted(resposta.json()["created"]) == [
        "comercial.unidade.kg",
        "comercial.unidade.l",
        "comercial.unidade.un",
    ]
    assert await _unidades(empresa.tenant_id) == ["Litro", "Quilograma", "Unidade"]


async def test_trazer_duas_vezes_nao_duplica(empresa: Empresa) -> None:
    """Clicar de novo precisa ser inofensivo: ninguém lembra se já clicou."""
    await empresa.client.post(f"{CORE}/modules/comercial/seed", headers=empresa.auth)

    segunda = await empresa.client.post(f"{CORE}/modules/comercial/seed", headers=empresa.auth)

    assert segunda.status_code == 200, segunda.text
    assert segunda.json()["created"] == []
    assert len(await _unidades(empresa.tenant_id)) == 3


async def test_item_apagado_nao_volta_pela_vitrine(empresa: Empresa) -> None:
    """O botão traz o que falta, e não desfaz o que a empresa decidiu."""
    await empresa.client.post(f"{CORE}/modules/comercial/seed", headers=empresa.auth)

    async with SessionFactory() as session, session.begin():
        await bind_tenant(session, empresa.tenant_id)
        await session.execute(delete(Unidade).where(Unidade.nome == "Litro"))

    de_novo = await empresa.client.post(f"{CORE}/modules/comercial/seed", headers=empresa.auth)

    assert de_novo.json()["created"] == []
    assert await _unidades(empresa.tenant_id) == ["Quilograma", "Unidade"]


async def test_modulo_nao_contratado_nao_e_semeado(empresa: Empresa) -> None:
    """Semear módulo que a empresa não tem criaria catálogo para tela que nem abre."""
    recusada = await empresa.client.post(f"{CORE}/modules/agro/seed", headers=empresa.auth)

    assert recusada.status_code == 409
    assert "não está ativo" in recusada.json()["detail"]


async def test_modulo_inexistente_nao_e_semeado(empresa: Empresa) -> None:
    recusada = await empresa.client.post(f"{CORE}/modules/pizzaria/seed", headers=empresa.auth)

    assert recusada.status_code == 404


async def test_trazer_itens_exige_autenticacao(empresa: Empresa) -> None:
    sem_token = await empresa.client.post(f"{CORE}/modules/comercial/seed")

    assert sem_token.status_code == 401
