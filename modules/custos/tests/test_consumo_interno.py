"""Consumo interno: o que saiu do estoque sem ser venda, e contra o quê.

O que estes testes mais guardam é a honestidade do número. O valor do consumo é **cópia do
preço de custo**, não avaliação de estoque — então ele tem de ficar gravado no lançamento,
não pode mudar quando o preço mudar, e não pode virar zero em silêncio quando o produto não
tem preço nenhum. Um número errado estraga mais do que um campo vazio.

E guardam a fronteira: o consumo dá saída de verdade na razão do `comercial`, e some do
saldo. Se não desse, seria um relatório bonito sobre estoque que não existe.

Decisões: `docs/adr/0026-consumo-interno-e-custo-por-centro.md`.
"""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from decimal import Decimal

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, text

from decko.db import SessionFactory
from decko.main import create_app
from decko_modules.core.cli import _bootstrap
from decko_modules.core.models import Tenant

PASSWORD = "senha-local-de-teste-123"
CORE = "/api/v1/core"
COMERCIAL = "/api/v1/comercial"
FINANCEIRO = "/api/v1/financeiro"
CUSTOS = "/api/v1/custos"


@dataclass
class Fazenda:
    client: AsyncClient
    tenant_id: uuid.UUID
    token: str
    unidade_id: str

    @property
    def auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


@pytest_asyncio.fixture
async def fazenda() -> AsyncIterator[Fazenda]:
    sufixo = uuid.uuid4().hex[:8]
    slug = f"custos-{sufixo}"
    email = f"admin-{sufixo}@teste-decko.com.br"

    async with SessionFactory() as session, session.begin():
        tenant, _user, _granted = await _bootstrap(
            session,
            tenant_name="Fazenda de Teste",
            tenant_slug=slug,
            admin_email=email,
            admin_name="Administradora",
            password=PASSWORD,
            modules=["comercial", "financeiro", "custos"],
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
        token = login.json()["access_token"]
        unidades = await http.get(
            f"{COMERCIAL}/unidades", headers={"Authorization": f"Bearer {token}"}
        )
        unidade_id = next(u["id"] for u in unidades.json() if u["nome"] == "Unidade")

        try:
            yield Fazenda(
                client=http, tenant_id=tenant_id, token=token, unidade_id=str(unidade_id)
            )
        finally:
            async with SessionFactory() as session, session.begin():
                await session.execute(delete(Tenant).where(Tenant.id == tenant_id))


async def _centro(fazenda: Fazenda, nome: str) -> str:
    criado = await fazenda.client.post(
        f"{FINANCEIRO}/centros-de-custo", headers=fazenda.auth, json={"nome": nome}
    )
    assert criado.status_code == 201, criado.text
    return str(criado.json()["id"])


async def _produto(fazenda: Fazenda, nome: str, custo: str | None = "25.00") -> str:
    corpo: dict[str, object] = {
        "codigo": f"COD-{uuid.uuid4().hex[:6]}",
        "nome": nome,
        "unidade_id": fazenda.unidade_id,
    }
    if custo is not None:
        corpo["preco_custo"] = custo
    criado = await fazenda.client.post(
        f"{COMERCIAL}/produtos", headers=fazenda.auth, json=corpo
    )
    assert criado.status_code == 201, criado.text
    return str(criado.json()["id"])


async def _entrada(fazenda: Fazenda, produto_id: str, quantidade: str) -> None:
    movimentado = await fazenda.client.post(
        f"{COMERCIAL}/movimentos",
        headers=fazenda.auth,
        json={
            "produto_id": produto_id,
            "tipo": "entrada",
            "quantidade": quantidade,
            "unidade_id": fazenda.unidade_id,
            "motivo": "Compra para o teste",
        },
    )
    assert movimentado.status_code == 201, movimentado.text


async def _saldo(fazenda: Fazenda, produto_id: str) -> Decimal:
    resposta = await fazenda.client.get(
        f"{COMERCIAL}/produtos/{produto_id}/saldo", headers=fazenda.auth
    )
    assert resposta.status_code == 200, resposta.text
    return Decimal(str(resposta.json()["quantidade"]))


async def _consumir(fazenda: Fazenda, **campos: object) -> dict[str, object]:
    corpo: dict[str, object] = {"unidade_id": fazenda.unidade_id}
    corpo.update(campos)
    criado = await fazenda.client.post(
        f"{CUSTOS}/consumos", headers=fazenda.auth, json=corpo
    )
    assert criado.status_code == 201, criado.text
    return dict(criado.json())


# ---------------------------------------------------------------- o consumo


async def test_consumo_tira_do_estoque_de_verdade(fazenda: Fazenda) -> None:
    """Sem isto, o relatório de custo falaria de estoque que nunca saiu."""
    centro = await _centro(fazenda, "Lavoura")
    adubo = await _produto(fazenda, "Adubo NPK")
    await _entrada(fazenda, adubo, "100")

    await _consumir(fazenda, produto_id=adubo, centro_custo_id=centro, quantidade="30")

    assert await _saldo(fazenda, adubo) == Decimal(70)


async def test_valor_sai_do_preco_de_custo_quando_nao_informado(fazenda: Fazenda) -> None:
    centro = await _centro(fazenda, "Lavoura")
    adubo = await _produto(fazenda, "Adubo NPK", custo="25.00")
    await _entrada(fazenda, adubo, "100")

    consumo = await _consumir(
        fazenda, produto_id=adubo, centro_custo_id=centro, quantidade="30"
    )

    assert Decimal(consumo["valor"]) == Decimal("750.00")
    assert Decimal(consumo["custo_unitario"]) == Decimal("25.0000")


async def test_valor_informado_manda(fazenda: Fazenda) -> None:
    centro = await _centro(fazenda, "Lavoura")
    adubo = await _produto(fazenda, "Adubo NPK", custo="25.00")
    await _entrada(fazenda, adubo, "100")

    consumo = await _consumir(
        fazenda,
        produto_id=adubo,
        centro_custo_id=centro,
        quantidade="30",
        valor="900.00",
    )

    assert Decimal(consumo["valor"]) == Decimal("900.00")
    # Sem custo unitário: o valor não veio de multiplicação nenhuma, e fingir que veio
    # daria ao número uma origem que ele não tem.
    assert consumo["custo_unitario"] is None


async def test_produto_sem_preco_de_custo_recusa_em_vez_de_lancar_zero(
    fazenda: Fazenda,
) -> None:
    """Zero é um número, e um número errado estraga mais do que um campo vazio."""
    centro = await _centro(fazenda, "Lavoura")
    semente = await _produto(fazenda, "Semente sem custo", custo=None)
    await _entrada(fazenda, semente, "100")

    recusado = await fazenda.client.post(
        f"{CUSTOS}/consumos",
        headers=fazenda.auth,
        json={
            "produto_id": semente,
            "centro_custo_id": centro,
            "quantidade": "10",
            "unidade_id": fazenda.unidade_id,
        },
    )

    assert recusado.status_code == 422, recusado.text
    assert "preço de custo" in recusado.json()["detail"]


async def test_custo_gravado_nao_muda_quando_o_preco_muda(fazenda: Fazenda) -> None:
    """O preço de custo é referência de hoje. O consumo do mês passado é história."""
    centro = await _centro(fazenda, "Lavoura")
    adubo = await _produto(fazenda, "Adubo NPK", custo="25.00")
    await _entrada(fazenda, adubo, "100")
    consumo = await _consumir(
        fazenda, produto_id=adubo, centro_custo_id=centro, quantidade="10"
    )

    # Direto no banco: não existe endpoint de alterar produto, e o que o teste precisa é
    # simular a passagem do tempo — o preço de custo de hoje não é o de quando se consumiu.
    async with SessionFactory() as sessao, sessao.begin():
        await sessao.execute(
            text("UPDATE comercial_produto SET preco_custo = 90 WHERE id = :id"),
            {"id": adubo},
        )

    listados = await fazenda.client.get(f"{CUSTOS}/consumos", headers=fazenda.auth)
    guardado = next(linha for linha in listados.json() if linha["id"] == consumo["id"])
    assert Decimal(guardado["valor"]) == Decimal("250.00")


async def test_centro_desativado_nao_recebe_consumo(fazenda: Fazenda) -> None:
    centro = await _centro(fazenda, "Safra passada")
    await fazenda.client.post(
        f"{FINANCEIRO}/centros-de-custo/{centro}/desativar", headers=fazenda.auth
    )
    adubo = await _produto(fazenda, "Adubo NPK")
    await _entrada(fazenda, adubo, "100")

    recusado = await fazenda.client.post(
        f"{CUSTOS}/consumos",
        headers=fazenda.auth,
        json={
            "produto_id": adubo,
            "centro_custo_id": centro,
            "quantidade": "10",
            "unidade_id": fazenda.unidade_id,
        },
    )

    assert recusado.status_code == 422, recusado.text
    assert "desativado" in recusado.json()["detail"]


async def test_consumo_alem_do_saldo_passa_e_deixa_o_estoque_negativo(
    fazenda: Fazenda,
) -> None:
    """E isto é decisão, não falta de validação.

    O ADR 0022 escolheu o princípio: *a divergência é o produto, não o defeito*. Se o adubo
    saiu do galpão, ele saiu — recusar o lançamento esconderia do dono exatamente o que ele
    quer ver. O saldo negativo é o aviso de que a conta do mês não fecha.
    """
    centro = await _centro(fazenda, "Lavoura")
    adubo = await _produto(fazenda, "Adubo NPK")
    await _entrada(fazenda, adubo, "5")

    await _consumir(fazenda, produto_id=adubo, centro_custo_id=centro, quantidade="50")

    assert await _saldo(fazenda, adubo) == Decimal(-45)


# ---------------------------------------------------------------- custo por centro


async def test_custo_por_centro_soma_consumo_e_despesa(fazenda: Fazenda) -> None:
    """É este número que responde "quanto custou a lavoura"."""
    lavoura = await _centro(fazenda, "Lavoura")
    adubo = await _produto(fazenda, "Adubo NPK", custo="25.00")
    await _entrada(fazenda, adubo, "100")
    await _consumir(fazenda, produto_id=adubo, centro_custo_id=lavoura, quantidade="40")

    despesa = await fazenda.client.post(
        f"{FINANCEIRO}/despesas",
        headers=fazenda.auth,
        json={
            "descricao": "Colheita terceirizada",
            "valor": "3000.00",
            "vencimento": "2026-12-10",
            "centro_custo_id": lavoura,
        },
    )
    assert despesa.status_code == 201, despesa.text

    resposta = await fazenda.client.get(
        f"{CUSTOS}/por-centro",
        headers=fazenda.auth,
        params={"de": "2026-01-01", "ate": "2027-12-31"},
    )

    linha = next(x for x in resposta.json() if x["centro_id"] == lavoura)
    assert Decimal(linha["consumo"]) == Decimal("1000.00")
    assert Decimal(linha["despesa"]) == Decimal("3000.00")
    assert Decimal(linha["total"]) == Decimal("4000.00")


async def test_custo_por_centro_usa_o_que_foi_pago_quando_ja_pagou(
    fazenda: Fazenda,
) -> None:
    """Antes de pagar vale o devido; depois, o que de fato saiu."""
    lavoura = await _centro(fazenda, "Lavoura")
    despesa = await fazenda.client.post(
        f"{FINANCEIRO}/despesas",
        headers=fazenda.auth,
        json={
            "descricao": "Colheita",
            "valor": "3000.00",
            "vencimento": "2026-12-10",
            "centro_custo_id": lavoura,
        },
    )
    await fazenda.client.post(
        f"{FINANCEIRO}/despesas/{despesa.json()['id']}/baixar",
        headers=fazenda.auth,
        json={"pago_em": "2026-12-18", "valor_pago": "3180.00"},
    )

    resposta = await fazenda.client.get(
        f"{CUSTOS}/por-centro",
        headers=fazenda.auth,
        params={"de": "2026-01-01", "ate": "2027-12-31"},
    )

    linha = next(x for x in resposta.json() if x["centro_id"] == lavoura)
    assert Decimal(linha["despesa"]) == Decimal("3180.00")


async def test_custo_por_centro_ignora_despesa_cancelada(fazenda: Fazenda) -> None:
    lavoura = await _centro(fazenda, "Lavoura")
    despesa = await fazenda.client.post(
        f"{FINANCEIRO}/despesas",
        headers=fazenda.auth,
        json={
            "descricao": "Serviço que não houve",
            "valor": "9000.00",
            "vencimento": "2026-12-10",
            "centro_custo_id": lavoura,
        },
    )
    await fazenda.client.post(
        f"{FINANCEIRO}/despesas/{despesa.json()['id']}/cancelar", headers=fazenda.auth
    )

    resposta = await fazenda.client.get(
        f"{CUSTOS}/por-centro",
        headers=fazenda.auth,
        params={"de": "2026-01-01", "ate": "2027-12-31"},
    )

    assert resposta.json() == []


async def test_maior_custo_vem_primeiro(fazenda: Fazenda) -> None:
    """É por onde quem lê começa a olhar."""
    # Os nomes estão escolhidos para que a ordem alfabética seja diferente da ordem de
    # custo. Sem isso, o teste passaria também com uma ordenação por nome.
    lavoura = await _centro(fazenda, "Lavoura")
    frota = await _centro(fazenda, "Frota")
    for centro, valor in ((lavoura, "7000.00"), (frota, "500.00")):
        criada = await fazenda.client.post(
            f"{FINANCEIRO}/despesas",
            headers=fazenda.auth,
            json={
                "descricao": "Gasto",
                "valor": valor,
                "vencimento": "2026-12-10",
                "centro_custo_id": centro,
            },
        )
        assert criada.status_code == 201, criada.text

    resposta = await fazenda.client.get(
        f"{CUSTOS}/por-centro",
        headers=fazenda.auth,
        params={"de": "2026-01-01", "ate": "2027-12-31"},
    )

    assert [linha["nome"] for linha in resposta.json()] == ["Lavoura", "Frota"]
