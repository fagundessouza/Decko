"""Conta de recebimento, e o pagamento que aponta para ela.

A dor que isto resolve é de conferência no fim do dia: o Decko já sabia **como** o cliente
pagou e não sabia **onde** o dinheiro caiu. Duas chaves Pix da mesma loja são dois
destinos, e era aí que a soma não fechava.

O que os testes mais cobrem é o que a conta **não** faz: não trava o caixa, não some
quando desativada, e não deixa dois nomes iguais — que sabotariam justamente a conferência.

Decisões: `docs/adr/0014-conta-de-recebimento.md`.
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
FINANCEIRO = "/api/v1/financeiro"
PDV = "/api/v1/pdv"


@dataclass
class Loja:
    client: AsyncClient
    tenant_id: uuid.UUID
    token: str

    @property
    def auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


@pytest_asyncio.fixture
async def loja() -> AsyncIterator[Loja]:
    sufixo = uuid.uuid4().hex[:8]
    slug = f"conta-{sufixo}"
    email = f"caixa-{sufixo}@teste-decko.com.br"

    async with SessionFactory() as session, session.begin():
        tenant, _user, _granted = await _bootstrap(
            session,
            tenant_name="Loja de Teste",
            tenant_slug=slug,
            admin_email=email,
            admin_name="Operador",
            password=PASSWORD,
            modules=["comercial", "clientes", "financeiro", "pdv"],
        )
        tenant_id = tenant.id

    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as http:
        login = await http.post(
            f"{CORE}/auth/login",
            json={"tenant_slug": slug, "email": email, "password": PASSWORD},
        )
        assert login.status_code == 200, login.text
        try:
            yield Loja(client=http, tenant_id=tenant_id, token=login.json()["access_token"])
        finally:
            async with SessionFactory() as session, session.begin():
                await session.execute(delete(Tenant).where(Tenant.id == tenant_id))


async def _conta(loja: Loja, nome: str, **extra: object) -> str:
    criada = await loja.client.post(
        f"{FINANCEIRO}/contas", headers=loja.auth, json={"nome": nome, **extra}
    )
    assert criada.status_code == 201, criada.text
    return str(criada.json()["id"])


async def _venda_com_item(loja: Loja) -> str:
    unidades = await loja.client.get(f"{COMERCIAL}/unidades", headers=loja.auth)
    unidade_id = next(u["id"] for u in unidades.json() if u["nome"] == "Unidade")
    produto = await loja.client.post(
        f"{COMERCIAL}/produtos",
        headers=loja.auth,
        json={
            "codigo": f"COD-{uuid.uuid4().hex[:6]}",
            "nome": "Refrigerante 2L",
            "unidade_id": unidade_id,
            "preco_venda": "10.00",
        },
    )
    venda = await loja.client.post(f"{PDV}/vendas", headers=loja.auth, json={})
    venda_id = venda.json()["id"]
    await loja.client.post(
        f"{PDV}/vendas/{venda_id}/itens",
        headers=loja.auth,
        json={"produto_id": produto.json()["id"], "quantidade": "1"},
    )
    return str(venda_id)


# ---------------------------------------------------------------- a conta


async def test_criar_conta_com_chave_pix(loja: Loja) -> None:
    criada = await loja.client.post(
        f"{FINANCEIRO}/contas",
        headers=loja.auth,
        json={"nome": "Nubank PJ", "instituicao": "Nubank", "chave_pix": "11222333000181"},
    )

    assert criada.status_code == 201, criada.text
    assert criada.json()["chave_pix"] == "11222333000181"
    assert criada.json()["ativa"] is True


async def test_duas_contas_com_o_mesmo_nome_sao_recusadas(loja: Loja) -> None:
    """Dois nomes iguais sabotam a conferência que a conta existe para permitir."""
    await _conta(loja, "Cofre")

    repetida = await loja.client.post(
        f"{FINANCEIRO}/contas", headers=loja.auth, json={"nome": "Cofre"}
    )

    assert repetida.status_code == 422
    assert "Já existe uma conta" in repetida.json()["detail"]


async def test_conta_desativada_some_da_lista_mas_continua_existindo(loja: Loja) -> None:
    conta_id = await _conta(loja, "Banco antigo")
    await loja.client.post(f"{FINANCEIRO}/contas/{conta_id}/desativar", headers=loja.auth)

    ativas = await loja.client.get(f"{FINANCEIRO}/contas", headers=loja.auth)
    todas = await loja.client.get(f"{FINANCEIRO}/contas?incluir_inativas=true", headers=loja.auth)

    assert [c["nome"] for c in ativas.json()] == []
    assert [c["nome"] for c in todas.json()] == ["Banco antigo"]


# ---------------------------------------------------------------- o pagamento


async def test_pagamento_sem_conta_continua_funcionando(loja: Loja) -> None:
    """O balcão não para para escolher conta. É a decisão 3 do ADR 0014."""
    venda_id = await _venda_com_item(loja)

    pago = await loja.client.post(
        f"{PDV}/vendas/{venda_id}/pagamentos",
        headers=loja.auth,
        json={"forma": "dinheiro", "valor": "10.00"},
    )

    assert pago.status_code == 200, pago.text
    assert pago.json()["pagamentos"][0]["conta_id"] is None
    assert pago.json()["pagamentos"][0]["conta_nome"] is None


async def test_pagamento_diz_em_qual_conta_caiu(loja: Loja) -> None:
    """A pergunta que o Decko não sabia responder."""
    conta_id = await _conta(loja, "Nubank PJ")
    venda_id = await _venda_com_item(loja)

    pago = await loja.client.post(
        f"{PDV}/vendas/{venda_id}/pagamentos",
        headers=loja.auth,
        json={"forma": "pix", "valor": "10.00", "conta_id": conta_id},
    )

    assert pago.status_code == 200, pago.text
    assert pago.json()["pagamentos"][0]["conta_nome"] == "Nubank PJ"


async def test_dois_pix_em_contas_diferentes_na_mesma_venda(loja: Loja) -> None:
    """O caso exato da cliente: "às vezes recebia o Pix em uma conta ou em outra"."""
    nubank = await _conta(loja, "Nubank PJ")
    bb = await _conta(loja, "Banco do Brasil")
    venda_id = await _venda_com_item(loja)

    await loja.client.post(
        f"{PDV}/vendas/{venda_id}/pagamentos",
        headers=loja.auth,
        json={"forma": "pix", "valor": "6.00", "conta_id": nubank},
    )
    segunda = await loja.client.post(
        f"{PDV}/vendas/{venda_id}/pagamentos",
        headers=loja.auth,
        json={"forma": "pix", "valor": "4.00", "conta_id": bb},
    )

    destinos = {p["conta_nome"] for p in segunda.json()["pagamentos"]}
    assert destinos == {"Nubank PJ", "Banco do Brasil"}
    assert Decimal(segunda.json()["pago"]) == Decimal("10.00")


async def test_conta_desativada_nao_recebe_pagamento_novo(loja: Loja) -> None:
    conta_id = await _conta(loja, "Conta encerrada")
    await loja.client.post(f"{FINANCEIRO}/contas/{conta_id}/desativar", headers=loja.auth)
    venda_id = await _venda_com_item(loja)

    recusado = await loja.client.post(
        f"{PDV}/vendas/{venda_id}/pagamentos",
        headers=loja.auth,
        json={"forma": "pix", "valor": "10.00", "conta_id": conta_id},
    )

    assert recusado.status_code == 422
    assert "desativada" in recusado.json()["detail"]


async def test_conta_inexistente_e_recusada(loja: Loja) -> None:
    venda_id = await _venda_com_item(loja)

    recusado = await loja.client.post(
        f"{PDV}/vendas/{venda_id}/pagamentos",
        headers=loja.auth,
        json={"forma": "pix", "valor": "10.00", "conta_id": str(uuid.uuid4())},
    )

    assert recusado.status_code == 422
    assert "não encontrada" in recusado.json()["detail"]


async def test_renomear_a_conta_vale_para_o_historico(loja: Loja) -> None:
    """O nome é lido na hora, não copiado: é cadastro, não fato histórico.

    É a mesma distinção do cliente na venda — e o oposto do preço do item, que é cópia.
    """
    conta_id = await _conta(loja, "Nubnak PJ")
    venda_id = await _venda_com_item(loja)
    await loja.client.post(
        f"{PDV}/vendas/{venda_id}/pagamentos",
        headers=loja.auth,
        json={"forma": "pix", "valor": "10.00", "conta_id": conta_id},
    )

    async with SessionFactory() as session, session.begin():
        from decko.db import bind_tenant
        from decko_modules.financeiro.models import ContaRecebimento

        await bind_tenant(session, loja.tenant_id)
        conta = await session.get(ContaRecebimento, uuid.UUID(conta_id))
        assert conta is not None
        conta.nome = "Nubank PJ"

    venda = await loja.client.get(f"{PDV}/vendas/{venda_id}", headers=loja.auth)
    assert venda.json()["pagamentos"][0]["conta_nome"] == "Nubank PJ"


async def test_instalar_o_pdv_traz_as_contas(loja: Loja) -> None:
    """O PDV declara `financeiro` em depends — contratar um traz o outro."""
    catalogo = await loja.client.get(f"{CORE}/modules", headers=loja.auth)
    pdv = next(m for m in catalogo.json() if m["name"] == "pdv")

    assert "financeiro" in pdv["depends"]


async def test_listar_contas_exige_autenticacao(loja: Loja) -> None:
    assert (await loja.client.get(f"{FINANCEIRO}/contas")).status_code == 401
