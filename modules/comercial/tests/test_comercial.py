"""Base comercial: unidade em árvore e estoque como razão.

As duas decisões que sustentam todas as verticais, e as duas que são fáceis de errar em
silêncio — conversão de embalagem e saldo que diverge da realidade.

Decisões: ``docs/adr/0006-base-comercial.md``.
"""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from decko.db import SessionFactory, bind_tenant
from decko_modules.comercial import service
from decko_modules.comercial.models import (
    TENANT_SCOPED_TABLES,
    Lote,
    Produto,
    TipoMovimento,
    Unidade,
)
from decko_modules.core.models import Tenant


@dataclass
class Embalagens:
    unidade: Unidade
    caixa: Unidade
    fardo: Unidade


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        await session.begin()
        try:
            yield session
        finally:
            await session.rollback()


async def _tenant(session: AsyncSession, slug: str = "com") -> Tenant:
    tenant = Tenant(name=f"Empresa {slug}", slug=f"{slug}-{uuid.uuid4().hex[:8]}")
    session.add(tenant)
    await session.flush()
    await bind_tenant(session, tenant.id)
    return tenant


async def _embalagens(session: AsyncSession, tenant: Tenant) -> Embalagens:
    """A pilha que o lojista usa: unidade, caixa com 12, fardo com 10 caixas."""
    unidade = await service.criar_unidade(
        session, tenant_id=tenant.id, nome=f"Unidade {uuid.uuid4().hex[:4]}", simbolo="un"
    )
    caixa = await service.criar_unidade(
        session,
        tenant_id=tenant.id,
        nome=f"Caixa 12 {uuid.uuid4().hex[:4]}",
        referencia_id=unidade.id,
        fator_relativo=Decimal(12),
    )
    fardo = await service.criar_unidade(
        session,
        tenant_id=tenant.id,
        nome=f"Fardo 10cx {uuid.uuid4().hex[:4]}",
        referencia_id=caixa.id,
        fator_relativo=Decimal(10),
    )
    return Embalagens(unidade=unidade, caixa=caixa, fardo=fardo)


async def _produto(
    session: AsyncSession,
    tenant: Tenant,
    unidade: Unidade,
    *,
    controla_lote: bool = False,
) -> Produto:
    produto = Produto(
        tenant_id=tenant.id,
        codigo=f"COD-{uuid.uuid4().hex[:8]}",
        nome="Produto de Teste",
        unidade_id=unidade.id,
        controla_lote=controla_lote,
    )
    session.add(produto)
    await session.flush()
    return produto


# ---------------------------------------------------------------- unidades


async def test_the_factor_is_the_product_up_the_tree(session: AsyncSession) -> None:
    """Fardo de 10 caixas de 12 dá 120 sem ninguém fazer a conta."""
    tenant = await _tenant(session)
    emb = await _embalagens(session, tenant)

    assert emb.unidade.fator == Decimal(1)
    assert emb.caixa.fator == Decimal(12)
    assert emb.fardo.fator == Decimal(120)


async def test_the_package_is_described_in_terms_of_the_one_below(
    session: AsyncSession,
) -> None:
    """O fardo é definido em caixas, que é como o lojista enxerga a embalagem."""
    tenant = await _tenant(session)
    emb = await _embalagens(session, tenant)

    assert emb.fardo.referencia_id == emb.caixa.id
    assert emb.fardo.fator_relativo == Decimal(10)


async def test_conversion_between_packages(session: AsyncSession) -> None:
    tenant = await _tenant(session)
    emb = await _embalagens(session, tenant)

    assert service.converter(Decimal(1), de=emb.fardo, para=emb.unidade) == Decimal(120)
    assert service.converter(Decimal(1), de=emb.fardo, para=emb.caixa) == Decimal(10)
    assert service.converter(Decimal(24), de=emb.unidade, para=emb.caixa) == Decimal(2)


async def test_units_from_different_trees_do_not_convert(session: AsyncSession) -> None:
    """Quilo não vira unidade. Recusar é melhor que devolver um número errado."""
    tenant = await _tenant(session)
    emb = await _embalagens(session, tenant)
    quilo = await service.criar_unidade(
        session, tenant_id=tenant.id, nome=f"Quilo {uuid.uuid4().hex[:4]}", simbolo="kg"
    )

    with pytest.raises(service.ConversaoImpossivelError):
        service.converter(Decimal(1), de=quilo, para=emb.unidade)


async def test_a_root_unit_cannot_declare_a_factor(session: AsyncSession) -> None:
    tenant = await _tenant(session)

    with pytest.raises(service.ComercialError):
        await service.criar_unidade(
            session, tenant_id=tenant.id, nome="Errada", fator_relativo=Decimal(12)
        )


# ---------------------------------------------------------------- estoque


async def test_balance_comes_from_the_ledger(session: AsyncSession) -> None:
    tenant = await _tenant(session)
    emb = await _embalagens(session, tenant)
    produto = await _produto(session, tenant, emb.unidade)

    for tipo, quantidade in (
        (TipoMovimento.ENTRADA, Decimal(100)),
        (TipoMovimento.SAIDA, Decimal(30)),
        (TipoMovimento.ENTRADA, Decimal(5)),
    ):
        await service.registrar_movimento(
            session,
            tenant_id=tenant.id,
            produto_id=produto.id,
            tipo=tipo,
            quantidade=quantidade,
            unidade_id=emb.unidade.id,
        )

    assert await service.saldo_do_produto(session, produto.id) == Decimal(75)


async def test_entry_in_boxes_is_stored_in_the_base_unit(session: AsyncSession) -> None:
    """A nota diz 10 fardos; o saldo soma em unidades. Os dois precisam sobreviver."""
    tenant = await _tenant(session)
    emb = await _embalagens(session, tenant)
    produto = await _produto(session, tenant, emb.unidade)

    movimento = await service.registrar_movimento(
        session,
        tenant_id=tenant.id,
        produto_id=produto.id,
        tipo=TipoMovimento.ENTRADA,
        quantidade=Decimal(10),
        unidade_id=emb.fardo.id,
        documento="NF 1234",
    )

    assert movimento.quantidade == Decimal(1200)
    # O que o fornecedor emitiu continua legível no lançamento.
    assert movimento.quantidade_digitada == Decimal(10)
    assert movimento.unidade_id == emb.fardo.id
    assert await service.saldo_do_produto(session, produto.id) == Decimal(1200)


async def test_a_negative_quantity_is_refused(session: AsyncSession) -> None:
    """O sinal vem do tipo; guardar negativo convidaria a somar errado."""
    tenant = await _tenant(session)
    emb = await _embalagens(session, tenant)
    produto = await _produto(session, tenant, emb.unidade)

    with pytest.raises(service.ComercialError):
        await service.registrar_movimento(
            session,
            tenant_id=tenant.id,
            produto_id=produto.id,
            tipo=TipoMovimento.SAIDA,
            quantidade=Decimal(-5),
            unidade_id=emb.unidade.id,
        )


async def test_an_adjustment_corrects_without_rewriting_the_past(
    session: AsyncSession,
) -> None:
    tenant = await _tenant(session)
    emb = await _embalagens(session, tenant)
    produto = await _produto(session, tenant, emb.unidade)

    await service.registrar_movimento(
        session,
        tenant_id=tenant.id,
        produto_id=produto.id,
        tipo=TipoMovimento.ENTRADA,
        quantidade=Decimal(100),
        unidade_id=emb.unidade.id,
    )
    await service.registrar_movimento(
        session,
        tenant_id=tenant.id,
        produto_id=produto.id,
        tipo=TipoMovimento.AJUSTE,
        quantidade=Decimal(3),
        unidade_id=emb.unidade.id,
        motivo="Contagem encontrou 103",
    )

    assert await service.saldo_do_produto(session, produto.id) == Decimal(103)


async def test_the_ledger_cannot_be_rewritten(session: AsyncSession) -> None:
    """Editar o passado apagaria a explicação de por que o saldo é o que é."""
    tenant = await _tenant(session)
    emb = await _embalagens(session, tenant)
    produto = await _produto(session, tenant, emb.unidade)
    movimento = await service.registrar_movimento(
        session,
        tenant_id=tenant.id,
        produto_id=produto.id,
        tipo=TipoMovimento.ENTRADA,
        quantidade=Decimal(10),
        unidade_id=emb.unidade.id,
    )

    alterou = await session.execute(
        text("UPDATE comercial_movimento SET quantidade = 999 WHERE id = :id"),
        {"id": movimento.id},
    )
    apagou = await session.execute(
        text("DELETE FROM comercial_movimento WHERE id = :id"), {"id": movimento.id}
    )

    assert alterou.rowcount == 0
    assert apagou.rowcount == 0


# ---------------------------------------------------------------- lote


async def test_a_product_that_controls_lots_demands_one(session: AsyncSession) -> None:
    tenant = await _tenant(session)
    emb = await _embalagens(session, tenant)
    produto = await _produto(session, tenant, emb.unidade, controla_lote=True)

    with pytest.raises(service.ComercialError) as erro:
        await service.registrar_movimento(
            session,
            tenant_id=tenant.id,
            produto_id=produto.id,
            tipo=TipoMovimento.ENTRADA,
            quantidade=Decimal(10),
            unidade_id=emb.unidade.id,
        )

    assert "lote" in str(erro.value).lower()


async def test_a_lot_from_another_product_is_refused(session: AsyncSession) -> None:
    """Deixar passar misturaria o estoque de dois produtos sem nenhum aviso."""
    tenant = await _tenant(session)
    emb = await _embalagens(session, tenant)
    produto = await _produto(session, tenant, emb.unidade, controla_lote=True)
    outro = await _produto(session, tenant, emb.unidade)

    lote_do_outro = Lote(tenant_id=tenant.id, produto_id=outro.id, codigo="L-1")
    session.add(lote_do_outro)
    await session.flush()

    with pytest.raises(service.ComercialError):
        await service.registrar_movimento(
            session,
            tenant_id=tenant.id,
            produto_id=produto.id,
            tipo=TipoMovimento.ENTRADA,
            quantidade=Decimal(10),
            unidade_id=emb.unidade.id,
            lote_id=lote_do_outro.id,
        )


async def test_balance_is_broken_down_by_lot(session: AsyncSession) -> None:
    """É o que permite ao supermercado saber qual validade está em estoque."""
    tenant = await _tenant(session)
    emb = await _embalagens(session, tenant)
    produto = await _produto(session, tenant, emb.unidade, controla_lote=True)

    lotes = []
    for codigo in ("L-1", "L-2"):
        lote = Lote(tenant_id=tenant.id, produto_id=produto.id, codigo=codigo)
        session.add(lote)
        await session.flush()
        lotes.append(lote)

    await service.registrar_movimento(
        session,
        tenant_id=tenant.id,
        produto_id=produto.id,
        tipo=TipoMovimento.ENTRADA,
        quantidade=Decimal(10),
        unidade_id=emb.unidade.id,
        lote_id=lotes[0].id,
    )
    await service.registrar_movimento(
        session,
        tenant_id=tenant.id,
        produto_id=produto.id,
        tipo=TipoMovimento.ENTRADA,
        quantidade=Decimal(4),
        unidade_id=emb.unidade.id,
        lote_id=lotes[1].id,
    )

    por_lote = {
        item.lote_id: item.quantidade for item in await service.saldo_por_lote(session, produto.id)
    }

    assert por_lote[lotes[0].id] == Decimal(10)
    assert por_lote[lotes[1].id] == Decimal(4)
    assert await service.saldo_do_produto(session, produto.id) == Decimal(14)


# ---------------------------------------------------------------- isolamento


async def test_every_table_is_isolated_between_companies(session: AsyncSession) -> None:
    rows = (
        await session.execute(
            text(
                "SELECT relname FROM pg_class WHERE relname = ANY(:names) "
                "AND relrowsecurity AND relforcerowsecurity"
            ),
            {"names": list(TENANT_SCOPED_TABLES)},
        )
    ).scalars()

    assert set(rows) == set(TENANT_SCOPED_TABLES)


async def test_the_stock_of_one_company_does_not_reach_another(
    session: AsyncSession,
) -> None:
    empresa_a = await _tenant(session, "alfa")
    emb = await _embalagens(session, empresa_a)
    produto = await _produto(session, empresa_a, emb.unidade)
    await service.registrar_movimento(
        session,
        tenant_id=empresa_a.id,
        produto_id=produto.id,
        tipo=TipoMovimento.ENTRADA,
        quantidade=Decimal(50),
        unidade_id=emb.unidade.id,
    )

    empresa_b = await _tenant(session, "beta")
    await bind_tenant(session, empresa_b.id)

    assert await service.saldo_do_produto(session, produto.id) == Decimal(0)
