import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from decko.db import get_session
from decko_modules.core.deps import CurrentPrincipal, require
from decko_modules.financeiro import service
from decko_modules.financeiro.models import ContaRecebimento
from decko_modules.financeiro.schemas import ContaIn, ContaOut

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _invalido(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))


async def _carregar(session: AsyncSession, conta_id: uuid.UUID) -> ContaRecebimento:
    conta = await session.get(ContaRecebimento, conta_id)
    if conta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conta não encontrada.")
    return conta


@router.get("/contas", response_model=list[ContaOut])
async def listar_contas(
    session: SessionDep,
    _: Annotated[object, Depends(require("financeiro.conta.read"))],
    incluir_inativas: Annotated[bool, Query()] = False,
) -> list[ContaRecebimento]:
    return await service.listar(session, incluir_inativas=incluir_inativas)


@router.post("/contas", response_model=ContaOut, status_code=status.HTTP_201_CREATED)
async def criar_conta(
    payload: ContaIn,
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("financeiro.conta.write"))],
) -> ContaRecebimento:
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
) -> ContaRecebimento:
    """Tira das escolhas novas. O que já foi recebido continua apontando para ela."""
    return await service.definir_ativa(
        session, conta=await _carregar(session, conta_id), ativa=False
    )


@router.post("/contas/{conta_id}/reativar", response_model=ContaOut)
async def reativar_conta(
    conta_id: uuid.UUID,
    session: SessionDep,
    _: Annotated[object, Depends(require("financeiro.conta.write"))],
) -> ContaRecebimento:
    return await service.definir_ativa(
        session, conta=await _carregar(session, conta_id), ativa=True
    )
