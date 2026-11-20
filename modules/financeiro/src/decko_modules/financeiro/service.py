"""Regras do financeiro: a conta onde o dinheiro está, e a despesa que vence.

A conta tem pouca regra de propósito — é um destino com nome, e não um plano de contas, ver
as decisões 5 e 6 do ``docs/adr/0014-conta-de-recebimento.md``.

A despesa tem a regra que importa: **o que já foi pago não volta atrás.** Dinheiro que saiu,
saiu; desfazer é estorno, que é outro registro — ver ``docs/adr/0024-contas-a-pagar.md``,
decisão 4.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from decko_modules.financeiro.models import Conta, Despesa, StatusDespesa


class FinanceiroError(Exception):
    """Erro de regra. Vira 422 na borda."""


# ------------------------------------------------------------------ conta


async def criar(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    nome: str,
    instituicao: str | None = None,
    chave_pix: str | None = None,
) -> Conta:
    limpo = nome.strip()
    if not limpo:
        raise FinanceiroError("A conta precisa de um nome.")

    repetida = await session.scalar(
        select(Conta.id).where(Conta.tenant_id == tenant_id, Conta.nome == limpo)
    )
    if repetida is not None:
        # Duas contas com o mesmo nome sabotam justamente a conferência que elas existem
        # para permitir: ninguém sabe em qual delas caiu.
        raise FinanceiroError(f"Já existe uma conta chamada '{limpo}'.")

    conta = Conta(
        tenant_id=tenant_id,
        nome=limpo,
        instituicao=(instituicao or "").strip() or None,
        chave_pix=(chave_pix or "").strip() or None,
    )
    session.add(conta)
    await session.flush()
    return conta


async def definir_ativa(session: AsyncSession, *, conta: Conta, ativa: bool) -> Conta:
    """Desativa ou reativa. Nunca apaga: o pagamento de ontem continua apontando para ela."""
    conta.ativa = ativa
    await session.flush()
    return conta


async def listar(session: AsyncSession, *, incluir_inativas: bool = False) -> list[Conta]:
    consulta = select(Conta).order_by(Conta.nome)
    if not incluir_inativas:
        consulta = consulta.where(Conta.ativa)
    return list((await session.execute(consulta)).scalars().all())


# ------------------------------------------------------------------ despesa


async def _conta_ativa(session: AsyncSession, conta_id: uuid.UUID) -> Conta:
    conta = await session.get(Conta, conta_id)
    if conta is None:
        raise FinanceiroError("Conta não encontrada.")
    if not conta.ativa:
        # Desativada sai das escolhas novas, e esta é uma escolha nova. O que já saiu dela
        # continua apontando para ela.
        raise FinanceiroError(f"A conta '{conta.nome}' está desativada.")
    return conta


async def lancar(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    descricao: str,
    valor: Decimal,
    vencimento: date,
    fornecedor_nome: str | None = None,
    fornecedor_cpf_cnpj: str | None = None,
    observacao: str | None = None,
) -> Despesa:
    """Registra uma conta a pagar. Nasce sempre em aberto."""
    limpa = descricao.strip()
    if not limpa:
        raise FinanceiroError("A despesa precisa de uma descrição.")
    if valor < 0:
        raise FinanceiroError("O valor da despesa não pode ser negativo.")

    despesa = Despesa(
        tenant_id=tenant_id,
        descricao=limpa,
        valor=valor,
        vencimento=vencimento,
        fornecedor_nome=(fornecedor_nome or "").strip() or None,
        fornecedor_cpf_cnpj=(fornecedor_cpf_cnpj or "").strip() or None,
        observacao=(observacao or "").strip() or None,
        status=StatusDespesa.ABERTA,
    )
    session.add(despesa)
    await session.flush()
    return despesa


async def editar(
    session: AsyncSession,
    *,
    despesa: Despesa,
    descricao: str | None = None,
    valor: Decimal | None = None,
    vencimento: date | None = None,
    fornecedor_nome: str | None = None,
    fornecedor_cpf_cnpj: str | None = None,
    observacao: str | None = None,
) -> Despesa:
    """Corrige uma despesa **em aberto**.

    Paga não se edita: o valor e a data do que saiu são o registro do que aconteceu, e
    mexer neles depois é reescrever o passado.
    """
    if despesa.status is not StatusDespesa.ABERTA:
        raise FinanceiroError("Só despesa em aberto pode ser corrigida.")

    if descricao is not None:
        limpa = descricao.strip()
        if not limpa:
            raise FinanceiroError("A despesa precisa de uma descrição.")
        despesa.descricao = limpa
    if valor is not None:
        if valor < 0:
            raise FinanceiroError("O valor da despesa não pode ser negativo.")
        despesa.valor = valor
    if vencimento is not None:
        despesa.vencimento = vencimento
    if fornecedor_nome is not None:
        despesa.fornecedor_nome = fornecedor_nome.strip() or None
    if fornecedor_cpf_cnpj is not None:
        despesa.fornecedor_cpf_cnpj = fornecedor_cpf_cnpj.strip() or None
    if observacao is not None:
        despesa.observacao = observacao.strip() or None

    await session.flush()
    return despesa


async def baixar(
    session: AsyncSession,
    *,
    despesa: Despesa,
    pago_em: date,
    valor_pago: Decimal | None = None,
    conta_id: uuid.UUID | None = None,
) -> Despesa:
    """Marca como paga, com o que de fato saiu e de onde.

    ``valor_pago`` em branco vira o valor devido: o caso comum é pagar o que estava na
    conta, e ele não deve dar trabalho. Quando difere — juros, multa, desconto —, é o
    informado que fica, porque é ele que aconteceu.
    """
    if despesa.status is StatusDespesa.PAGA:
        raise FinanceiroError("Esta despesa já está paga.")
    if despesa.status is StatusDespesa.CANCELADA:
        raise FinanceiroError("Despesa cancelada não é paga. Lance uma nova.")

    efetivo = despesa.valor if valor_pago is None else valor_pago
    if efetivo < 0:
        raise FinanceiroError("O valor pago não pode ser negativo.")

    if conta_id is not None:
        await _conta_ativa(session, conta_id)

    despesa.status = StatusDespesa.PAGA
    despesa.pago_em = pago_em
    despesa.valor_pago = efetivo
    despesa.conta_id = conta_id
    await session.flush()
    return despesa


async def cancelar(session: AsyncSession, *, despesa: Despesa) -> Despesa:
    """Diz que esta conta não será paga. Não apaga: fica, com o motivo."""
    if despesa.status is StatusDespesa.PAGA:
        raise FinanceiroError("Despesa paga não é cancelada. Dinheiro que saiu, saiu.")
    if despesa.status is StatusDespesa.CANCELADA:
        return despesa

    despesa.status = StatusDespesa.CANCELADA
    await session.flush()
    return despesa


async def listar_despesas(
    session: AsyncSession,
    *,
    status: StatusDespesa | None = None,
    de: date | None = None,
    ate: date | None = None,
) -> list[Despesa]:
    """O que vence no período, mais antigo primeiro.

    A ordem é a do vencimento porque é assim que quem paga olha: o que vence primeiro é o
    que decide o dia.
    """
    consulta = select(Despesa).order_by(Despesa.vencimento, Despesa.descricao)
    if status is not None:
        consulta = consulta.where(Despesa.status == status)
    if de is not None:
        consulta = consulta.where(Despesa.vencimento >= de)
    if ate is not None:
        consulta = consulta.where(Despesa.vencimento <= ate)
    return list((await session.execute(consulta)).unique().scalars().all())


@dataclass(frozen=True)
class Resumo:
    """Quanto vence, quanto já saiu, e o que passou do prazo."""

    em_aberto: Decimal
    pago: Decimal
    vencido: Decimal
    quantidade_em_aberto: int


async def resumo(session: AsyncSession, *, de: date, ate: date, hoje: date) -> Resumo:
    """Soma na consulta, e não saldo guardado — decisão 6 do ADR 0014.

    ``hoje`` entra por parâmetro em vez de sair de ``date.today()`` aqui dentro: função que
    lê o relógio sozinha não se testa sem viajar no tempo.
    """
    linhas = (
        await session.execute(
            select(
                Despesa.status,
                func.coalesce(func.sum(Despesa.valor), 0),
                func.coalesce(func.sum(Despesa.valor_pago), 0),
                func.count(),
            )
            .where(Despesa.vencimento >= de, Despesa.vencimento <= ate)
            .group_by(Despesa.status)
        )
    ).all()

    em_aberto = Decimal(0)
    pago = Decimal(0)
    quantidade = 0
    for status, soma_valor, soma_pago, contagem in linhas:
        if status is StatusDespesa.ABERTA:
            em_aberto += Decimal(soma_valor)
            quantidade += contagem
        elif status is StatusDespesa.PAGA:
            pago += Decimal(soma_pago)

    vencido = Decimal(
        await session.scalar(
            select(func.coalesce(func.sum(Despesa.valor), 0)).where(
                Despesa.status == StatusDespesa.ABERTA,
                Despesa.vencimento >= de,
                Despesa.vencimento <= ate,
                Despesa.vencimento < hoje,
            )
        )
        or 0
    )

    return Resumo(em_aberto=em_aberto, pago=pago, vencido=vencido, quantidade_em_aberto=quantidade)
