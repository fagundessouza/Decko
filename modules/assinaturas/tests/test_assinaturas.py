"""Assinatura recorrente: o ciclo, o aviso, o bloqueio e o prazo de confiança.

A regra que estes testes existem para proteger é a dos cinco dias, e ela tem uma sutileza
que um teste descuidado não pega: o relógio conta do **vencimento**, não do aviso. Aviso
que não chega — e-mail no spam, celular trocado — não pode adiar o bloqueio para sempre.

O resto é o que o módulo recusa: cobrar duas vezes a mesma competência, dar baixa no que
já está pago, e conceder prazo com data que já passou.

Decisões: `docs/adr/0013-assinatura-recorrente.md`.
"""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from decko.db import SessionFactory
from decko.main import create_app
from decko_modules.assinaturas.models import Acesso, Cobranca, StatusCobranca
from decko_modules.assinaturas.service import acesso_de, limite_de
from decko_modules.core.cli import _bootstrap
from decko_modules.core.models import Tenant

PASSWORD = "senha-local-de-teste-123"
CORE = "/api/v1/core"
CLIENTES = "/api/v1/clientes"
ASSINATURAS = "/api/v1/assinaturas"


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
    slug = f"assina-{sufixo}"
    email = f"dono-{sufixo}@teste-decko.com.br"

    async with SessionFactory() as session, session.begin():
        tenant, _user, _granted = await _bootstrap(
            session,
            tenant_name="Decko de Teste",
            tenant_slug=slug,
            admin_email=email,
            admin_name="Dono",
            password=PASSWORD,
            modules=["clientes", "assinaturas"],
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


def _cobranca(vencimento: date, *, prazo: date | None = None, paga: bool = False) -> Cobranca:
    """Uma cobrança solta, só para exercitar a regra de acesso. Não vai ao banco."""
    return Cobranca(
        competencia=vencimento.replace(day=1),
        valor=Decimal("100.00"),
        vencimento=vencimento,
        status=StatusCobranca.PAGA if paga else StatusCobranca.ABERTA,
        prazo_ate=prazo,
    )


# ---------------------------------------------------------------- a regra dos 5 dias


def test_em_dia_enquanto_nao_vence() -> None:
    hoje = date(2026, 3, 10)
    assert acesso_de([_cobranca(date(2026, 3, 15))], hoje) is Acesso.EM_DIA


def test_em_aviso_no_dia_seguinte_ao_vencimento() -> None:
    hoje = date(2026, 3, 11)
    assert acesso_de([_cobranca(date(2026, 3, 10))], hoje) is Acesso.EM_AVISO


def test_ainda_em_aviso_no_quinto_dia() -> None:
    """O quinto dia ainda é prazo. Bloquear nele seria dar quatro."""
    assert acesso_de([_cobranca(date(2026, 3, 10))], date(2026, 3, 15)) is Acesso.EM_AVISO


def test_bloqueada_no_sexto_dia() -> None:
    assert acesso_de([_cobranca(date(2026, 3, 10))], date(2026, 3, 16)) is Acesso.BLOQUEADA


def test_o_relogio_conta_do_vencimento_e_nao_do_aviso() -> None:
    """A sutileza da regra: aviso que não chega não adia o bloqueio para sempre.

    Nada no modelo guarda "quando avisei" — e é de propósito. O limite sai do vencimento.
    """
    vencida = _cobranca(date(2026, 3, 10))
    assert limite_de(vencida) == date(2026, 3, 15)


def test_cobranca_paga_nao_bloqueia() -> None:
    assert acesso_de([_cobranca(date(2026, 1, 10), paga=True)], date(2026, 3, 20)) is Acesso.EM_DIA


def test_a_mais_antiga_em_aberto_e_que_manda() -> None:
    """Uma de dois meses atrás bloqueia, ainda que a deste mês nem tenha vencido."""
    antiga = _cobranca(date(2026, 1, 10))
    nova = _cobranca(date(2026, 3, 25))

    assert acesso_de([antiga, nova], date(2026, 3, 20)) is Acesso.BLOQUEADA


# ---------------------------------------------------------------- prazo de confiança


def test_o_prazo_de_confianca_empurra_o_bloqueio() -> None:
    """O caso que o pedido descreve: a pessoa liga depois dos cinco dias e ganha 24 horas."""
    com_prazo = _cobranca(date(2026, 3, 10), prazo=date(2026, 3, 17))

    assert acesso_de([com_prazo], date(2026, 3, 16)) is Acesso.EM_AVISO
    assert acesso_de([com_prazo], date(2026, 3, 17)) is Acesso.EM_AVISO
    # Vencido o prazo, bloqueia sem pedir licença.
    assert acesso_de([com_prazo], date(2026, 3, 18)) is Acesso.BLOQUEADA


def test_prazo_mais_curto_que_o_aviso_nao_encurta_o_aviso() -> None:
    """Conceder prazo nunca piora a situação de quem recebeu."""
    curto = _cobranca(date(2026, 3, 10), prazo=date(2026, 3, 12))

    assert limite_de(curto) == date(2026, 3, 15)


# ---------------------------------------------------------------- pela API


async def _plano(empresa: Empresa, preco: str = "149.90") -> str:
    criado = await empresa.client.post(
        f"{ASSINATURAS}/planos",
        headers=empresa.auth,
        json={"nome": f"Mensal {uuid.uuid4().hex[:4]}", "preco_mensal": preco},
    )
    assert criado.status_code == 201, criado.text
    return str(criado.json()["id"])


async def _cliente(empresa: Empresa, nome: str = "Mercado do Zé") -> str:
    criado = await empresa.client.post(
        f"{CLIENTES}/clientes", headers=empresa.auth, json={"nome": nome, "tipo": "juridica"}
    )
    assert criado.status_code == 201, criado.text
    return str(criado.json()["id"])


async def _assinar(empresa: Empresa, cliente_id: str, plano_id: str, dia: int = 10):
    return await empresa.client.post(
        f"{ASSINATURAS}/assinaturas",
        headers=empresa.auth,
        json={
            "cliente_id": cliente_id,
            "plano_id": plano_id,
            "inicio": "2026-01-01",
            "dia_vencimento": dia,
        },
    )


async def test_assinar_e_ver_quem_assina(empresa: Empresa) -> None:
    resposta = await _assinar(empresa, await _cliente(empresa), await _plano(empresa))

    assert resposta.status_code == 201, resposta.text
    assert resposta.json()["cliente_nome"] == "Mercado do Zé"
    assert resposta.json()["acesso"] == "em_dia"
    assert resposta.json()["cobrancas"] == []


async def test_nao_assina_o_mesmo_plano_duas_vezes(empresa: Empresa) -> None:
    """Cobrar duas vezes o mesmo plano da mesma pessoa chega como reclamação, não aviso."""
    cliente_id = await _cliente(empresa)
    plano_id = await _plano(empresa)
    assert (await _assinar(empresa, cliente_id, plano_id)).status_code == 201

    repetida = await _assinar(empresa, cliente_id, plano_id)

    assert repetida.status_code == 422
    assert "já assina" in repetida.json()["detail"]


async def test_cliente_desativado_nao_assina(empresa: Empresa) -> None:
    cliente_id = await _cliente(empresa)
    await empresa.client.post(f"{CLIENTES}/clientes/{cliente_id}/desativar", headers=empresa.auth)

    recusada = await _assinar(empresa, cliente_id, await _plano(empresa))

    assert recusada.status_code == 422
    assert "desativado" in recusada.json()["detail"]


async def test_gerar_o_mes_e_repetir_nao_cobra_duas_vezes(empresa: Empresa) -> None:
    """A mesma disciplina do dado-semente: rodar duas vezes não pode duplicar."""
    await _assinar(empresa, await _cliente(empresa), await _plano(empresa))

    primeira = await empresa.client.post(
        f"{ASSINATURAS}/cobrancas/gerar", headers=empresa.auth, json={"ano": 2026, "mes": 3}
    )
    segunda = await empresa.client.post(
        f"{ASSINATURAS}/cobrancas/gerar", headers=empresa.auth, json={"ano": 2026, "mes": 3}
    )

    assert primeira.json()["criadas"] == 1
    assert segunda.json()["criadas"] == 0

    lista = await empresa.client.get(f"{ASSINATURAS}/assinaturas", headers=empresa.auth)
    assert len(lista.json()[0]["cobrancas"]) == 1


async def test_o_valor_da_cobranca_e_copia_do_preco(empresa: Empresa) -> None:
    """O que foi cobrado em março precisa continuar sendo o que foi cobrado em março."""
    await _assinar(empresa, await _cliente(empresa), await _plano(empresa, "149.90"))
    await empresa.client.post(
        f"{ASSINATURAS}/cobrancas/gerar", headers=empresa.auth, json={"ano": 2026, "mes": 3}
    )

    lista = await empresa.client.get(f"{ASSINATURAS}/assinaturas", headers=empresa.auth)
    cobranca = lista.json()[0]["cobrancas"][0]

    assert Decimal(cobranca["valor"]) == Decimal("149.90")
    assert cobranca["vencimento"] == "2026-03-10"
    # O servidor já diz quando bloqueia: a tela não refaz regra de cobrança.
    assert cobranca["bloqueia_em"] == "2026-03-15"


async def test_dar_baixa_zera_o_que_esta_em_aberto(empresa: Empresa) -> None:
    await _assinar(empresa, await _cliente(empresa), await _plano(empresa, "100.00"))
    await empresa.client.post(
        f"{ASSINATURAS}/cobrancas/gerar", headers=empresa.auth, json={"ano": 2026, "mes": 3}
    )
    lista = await empresa.client.get(f"{ASSINATURAS}/assinaturas", headers=empresa.auth)
    cobranca_id = lista.json()[0]["cobrancas"][0]["id"]

    paga = await empresa.client.post(
        f"{ASSINATURAS}/cobrancas/{cobranca_id}/baixar",
        headers=empresa.auth,
        json={"pago_em": "2026-03-09", "forma_pagamento": "pix"},
    )

    assert paga.status_code == 200, paga.text
    assert Decimal(paga.json()["em_aberto"]) == Decimal(0)
    assert paga.json()["acesso"] == "em_dia"


async def test_baixa_repetida_e_recusada(empresa: Empresa) -> None:
    await _assinar(empresa, await _cliente(empresa), await _plano(empresa))
    await empresa.client.post(
        f"{ASSINATURAS}/cobrancas/gerar", headers=empresa.auth, json={"ano": 2026, "mes": 3}
    )
    lista = await empresa.client.get(f"{ASSINATURAS}/assinaturas", headers=empresa.auth)
    cobranca_id = lista.json()[0]["cobrancas"][0]["id"]
    corpo = {"pago_em": "2026-03-09"}
    await empresa.client.post(
        f"{ASSINATURAS}/cobrancas/{cobranca_id}/baixar", headers=empresa.auth, json=corpo
    )

    repetida = await empresa.client.post(
        f"{ASSINATURAS}/cobrancas/{cobranca_id}/baixar", headers=empresa.auth, json=corpo
    )

    assert repetida.status_code == 422
    assert "já está paga" in repetida.json()["detail"]


async def test_prazo_com_data_que_ja_passou_e_recusado(empresa: Empresa) -> None:
    """Data que já passou não é prazo; é bloqueio com outro nome."""
    await _assinar(empresa, await _cliente(empresa), await _plano(empresa))
    await empresa.client.post(
        f"{ASSINATURAS}/cobrancas/gerar", headers=empresa.auth, json={"ano": 2026, "mes": 3}
    )
    lista = await empresa.client.get(f"{ASSINATURAS}/assinaturas", headers=empresa.auth)
    cobranca_id = lista.json()[0]["cobrancas"][0]["id"]

    recusado = await empresa.client.post(
        f"{ASSINATURAS}/cobrancas/{cobranca_id}/prazo",
        headers=empresa.auth,
        json={"ate": "2020-01-01", "motivo": "pediu no WhatsApp"},
    )

    assert recusado.status_code == 422
    assert "depois de hoje" in recusado.json()["detail"]


async def test_prazo_concedido_fica_na_trilha(empresa: Empresa) -> None:
    """Sem rastro, "fulano ganhou prazo" vira palavra contra palavra."""
    await _assinar(empresa, await _cliente(empresa), await _plano(empresa))
    await empresa.client.post(
        f"{ASSINATURAS}/cobrancas/gerar", headers=empresa.auth, json={"ano": 2026, "mes": 3}
    )
    lista = await empresa.client.get(f"{ASSINATURAS}/assinaturas", headers=empresa.auth)
    cobranca_id = lista.json()[0]["cobrancas"][0]["id"]
    ate = (date.today() + timedelta(days=1)).isoformat()

    concedido = await empresa.client.post(
        f"{ASSINATURAS}/cobrancas/{cobranca_id}/prazo",
        headers=empresa.auth,
        json={"ate": ate, "motivo": "pediu 24h pelo WhatsApp"},
    )
    assert concedido.status_code == 200, concedido.text
    assert concedido.json()["cobrancas"][0]["prazo_motivo"] == "pediu 24h pelo WhatsApp"

    trilha = await empresa.client.get(
        f"{CORE}/audit?action_prefix=assinatura.", headers=empresa.auth
    )
    entradas = [e for e in trilha.json()["entries"] if e["action"] == "assinatura.cobranca.prazo"]
    assert len(entradas) == 1
    assert entradas[0]["data"]["motivo"] == "pediu 24h pelo WhatsApp"
    assert entradas[0]["author"] == "Dono"


async def test_cancelar_nao_perdoa_divida(empresa: Empresa) -> None:
    """Encerrar a assinatura não apaga o que ficou em aberto."""
    assinatura = await _assinar(empresa, await _cliente(empresa), await _plano(empresa, "100.00"))
    await empresa.client.post(
        f"{ASSINATURAS}/cobrancas/gerar", headers=empresa.auth, json={"ano": 2026, "mes": 3}
    )

    cancelada = await empresa.client.post(
        f"{ASSINATURAS}/assinaturas/{assinatura.json()['id']}/cancelar", headers=empresa.auth
    )

    assert cancelada.json()["status"] == "cancelada"
    assert Decimal(cancelada.json()["em_aberto"]) == Decimal("100.00")


async def test_assinatura_que_comeca_depois_nao_e_cobrada_pelo_mes(empresa: Empresa) -> None:
    cliente_id = await _cliente(empresa)
    plano_id = await _plano(empresa)
    await empresa.client.post(
        f"{ASSINATURAS}/assinaturas",
        headers=empresa.auth,
        json={
            "cliente_id": cliente_id,
            "plano_id": plano_id,
            "inicio": "2026-06-01",
            "dia_vencimento": 10,
        },
    )

    gerada = await empresa.client.post(
        f"{ASSINATURAS}/cobrancas/gerar", headers=empresa.auth, json={"ano": 2026, "mes": 3}
    )

    assert gerada.json()["criadas"] == 0


async def test_listar_exige_autenticacao(empresa: Empresa) -> None:
    assert (await empresa.client.get(f"{ASSINATURAS}/assinaturas")).status_code == 401
