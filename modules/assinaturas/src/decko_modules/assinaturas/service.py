"""As regras da assinatura: o ciclo, o aviso, o bloqueio e o prazo de confiança.

O que estas funções mais fazem é **recusar**. Cobrar duas vezes a mesma competência, dar
baixa numa cobrança já paga, conceder prazo com data que já passou — cada uma dessas é um
erro que ninguém descobre a tempo, e por isso nenhuma passa daqui.

Decisões: ``docs/adr/0013-assinatura-recorrente.md``.
Requisitos: ``docs/discovery/assinaturas-dois-modulos.md``, seções 3 e 5.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from decko_modules.assinaturas.models import (
    DIAS_DE_AVISO,
    Acesso,
    Assinatura,
    Cobranca,
    Plano,
    StatusAssinatura,
    StatusCobranca,
)
from decko_modules.clientes.models import Cliente


class AssinaturasError(Exception):
    """Erro de regra. Vira 422 na borda."""


# ---------------------------------------------------------------- acesso


def limite_de(cobranca: Cobranca) -> date:
    """O último dia em que esta cobrança ainda não bloqueia.

    São os cinco dias de aviso contados do **vencimento** — não do aviso, porque aviso que
    não chega não pode adiar o relógio para sempre. O prazo de confiança empurra essa data,
    e só para frente: conceder prazo mais curto que o aviso não encurta o aviso.
    """
    padrao = cobranca.vencimento + timedelta(days=DIAS_DE_AVISO)
    if cobranca.prazo_ate is not None and cobranca.prazo_ate > padrao:
        return cobranca.prazo_ate
    return padrao


def acesso_de(cobrancas: list[Cobranca], hoje: date) -> Acesso:
    """O que a assinatura permite hoje, a partir do que está em aberto.

    Derivado, nunca guardado: coluna de estado precisaria de alguém passando para
    atualizá-la, e entre duas passadas estaria errada — ver ADR 0013, decisão 3.

    Manda a cobrança **mais grave**: uma em aberto há dois meses bloqueia, ainda que a
    deste mês nem tenha vencido.
    """
    pior = Acesso.EM_DIA
    for cobranca in cobrancas:
        if cobranca.status is not StatusCobranca.ABERTA:
            continue
        if cobranca.vencimento >= hoje:
            continue
        pior = Acesso.BLOQUEADA if hoje > limite_de(cobranca) else Acesso.EM_AVISO
        if pior is Acesso.BLOQUEADA:
            return pior
    return pior


async def cobrancas_de(session: AsyncSession, assinatura: Assinatura) -> list[Cobranca]:
    resultado = await session.execute(
        select(Cobranca)
        .where(Cobranca.assinatura_id == assinatura.id)
        .order_by(Cobranca.competencia)
    )
    return list(resultado.scalars().all())


# ---------------------------------------------------------------- plano


async def criar_plano(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    nome: str,
    preco_mensal: Decimal,
    descricao: str | None = None,
) -> Plano:
    if preco_mensal < 0:
        raise AssinaturasError("O preço do plano não pode ser negativo.")

    plano = Plano(
        tenant_id=tenant_id,
        nome=nome.strip(),
        preco_mensal=preco_mensal,
        descricao=descricao,
    )
    session.add(plano)
    await session.flush()
    return plano


# ---------------------------------------------------------------- assinatura


async def assinar(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    cliente_id: uuid.UUID,
    plano_id: uuid.UUID,
    inicio: date,
    dia_vencimento: int = 10,
) -> Assinatura:
    if not 1 <= dia_vencimento <= 28:
        # Até 28 para existir em fevereiro. Quem vende no dia 31 descobre em março.
        raise AssinaturasError("O dia de vencimento precisa estar entre 1 e 28.")

    cliente = await session.get(Cliente, cliente_id)
    if cliente is None:
        raise AssinaturasError("Cliente não encontrado.")
    if not cliente.ativo:
        raise AssinaturasError(f"'{cliente.nome}' está desativado e não pode assinar.")

    plano = await session.get(Plano, plano_id)
    if plano is None:
        raise AssinaturasError("Plano não encontrado.")
    if not plano.ativo:
        raise AssinaturasError(f"O plano '{plano.nome}' está inativo.")

    repetida = await session.scalar(
        select(Assinatura.id).where(
            Assinatura.cliente_id == cliente_id,
            Assinatura.plano_id == plano_id,
            Assinatura.status == StatusAssinatura.ATIVA,
        )
    )
    if repetida is not None:
        # Quase sempre é engano, e cobrar duas vezes o mesmo plano da mesma pessoa é o tipo
        # de erro que chega como reclamação, não como aviso.
        raise AssinaturasError(f"'{cliente.nome}' já assina o plano '{plano.nome}'.")

    assinatura = Assinatura(
        tenant_id=tenant_id,
        cliente_id=cliente_id,
        plano_id=plano_id,
        inicio=inicio,
        dia_vencimento=dia_vencimento,
    )
    session.add(assinatura)
    await session.flush()
    return assinatura


async def cancelar(session: AsyncSession, *, assinatura: Assinatura) -> Assinatura:
    """Encerra a assinatura. As cobranças dela continuam — cancelar não perdoa dívida."""
    if assinatura.status is StatusAssinatura.CANCELADA:
        raise AssinaturasError("Esta assinatura já está cancelada.")

    assinatura.status = StatusAssinatura.CANCELADA
    assinatura.cancelada_em = datetime.now(UTC)
    await session.flush()
    return assinatura


# ---------------------------------------------------------------- ciclo


async def gerar_competencia(
    session: AsyncSession, *, tenant_id: uuid.UUID, ano: int, mes: int
) -> list[Cobranca]:
    """Gera a cobrança do mês para cada assinatura ativa. Devolve o que criou.

    Operação explícita, e não tarefa agendada: o projeto não tem agendador, e fingir que
    tem seria pior que pedir um clique por mês.

    Repetir não cobra de novo — a competência é única por assinatura, e quem já tem a
    linha é pulado. É o mesmo princípio do dado-semente (ADR 0010): rodar duas vezes não
    pode duplicar.
    """
    if not 1 <= mes <= 12:
        raise AssinaturasError("Mês inválido.")

    competencia = date(ano, mes, 1)
    fim_do_mes = date(ano + (mes // 12), (mes % 12) + 1, 1) - timedelta(days=1)

    ativas = await session.execute(
        select(Assinatura).where(
            Assinatura.tenant_id == tenant_id,
            Assinatura.status == StatusAssinatura.ATIVA,
            # Assinatura que começa depois do mês não é cobrada por ele.
            Assinatura.inicio <= fim_do_mes,
        )
    )

    ja_existem = set(
        (
            await session.execute(
                select(Cobranca.assinatura_id).where(Cobranca.competencia == competencia)
            )
        )
        .scalars()
        .all()
    )

    criadas: list[Cobranca] = []
    for assinatura in ativas.scalars().all():
        if assinatura.id in ja_existem:
            continue

        plano = await session.get(Plano, assinatura.plano_id)
        if plano is None:
            # Chave estrangeira RESTRICT: não deveria acontecer. Se acontecer, pular é
            # melhor que cobrar um valor inventado.
            continue

        cobranca = Cobranca(
            tenant_id=tenant_id,
            assinatura_id=assinatura.id,
            competencia=competencia,
            # Cópia, não referência: o preço de março tem de continuar sendo o de março.
            valor=plano.preco_mensal,
            vencimento=date(ano, mes, assinatura.dia_vencimento),
        )
        session.add(cobranca)
        criadas.append(cobranca)

    if criadas:
        await session.flush()
    return criadas


# ---------------------------------------------------------------- cobrança


async def baixar(
    session: AsyncSession,
    *,
    cobranca: Cobranca,
    pago_em: date,
    forma_pagamento: str | None = None,
) -> Cobranca:
    """Marca a cobrança como paga.

    À mão, porque não há gateway. Quando houver, ele entra como **quem confirma** — a
    cobrança continua sendo esta linha.
    """
    if cobranca.status is StatusCobranca.PAGA:
        raise AssinaturasError("Esta cobrança já está paga.")
    if cobranca.status is StatusCobranca.CANCELADA:
        raise AssinaturasError("Esta cobrança foi cancelada e não aceita baixa.")

    cobranca.status = StatusCobranca.PAGA
    cobranca.pago_em = pago_em
    cobranca.forma_pagamento = forma_pagamento
    await session.flush()
    return cobranca


async def conceder_prazo(
    session: AsyncSession,
    *,
    cobranca: Cobranca,
    ate: date,
    motivo: str,
    concedido_por: uuid.UUID | None,
    hoje: date | None = None,
) -> Cobranca:
    """Dá mais tempo antes de bloquear, por decisão de gente.

    O pedido chega por fora — WhatsApp, telefone. O que se guarda é o que foi **decidido
    aqui**, não a conversa.

    A concessão nova substitui a anterior; o histórico das duas fica na trilha de
    auditoria, que é onde mora histórico (ADR 0013, decisão 4).
    """
    hoje = hoje or date.today()

    if cobranca.status is not StatusCobranca.ABERTA:
        raise AssinaturasError("Só cobrança em aberto recebe prazo.")
    if ate <= hoje:
        # Data que já passou não é prazo; é bloqueio com outro nome.
        raise AssinaturasError("O prazo precisa terminar depois de hoje.")
    if not motivo.strip():
        # Sem motivo, daqui a três meses ninguém sabe por que aquele cliente teve prazo.
        raise AssinaturasError("Diga o motivo do prazo.")

    cobranca.prazo_ate = ate
    cobranca.prazo_motivo = motivo.strip()
    cobranca.prazo_por = concedido_por
    await session.flush()
    return cobranca
