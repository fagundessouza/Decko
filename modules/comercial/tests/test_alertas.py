"""O que está acabando e o que está vencendo.

Os dois avisos que o dono da loja não consegue dar sozinho: um exige somar a razão de
cada produto, o outro exige olhar a validade de cada lote com saldo.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import date, timedelta
from decimal import Decimal

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from decko.db import SessionFactory, bind_tenant
from decko_modules.comercial import alertas, service
from decko_modules.comercial.models import Lote, Produto, TipoMovimento, Unidade
from decko_modules.core.models import Tenant

HOJE = date(2026, 10, 25)


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        await session.begin()
        try:
            yield session
        finally:
            await session.rollback()


async def _loja(session: AsyncSession) -> tuple[Tenant, Unidade]:
    tenant = Tenant(name="Mercado de Teste", slug=f"alerta-{uuid.uuid4().hex[:8]}")
    session.add(tenant)
    await session.flush()
    await bind_tenant(session, tenant.id)

    unidade = await service.criar_unidade(
        session, tenant_id=tenant.id, nome=f"Unidade {uuid.uuid4().hex[:4]}", simbolo="un"
    )
    return tenant, unidade


async def _produto(
    session: AsyncSession,
    tenant: Tenant,
    unidade: Unidade,
    nome: str,
    *,
    minimo: Decimal | None = None,
    controla_lote: bool = False,
) -> Produto:
    produto = Produto(
        tenant_id=tenant.id,
        codigo=f"SKU-{uuid.uuid4().hex[:8]}",
        nome=nome,
        unidade_id=unidade.id,
        estoque_minimo=minimo,
        controla_lote=controla_lote,
    )
    session.add(produto)
    await session.flush()
    return produto


async def _entrada(
    session: AsyncSession,
    tenant: Tenant,
    produto: Produto,
    unidade: Unidade,
    quantidade: str,
    *,
    lote: Lote | None = None,
) -> None:
    await service.registrar_movimento(
        session,
        tenant_id=tenant.id,
        produto_id=produto.id,
        tipo=TipoMovimento.ENTRADA,
        quantidade=Decimal(quantidade),
        unidade_id=unidade.id,
        lote_id=lote.id if lote else None,
        documento="Carga do teste",
    )


async def _lote(session: AsyncSession, tenant: Tenant, produto: Produto, validade: date) -> Lote:
    lote = Lote(
        tenant_id=tenant.id,
        produto_id=produto.id,
        codigo=f"L{uuid.uuid4().hex[:6]}",
        validade=validade,
    )
    session.add(lote)
    await session.flush()
    return lote


# --------------------------------------------------------------- acabando


async def test_produto_abaixo_do_minimo_aparece(session: AsyncSession) -> None:
    tenant, unidade = await _loja(session)
    produto = await _produto(session, tenant, unidade, "Arroz 5kg", minimo=Decimal(10))
    await _entrada(session, tenant, produto, unidade, "8")

    achados = await alertas.acabando(session)

    assert [item.nome for item in achados] == ["Arroz 5kg"]
    assert achados[0].saldo == Decimal(8)
    assert achados[0].acabou is False


async def test_produto_acima_do_minimo_nao_aparece(session: AsyncSession) -> None:
    tenant, unidade = await _loja(session)
    produto = await _produto(session, tenant, unidade, "Arroz 5kg", minimo=Decimal(10))
    await _entrada(session, tenant, produto, unidade, "50")

    assert await alertas.acabando(session) == []


async def test_produto_sem_minimo_nunca_aparece(session: AsyncSession) -> None:
    """Avisar sobre tudo é o mesmo que não avisar."""
    tenant, unidade = await _loja(session)
    await _produto(session, tenant, unidade, "Vassoura", minimo=None)

    assert await alertas.acabando(session) == []


async def test_produto_zerado_aparece_como_acabou(session: AsyncSession) -> None:
    """Saldo zero, sem movimento nenhum: o alerta precisa pegar isso também."""
    tenant, unidade = await _loja(session)
    await _produto(session, tenant, unidade, "Feijão 1kg", minimo=Decimal(5))

    achados = await alertas.acabando(session)

    assert [item.nome for item in achados] == ["Feijão 1kg"]
    assert achados[0].saldo == Decimal(0)
    assert achados[0].acabou is True


async def test_saida_derruba_o_saldo_e_dispara_o_alerta(session: AsyncSession) -> None:
    """É o caminho real: o produto vai vendendo até cruzar o mínimo."""
    tenant, unidade = await _loja(session)
    produto = await _produto(session, tenant, unidade, "Leite 1L", minimo=Decimal(12))
    await _entrada(session, tenant, produto, unidade, "24")

    assert await alertas.acabando(session) == []

    await service.registrar_movimento(
        session,
        tenant_id=tenant.id,
        produto_id=produto.id,
        tipo=TipoMovimento.SAIDA,
        quantidade=Decimal(13),
        unidade_id=unidade.id,
        documento="Venda do teste",
    )

    achados = await alertas.acabando(session)
    assert [item.nome for item in achados] == ["Leite 1L"]
    assert achados[0].saldo == Decimal(11)


# --------------------------------------------------------------- vencendo


async def test_lote_perto_de_vencer_aparece(session: AsyncSession) -> None:
    tenant, unidade = await _loja(session)
    produto = await _produto(session, tenant, unidade, "Iogurte", controla_lote=True)
    lote = await _lote(session, tenant, produto, HOJE + timedelta(days=10))
    await _entrada(session, tenant, produto, unidade, "6", lote=lote)

    achados = await alertas.vencendo(session, hoje=HOJE)

    assert [item.produto_nome for item in achados] == ["Iogurte"]
    assert achados[0].vencido_em(HOJE) is False


async def test_lote_longe_de_vencer_nao_aparece(session: AsyncSession) -> None:
    tenant, unidade = await _loja(session)
    produto = await _produto(session, tenant, unidade, "Macarrão", controla_lote=True)
    lote = await _lote(session, tenant, produto, HOJE + timedelta(days=200))
    await _entrada(session, tenant, produto, unidade, "6", lote=lote)

    assert await alertas.vencendo(session, hoje=HOJE) == []


async def test_lote_vencido_com_saldo_aparece(session: AsyncSession) -> None:
    """Vencido na prateleira é o caso mais grave: não pode sair da lista."""
    tenant, unidade = await _loja(session)
    produto = await _produto(session, tenant, unidade, "Presunto", controla_lote=True)
    lote = await _lote(session, tenant, produto, HOJE - timedelta(days=3))
    await _entrada(session, tenant, produto, unidade, "2", lote=lote)

    achados = await alertas.vencendo(session, hoje=HOJE)

    assert len(achados) == 1
    assert achados[0].vencido_em(HOJE) is True


async def test_lote_vencido_sem_saldo_nao_aparece(session: AsyncSession) -> None:
    """Já saiu da loja; continuar avisando ensina a ignorar o aviso."""
    tenant, unidade = await _loja(session)
    produto = await _produto(session, tenant, unidade, "Queijo", controla_lote=True)
    lote = await _lote(session, tenant, produto, HOJE - timedelta(days=3))
    await _entrada(session, tenant, produto, unidade, "5", lote=lote)
    await service.registrar_movimento(
        session,
        tenant_id=tenant.id,
        produto_id=produto.id,
        tipo=TipoMovimento.SAIDA,
        quantidade=Decimal(5),
        unidade_id=unidade.id,
        lote_id=lote.id,
        documento="Venda do teste",
    )

    assert await alertas.vencendo(session, hoje=HOJE) == []


async def test_lote_sem_validade_nao_aparece(session: AsyncSession) -> None:
    tenant, unidade = await _loja(session)
    produto = await _produto(session, tenant, unidade, "Parafuso", controla_lote=True)
    lote = await _lote(session, tenant, produto, HOJE)
    lote.validade = None
    await session.flush()
    await _entrada(session, tenant, produto, unidade, "100", lote=lote)

    assert await alertas.vencendo(session, hoje=HOJE) == []


# --------------------------------------------------------------- isolamento


async def test_uma_loja_nao_ve_o_alerta_da_outra(session: AsyncSession) -> None:
    primeira, unidade = await _loja(session)
    await _produto(session, primeira, unidade, "Arroz 5kg", minimo=Decimal(10))

    assert len(await alertas.acabando(session)) == 1

    await _loja(session)
    session.expunge_all()

    assert await alertas.acabando(session) == []


async def test_levantar_junta_os_dois(session: AsyncSession) -> None:
    tenant, unidade = await _loja(session)
    await _produto(session, tenant, unidade, "Arroz 5kg", minimo=Decimal(10))
    iogurte = await _produto(session, tenant, unidade, "Iogurte", controla_lote=True)
    lote = await _lote(session, tenant, iogurte, HOJE + timedelta(days=5))
    await _entrada(session, tenant, iogurte, unidade, "6", lote=lote)

    levantamento = await alertas.levantar(session, hoje=HOJE)

    assert levantamento.total == 2
