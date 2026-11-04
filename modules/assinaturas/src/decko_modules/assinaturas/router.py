import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from decko.db import get_session
from decko_modules.assinaturas import service
from decko_modules.assinaturas.models import (
    Assinatura,
    Cobranca,
    Plano,
    StatusAssinatura,
    StatusCobranca,
)
from decko_modules.assinaturas.schemas import (
    AssinaturaIn,
    AssinaturaOut,
    BaixaIn,
    CobrancaOut,
    CompetenciaIn,
    GeracaoOut,
    PlanoIn,
    PlanoOut,
    PrazoIn,
)
from decko_modules.clientes.models import Cliente
from decko_modules.core import audit
from decko_modules.core.deps import CurrentPrincipal, require

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _invalido(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))


async def _assinatura_ou_404(session: AsyncSession, assinatura_id: uuid.UUID) -> Assinatura:
    assinatura = await session.get(Assinatura, assinatura_id)
    if assinatura is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Assinatura não encontrada."
        )
    return assinatura


async def _cobranca_ou_404(session: AsyncSession, cobranca_id: uuid.UUID) -> Cobranca:
    cobranca = await session.get(Cobranca, cobranca_id)
    if cobranca is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Cobrança não encontrada."
        )
    return cobranca


async def _ver(session: AsyncSession, assinatura: Assinatura) -> AssinaturaOut:
    """Monta a assinatura com o estado de acesso resolvido pelo servidor.

    A tela não refaz regra de cobrança, do mesmo jeito que não soma dinheiro no PDV: duas
    implementações da mesma regra divergem, e a que corta o acesso de alguém é esta.
    """
    cobrancas = await service.cobrancas_de(session, assinatura)
    hoje = date.today()
    cliente = await session.get(Cliente, assinatura.cliente_id)
    plano = await session.get(Plano, assinatura.plano_id)

    return AssinaturaOut(
        id=assinatura.id,
        cliente_id=assinatura.cliente_id,
        cliente_nome=cliente.nome if cliente else "—",
        plano_id=assinatura.plano_id,
        plano_nome=plano.nome if plano else "—",
        status=assinatura.status,
        inicio=assinatura.inicio,
        dia_vencimento=assinatura.dia_vencimento,
        acesso=service.acesso_de(cobrancas, hoje),
        em_aberto=sum(
            (c.valor for c in cobrancas if c.status is StatusCobranca.ABERTA), Decimal(0)
        ),
        cobrancas=[
            CobrancaOut(
                id=c.id,
                competencia=c.competencia,
                valor=c.valor,
                vencimento=c.vencimento,
                status=c.status,
                pago_em=c.pago_em,
                forma_pagamento=c.forma_pagamento,
                prazo_ate=c.prazo_ate,
                prazo_motivo=c.prazo_motivo,
                bloqueia_em=service.limite_de(c),
            )
            for c in cobrancas
        ],
    )


# ---------------------------------------------------------------- planos


@router.get("/planos", response_model=list[PlanoOut])
async def listar_planos(
    session: SessionDep,
    _: Annotated[object, Depends(require("assinaturas.plano.read"))],
) -> list[Plano]:
    resultado = await session.execute(select(Plano).order_by(Plano.nome))
    return list(resultado.scalars().all())


@router.post("/planos", response_model=PlanoOut, status_code=status.HTTP_201_CREATED)
async def criar_plano(
    payload: PlanoIn,
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("assinaturas.plano.write"))],
) -> Plano:
    try:
        return await service.criar_plano(
            session,
            tenant_id=principal.tenant_id,
            nome=payload.nome,
            preco_mensal=payload.preco_mensal,
            descricao=payload.descricao,
        )
    except service.AssinaturasError as exc:
        raise _invalido(exc) from exc


# ---------------------------------------------------------------- assinaturas


@router.get("/assinaturas", response_model=list[AssinaturaOut])
async def listar_assinaturas(
    session: SessionDep,
    _: Annotated[object, Depends(require("assinaturas.assinatura.read"))],
    incluir_canceladas: Annotated[bool, Query()] = False,
) -> list[AssinaturaOut]:
    consulta = select(Assinatura).order_by(Assinatura.created_at)
    if not incluir_canceladas:
        consulta = consulta.where(Assinatura.status == StatusAssinatura.ATIVA)

    resultado = await session.execute(consulta)
    return [await _ver(session, a) for a in resultado.scalars().all()]


@router.post("/assinaturas", response_model=AssinaturaOut, status_code=status.HTTP_201_CREATED)
async def assinar(
    payload: AssinaturaIn,
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("assinaturas.assinatura.write"))],
) -> AssinaturaOut:
    try:
        assinatura = await service.assinar(
            session,
            tenant_id=principal.tenant_id,
            cliente_id=payload.cliente_id,
            plano_id=payload.plano_id,
            inicio=payload.inicio,
            dia_vencimento=payload.dia_vencimento,
        )
    except service.AssinaturasError as exc:
        raise _invalido(exc) from exc
    return await _ver(session, assinatura)


@router.post("/assinaturas/{assinatura_id}/cancelar", response_model=AssinaturaOut)
async def cancelar(
    assinatura_id: uuid.UUID,
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("assinaturas.assinatura.write"))],
) -> AssinaturaOut:
    """Encerra a assinatura. As cobranças dela continuam — cancelar não perdoa dívida."""
    assinatura = await _assinatura_ou_404(session, assinatura_id)
    try:
        await service.cancelar(session, assinatura=assinatura)
    except service.AssinaturasError as exc:
        raise _invalido(exc) from exc

    audit.registrar(
        session,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        action="assinatura.cancelar",
        entity="assinaturas_assinatura",
        entity_id=str(assinatura.id),
    )
    return await _ver(session, assinatura)


# ---------------------------------------------------------------- ciclo e cobrança


@router.post("/cobrancas/gerar", response_model=GeracaoOut)
async def gerar_competencia(
    payload: CompetenciaIn,
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("assinaturas.cobranca.gerar"))],
) -> GeracaoOut:
    """Gera a cobrança do mês para cada assinatura ativa.

    Clique, e não tarefa agendada: o projeto não tem agendador, e fingir que tem seria
    pior. Repetir não cobra de novo.
    """
    try:
        criadas = await service.gerar_competencia(
            session, tenant_id=principal.tenant_id, ano=payload.ano, mes=payload.mes
        )
    except service.AssinaturasError as exc:
        raise _invalido(exc) from exc

    competencia = date(payload.ano, payload.mes, 1)
    audit.registrar(
        session,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        action="assinatura.cobranca.gerar",
        entity="assinaturas_cobranca",
        entity_id=competencia.isoformat(),
        data={"criadas": len(criadas)},
    )
    return GeracaoOut(competencia=competencia, criadas=len(criadas))


@router.post("/cobrancas/{cobranca_id}/baixar", response_model=AssinaturaOut)
async def baixar(
    cobranca_id: uuid.UUID,
    payload: BaixaIn,
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("assinaturas.cobranca.baixar"))],
) -> AssinaturaOut:
    cobranca = await _cobranca_ou_404(session, cobranca_id)
    try:
        await service.baixar(
            session,
            cobranca=cobranca,
            pago_em=payload.pago_em,
            forma_pagamento=payload.forma_pagamento,
        )
    except service.AssinaturasError as exc:
        raise _invalido(exc) from exc

    audit.registrar(
        session,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        action="assinatura.cobranca.baixar",
        entity="assinaturas_cobranca",
        entity_id=str(cobranca.id),
        # O valor entra: é dinheiro recebido, e a trilha é onde se confere isso depois.
        data={"valor": str(cobranca.valor), "forma": payload.forma_pagamento},
    )
    return await _ver(session, await _assinatura_ou_404(session, cobranca.assinatura_id))


@router.post("/cobrancas/{cobranca_id}/prazo", response_model=AssinaturaOut)
async def conceder_prazo(
    cobranca_id: uuid.UUID,
    payload: PrazoIn,
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("assinaturas.cobranca.prazo"))],
) -> AssinaturaOut:
    """Dá mais tempo antes de bloquear, por decisão de gente.

    Permissão própria, separada de dar baixa: quem confere pagamento não é
    necessariamente quem pode decidir esperar mais.
    """
    cobranca = await _cobranca_ou_404(session, cobranca_id)
    try:
        await service.conceder_prazo(
            session,
            cobranca=cobranca,
            ate=payload.ate,
            motivo=payload.motivo,
            concedido_por=principal.user_id,
        )
    except service.AssinaturasError as exc:
        raise _invalido(exc) from exc

    # Sem isto, "fulano ganhou prazo" vira palavra contra palavra.
    audit.registrar(
        session,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        action="assinatura.cobranca.prazo",
        entity="assinaturas_cobranca",
        entity_id=str(cobranca.id),
        data={"ate": payload.ate.isoformat(), "motivo": payload.motivo},
    )
    return await _ver(session, await _assinatura_ou_404(session, cobranca.assinatura_id))
