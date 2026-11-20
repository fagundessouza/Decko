import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from decko.db import get_session
from decko_modules.core.deps import CurrentPrincipal, require
from decko_modules.financeiro import service
from decko_modules.financeiro.models import Conta, Despesa, StatusDespesa
from decko_modules.financeiro.schemas import (
    BaixaIn,
    ContaIn,
    ContaOut,
    DespesaIn,
    DespesaOut,
    DespesaPatch,
    ResumoOut,
)

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _invalido(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))


async def _carregar(session: AsyncSession, conta_id: uuid.UUID) -> Conta:
    conta = await session.get(Conta, conta_id)
    if conta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conta não encontrada.")
    return conta


async def _carregar_despesa(session: AsyncSession, despesa_id: uuid.UUID) -> Despesa:
    despesa = await session.get(Despesa, despesa_id)
    if despesa is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Despesa não encontrada.")
    return despesa


# ------------------------------------------------------------------ contas


@router.get("/contas", response_model=list[ContaOut])
async def listar_contas(
    session: SessionDep,
    _: Annotated[object, Depends(require("financeiro.conta.read"))],
    incluir_inativas: Annotated[bool, Query()] = False,
) -> list[Conta]:
    return await service.listar(session, incluir_inativas=incluir_inativas)


@router.post("/contas", response_model=ContaOut, status_code=status.HTTP_201_CREATED)
async def criar_conta(
    payload: ContaIn,
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("financeiro.conta.write"))],
) -> Conta:
    try:
        return await service.criar(
            session,
            tenant_id=principal.tenant_id,
            nome=payload.nome,
            instituicao=payload.instituicao,
            chave_pix=payload.chave_pix,
        )
    except service.FinanceiroError as exc:
        raise _invalido(exc) from exc


@router.post("/contas/{conta_id}/desativar", response_model=ContaOut)
async def desativar_conta(
    conta_id: uuid.UUID,
    session: SessionDep,
    _: Annotated[object, Depends(require("financeiro.conta.write"))],
) -> Conta:
    """Tira das escolhas novas. O que já foi recebido continua apontando para ela."""
    return await service.definir_ativa(
        session, conta=await _carregar(session, conta_id), ativa=False
    )


@router.post("/contas/{conta_id}/reativar", response_model=ContaOut)
async def reativar_conta(
    conta_id: uuid.UUID,
    session: SessionDep,
    _: Annotated[object, Depends(require("financeiro.conta.write"))],
) -> Conta:
    return await service.definir_ativa(
        session, conta=await _carregar(session, conta_id), ativa=True
    )


# ------------------------------------------------------------------ despesas


@router.get("/despesas", response_model=list[DespesaOut])
async def listar_despesas(
    session: SessionDep,
    _: Annotated[object, Depends(require("financeiro.despesa.read"))],
    situacao: Annotated[StatusDespesa | None, Query()] = None,
    de: Annotated[date | None, Query()] = None,
    ate: Annotated[date | None, Query()] = None,
) -> list[Despesa]:
    """O que vence no período, mais antigo primeiro."""
    return await service.listar_despesas(session, status=situacao, de=de, ate=ate)


@router.get("/despesas/resumo", response_model=ResumoOut)
async def resumo_despesas(
    session: SessionDep,
    _: Annotated[object, Depends(require("financeiro.despesa.read"))],
    de: Annotated[date, Query()],
    ate: Annotated[date, Query()],
) -> ResumoOut:
    """Quanto vence no período, quanto já saiu, e o que passou do prazo.

    Soma na consulta: a decisão 6 do ADR 0014 vale aqui igual — saldo guardado precisa de
    alguém mantendo verdadeiro.
    """
    calculado = await service.resumo(session, de=de, ate=ate, hoje=date.today())
    return ResumoOut(
        em_aberto=calculado.em_aberto,
        pago=calculado.pago,
        vencido=calculado.vencido,
        quantidade_em_aberto=calculado.quantidade_em_aberto,
    )


@router.post("/despesas", response_model=DespesaOut, status_code=status.HTTP_201_CREATED)
async def lancar_despesa(
    payload: DespesaIn,
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("financeiro.despesa.write"))],
) -> Despesa:
    try:
        return await service.lancar(
            session,
            tenant_id=principal.tenant_id,
            descricao=payload.descricao,
            valor=payload.valor,
            vencimento=payload.vencimento,
            fornecedor_nome=payload.fornecedor_nome,
            fornecedor_cpf_cnpj=payload.fornecedor_cpf_cnpj,
            observacao=payload.observacao,
        )
    except service.FinanceiroError as exc:
        raise _invalido(exc) from exc


@router.put("/despesas/{despesa_id}", response_model=DespesaOut)
async def editar_despesa(
    despesa_id: uuid.UUID,
    payload: DespesaPatch,
    session: SessionDep,
    _: Annotated[object, Depends(require("financeiro.despesa.write"))],
) -> Despesa:
    """Correção parcial, e só enquanto em aberto. Campo ausente é campo que não muda."""
    informados = payload.model_dump(exclude_unset=True)
    try:
        return await service.editar(
            session, despesa=await _carregar_despesa(session, despesa_id), **informados
        )
    except service.FinanceiroError as exc:
        raise _invalido(exc) from exc


@router.post("/despesas/{despesa_id}/baixar", response_model=DespesaOut)
async def baixar_despesa(
    despesa_id: uuid.UUID,
    payload: BaixaIn,
    session: SessionDep,
    # Permissão própria: registrar que uma conta existe não é a mesma autoridade que
    # declarar que ela foi paga. Ver ADR 0024, consequências.
    _: Annotated[object, Depends(require("financeiro.despesa.baixar"))],
) -> Despesa:
    try:
        return await service.baixar(
            session,
            despesa=await _carregar_despesa(session, despesa_id),
            pago_em=payload.pago_em,
            valor_pago=payload.valor_pago,
            conta_id=payload.conta_id,
        )
    except service.FinanceiroError as exc:
        raise _invalido(exc) from exc


@router.post("/despesas/{despesa_id}/cancelar", response_model=DespesaOut)
async def cancelar_despesa(
    despesa_id: uuid.UUID,
    session: SessionDep,
    _: Annotated[object, Depends(require("financeiro.despesa.write"))],
) -> Despesa:
    """Diz que esta conta não será paga. Não apaga, e não serve para despesa já paga."""
    try:
        return await service.cancelar(session, despesa=await _carregar_despesa(session, despesa_id))
    except service.FinanceiroError as exc:
        raise _invalido(exc) from exc
