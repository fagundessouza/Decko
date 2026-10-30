"""O que o dono da loja precisa ver antes de o problema acontecer.

Duas perguntas, e as duas só aparecem olhando o estoque inteiro de uma vez:

1. **O que está acabando** — saldo abaixo do mínimo que o produto declara. Produto sem
   mínimo não entra: avisar sobre tudo é o mesmo que não avisar.
2. **O que está vencendo** — lote com validade perto, e com saldo. Lote vencido com saldo
   zero já saiu da loja e não interessa mais.

O saldo sai da razão de estoque, somado no banco. Comparar em Python exigiria baixar a
razão inteira, e o alvo inclui PC antigo de caixa.
"""

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import Select, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from decko_modules.comercial.models import Lote, Movimento, Produto, TipoMovimento

# Quanto tempo antes de vencer o lote entra na lista. Um mês é o que dá para negociar
# promoção, devolver ao fornecedor ou remanejar.
DIAS_PARA_VENCER = 30


@dataclass(frozen=True)
class ProdutoAcabando:
    produto_id: uuid.UUID
    codigo: str
    nome: str
    saldo: Decimal
    estoque_minimo: Decimal

    @property
    def acabou(self) -> bool:
        return self.saldo <= 0


@dataclass(frozen=True)
class LoteVencendo:
    produto_id: uuid.UUID
    produto_nome: str
    lote_id: uuid.UUID
    lote_codigo: str
    validade: date
    saldo: Decimal

    def vencido_em(self, hoje: date) -> bool:
        return self.validade < hoje


@dataclass(frozen=True)
class Alertas:
    acabando: list[ProdutoAcabando]
    vencendo: list[LoteVencendo]

    @property
    def total(self) -> int:
        return len(self.acabando) + len(self.vencendo)


def _saldo_somado() -> Select:
    """Saldo por produto e por lote, direto da razão.

    Entrada e ajuste somam, saída subtrai — o sinal vem do tipo, e não do número, porque
    a razão guarda quantidade sempre positiva.
    """
    sinal = case(
        (Movimento.tipo == TipoMovimento.SAIDA, -Movimento.quantidade),
        else_=Movimento.quantidade,
    )
    return (
        select(
            Movimento.produto_id.label("produto_id"),
            Movimento.lote_id.label("lote_id"),
            func.sum(sinal).label("saldo"),
        )
        .group_by(Movimento.produto_id, Movimento.lote_id)
        .subquery()
    )


async def acabando(session: AsyncSession) -> list[ProdutoAcabando]:
    """Produtos cujo saldo caiu até o mínimo declarado."""
    saldos = (
        select(
            Movimento.produto_id.label("produto_id"),
            func.sum(
                case(
                    (Movimento.tipo == TipoMovimento.SAIDA, -Movimento.quantidade),
                    else_=Movimento.quantidade,
                )
            ).label("saldo"),
        )
        .group_by(Movimento.produto_id)
        .subquery()
    )

    consulta = (
        select(
            Produto.id,
            Produto.codigo,
            Produto.nome,
            func.coalesce(saldos.c.saldo, 0).label("saldo"),
            Produto.estoque_minimo,
        )
        .outerjoin(saldos, saldos.c.produto_id == Produto.id)
        .where(
            Produto.ativo,
            Produto.estoque_minimo.is_not(None),
            func.coalesce(saldos.c.saldo, 0) <= Produto.estoque_minimo,
        )
        # O que acabou de vez primeiro; depois o que está mais perto de acabar.
        .order_by(func.coalesce(saldos.c.saldo, 0), Produto.nome)
    )

    return [
        ProdutoAcabando(
            produto_id=linha.id,
            codigo=linha.codigo,
            nome=linha.nome,
            saldo=Decimal(linha.saldo),
            estoque_minimo=linha.estoque_minimo,
        )
        for linha in (await session.execute(consulta)).all()
    ]


async def vencendo(
    session: AsyncSession, *, hoje: date, dias: int = DIAS_PARA_VENCER
) -> list[LoteVencendo]:
    """Lotes com validade até ``dias`` à frente, e os já vencidos, que ainda têm saldo."""
    saldos = _saldo_somado()
    limite = hoje + timedelta(days=dias)

    consulta = (
        select(
            Produto.id,
            Produto.nome,
            Lote.id,
            Lote.codigo,
            Lote.validade,
            func.coalesce(saldos.c.saldo, 0).label("saldo"),
        )
        .join(Produto, Produto.id == Lote.produto_id)
        .outerjoin(saldos, saldos.c.lote_id == Lote.id)
        .where(
            Lote.validade.is_not(None),
            Lote.validade <= limite,
            # Lote vencido com saldo zero já saiu da loja.
            func.coalesce(saldos.c.saldo, 0) > 0,
        )
        .order_by(Lote.validade, Produto.nome)
    )

    return [
        LoteVencendo(
            produto_id=linha[0],
            produto_nome=linha[1],
            lote_id=linha[2],
            lote_codigo=linha[3],
            validade=linha[4],
            saldo=Decimal(linha[5]),
        )
        for linha in (await session.execute(consulta)).all()
    ]


async def levantar(session: AsyncSession, *, hoje: date, dias: int = DIAS_PARA_VENCER) -> Alertas:
    return Alertas(
        acabando=await acabando(session),
        vencendo=await vencendo(session, hoje=hoje, dias=dias),
    )
