from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from decko.db import get_session
from decko_modules.agro.models import Aircraft, Client
from decko_modules.agro.schemas import AircraftIn, AircraftOut, ClientIn, ClientOut
from decko_modules.core.deps import CurrentPrincipal, require

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/clients", response_model=list[ClientOut])
async def list_clients(
    session: SessionDep,
    _: Annotated[object, Depends(require("agro.client.read"))],
) -> list[Client]:
    # Sem filtro por empresa na consulta: quem filtra é a política de RLS, a partir do
    # tenant que a dependência de autenticação amarrou nesta sessão.
    result = await session.execute(select(Client).order_by(Client.nome))
    return list(result.scalars().all())


@router.post("/clients", response_model=ClientOut, status_code=status.HTTP_201_CREATED)
async def create_client(
    payload: ClientIn,
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("agro.client.write"))],
) -> Client:
    client = Client(tenant_id=principal.tenant_id, **payload.model_dump())
    session.add(client)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe um contratante com este CPF/CNPJ.",
        ) from exc
    return client


@router.get("/aircraft", response_model=list[AircraftOut])
async def list_aircraft(
    session: SessionDep,
    _: Annotated[object, Depends(require("agro.aircraft.read"))],
) -> list[Aircraft]:
    result = await session.execute(select(Aircraft).order_by(Aircraft.prefixo))
    return list(result.scalars().all())


@router.post("/aircraft", response_model=AircraftOut, status_code=status.HTTP_201_CREATED)
async def create_aircraft(
    payload: AircraftIn,
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("agro.aircraft.write"))],
) -> Aircraft:
    aircraft = Aircraft(tenant_id=principal.tenant_id, **payload.model_dump())
    session.add(aircraft)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe uma aeronave com este prefixo.",
        ) from exc
    return aircraft
