"""Regra de negócio da base comercial. Não conhece HTTP.

Decisões em ``docs/adr/0006-base-comercial.md``.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from decko_modules.comercial.models import (
    Lote,
    Movimento,
    Produto,
    TipoMovimento,
    Unidade,
)


class ComercialError(Exception):
    pass


class ConversaoImpossivelError(ComercialError):
    """Unidades de árvores diferentes. Quilo não vira unidade."""


# ---------------------------------------------------------------- unidades


async def criar_unidade(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    nome: str,
    simbolo: str | None = None,
    referencia_id: uuid.UUID | None = None,
    fator_relativo: Decimal = Decimal(1),
) -> Unidade:
    """Cria a unidade já com o fator absoluto e a raiz resolvidos.

    Resolver na escrita, e não na leitura, é o que mantém a consulta de saldo simples: ela
    multiplica um número, sem subir árvore nenhuma.
    """
    if fator_relativo <= 0:
        raise ComercialError("O fator precisa ser maior que zero.")

    if referencia_id is None:
        # Raiz: é a unidade de referência do próprio sistema de medida.
        if fator_relativo != 1:
            raise ComercialError(
                "Unidade sem referência é a raiz do seu sistema e tem fator 1. "
                "Para descrever uma embalagem, informe a unidade de referência."
            )
        unidade = Unidade(
            tenant_id=tenant_id,
            nome=nome,
            simbolo=simbolo,
            referencia_id=None,
            fator_relativo=Decimal(1),
            fator=Decimal(1),
            raiz_id=uuid.uuid4(),  # substituído abaixo pelo próprio id
        )
        session.add(unidade)
        await session.flush()
        unidade.raiz_id = unidade.id
        await session.flush()
        return unidade

    referencia = await session.get(Unidade, referencia_id)
    if referencia is None:
        raise ComercialError("Unidade de referência não encontrada.")

    unidade = Unidade(
        tenant_id=tenant_id,
        nome=nome,
        simbolo=simbolo,
        referencia_id=referencia.id,
        fator_relativo=fator_relativo,
        # O absoluto é o produto recursivo: um fardo de 10 caixas de 12 dá 120.
        fator=fator_relativo * referencia.fator,
        raiz_id=referencia.raiz_id,
    )
    session.add(unidade)
    await session.flush()
    return unidade


def converter(quantidade: Decimal, *, de: Unidade, para: Unidade) -> Decimal:
    """Converte entre unidades da mesma árvore.

    Recusa árvores diferentes em vez de devolver um número: um saldo errado em silêncio é
    pior que uma operação que não acontece.
    """
    if de.raiz_id != para.raiz_id:
        raise ConversaoImpossivelError(
            f"'{de.nome}' e '{para.nome}' medem coisas diferentes e não se convertem."
        )
    if de.id == para.id:
        return quantidade
    return quantidade * de.fator / para.fator


# ---------------------------------------------------------------- estoque


@dataclass(frozen=True)
class Saldo:
    produto_id: uuid.UUID
    lote_id: uuid.UUID | None
    quantidade: Decimal


def _assinado() -> object:
    """Soma com o sinal vindo do tipo.

    A quantidade é sempre positiva na tabela; guardar negativo convidaria a somar errado
    em qualquer consulta que esquecesse o filtro.
    """
    return func.sum(
        case(
            (Movimento.tipo == TipoMovimento.SAIDA, -Movimento.quantidade),
            else_=Movimento.quantidade,
        )
    )


async def saldo_do_produto(session: AsyncSession, produto_id: uuid.UUID) -> Decimal:
    """Saldo na unidade base do produto, somado da razão."""
    total = await session.scalar(select(_assinado()).where(Movimento.produto_id == produto_id))
    return Decimal(total or 0)


async def saldo_por_lote(session: AsyncSession, produto_id: uuid.UUID) -> list[Saldo]:
    result = await session.execute(
        select(Movimento.lote_id, _assinado())
        .where(Movimento.produto_id == produto_id)
        .group_by(Movimento.lote_id)
        .order_by(Movimento.lote_id)
    )
    return [
        Saldo(produto_id=produto_id, lote_id=lote_id, quantidade=Decimal(total or 0))
        for lote_id, total in result.all()
    ]


async def registrar_movimento(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    produto_id: uuid.UUID,
    tipo: TipoMovimento,
    quantidade: Decimal,
    unidade_id: uuid.UUID,
    lote_id: uuid.UUID | None = None,
    documento: str | None = None,
    motivo: str | None = None,
    ocorrido_em: datetime | None = None,
    registrado_por: uuid.UUID | None = None,
) -> Movimento:
    """Lança na razão, convertendo para a unidade base do produto."""
    if quantidade <= 0:
        raise ComercialError(
            "A quantidade é sempre positiva; o que define entrada ou saída é o tipo."
        )

    produto = await session.get(Produto, produto_id)
    if produto is None:
        raise ComercialError("Produto não encontrado.")

    unidade = await session.get(Unidade, unidade_id)
    if unidade is None:
        raise ComercialError("Unidade não encontrada.")

    base = await session.get(Unidade, produto.unidade_id)
    if base is None:
        raise ComercialError("Produto sem unidade base válida.")

    if produto.controla_lote and lote_id is None:
        raise ComercialError(
            f"'{produto.nome}' controla lote: informe de qual lote é a movimentação."
        )

    if lote_id is not None:
        lote = await session.get(Lote, lote_id)
        if lote is None:
            raise ComercialError("Lote não encontrado.")
        if lote.produto_id != produto_id:
            # Deixar passar misturaria o estoque de dois produtos sem nenhum aviso.
            raise ComercialError("O lote informado é de outro produto.")

    movimento = Movimento(
        tenant_id=tenant_id,
        produto_id=produto_id,
        lote_id=lote_id,
        tipo=tipo,
        quantidade=converter(quantidade, de=unidade, para=base),
        quantidade_digitada=quantidade,
        unidade_id=unidade_id,
        documento=documento,
        motivo=motivo,
        registrado_por=registrado_por,
        **({"ocorrido_em": ocorrido_em} if ocorrido_em is not None else {}),
    )
    session.add(movimento)
    await session.flush()
    return movimento
