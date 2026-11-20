"""Regras do consumo interno.

Lançar um consumo é pedir ao ``comercial`` que dê saída no estoque e guardar, aqui, contra
qual centro aquilo foi. Nenhuma linha escreve na tabela de outro módulo — ver
``docs/adr/0007-dependencia-entre-modulos.md``.

Decisões e limites: ``docs/adr/0026-consumo-interno-e-custo-por-centro.md``.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from decko_modules.comercial import service as comercial
from decko_modules.comercial.models import Movimento, Produto, TipoMovimento, Unidade
from decko_modules.custos.models import Consumo
from decko_modules.financeiro.models import CentroDeCusto, Despesa, StatusDespesa

# O que aparece na razão de estoque. Texto, porque é o campo que o `comercial` tem — e é
# ele que explica, para quem olha o extrato do produto, por que o saldo caiu sem venda.
MOTIVO = "Consumo interno"


class CustosError(Exception):
    """Erro de regra. Vira 422 na borda."""


async def _centro_ativo(session: AsyncSession, centro_id: uuid.UUID) -> CentroDeCusto:
    centro = await session.get(CentroDeCusto, centro_id)
    if centro is None:
        raise CustosError("Centro de custo não encontrado.")
    if not centro.ativo:
        raise CustosError(f"O centro de custo '{centro.nome}' está desativado.")
    return centro


async def _valor_do_consumo(
    session: AsyncSession,
    *,
    produto: Produto,
    unidade: Unidade,
    quantidade: Decimal,
    valor_informado: Decimal | None,
) -> tuple[Decimal, Decimal | None]:
    """Quanto custou, e qual custo unitário foi usado.

    O informado manda. Sem informado, usa o ``preco_custo`` do produto — **cópia de uma
    referência**, e não avaliação de estoque (ADR 0026, decisão 3).

    Produto sem preço de custo e sem valor informado é recusado, em vez de lançar zero: um
    número errado estraga mais do que um campo vazio.
    """
    if valor_informado is not None:
        if valor_informado < 0:
            raise CustosError("O valor do consumo não pode ser negativo.")
        return valor_informado, None

    if produto.preco_custo is None:
        raise CustosError(
            f"O produto '{produto.nome}' não tem preço de custo. Informe o valor do consumo."
        )

    # O preço de custo é por unidade base; a quantidade digitada pode estar em outra. A
    # conversão é a do `comercial` — refazer a conta aqui seria a segunda verdade sobre
    # fardo, caixa e unidade, e as duas divergiriam no dia em que a árvore mudasse.
    base = await session.get(Unidade, produto.unidade_id)
    if base is None:
        raise CustosError("Produto sem unidade base válida.")
    try:
        na_base = comercial.converter(quantidade, de=unidade, para=base)
    except comercial.ConversaoImpossivelError as exc:
        raise CustosError(str(exc)) from exc

    return (produto.preco_custo * na_base).quantize(Decimal("0.01")), produto.preco_custo


async def registrar(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    produto_id: uuid.UUID,
    centro_custo_id: uuid.UUID,
    quantidade: Decimal,
    unidade_id: uuid.UUID,
    lote_id: uuid.UUID | None = None,
    valor: Decimal | None = None,
    documento: str | None = None,
    observacao: str | None = None,
    ocorrido_em: datetime | None = None,
    registrado_por: uuid.UUID | None = None,
) -> Consumo:
    """Dá saída no estoque e anota contra qual centro aquilo foi."""
    if quantidade <= 0:
        raise CustosError("A quantidade do consumo é sempre positiva.")

    await _centro_ativo(session, centro_custo_id)

    produto = await session.get(Produto, produto_id)
    if produto is None:
        raise CustosError("Produto não encontrado.")
    unidade = await session.get(Unidade, unidade_id)
    if unidade is None:
        raise CustosError("Unidade não encontrada.")

    quanto, unitario = await _valor_do_consumo(
        session,
        produto=produto,
        unidade=unidade,
        quantidade=quantidade,
        valor_informado=valor,
    )

    try:
        movimento = await comercial.registrar_movimento(
            session,
            tenant_id=tenant_id,
            produto_id=produto_id,
            tipo=TipoMovimento.SAIDA,
            quantidade=quantidade,
            unidade_id=unidade_id,
            lote_id=lote_id,
            documento=documento,
            motivo=MOTIVO,
            ocorrido_em=ocorrido_em,
            registrado_por=registrado_por,
        )
    except comercial.ComercialError as exc:
        # A mensagem dele é melhor do que qualquer texto genérico daqui: ele sabe se foi
        # saldo, lote exigido ou unidade incompatível.
        raise CustosError(str(exc)) from exc

    consumo = Consumo(
        tenant_id=tenant_id,
        movimento_id=movimento.id,
        centro_custo_id=centro_custo_id,
        valor=quanto,
        custo_unitario=unitario,
        observacao=(observacao or "").strip() or None,
    )
    session.add(consumo)
    await session.flush()
    return consumo


@dataclass(frozen=True)
class LinhaConsumo:
    """Um consumo com o que o movimento guarda, para a lista não exigir duas chamadas."""

    id: uuid.UUID
    centro_custo_id: uuid.UUID
    centro_nome: str
    produto_nome: str
    quantidade: Decimal
    valor: Decimal
    custo_unitario: Decimal | None
    ocorrido_em: datetime
    observacao: str | None


async def listar(
    session: AsyncSession,
    *,
    de: date | None = None,
    ate: date | None = None,
    centro_custo_id: uuid.UUID | None = None,
) -> list[LinhaConsumo]:
    """O que foi consumido no período, do mais recente para o mais antigo."""
    consulta = (
        select(
            Consumo.id,
            Consumo.centro_custo_id,
            CentroDeCusto.nome,
            Produto.nome,
            Movimento.quantidade,
            Consumo.valor,
            Consumo.custo_unitario,
            Movimento.ocorrido_em,
            Consumo.observacao,
        )
        .join(Movimento, Movimento.id == Consumo.movimento_id)
        .join(Produto, Produto.id == Movimento.produto_id)
        .join(CentroDeCusto, CentroDeCusto.id == Consumo.centro_custo_id)
        .order_by(Movimento.ocorrido_em.desc())
    )
    if de is not None:
        consulta = consulta.where(func.date(Movimento.ocorrido_em) >= de)
    if ate is not None:
        consulta = consulta.where(func.date(Movimento.ocorrido_em) <= ate)
    if centro_custo_id is not None:
        consulta = consulta.where(Consumo.centro_custo_id == centro_custo_id)

    return [LinhaConsumo(*linha) for linha in (await session.execute(consulta)).all()]


@dataclass(frozen=True)
class CustoDoCentro:
    """O que um centro custou no período, pelas duas fontes."""

    centro_id: uuid.UUID
    nome: str
    consumo: Decimal
    despesa: Decimal
    total: Decimal


async def custo_por_centro(session: AsyncSession, *, de: date, ate: date) -> list[CustoDoCentro]:
    """Soma consumo de estoque e despesa, por centro, no período.

    Este módulo é o único que enxerga as duas fontes — ADR 0026, decisão 5. E, como sempre,
    é soma na consulta: saldo guardado precisaria de alguém mantendo verdadeiro.

    A despesa entra pelo **valor pago** quando já foi paga, e pelo devido enquanto está em
    aberto: antes de pagar, o que se sabe é o que se deve; depois, o que importa é o que
    saiu. Cancelada não entra.
    """
    consumos = dict(
        (
            await session.execute(
                select(Consumo.centro_custo_id, func.coalesce(func.sum(Consumo.valor), 0))
                .join(Movimento, Movimento.id == Consumo.movimento_id)
                .where(
                    func.date(Movimento.ocorrido_em) >= de,
                    func.date(Movimento.ocorrido_em) <= ate,
                )
                .group_by(Consumo.centro_custo_id)
            )
        ).all()
    )

    despesas = dict(
        (
            await session.execute(
                select(
                    Despesa.centro_custo_id,
                    func.coalesce(func.sum(func.coalesce(Despesa.valor_pago, Despesa.valor)), 0),
                )
                .where(
                    Despesa.centro_custo_id.is_not(None),
                    Despesa.vencimento >= de,
                    Despesa.vencimento <= ate,
                    Despesa.status != StatusDespesa.CANCELADA,
                )
                .group_by(Despesa.centro_custo_id)
            )
        ).all()
    )

    nomes = dict((await session.execute(select(CentroDeCusto.id, CentroDeCusto.nome))).all())

    linhas = [
        CustoDoCentro(
            centro_id=centro_id,
            nome=nomes.get(centro_id, "?"),
            consumo=Decimal(consumos.get(centro_id, 0)),
            despesa=Decimal(despesas.get(centro_id, 0)),
            total=Decimal(consumos.get(centro_id, 0)) + Decimal(despesas.get(centro_id, 0)),
        )
        for centro_id in set(consumos) | set(despesas)
    ]
    # Maior custo primeiro: é por onde quem lê começa a olhar.
    linhas.sort(key=lambda linha: (-linha.total, linha.nome))
    return linhas
