"""Regras da conta de recebimento.

Pouca regra de propósito: a conta é um destino com nome, e não um plano de contas — ver as
decisões 5 e 6 do ``docs/adr/0014-conta-de-recebimento.md``.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from decko_modules.financeiro.models import ContaRecebimento


class FinanceiroError(Exception):
    """Erro de regra. Vira 422 na borda."""


async def criar(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    nome: str,
    instituicao: str | None = None,
    chave_pix: str | None = None,
) -> ContaRecebimento:
    limpo = nome.strip()
    if not limpo:
        raise FinanceiroError("A conta precisa de um nome.")

    repetida = await session.scalar(
        select(ContaRecebimento.id).where(
            ContaRecebimento.tenant_id == tenant_id, ContaRecebimento.nome == limpo
        )
    )
    if repetida is not None:
        # Duas contas com o mesmo nome sabotam justamente a conferência que elas existem
        # para permitir: ninguém sabe em qual delas caiu.
        raise FinanceiroError(f"Já existe uma conta chamada '{limpo}'.")

    conta = ContaRecebimento(
        tenant_id=tenant_id,
        nome=limpo,
        instituicao=(instituicao or "").strip() or None,
        chave_pix=(chave_pix or "").strip() or None,
    )
    session.add(conta)
    await session.flush()
    return conta


async def definir_ativa(
    session: AsyncSession, *, conta: ContaRecebimento, ativa: bool
) -> ContaRecebimento:
    """Desativa ou reativa. Nunca apaga: o pagamento de ontem continua apontando para ela."""
    conta.ativa = ativa
    await session.flush()
    return conta


async def listar(
    session: AsyncSession, *, incluir_inativas: bool = False
) -> list[ContaRecebimento]:
    consulta = select(ContaRecebimento).order_by(ContaRecebimento.nome)
    if not incluir_inativas:
        consulta = consulta.where(ContaRecebimento.ativa)
    return list((await session.execute(consulta)).scalars().all())
