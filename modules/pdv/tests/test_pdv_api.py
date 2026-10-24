"""A venda pela API, do jeito que a tela do caixa a faz.

O serviço já é testado contra o banco em ``test_pdv.py``. Aqui o que se prova é o caminho
inteiro: abrir, bipar, receber, fechar — e que o total que o caixa mostra vem do servidor,
não de uma soma feita na tela.
"""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from decimal import Decimal

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
PDV = "/api/v1/pdv"


@dataclass
class Loja:
    tenant_id: uuid.UUID
    token: str


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    criadas: list[uuid.UUID] = []
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as http:
        http.criadas = criadas  # type: ignore[attr-defined]
        try:
            yield http
        finally:
            async with SessionFactory() as session, session.begin():
                for tenant_id in criadas:
                    await session.execute(delete(Tenant).where(Tenant.id == tenant_id))


async def _loja(client: AsyncClient) -> Loja:
    sufixo = uuid.uuid4().hex[:8]
    slug = f"loja-{sufixo}"
    email = f"caixa-{sufixo}@teste-decko.com.br"

    async with SessionFactory() as session, session.begin():
        tenant, _user, _granted = await _bootstrap(
            session,
            tenant_name="Loja de Teste",
            tenant_slug=slug,
            admin_email=email,
            admin_name="Operador",
            password=PASSWORD,
            modules=["comercial", "pdv"],
        )
        tenant_id = tenant.id

    login = await client.post(
        f"{CORE}/auth/login",
        json={"tenant_slug": slug, "email": email, "password": PASSWORD},
    )
    assert login.status_code == 200, login.text

    client.criadas.append(tenant_id)  # type: ignore[attr-defined]
    return Loja(tenant_id=tenant_id, token=login.json()["access_token"])


def _auth(loja: Loja) -> dict[str, str]:
    return {"Authorization": f"Bearer {loja.token}"}


async def _produto(client: AsyncClient, loja: Loja, *, preco: str = "7.50") -> str:
    unidade = await client.post(
        f"{COMERCIAL}/unidades",
        headers=_auth(loja),
        json={"nome": "Unidade", "simbolo": "un"},
    )
    assert unidade.status_code == 201, unidade.text

    produto = await client.post(
        f"{COMERCIAL}/produtos",
        headers=_auth(loja),
        json={
            "codigo": f"COD-{uuid.uuid4().hex[:6]}",
            "nome": "Pão francês",
            "unidade_id": unidade.json()["id"],
            "preco_venda": preco,
        },
    )
    assert produto.status_code == 201, produto.text

    entrada = await client.post(
        f"{COMERCIAL}/movimentos",
        headers=_auth(loja),
        json={
            "produto_id": produto.json()["id"],
            "tipo": "entrada",
            "quantidade": "50",
            "unidade_id": unidade.json()["id"],
            "documento": "Carga do teste",
        },
    )
    assert entrada.status_code == 201, entrada.text

    return str(produto.json()["id"])


async def test_venda_completa_pela_api(client: AsyncClient) -> None:
    loja = await _loja(client)
    produto_id = await _produto(client, loja, preco="7.50")

    aberta = await client.post(f"{PDV}/vendas", headers=_auth(loja))
    assert aberta.status_code == 201, aberta.text
    venda_id = aberta.json()["id"]
    assert aberta.json()["numero"] is None

    com_item = await client.post(
        f"{PDV}/vendas/{venda_id}/itens",
        headers=_auth(loja),
        json={"produto_id": produto_id, "quantidade": "4"},
    )
    assert com_item.status_code == 200, com_item.text
    assert Decimal(com_item.json()["total"]) == Decimal("30.00")
    assert Decimal(com_item.json()["falta"]) == Decimal("30.00")
    assert com_item.json()["itens"][0]["descricao"] == "Pão francês"

    pago = await client.post(
        f"{PDV}/vendas/{venda_id}/pagamentos",
        headers=_auth(loja),
        json={"forma": "dinheiro", "valor": "50.00"},
    )
    assert pago.status_code == 200, pago.text
    assert Decimal(pago.json()["falta"]) == Decimal("0.00")
    assert Decimal(pago.json()["troco"]) == Decimal("20.00")

    fechada = await client.post(f"{PDV}/vendas/{venda_id}/finalizar", headers=_auth(loja))
    assert fechada.status_code == 200, fechada.text
    assert fechada.json()["status"] == "finalizada"
    assert fechada.json()["numero"] == 1

    saldo = await client.get(f"{COMERCIAL}/produtos/{produto_id}/saldo", headers=_auth(loja))
    assert saldo.status_code == 200, saldo.text
    assert Decimal(saldo.json()["quantidade"]) == Decimal(46)


async def test_fechar_sem_pagar_e_recusado_com_motivo(client: AsyncClient) -> None:
    loja = await _loja(client)
    produto_id = await _produto(client, loja)

    venda_id = (await client.post(f"{PDV}/vendas", headers=_auth(loja))).json()["id"]
    await client.post(
        f"{PDV}/vendas/{venda_id}/itens",
        headers=_auth(loja),
        json={"produto_id": produto_id, "quantidade": "1"},
    )

    recusa = await client.post(f"{PDV}/vendas/{venda_id}/finalizar", headers=_auth(loja))

    assert recusa.status_code == 422
    assert "Falta receber" in recusa.json()["detail"]


async def test_item_removido_sai_do_total(client: AsyncClient) -> None:
    loja = await _loja(client)
    produto_id = await _produto(client, loja, preco="10.00")

    venda_id = (await client.post(f"{PDV}/vendas", headers=_auth(loja))).json()["id"]
    com_item = await client.post(
        f"{PDV}/vendas/{venda_id}/itens",
        headers=_auth(loja),
        json={"produto_id": produto_id, "quantidade": "2"},
    )
    item_id = com_item.json()["itens"][0]["id"]

    sem_item = await client.delete(f"{PDV}/vendas/{venda_id}/itens/{item_id}", headers=_auth(loja))

    assert sem_item.status_code == 200, sem_item.text
    assert sem_item.json()["itens"] == []
    assert Decimal(sem_item.json()["total"]) == Decimal("0.00")


async def test_pdv_nao_contratado_nao_existe(client: AsyncClient) -> None:
    """A loja que não contratou o PDV não enxerga a rota — ver ADR 0004."""
    sufixo = uuid.uuid4().hex[:8]
    slug = f"sem-pdv-{sufixo}"
    email = f"dono-{sufixo}@teste-decko.com.br"

    async with SessionFactory() as session, session.begin():
        tenant, _user, _granted = await _bootstrap(
            session,
            tenant_name="Loja sem PDV",
            tenant_slug=slug,
            admin_email=email,
            admin_name="Dono",
            password=PASSWORD,
            modules=["comercial"],
        )
        client.criadas.append(tenant.id)  # type: ignore[attr-defined]

    login = await client.post(
        f"{CORE}/auth/login",
        json={"tenant_slug": slug, "email": email, "password": PASSWORD},
    )
    token = {"Authorization": f"Bearer {login.json()['access_token']}"}

    assert (await client.get(f"{PDV}/vendas", headers=token)).status_code == 404
