"""Ponto de venda: o que não pode dar errado no caixa.

Duas coisas sustentam o módulo e falham em silêncio quando erradas: a venda fechar sem o
estoque baixar, e o total mudar depois de o cliente pagar. Os dois têm teste aqui.

Decisões: ``docs/adr/0008-ponto-de-venda.md``.
"""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from decko.db import SessionFactory, bind_tenant
from decko_modules.comercial import service as comercial
from decko_modules.comercial.models import Produto, Unidade
from decko_modules.core.models import Tenant
from decko_modules.pdv import service
from decko_modules.pdv.models import FormaPagamento, StatusVenda, Venda


@dataclass
class Loja:
    tenant: Tenant
    unidade: Unidade
    caixa: Unidade
    produto: Produto


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        await session.begin()
        try:
            yield session
        finally:
            await session.rollback()


async def _loja(session: AsyncSession, slug: str = "pdv", preco: str = "10.00") -> Loja:
    tenant = Tenant(name=f"Loja {slug}", slug=f"{slug}-{uuid.uuid4().hex[:8]}")
    session.add(tenant)
    await session.flush()
    await bind_tenant(session, tenant.id)

    unidade = await comercial.criar_unidade(
        session, tenant_id=tenant.id, nome=f"Unidade {uuid.uuid4().hex[:4]}", simbolo="un"
    )
    caixa = await comercial.criar_unidade(
        session,
        tenant_id=tenant.id,
        nome=f"Caixa 12 {uuid.uuid4().hex[:4]}",
        referencia_id=unidade.id,
        fator_relativo=Decimal(12),
    )

    produto = Produto(
        tenant_id=tenant.id,
        codigo=f"COD-{uuid.uuid4().hex[:8]}",
        nome="Refrigerante 2L",
        unidade_id=unidade.id,
        preco_venda=Decimal(preco),
    )
    session.add(produto)
    await session.flush()

    return Loja(tenant=tenant, unidade=unidade, caixa=caixa, produto=produto)


async def _com_estoque(session: AsyncSession, loja: Loja, quantidade: str = "100") -> None:
    await comercial.registrar_movimento(
        session,
        tenant_id=loja.tenant.id,
        produto_id=loja.produto.id,
        tipo=comercial.TipoMovimento.ENTRADA,
        quantidade=Decimal(quantidade),
        unidade_id=loja.unidade.id,
        documento="Carga inicial do teste",
    )


async def test_venda_fechada_baixa_o_estoque(session: AsyncSession) -> None:
    """O essencial: cupom e estoque na mesma transação, ou nenhum dos dois."""
    loja = await _loja(session)
    await _com_estoque(session, loja, "100")

    venda = await service.abrir_venda(session, tenant_id=loja.tenant.id)
    await service.adicionar_item(
        session, venda=venda, produto_id=loja.produto.id, quantidade=Decimal(3)
    )
    await service.registrar_pagamento(
        session, venda=venda, forma=FormaPagamento.PIX, valor=Decimal("30.00")
    )

    fechamento = await service.finalizar_venda(session, venda=venda)

    assert fechamento.total == Decimal("30.00")
    assert fechamento.troco == Decimal("0.00")
    assert venda.status is StatusVenda.FINALIZADA
    assert venda.numero == 1
    assert await comercial.saldo_do_produto(session, loja.produto.id) == Decimal(97)


async def test_venda_em_caixa_baixa_na_unidade_base(session: AsyncSession) -> None:
    """Vender 2 caixas de 12 tira 24 unidades, não 2."""
    loja = await _loja(session)
    await _com_estoque(session, loja, "100")

    venda = await service.abrir_venda(session, tenant_id=loja.tenant.id)
    await service.adicionar_item(
        session,
        venda=venda,
        produto_id=loja.produto.id,
        quantidade=Decimal(2),
        unidade_id=loja.caixa.id,
        preco_unitario=Decimal("100.00"),
    )
    await service.registrar_pagamento(
        session, venda=venda, forma=FormaPagamento.DEBITO, valor=Decimal("200.00")
    )
    await service.finalizar_venda(session, venda=venda)

    assert await comercial.saldo_do_produto(session, loja.produto.id) == Decimal(76)


async def test_nao_fecha_sem_receber_tudo(session: AsyncSession) -> None:
    loja = await _loja(session)
    await _com_estoque(session, loja)

    venda = await service.abrir_venda(session, tenant_id=loja.tenant.id)
    await service.adicionar_item(
        session, venda=venda, produto_id=loja.produto.id, quantidade=Decimal(2)
    )
    await service.registrar_pagamento(
        session, venda=venda, forma=FormaPagamento.DINHEIRO, valor=Decimal("15.00")
    )

    with pytest.raises(service.PdvError, match="Falta receber"):
        await service.finalizar_venda(session, venda=venda)

    # E o estoque não foi tocado por uma venda que não fechou.
    assert await comercial.saldo_do_produto(session, loja.produto.id) == Decimal(100)


async def test_troco_so_sai_de_dinheiro(session: AsyncSession) -> None:
    """Receber no cartão mais do que a venda e devolver em espécie vira saque."""
    loja = await _loja(session)
    await _com_estoque(session, loja)

    venda = await service.abrir_venda(session, tenant_id=loja.tenant.id)
    await service.adicionar_item(
        session, venda=venda, produto_id=loja.produto.id, quantidade=Decimal(1)
    )
    await service.registrar_pagamento(
        session, venda=venda, forma=FormaPagamento.CREDITO, valor=Decimal("50.00")
    )

    with pytest.raises(service.PdvError, match="dinheiro"):
        await service.finalizar_venda(session, venda=venda)


async def test_dinheiro_devolve_troco(session: AsyncSession) -> None:
    loja = await _loja(session)
    await _com_estoque(session, loja)

    venda = await service.abrir_venda(session, tenant_id=loja.tenant.id)
    await service.adicionar_item(
        session, venda=venda, produto_id=loja.produto.id, quantidade=Decimal(1)
    )
    await service.registrar_pagamento(
        session, venda=venda, forma=FormaPagamento.DINHEIRO, valor=Decimal("50.00")
    )

    fechamento = await service.finalizar_venda(session, venda=venda)

    assert fechamento.troco == Decimal("40.00")


async def test_preco_do_item_e_copia_e_nao_referencia(session: AsyncSession) -> None:
    """Remarcar o produto amanhã não pode mudar o que o cliente pagou hoje."""
    loja = await _loja(session, preco="10.00")
    await _com_estoque(session, loja)

    venda = await service.abrir_venda(session, tenant_id=loja.tenant.id)
    await service.adicionar_item(
        session, venda=venda, produto_id=loja.produto.id, quantidade=Decimal(2)
    )
    await service.registrar_pagamento(
        session, venda=venda, forma=FormaPagamento.PIX, valor=Decimal("20.00")
    )
    await service.finalizar_venda(session, venda=venda)

    loja.produto.preco_venda = Decimal("99.00")
    await session.flush()

    assert await service.total_a_pagar(session, venda) == Decimal("20.00")


async def test_venda_fechada_nao_aceita_mais_item(session: AsyncSession) -> None:
    loja = await _loja(session)
    await _com_estoque(session, loja)

    venda = await service.abrir_venda(session, tenant_id=loja.tenant.id)
    await service.adicionar_item(
        session, venda=venda, produto_id=loja.produto.id, quantidade=Decimal(1)
    )
    await service.registrar_pagamento(
        session, venda=venda, forma=FormaPagamento.PIX, valor=Decimal("10.00")
    )
    await service.finalizar_venda(session, venda=venda)

    with pytest.raises(service.PdvError, match="finalizada"):
        await service.adicionar_item(
            session, venda=venda, produto_id=loja.produto.id, quantidade=Decimal(1)
        )


async def test_venda_fechada_nao_e_cancelada(session: AsyncSession) -> None:
    """Desfazer saída de estoque já lançada é devolução, que ainda não tem requisito."""
    loja = await _loja(session)
    await _com_estoque(session, loja)

    venda = await service.abrir_venda(session, tenant_id=loja.tenant.id)
    await service.adicionar_item(
        session, venda=venda, produto_id=loja.produto.id, quantidade=Decimal(1)
    )
    await service.registrar_pagamento(
        session, venda=venda, forma=FormaPagamento.PIX, valor=Decimal("10.00")
    )
    await service.finalizar_venda(session, venda=venda)

    with pytest.raises(service.PdvError, match="devolução"):
        await service.cancelar_venda(session, venda=venda)


async def test_venda_sem_item_nao_fecha(session: AsyncSession) -> None:
    loja = await _loja(session)
    venda = await service.abrir_venda(session, tenant_id=loja.tenant.id)

    with pytest.raises(service.PdvError, match="sem itens"):
        await service.finalizar_venda(session, venda=venda)


async def test_produto_sem_preco_nao_vai_a_zero(session: AsyncSession) -> None:
    """Vender de graça por omissão só aparece no fechamento do caixa."""
    loja = await _loja(session)
    loja.produto.preco_venda = None
    await session.flush()

    venda = await service.abrir_venda(session, tenant_id=loja.tenant.id)

    with pytest.raises(service.PdvError, match="preço de venda"):
        await service.adicionar_item(
            session, venda=venda, produto_id=loja.produto.id, quantidade=Decimal(1)
        )


async def test_produto_com_lote_exige_lote(session: AsyncSession) -> None:
    loja = await _loja(session)
    loja.produto.controla_lote = True
    await session.flush()

    venda = await service.abrir_venda(session, tenant_id=loja.tenant.id)

    with pytest.raises(service.PdvError, match="lote"):
        await service.adicionar_item(
            session, venda=venda, produto_id=loja.produto.id, quantidade=Decimal(1)
        )


async def test_numeracao_e_por_empresa(session: AsyncSession) -> None:
    """Duas lojas começam no 1. O número é da empresa, não da instalação."""
    primeira = await _loja(session, slug="um")
    await _com_estoque(session, primeira)

    async def vender(loja: Loja) -> Venda:
        await bind_tenant(session, loja.tenant.id)
        venda = await service.abrir_venda(session, tenant_id=loja.tenant.id)
        await service.adicionar_item(
            session, venda=venda, produto_id=loja.produto.id, quantidade=Decimal(1)
        )
        await service.registrar_pagamento(
            session, venda=venda, forma=FormaPagamento.PIX, valor=Decimal("10.00")
        )
        await service.finalizar_venda(session, venda=venda)
        return venda

    assert (await vender(primeira)).numero == 1
    assert (await vender(primeira)).numero == 2

    segunda = await _loja(session, slug="dois")
    await _com_estoque(session, segunda)
    assert (await vender(segunda)).numero == 1


async def test_uma_loja_nao_enxerga_a_venda_da_outra(session: AsyncSession) -> None:
    """Isolamento garantido pelo banco, não pela disciplina de quem escreve a consulta."""
    primeira = await _loja(session, slug="vis-um")
    await _com_estoque(session, primeira)

    venda = await service.abrir_venda(session, tenant_id=primeira.tenant.id)
    await service.adicionar_item(
        session, venda=venda, produto_id=primeira.produto.id, quantidade=Decimal(1)
    )
    venda_id = venda.id

    segunda = await _loja(session, slug="vis-dois")
    await bind_tenant(session, segunda.tenant.id)
    session.expunge_all()

    assert await session.get(Venda, venda_id) is None


async def test_desconto_da_venda_entra_no_total(session: AsyncSession) -> None:
    loja = await _loja(session)
    await _com_estoque(session, loja)

    venda = await service.abrir_venda(session, tenant_id=loja.tenant.id)
    await service.adicionar_item(
        session, venda=venda, produto_id=loja.produto.id, quantidade=Decimal(5)
    )
    await service.definir_desconto(session, venda=venda, desconto=Decimal("5.00"))

    assert await service.total_a_pagar(session, venda) == Decimal("45.00")

    with pytest.raises(service.PdvError, match="maior que a venda"):
        await service.definir_desconto(session, venda=venda, desconto=Decimal("999.00"))
