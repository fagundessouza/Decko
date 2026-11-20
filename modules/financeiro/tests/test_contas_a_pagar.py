"""Contas a pagar: o que vence, quanto sai, e o que não volta atrás.

A dor que isto resolve veio do levantamento da fazenda — *"quais contas vencem todo mês sem
falta?"* —, mas não é do agro: energia, aluguel e fornecedor vencem em qualquer vertical.

O que os testes mais cobrem é o que a despesa **recusa**: paga não se edita, paga não se
cancela, cancelada não se paga, e conta desativada não recebe baixa nova. São as regras que,
quando faltam, deixam o passado ser reescrito — e aí nenhuma conferência vale.

Decisões: `docs/adr/0024-contas-a-pagar.md`.
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
FINANCEIRO = "/api/v1/financeiro"


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
    slug = f"pagar-{sufixo}"
    email = f"admin-{sufixo}@teste-decko.com.br"

    async with SessionFactory() as session, session.begin():
        tenant, _user, _granted = await _bootstrap(
            session,
            tenant_name="Fazenda de Teste",
            tenant_slug=slug,
            admin_email=email,
            admin_name="Administradora",
            password=PASSWORD,
            modules=["financeiro"],
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
            yield Empresa(client=http, tenant_id=tenant_id, token=login.json()["access_token"])
        finally:
            async with SessionFactory() as session, session.begin():
                await session.execute(delete(Tenant).where(Tenant.id == tenant_id))


async def _lancar(empresa: Empresa, **campos: object) -> dict[str, object]:
    corpo: dict[str, object] = {
        "descricao": "Energia da sede",
        "valor": "480.00",
        "vencimento": "2026-12-10",
    }
    corpo.update(campos)
    criada = await empresa.client.post(f"{FINANCEIRO}/despesas", headers=empresa.auth, json=corpo)
    assert criada.status_code == 201, criada.text
    return dict(criada.json())


async def _conta(empresa: Empresa, nome: str) -> str:
    criada = await empresa.client.post(
        f"{FINANCEIRO}/contas", headers=empresa.auth, json={"nome": nome}
    )
    assert criada.status_code == 201, criada.text
    return str(criada.json()["id"])


# ---------------------------------------------------------------- lançar


async def test_despesa_nasce_em_aberto_e_sem_pagamento(empresa: Empresa) -> None:
    despesa = await _lancar(empresa, fornecedor_nome="Enel")

    assert despesa["status"] == "aberta"
    assert despesa["pago_em"] is None
    assert despesa["valor_pago"] is None
    assert despesa["fornecedor_nome"] == "Enel"


async def test_descricao_em_branco_e_recusada(empresa: Empresa) -> None:
    recusada = await empresa.client.post(
        f"{FINANCEIRO}/despesas",
        headers=empresa.auth,
        json={"descricao": "   ", "valor": "10.00", "vencimento": "2026-12-01"},
    )

    assert recusada.status_code == 422, recusada.text


async def test_valor_negativo_e_recusado(empresa: Empresa) -> None:
    recusada = await empresa.client.post(
        f"{FINANCEIRO}/despesas",
        headers=empresa.auth,
        json={"descricao": "Estorno", "valor": "-10.00", "vencimento": "2026-12-01"},
    )

    assert recusada.status_code == 422, recusada.text


# ---------------------------------------------------------------- baixar


async def test_baixa_sem_valor_usa_o_que_se_devia(empresa: Empresa) -> None:
    """O caso comum é pagar o que estava na conta, e ele não deve dar trabalho."""
    despesa = await _lancar(empresa)

    paga = await empresa.client.post(
        f"{FINANCEIRO}/despesas/{despesa['id']}/baixar",
        headers=empresa.auth,
        json={"pago_em": "2026-12-10"},
    )

    assert paga.status_code == 200, paga.text
    assert paga.json()["status"] == "paga"
    assert Decimal(paga.json()["valor_pago"]) == Decimal("480.00")


async def test_baixa_guarda_o_que_de_fato_saiu(empresa: Empresa) -> None:
    """Juros e multa existem. Fingir que o pago é igual ao devido apagaria a diferença."""
    despesa = await _lancar(empresa)

    paga = await empresa.client.post(
        f"{FINANCEIRO}/despesas/{despesa['id']}/baixar",
        headers=empresa.auth,
        json={"pago_em": "2026-12-18", "valor_pago": "501.37"},
    )

    assert Decimal(paga.json()["valor_pago"]) == Decimal("501.37")
    assert Decimal(paga.json()["valor"]) == Decimal("480.00")


async def test_baixa_aponta_de_qual_conta_saiu(empresa: Empresa) -> None:
    conta_id = await _conta(empresa, "Nubank PJ")
    despesa = await _lancar(empresa)

    paga = await empresa.client.post(
        f"{FINANCEIRO}/despesas/{despesa['id']}/baixar",
        headers=empresa.auth,
        json={"pago_em": "2026-12-10", "conta_id": conta_id},
    )

    assert paga.json()["conta_id"] == conta_id


async def test_conta_desativada_nao_recebe_baixa_nova(empresa: Empresa) -> None:
    """Desativada sai das escolhas novas, e esta é uma escolha nova."""
    conta_id = await _conta(empresa, "Conta antiga")
    await empresa.client.post(f"{FINANCEIRO}/contas/{conta_id}/desativar", headers=empresa.auth)
    despesa = await _lancar(empresa)

    recusada = await empresa.client.post(
        f"{FINANCEIRO}/despesas/{despesa['id']}/baixar",
        headers=empresa.auth,
        json={"pago_em": "2026-12-10", "conta_id": conta_id},
    )

    assert recusada.status_code == 422, recusada.text
    assert "desativada" in recusada.json()["detail"]


async def test_despesa_paga_nao_e_paga_de_novo(empresa: Empresa) -> None:
    despesa = await _lancar(empresa)
    await empresa.client.post(
        f"{FINANCEIRO}/despesas/{despesa['id']}/baixar",
        headers=empresa.auth,
        json={"pago_em": "2026-12-10"},
    )

    repetida = await empresa.client.post(
        f"{FINANCEIRO}/despesas/{despesa['id']}/baixar",
        headers=empresa.auth,
        json={"pago_em": "2026-12-11"},
    )

    assert repetida.status_code == 422, repetida.text


# ---------------------------------------------------------------- o que não volta atrás


async def test_despesa_paga_nao_e_editada(empresa: Empresa) -> None:
    """O valor do que saiu é registro do que aconteceu, e não rascunho."""
    despesa = await _lancar(empresa)
    await empresa.client.post(
        f"{FINANCEIRO}/despesas/{despesa['id']}/baixar",
        headers=empresa.auth,
        json={"pago_em": "2026-12-10"},
    )

    recusada = await empresa.client.put(
        f"{FINANCEIRO}/despesas/{despesa['id']}",
        headers=empresa.auth,
        json={"valor": "1.00"},
    )

    assert recusada.status_code == 422, recusada.text


async def test_despesa_paga_nao_e_cancelada(empresa: Empresa) -> None:
    despesa = await _lancar(empresa)
    await empresa.client.post(
        f"{FINANCEIRO}/despesas/{despesa['id']}/baixar",
        headers=empresa.auth,
        json={"pago_em": "2026-12-10"},
    )

    recusada = await empresa.client.post(
        f"{FINANCEIRO}/despesas/{despesa['id']}/cancelar", headers=empresa.auth
    )

    assert recusada.status_code == 422, recusada.text
    assert "saiu" in recusada.json()["detail"]


async def test_despesa_cancelada_nao_e_paga(empresa: Empresa) -> None:
    despesa = await _lancar(empresa)
    await empresa.client.post(
        f"{FINANCEIRO}/despesas/{despesa['id']}/cancelar", headers=empresa.auth
    )

    recusada = await empresa.client.post(
        f"{FINANCEIRO}/despesas/{despesa['id']}/baixar",
        headers=empresa.auth,
        json={"pago_em": "2026-12-10"},
    )

    assert recusada.status_code == 422, recusada.text


async def test_cancelada_continua_existindo(empresa: Empresa) -> None:
    """Cancelar não é apagar: a linha fica, e a lista do período a mostra."""
    despesa = await _lancar(empresa)
    await empresa.client.post(
        f"{FINANCEIRO}/despesas/{despesa['id']}/cancelar", headers=empresa.auth
    )

    listadas = await empresa.client.get(
        f"{FINANCEIRO}/despesas", headers=empresa.auth, params={"situacao": "cancelada"}
    )

    assert [d["id"] for d in listadas.json()] == [despesa["id"]]


# ---------------------------------------------------------------- editar e listar


async def test_edicao_parcial_nao_apaga_o_que_nao_veio(empresa: Empresa) -> None:
    despesa = await _lancar(empresa, fornecedor_nome="Enel", observacao="medidor 7781")

    editada = await empresa.client.put(
        f"{FINANCEIRO}/despesas/{despesa['id']}",
        headers=empresa.auth,
        json={"valor": "512.90"},
    )

    assert Decimal(editada.json()["valor"]) == Decimal("512.90")
    assert editada.json()["fornecedor_nome"] == "Enel"
    assert editada.json()["observacao"] == "medidor 7781"


async def test_lista_vem_por_vencimento(empresa: Empresa) -> None:
    """Quem paga olha pelo que vence primeiro, e é o que decide o dia.

    As descrições estão escolhidas para que a ordem alfabética — crescente **ou**
    decrescente — seja diferente da ordem de vencimento. Sem isso, o teste passaria também
    com uma ordenação por nome, e não estaria provando nada.
    """
    await _lancar(empresa, descricao="Arrendamento", vencimento="2026-12-05")
    await _lancar(empresa, descricao="Diesel", vencimento="2026-12-20")
    await _lancar(empresa, descricao="Energia", vencimento="2026-12-12")

    listadas = await empresa.client.get(f"{FINANCEIRO}/despesas", headers=empresa.auth)

    assert [d["descricao"] for d in listadas.json()] == ["Arrendamento", "Energia", "Diesel"]


async def test_lista_filtra_o_periodo(empresa: Empresa) -> None:
    await _lancar(empresa, descricao="Novembro", vencimento="2026-11-10")
    await _lancar(empresa, descricao="Dezembro", vencimento="2026-12-10")

    listadas = await empresa.client.get(
        f"{FINANCEIRO}/despesas",
        headers=empresa.auth,
        params={"de": "2026-12-01", "ate": "2026-12-31"},
    )

    assert [d["descricao"] for d in listadas.json()] == ["Dezembro"]


# ---------------------------------------------------------------- resumo


async def test_resumo_soma_aberto_e_pago_do_periodo(empresa: Empresa) -> None:
    await _lancar(empresa, descricao="Arrendamento", valor="3000.00", vencimento="2026-12-05")
    paga = await _lancar(empresa, descricao="Energia", valor="480.00", vencimento="2026-12-10")
    fora = await _lancar(empresa, descricao="Janeiro", valor="999.00", vencimento="2027-01-10")
    await empresa.client.post(
        f"{FINANCEIRO}/despesas/{paga['id']}/baixar",
        headers=empresa.auth,
        json={"pago_em": "2026-12-09", "valor_pago": "475.20"},
    )

    resumo = await empresa.client.get(
        f"{FINANCEIRO}/despesas/resumo",
        headers=empresa.auth,
        params={"de": "2026-12-01", "ate": "2026-12-31"},
    )

    corpo = resumo.json()
    assert Decimal(corpo["em_aberto"]) == Decimal("3000.00")
    # O resumo soma o que **saiu**, e não o que se devia: foi 475,20 e não 480,00.
    assert Decimal(corpo["pago"]) == Decimal("475.20")
    assert corpo["quantidade_em_aberto"] == 1
    assert fora["id"] is not None


async def test_resumo_nao_conta_cancelada(empresa: Empresa) -> None:
    """Conta que não será paga não é dinheiro a sair, e somá-la assustaria à toa."""
    cancelada = await _lancar(empresa, valor="5000.00", vencimento="2026-12-05")
    await empresa.client.post(
        f"{FINANCEIRO}/despesas/{cancelada['id']}/cancelar", headers=empresa.auth
    )

    resumo = await empresa.client.get(
        f"{FINANCEIRO}/despesas/resumo",
        headers=empresa.auth,
        params={"de": "2026-12-01", "ate": "2026-12-31"},
    )

    assert Decimal(resumo.json()["em_aberto"]) == Decimal(0)
    assert resumo.json()["quantidade_em_aberto"] == 0


# ---------------------------------------------------------------- isolamento


async def test_despesa_de_uma_empresa_nao_aparece_na_outra(empresa: Empresa) -> None:
    """A fronteira é do banco, não da consulta — ver docs/adr/0001."""
    await _lancar(empresa, descricao="Arrendamento")

    sufixo = uuid.uuid4().hex[:8]
    slug = f"vizinha-{sufixo}"
    email = f"admin-{sufixo}@teste-decko.com.br"
    async with SessionFactory() as session, session.begin():
        tenant, _user, _granted = await _bootstrap(
            session,
            tenant_name="Vizinha",
            tenant_slug=slug,
            admin_email=email,
            admin_name="Vizinha",
            password=PASSWORD,
            modules=["financeiro"],
        )
        vizinha_id = tenant.id

    try:
        login = await empresa.client.post(
            f"{CORE}/auth/login",
            json={"tenant_slug": slug, "email": email, "password": PASSWORD},
        )
        token = login.json()["access_token"]
        listadas = await empresa.client.get(
            f"{FINANCEIRO}/despesas", headers={"Authorization": f"Bearer {token}"}
        )

        assert listadas.json() == []
    finally:
        async with SessionFactory() as session, session.begin():
            await session.execute(delete(Tenant).where(Tenant.id == vizinha_id))
