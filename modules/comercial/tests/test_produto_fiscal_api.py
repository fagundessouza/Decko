"""Classificação fiscal do produto, pela API.

A conferência do NCM mora no schema, então só acontece de verdade numa chamada HTTP.
Requisito e limites em ``docs/discovery/comercial-produto-fiscal.md``.
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
CORE = "/api/v1/core"
COMERCIAL = "/api/v1/comercial"


@dataclass
class Loja:
    tenant_id: uuid.UUID
    token: str
    unidade_id: str


@pytest_asyncio.fixture
async def loja() -> AsyncIterator[tuple[AsyncClient, Loja]]:
    sufixo = uuid.uuid4().hex[:8]
    slug = f"fiscal-{sufixo}"
    email = f"vendedor-{sufixo}@teste-decko.com.br"

    async with SessionFactory() as session, session.begin():
        tenant, _user, _granted = await _bootstrap(
            session,
            tenant_name="Distribuidora de Teste",
            tenant_slug=slug,
            admin_email=email,
            admin_name="Vendedor",
            password=PASSWORD,
            modules=["comercial"],
        )
        tenant_id = tenant.id

    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        login = await client.post(
            f"{CORE}/auth/login",
            json={"tenant_slug": slug, "email": email, "password": PASSWORD},
        )
        assert login.status_code == 200, login.text
        token = login.json()["access_token"]

        unidade = await client.post(
            f"{COMERCIAL}/unidades",
            headers={"Authorization": f"Bearer {token}"},
            json={"nome": "Unidade", "simbolo": "un"},
        )
        assert unidade.status_code == 201, unidade.text

        try:
            yield client, Loja(tenant_id=tenant_id, token=token, unidade_id=unidade.json()["id"])
        finally:
            async with SessionFactory() as session, session.begin():
                await session.execute(delete(Tenant).where(Tenant.id == tenant_id))


def _auth(dados: Loja) -> dict[str, str]:
    return {"Authorization": f"Bearer {dados.token}"}


def _produto(dados: Loja, **extra: object) -> dict[str, object]:
    return {
        "codigo": f"SKU-{uuid.uuid4().hex[:6]}",
        "nome": "Cabo de energia 3x2,5mm",
        "unidade_id": dados.unidade_id,
        **extra,
    }


async def test_ncm_entra_com_mascara_e_sai_so_com_digitos(
    loja: tuple[AsyncClient, Loja],
) -> None:
    """O vendedor copia do edital, com ponto. O banco guarda o número."""
    client, dados = loja

    criado = await client.post(
        f"{COMERCIAL}/produtos",
        headers=_auth(dados),
        json=_produto(dados, ncm="8544.42.00", cest="17.004.00"),
    )

    assert criado.status_code == 201, criado.text
    assert criado.json()["ncm"] == "85444200"
    assert criado.json()["cest"] == "1700400"


async def test_produto_sem_ncm_continua_valendo(loja: tuple[AsyncClient, Loja]) -> None:
    """Lanchonete não tem licitação. O campo é opcional, e tem de continuar sendo."""
    client, dados = loja

    criado = await client.post(f"{COMERCIAL}/produtos", headers=_auth(dados), json=_produto(dados))

    assert criado.status_code == 201, criado.text
    assert criado.json()["ncm"] is None


async def test_ncm_com_numero_errado_de_digitos_e_recusado(
    loja: tuple[AsyncClient, Loja],
) -> None:
    client, dados = loja

    recusado = await client.post(
        f"{COMERCIAL}/produtos", headers=_auth(dados), json=_produto(dados, ncm="8544.42")
    )

    assert recusado.status_code == 422
    assert "8 dígitos" in recusado.text


async def test_busca_por_ncm_acha_o_produto(loja: tuple[AsyncClient, Loja]) -> None:
    """A pergunta do comprador às vezes vem ao contrário: o NCM primeiro."""
    client, dados = loja

    await client.post(
        f"{COMERCIAL}/produtos",
        headers=_auth(dados),
        json=_produto(dados, nome="Cabo de energia", ncm="85444200"),
    )
    await client.post(
        f"{COMERCIAL}/produtos",
        headers=_auth(dados),
        json=_produto(dados, nome="Fita isolante", ncm="39191000"),
    )

    # Com máscara, que é como o comprador manda.
    achados = await client.get(f"{COMERCIAL}/produtos?busca=8544.42.00", headers=_auth(dados))

    assert achados.status_code == 200, achados.text
    assert [p["nome"] for p in achados.json()] == ["Cabo de energia"]


async def test_busca_por_nome_continua_funcionando(loja: tuple[AsyncClient, Loja]) -> None:
    """O NCM entrou na busca sem tirar o que já havia."""
    client, dados = loja

    await client.post(
        f"{COMERCIAL}/produtos",
        headers=_auth(dados),
        json=_produto(dados, nome="Fita isolante preta", ncm="39191000"),
    )

    achados = await client.get(f"{COMERCIAL}/produtos?busca=isolante", headers=_auth(dados))

    assert [p["nome"] for p in achados.json()] == ["Fita isolante preta"]
