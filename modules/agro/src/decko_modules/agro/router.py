import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from decko.db import get_session
from decko_modules.agro import pdf, service
from decko_modules.agro.models import (
    Aircraft,
    Client,
    OperationalPlan,
    Property,
    WeatherReading,
)
from decko_modules.agro.schemas import (
    AircraftIn,
    AircraftOut,
    ClientIn,
    ClientOut,
    PlanIn,
    PlanOut,
    PropertyIn,
    PropertyOut,
    WeatherCaptureIn,
    WeatherCaptureOut,
    WeatherReadingOut,
)
from decko_modules.agro.weather import OpenMeteoProvider, WeatherProvider, WeatherUnavailableError
from decko_modules.core.deps import CurrentPrincipal, require

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_weather_provider() -> WeatherProvider:
    """Ponto de injeção do provedor de clima.

    Declarado como dependência para que o teste substitua a chamada externa sem depender
    da rede, e para que trocar de provedor não toque no endpoint.
    """
    return OpenMeteoProvider()


WeatherProviderDep = Annotated[WeatherProvider, Depends(get_weather_provider)]


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


@router.get("/properties", response_model=list[PropertyOut])
async def list_properties(
    session: SessionDep,
    _: Annotated[object, Depends(require("agro.property.read"))],
) -> list[Property]:
    result = await session.execute(select(Property).order_by(Property.nome))
    return list(result.scalars().all())


@router.post("/properties", response_model=PropertyOut, status_code=status.HTTP_201_CREATED)
async def create_property(
    payload: PropertyIn,
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("agro.property.write"))],
) -> Property:
    prop = Property(tenant_id=principal.tenant_id, **payload.model_dump())
    session.add(prop)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Contratante não encontrado.",
        ) from exc
    return prop


@router.post("/plans", response_model=PlanOut, status_code=status.HTTP_201_CREATED)
async def create_plan(
    payload: PlanIn,
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("agro.plan.write"))],
) -> OperationalPlan:
    plan = OperationalPlan(
        tenant_id=principal.tenant_id,
        numero=await service.next_plan_number(session, principal.tenant_id),
        **payload.model_dump(),
    )
    session.add(plan)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Contratante, propriedade ou aeronave não encontrados.",
        ) from exc
    return plan


@router.get("/plans", response_model=list[PlanOut])
async def list_plans(
    session: SessionDep,
    _: Annotated[object, Depends(require("agro.plan.read"))],
) -> list[OperationalPlan]:
    result = await session.execute(select(OperationalPlan).order_by(OperationalPlan.numero.desc()))
    return list(result.scalars().all())


@router.post(
    "/plans/{plan_id}/weather",
    response_model=WeatherCaptureOut,
    status_code=status.HTTP_201_CREATED,
)
async def capture_weather(
    plan_id: uuid.UUID,
    payload: WeatherCaptureIn,
    session: SessionDep,
    provider: WeatherProviderDep,
    _: Annotated[object, Depends(require("agro.plan.write"))],
) -> WeatherCaptureOut:
    """Registra a condição meteorológica daquele ponto do formulário.

    Substitui as doze leituras que hoje são escritas à mão, e guarda junto a procedência
    do dado, que é o que a torna defensável em disputa de deriva.
    """
    plan = await session.get(OperationalPlan, plan_id)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Planejamento não encontrado."
        )

    try:
        reading, problems = await service.capture_weather(
            session,
            plan=plan,
            provider=provider,
            data=payload.data,
            periodo=payload.periodo,
            momento=payload.momento,
            hora=payload.hora,
            latitude=float(payload.latitude) if payload.latitude is not None else None,
            longitude=float(payload.longitude) if payload.longitude is not None else None,
        )
    except service.PlanError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except WeatherUnavailableError as exc:
        # 502: a falha é do provedor externo, não do pedido de quem chamou.
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return WeatherCaptureOut(leitura=WeatherReadingOut.model_validate(reading), alertas=problems)


@router.get("/plans/{plan_id}/pdf", response_class=Response)
async def export_plan_pdf(
    plan_id: uuid.UUID,
    session: SessionDep,
    _: Annotated[object, Depends(require("agro.plan.export"))],
) -> Response:
    """Emite o Planejamento Operacional no formato do talão, pronto para impressão."""
    plan = await session.get(OperationalPlan, plan_id)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Planejamento não encontrado."
        )

    document = await service.build_document(session, plan)
    return Response(
        content=pdf.render(document),
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="planejamento-operacional-{plan.numero}.pdf"'
            )
        },
    )


@router.get("/plans/{plan_id}/weather", response_model=list[WeatherReadingOut])
async def list_weather(
    plan_id: uuid.UUID,
    session: SessionDep,
    _: Annotated[object, Depends(require("agro.plan.read"))],
) -> list[WeatherReading]:
    result = await session.execute(
        select(WeatherReading)
        .where(WeatherReading.plan_id == plan_id)
        .order_by(WeatherReading.data, WeatherReading.periodo, WeatherReading.momento)
    )
    return list(result.scalars().all())


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
