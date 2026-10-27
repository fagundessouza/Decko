import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from decko.db import get_session
from decko_modules.clientes import service
from decko_modules.clientes.models import Cliente
from decko_modules.clientes.schemas import ClienteIn, ClienteOut
from decko_modules.core.deps import CurrentPrincipal, require

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _invalido(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))


async def _carregar(session: AsyncSession, cliente_id: uuid.UUID) -> Cliente:
    cliente = await session.get(Cliente, cliente_id)
    if cliente is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente não encontrado.")
    return cliente


@router.get("/clientes", response_model=list[ClienteOut])
async def listar_clientes(
    session: SessionDep,
    _: Annotated[object, Depends(require("clientes.cliente.read"))],
    busca: Annotated[str | None, Query(max_length=120)] = None,
    incluir_inativos: Annotated[bool, Query()] = False,
    limite: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[Cliente]:
    """Acha por nome, apelido ou documento. Inativo fica de fora salvo se pedido."""
    return await service.procurar(
        session, busca=busca, incluir_inativos=incluir_inativos, limite=limite
    )


@router.post("/clientes", response_model=ClienteOut, status_code=status.HTTP_201_CREATED)
async def criar_cliente(
    payload: ClienteIn,
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("clientes.cliente.write"))],
) -> Cliente:
    try:
        return await service.criar(
            session,
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            dados=payload.model_dump(),
        )
    except service.ClientesError as exc:
        raise _invalido(exc) from exc


@router.get("/clientes/{cliente_id}", response_model=ClienteOut)
async def ver_cliente(
    cliente_id: uuid.UUID,
    session: SessionDep,
    _: Annotated[object, Depends(require("clientes.cliente.read"))],
) -> Cliente:
    return await _carregar(session, cliente_id)


@router.put("/clientes/{cliente_id}", response_model=ClienteOut)
async def atualizar_cliente(
    cliente_id: uuid.UUID,
    payload: ClienteIn,
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("clientes.cliente.write"))],
) -> Cliente:
    cliente = await _carregar(session, cliente_id)
    try:
        return await service.atualizar(
            session,
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            cliente=cliente,
            dados=payload.model_dump(),
        )
    except service.ClientesError as exc:
        raise _invalido(exc) from exc


@router.post("/clientes/{cliente_id}/desativar", response_model=ClienteOut)
async def desativar_cliente(
    cliente_id: uuid.UUID,
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("clientes.cliente.deactivate"))],
) -> Cliente:
    """Tira das telas de lançamento. O cadastro continua, porque documentos o citam."""
    return await service.definir_ativo(
        session,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        cliente=await _carregar(session, cliente_id),
        ativo=False,
    )


@router.post("/clientes/{cliente_id}/reativar", response_model=ClienteOut)
async def reativar_cliente(
    cliente_id: uuid.UUID,
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("clientes.cliente.deactivate"))],
) -> Cliente:
    return await service.definir_ativo(
        session,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        cliente=await _carregar(session, cliente_id),
        ativo=True,
    )
