"""As regras da venda de balcão.

A baixa de estoque não é escrita aqui: é pedida ao serviço do módulo ``comercial``. Quem
conhece conversão de embalagem, exigência de lote e razão de estoque é ele — ver
``docs/adr/0007-dependencia-entre-modulos.md``.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from decko_modules.clientes.models import Cliente
from decko_modules.comercial import service as comercial
from decko_modules.comercial.models import Produto, TipoMovimento
from decko_modules.pdv.models import (
    Contador,
    FormaPagamento,
    ItemVenda,
    Pagamento,
    StatusVenda,
    Venda,
)

CENTAVO = Decimal("0.01")


class PdvError(Exception):
    """Erro de regra da venda. Vira 422 na borda."""


def _dinheiro(valor: Decimal) -> Decimal:
    """Arredonda para centavo, meio para cima — como se faz no caixa."""
    return valor.quantize(CENTAVO, rounding=ROUND_HALF_UP)


async def abrir_venda(
    session: AsyncSession, *, tenant_id: uuid.UUID, operador_id: uuid.UUID | None = None
) -> Venda:
    venda = Venda(tenant_id=tenant_id, operador_id=operador_id, status=StatusVenda.ABERTA)
    session.add(venda)
    await session.flush()
    return venda


def _exige_aberta(venda: Venda) -> None:
    if venda.status is not StatusVenda.ABERTA:
        raise PdvError(f"A venda já está {venda.status.value}; não aceita mais alteração.")


async def identificar(session: AsyncSession, *, venda: Venda, cliente_id: uuid.UUID) -> Venda:
    """Diz de quem é esta venda.

    Só enquanto aberta: depois de finalizada tudo na venda é congelado — total, preço e
    descrição de cada item — porque o cupom precisa continuar dizendo o que o cliente
    pagou. Trocar a quem a venda pertence depois de fechada seria reescrever um documento
    entregue.
    """
    _exige_aberta(venda)

    cliente = await session.get(Cliente, cliente_id)
    if cliente is None:
        raise PdvError("Cliente não encontrado.")
    if not cliente.ativo:
        # Vendas antigas dele continuam intactas; desativar quer dizer "não use mais daqui
        # para frente".
        raise PdvError(f"'{cliente.nome}' está desativado e não pode entrar numa venda nova.")

    venda.cliente_id = cliente.id
    await session.flush()
    return venda


async def desidentificar(session: AsyncSession, *, venda: Venda) -> Venda:
    """Volta a venda a anônima. Errar o cliente no balcão é comum e tem de ser reversível."""
    _exige_aberta(venda)
    venda.cliente_id = None
    await session.flush()
    return venda


async def cliente_de(session: AsyncSession, venda: Venda) -> Cliente | None:
    """O cliente da venda, lido na hora.

    Ao contrário do preço e da descrição do item, que são cópia: o preço de ontem é fato
    histórico e não pode mudar, mas quem a pessoa é é cadastro, e corrigir um nome digitado
    errado precisa valer para as vendas dela também.
    """
    if venda.cliente_id is None:
        return None
    return await session.get(Cliente, venda.cliente_id)


async def adicionar_item(
    session: AsyncSession,
    *,
    venda: Venda,
    produto_id: uuid.UUID,
    quantidade: Decimal,
    unidade_id: uuid.UUID | None = None,
    lote_id: uuid.UUID | None = None,
    preco_unitario: Decimal | None = None,
    desconto: Decimal = Decimal(0),
) -> ItemVenda:
    """Lança um item na venda aberta.

    Sem ``preco_unitario``, usa o preço de venda do cadastro. Produto sem preço é recusado
    em vez de ir a zero: vender de graça por omissão é o tipo de defeito que só aparece no
    fechamento do caixa.
    """
    _exige_aberta(venda)

    if quantidade <= 0:
        raise PdvError("A quantidade precisa ser maior que zero.")
    if desconto < 0:
        raise PdvError("O desconto não pode ser negativo.")

    produto = await session.get(Produto, produto_id)
    if produto is None:
        raise PdvError("Produto não encontrado.")
    if not produto.ativo:
        raise PdvError(f"'{produto.nome}' está inativo e não pode ser vendido.")

    preco = preco_unitario if preco_unitario is not None else produto.preco_venda
    if preco is None:
        raise PdvError(f"'{produto.nome}' não tem preço de venda cadastrado.")
    if preco < 0:
        raise PdvError("O preço não pode ser negativo.")

    if produto.controla_lote and lote_id is None:
        raise PdvError(f"'{produto.nome}' controla lote: informe de qual lote é a saída.")

    total = _dinheiro(quantidade * preco) - _dinheiro(desconto)
    if total < 0:
        raise PdvError("O desconto do item é maior que o próprio item.")

    item = ItemVenda(
        tenant_id=venda.tenant_id,
        venda_id=venda.id,
        produto_id=produto_id,
        lote_id=lote_id,
        # Sem unidade informada, vende-se na unidade base do produto.
        unidade_id=unidade_id if unidade_id is not None else produto.unidade_id,
        quantidade=quantidade,
        preco_unitario=preco,
        desconto=_dinheiro(desconto),
        total=total,
        descricao=produto.nome,
    )
    session.add(item)
    await session.flush()
    return item


async def remover_item(session: AsyncSession, *, venda: Venda, item_id: uuid.UUID) -> None:
    _exige_aberta(venda)

    item = await session.get(ItemVenda, item_id)
    if item is None or item.venda_id != venda.id:
        raise PdvError("Item não encontrado nesta venda.")

    await session.delete(item)
    await session.flush()


async def definir_desconto(session: AsyncSession, *, venda: Venda, desconto: Decimal) -> Venda:
    """Desconto sobre a venda inteira, além do que cada item já tenha."""
    _exige_aberta(venda)
    if desconto < 0:
        raise PdvError("O desconto não pode ser negativo.")

    soma = await soma_dos_itens(session, venda)
    if desconto > soma:
        raise PdvError("O desconto é maior que a venda.")

    venda.desconto = _dinheiro(desconto)
    await session.flush()
    return venda


async def registrar_pagamento(
    session: AsyncSession, *, venda: Venda, forma: FormaPagamento, valor: Decimal
) -> Pagamento:
    """Registra uma forma de pagamento. Uma venda pode ter várias."""
    _exige_aberta(venda)
    if valor <= 0:
        raise PdvError("O valor do pagamento precisa ser maior que zero.")

    pagamento = Pagamento(
        tenant_id=venda.tenant_id, venda_id=venda.id, forma=forma, valor=_dinheiro(valor)
    )
    session.add(pagamento)
    await session.flush()
    return pagamento


async def remover_pagamento(
    session: AsyncSession, *, venda: Venda, pagamento_id: uuid.UUID
) -> None:
    _exige_aberta(venda)

    pagamento = await session.get(Pagamento, pagamento_id)
    if pagamento is None or pagamento.venda_id != venda.id:
        raise PdvError("Pagamento não encontrado nesta venda.")

    await session.delete(pagamento)
    await session.flush()


async def _pagamentos(session: AsyncSession, venda: Venda) -> list[Pagamento]:
    result = await session.execute(select(Pagamento).where(Pagamento.venda_id == venda.id))
    return list(result.scalars())


async def soma_dos_itens(session: AsyncSession, venda: Venda) -> Decimal:
    result = await session.execute(select(ItemVenda.total).where(ItemVenda.venda_id == venda.id))
    return _dinheiro(sum(result.scalars().all(), Decimal(0)))


async def total_a_pagar(session: AsyncSession, venda: Venda) -> Decimal:
    """O que a venda custa agora.

    Venda finalizada devolve o total congelado; venda aberta, a soma dos itens menos o
    desconto — que ainda muda a cada bipada.
    """
    if venda.total is not None:
        return venda.total
    return _dinheiro(await soma_dos_itens(session, venda) - venda.desconto)


async def total_pago(session: AsyncSession, venda: Venda) -> Decimal:
    result = await session.execute(select(Pagamento.valor).where(Pagamento.venda_id == venda.id))
    return _dinheiro(sum(result.scalars().all(), Decimal(0)))


@dataclass(frozen=True)
class Fechamento:
    venda: Venda
    total: Decimal
    pago: Decimal
    troco: Decimal


async def _proximo_numero(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    """Reserva o próximo número da empresa, no banco.

    A linha do contador é travada pelo próprio ``ON CONFLICT DO UPDATE``, então dois
    caixas que fecham no mesmo instante recebem números diferentes.

    Pode haver buraco na sequência se a transação for desfeita depois de reservar. Isso é
    aceito: este número identifica a venda na operação, não é número de documento fiscal,
    que tem exigência própria e virá com o módulo fiscal.
    """
    statement = (
        pg_insert(Contador)
        .values(tenant_id=tenant_id, proximo=1)
        .on_conflict_do_update(
            index_elements=[Contador.tenant_id],
            set_={"proximo": Contador.proximo + 1},
        )
        .returning(Contador.proximo)
    )
    numero = await session.scalar(statement)
    if numero is None:  # pragma: no cover - o RETURNING sempre traz a linha
        raise PdvError("Não foi possível reservar o número da venda.")
    return int(numero)


async def finalizar_venda(
    session: AsyncSession, *, venda: Venda, registrado_por: uuid.UUID | None = None
) -> Fechamento:
    """Fecha a venda: confere o pagamento, baixa o estoque e congela o total.

    A baixa acontece na mesma transação da venda. Se o estoque recusar a saída, a venda
    não fecha — não existe estado em que o cupom saiu e o estoque não baixou.
    """
    _exige_aberta(venda)

    itens = list(
        (await session.execute(select(ItemVenda).where(ItemVenda.venda_id == venda.id))).scalars()
    )
    if not itens:
        raise PdvError("Não dá para fechar uma venda sem itens.")

    total = await total_a_pagar(session, venda)
    pago = await total_pago(session, venda)
    if pago < total:
        falta = _dinheiro(total - pago)
        raise PdvError(f"Falta receber R$ {falta}.")

    troco = _dinheiro(pago - total)
    if troco > 0:
        # Só dinheiro devolve troco. Cobrar no cartão mais do que a venda e devolver a
        # diferença em espécie é transformar o caixa em saque, e não é o que a loja pediu.
        em_dinheiro = sum(
            (
                p.valor
                for p in await _pagamentos(session, venda)
                if p.forma is FormaPagamento.DINHEIRO
            ),
            Decimal(0),
        )
        if troco > em_dinheiro:
            raise PdvError("Só pagamento em dinheiro devolve troco; confira os valores.")

    venda.numero = await _proximo_numero(session, venda.tenant_id)
    documento = f"Venda {venda.numero}"

    for item in itens:
        await comercial.registrar_movimento(
            session,
            tenant_id=venda.tenant_id,
            produto_id=item.produto_id,
            tipo=TipoMovimento.SAIDA,
            quantidade=item.quantidade,
            unidade_id=item.unidade_id,
            lote_id=item.lote_id,
            documento=documento,
            registrado_por=registrado_por,
        )

    venda.total = total
    venda.status = StatusVenda.FINALIZADA
    venda.fechada_em = datetime.now(UTC)
    await session.flush()

    return Fechamento(venda=venda, total=total, pago=pago, troco=troco)


async def cancelar_venda(session: AsyncSession, *, venda: Venda) -> Venda:
    """Cancela uma venda que ainda não fechou.

    Venda finalizada não é cancelada aqui: desfazer uma saída de estoque já lançada é
    devolução, que tem regra própria e consequência fiscal. Enquanto não houver requisito
    escrito, a operação é recusada em vez de inventada — ver ADR 0008.
    """
    if venda.status is StatusVenda.FINALIZADA:
        raise PdvError(
            "Venda finalizada não pode ser cancelada. A devolução ainda não está implementada."
        )
    if venda.status is StatusVenda.CANCELADA:
        return venda

    venda.status = StatusVenda.CANCELADA
    venda.fechada_em = datetime.now(UTC)
    await session.flush()
    return venda


__all__ = [
    "Fechamento",
    "PdvError",
    "abrir_venda",
    "adicionar_item",
    "cancelar_venda",
    "definir_desconto",
    "finalizar_venda",
    "registrar_pagamento",
    "remover_item",
    "remover_pagamento",
    "soma_dos_itens",
    "total_a_pagar",
    "total_pago",
]
