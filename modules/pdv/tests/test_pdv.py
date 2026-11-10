"""Ponto de venda: o que não pode dar errado no caixa.

Duas coisas sustentam o módulo e falham em silêncio quando erradas: a venda fechar sem o
estoque baixar, e o total mudar depois de o cliente pagar. Os dois têm teste aqui.

Decisões: ``docs/adr/0008-ponto-de-venda.md``.
"""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from decko.db import SessionFactory, bind_tenant
from decko_modules.comercial import service as comercial
from decko_modules.comercial.models import Produto, Unidade
from decko_modules.core.models import Tenant
from decko_modules.pdv import service
from decko_modules.pdv.models import (
    DestinoDevolucao,
    FormaPagamento,
    StatusVenda,
    Venda,
)


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
    """Desfazer saída de estoque já lançada é devolução, e ela é documento próprio."""
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


# ------------------------------------------------------------------- devolução de venda
#
# Decisão: atualização de 10/11/2026 da docs/adr/0008-ponto-de-venda.md.
# Requisito: docs/discovery/pdv-devolucao-de-venda.md.


async def _vendida(
    session: AsyncSession, loja: Loja, *, quantidade: str = "3", desconto: str | None = None
) -> Venda:
    """Uma venda fechada, em dinheiro, pronta para devolver."""
    venda = await service.abrir_venda(session, tenant_id=loja.tenant.id)
    await service.adicionar_item(
        session, venda=venda, produto_id=loja.produto.id, quantidade=Decimal(quantidade)
    )
    if desconto is not None:
        await service.definir_desconto(session, venda=venda, desconto=Decimal(desconto))

    total = await service.total_a_pagar(session, venda)
    await service.registrar_pagamento(
        session, venda=venda, forma=FormaPagamento.DINHEIRO, valor=total
    )
    await service.finalizar_venda(session, venda=venda)
    return venda


async def _primeira_linha(session: AsyncSession, venda: Venda) -> uuid.UUID:
    return (await service.devolvivel(session, venda))[0].venda_item_id


async def test_devolucao_volta_o_produto_ao_estoque(session: AsyncSession) -> None:
    """A perna que importa: o dinheiro volta e o estoque volta, na mesma transação."""
    loja = await _loja(session)
    await _com_estoque(session, loja, "100")
    venda = await _vendida(session, loja, quantidade="3")

    assert await comercial.saldo_do_produto(session, loja.produto.id) == Decimal(97)

    devolucao = await service.devolver(
        session,
        venda=venda,
        linhas=[service.LinhaDevolver(await _primeira_linha(session, venda), Decimal(1))],
        forma=FormaPagamento.DINHEIRO,
        motivo="Cliente levou errado",
    )

    assert devolucao.total == Decimal("10.00")
    assert await comercial.saldo_do_produto(session, loja.produto.id) == Decimal(98)
    # A venda não é tocada: ela continua dizendo o que o cliente pagou.
    assert venda.status is StatusVenda.FINALIZADA
    assert venda.total == Decimal("30.00")


async def test_avaria_nao_volta_ao_estoque(session: AsyncSession) -> None:
    """Contar avaria como estoque faria o sistema dizer que dá para vender o quebrado."""
    loja = await _loja(session)
    await _com_estoque(session, loja, "100")
    venda = await _vendida(session, loja, quantidade="3")

    devolucao = await service.devolver(
        session,
        venda=venda,
        linhas=[
            service.LinhaDevolver(
                await _primeira_linha(session, venda), Decimal(1), DestinoDevolucao.AVARIA
            )
        ],
        forma=FormaPagamento.DINHEIRO,
        motivo="Garrafa trincada",
    )

    # O dinheiro volta igual: o cliente não paga pelo defeito.
    assert devolucao.total == Decimal("10.00")
    # O estoque, não: continua nos 97 que a venda deixou.
    assert await comercial.saldo_do_produto(session, loja.produto.id) == Decimal(97)

    agora = datetime.now(UTC)
    linhas = await service.avarias(
        session, de=agora - timedelta(hours=1), ate=agora + timedelta(hours=1)
    )
    assert [(linha.descricao, linha.quantidade) for linha in linhas] == [
        ("Refrigerante 2L", Decimal(1))
    ]


async def test_uma_linha_volta_ao_estoque_e_a_outra_e_avaria(session: AsyncSession) -> None:
    """O caso real: três garrafas voltam e uma quebrou. Uma devolução, dois destinos."""
    loja = await _loja(session)
    await _com_estoque(session, loja, "100")
    venda = await _vendida(session, loja, quantidade="4")
    linha = await _primeira_linha(session, venda)

    devolucao = await service.devolver(
        session,
        venda=venda,
        linhas=[
            service.LinhaDevolver(linha, Decimal(3), DestinoDevolucao.ESTOQUE),
            service.LinhaDevolver(linha, Decimal(1), DestinoDevolucao.AVARIA),
        ],
        forma=FormaPagamento.DINHEIRO,
        motivo="Uma veio trincada",
    )

    # Devolve a venda inteira em dinheiro, porque o defeito não é do cliente.
    assert devolucao.total == Decimal("40.00")
    # E só as três boas voltam a ser vendáveis: 100 - 4 + 3.
    assert await comercial.saldo_do_produto(session, loja.produto.id) == Decimal(99)


async def test_desconto_da_venda_entra_no_valor_devolvido(session: AsyncSession) -> None:
    """Devolver o total da linha devolveria mais do que o cliente pagou."""
    loja = await _loja(session)
    await _com_estoque(session, loja, "100")

    # 10 unidades a R$ 10, com R$ 10 de desconto: a venda custou R$ 90.
    venda = await _vendida(session, loja, quantidade="10", desconto="10.00")
    assert venda.total == Decimal("90.00")

    devolucao = await service.devolver(
        session,
        venda=venda,
        linhas=[service.LinhaDevolver(await _primeira_linha(session, venda), Decimal(1))],
        forma=FormaPagamento.DINHEIRO,
        motivo="Cliente desistiu de uma",
    )

    # Nove reais, não dez: é o que aquela unidade custou ao cliente.
    assert devolucao.total == Decimal("9.00")


async def test_devolver_a_venda_inteira_devolve_exatamente_o_total(
    session: AsyncSession,
) -> None:
    """O centavo do arredondamento não pode ficar preso no sistema.

    Três linhas de R$ 10 com R$ 0,01 de desconto não dividem redondo. O rateio põe o
    resíduo na maior linha, e devolver tudo tem de somar o total da venda — nem um centavo
    a mais, que seria furo de caixa, nem a menos, que seria o cliente pagando a divisão.
    """
    loja = await _loja(session)
    await _com_estoque(session, loja, "100")

    venda = await service.abrir_venda(session, tenant_id=loja.tenant.id)
    for _ in range(3):
        await service.adicionar_item(
            session, venda=venda, produto_id=loja.produto.id, quantidade=Decimal(1)
        )
    await service.definir_desconto(session, venda=venda, desconto=Decimal("0.01"))
    await service.registrar_pagamento(
        session, venda=venda, forma=FormaPagamento.DINHEIRO, valor=Decimal("29.99")
    )
    await service.finalizar_venda(session, venda=venda)

    linhas = await service.devolvivel(session, venda)
    devolucao = await service.devolver(
        session,
        venda=venda,
        linhas=[service.LinhaDevolver(linha.venda_item_id, linha.resta) for linha in linhas],
        forma=FormaPagamento.DINHEIRO,
        motivo="Desistiu da compra",
    )

    assert devolucao.total == venda.total == Decimal("29.99")


async def test_nao_devolve_mais_do_que_foi_vendido(session: AsyncSession) -> None:
    loja = await _loja(session)
    await _com_estoque(session, loja, "100")
    venda = await _vendida(session, loja, quantidade="2")

    with pytest.raises(service.PdvError, match="resta devolver 2"):
        await service.devolver(
            session,
            venda=venda,
            linhas=[service.LinhaDevolver(await _primeira_linha(session, venda), Decimal(3))],
            forma=FormaPagamento.DINHEIRO,
            motivo="Tentando devolver demais",
        )


async def test_duas_devolucoes_parciais_somam_o_mesmo_limite(session: AsyncSession) -> None:
    """O limite é a venda, não a devolução: três parciais não passam do que foi vendido."""
    loja = await _loja(session)
    await _com_estoque(session, loja, "100")
    venda = await _vendida(session, loja, quantidade="3")
    linha = await _primeira_linha(session, venda)

    await service.devolver(
        session,
        venda=venda,
        linhas=[service.LinhaDevolver(linha, Decimal(2))],
        forma=FormaPagamento.DINHEIRO,
        motivo="Devolveu duas",
    )

    with pytest.raises(service.PdvError, match="resta devolver 1"):
        await service.devolver(
            session,
            venda=venda,
            linhas=[service.LinhaDevolver(linha, Decimal(2))],
            forma=FormaPagamento.DINHEIRO,
            motivo="Tentou devolver duas de novo",
        )


async def test_venda_aberta_nao_tem_o_que_devolver(session: AsyncSession) -> None:
    """Venda aberta se cancela: nada foi lançado ainda."""
    loja = await _loja(session)
    venda = await service.abrir_venda(session, tenant_id=loja.tenant.id)
    item = await service.adicionar_item(
        session, venda=venda, produto_id=loja.produto.id, quantidade=Decimal(1)
    )

    with pytest.raises(service.PdvError, match="finalizada"):
        await service.devolver(
            session,
            venda=venda,
            linhas=[service.LinhaDevolver(item.id, Decimal(1))],
            forma=FormaPagamento.DINHEIRO,
            motivo="Não deveria passar",
        )


async def test_devolucao_exige_motivo(session: AsyncSession) -> None:
    """Devolução que ninguém explica depois é justamente a que importa explicar."""
    loja = await _loja(session)
    await _com_estoque(session, loja, "100")
    venda = await _vendida(session, loja, quantidade="1")

    with pytest.raises(service.PdvError, match="motivo"):
        await service.devolver(
            session,
            venda=venda,
            linhas=[service.LinhaDevolver(await _primeira_linha(session, venda), Decimal(1))],
            forma=FormaPagamento.DINHEIRO,
            motivo="   ",
        )


async def test_devolvivel_mostra_o_que_resta(session: AsyncSession) -> None:
    loja = await _loja(session)
    await _com_estoque(session, loja, "100")
    venda = await _vendida(session, loja, quantidade="3")
    linha = await _primeira_linha(session, venda)

    await service.devolver(
        session,
        venda=venda,
        linhas=[service.LinhaDevolver(linha, Decimal(1))],
        forma=FormaPagamento.DINHEIRO,
        motivo="Uma só",
    )

    restante = (await service.devolvivel(session, venda))[0]
    assert restante.devolvida == Decimal(1)
    assert restante.resta == Decimal(2)
    assert restante.valor_resta == Decimal("20.00")


async def test_desconto_e_rateado_entre_linhas_diferentes(session: AsyncSession) -> None:
    """O desconto da venda é de todas as linhas, na proporção de cada uma.

    Duas linhas, R$ 20 e R$ 80, com R$ 10 de desconto: a venda custou R$ 90, e cada linha
    custou R$ 18 e R$ 72. Devolver uma unidade da primeira devolve R$ 9 — se o desconto
    fosse jogado todo numa linha só, o total continuaria certo e **esta** linha devolveria
    errado, que é o jeito silencioso de o erro passar.
    """
    loja = await _loja(session)
    await _com_estoque(session, loja, "100")

    venda = await service.abrir_venda(session, tenant_id=loja.tenant.id)
    await service.adicionar_item(
        session, venda=venda, produto_id=loja.produto.id, quantidade=Decimal(2)
    )
    await service.adicionar_item(
        session, venda=venda, produto_id=loja.produto.id, quantidade=Decimal(8)
    )
    await service.definir_desconto(session, venda=venda, desconto=Decimal("10.00"))
    await service.registrar_pagamento(
        session, venda=venda, forma=FormaPagamento.DINHEIRO, valor=Decimal("90.00")
    )
    await service.finalizar_venda(session, venda=venda)

    primeira, segunda = await service.devolvivel(session, venda)
    assert primeira.valor_resta == Decimal("18.00")
    assert segunda.valor_resta == Decimal("72.00")

    devolucao = await service.devolver(
        session,
        venda=venda,
        linhas=[service.LinhaDevolver(primeira.venda_item_id, Decimal(1))],
        forma=FormaPagamento.DINHEIRO,
        motivo="Uma das duas",
    )
    assert devolucao.total == Decimal("9.00")


async def test_devolucoes_de_um_em_um_nao_passam_do_total(session: AsyncSession) -> None:
    """Três devoluções de uma unidade não podem somar mais do que a venda custou.

    R$ 29,99 em três unidades não divide redondo: cada uma dá R$ 9,996. Arredondando para
    cima as três, o cliente receberia R$ 30 por uma compra de R$ 29,99 — um centavo de
    furo de caixa por venda devolvida, que é o tipo de defeito que só aparece na
    conferência e nunca se explica.

    A última devolução leva o que resta do rateio daquela linha, e é isso que fecha a
    conta.
    """
    loja = await _loja(session)
    await _com_estoque(session, loja, "100")

    venda = await service.abrir_venda(session, tenant_id=loja.tenant.id)
    await service.adicionar_item(
        session, venda=venda, produto_id=loja.produto.id, quantidade=Decimal(3)
    )
    await service.definir_desconto(session, venda=venda, desconto=Decimal("0.01"))
    await service.registrar_pagamento(
        session, venda=venda, forma=FormaPagamento.DINHEIRO, valor=Decimal("29.99")
    )
    await service.finalizar_venda(session, venda=venda)
    linha = await _primeira_linha(session, venda)

    devolvido = Decimal("0.00")
    for _ in range(3):
        devolucao = await service.devolver(
            session,
            venda=venda,
            linhas=[service.LinhaDevolver(linha, Decimal(1))],
            forma=FormaPagamento.DINHEIRO,
            motivo="Uma por vez",
        )
        devolvido += devolucao.total

    assert devolvido == venda.total == Decimal("29.99")
