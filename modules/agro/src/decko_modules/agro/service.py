"""Regra de negócio do módulo agro. Não conhece HTTP."""

import uuid
from datetime import date, datetime, time

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from decko_modules.agro.enums import Momento, Periodo, WeatherSource
from decko_modules.agro.models import OperationalPlan, Property, WeatherReading
from decko_modules.agro.weather import (
    Observation,
    ParameterLimits,
    WeatherProvider,
    evaluate,
)


class PlanError(Exception):
    pass


async def next_plan_number(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    """Próximo sequencial da empresa.

    Duas emissões simultâneas podem calcular o mesmo número; a restrição de unicidade
    (tenant_id, numero) recusa a segunda, e a emissão é refeita. Preferível a uma sequência
    global, que entregaria números com buracos e revelaria o volume de uma empresa à outra.
    """
    current = await session.scalar(
        select(func.max(OperationalPlan.numero)).where(OperationalPlan.tenant_id == tenant_id)
    )
    return int(current or 0) + 1


def limits_of(plan: OperationalPlan) -> ParameterLimits:
    return ParameterLimits(
        temperatura_maxima_c=plan.param_temperatura_maxima_c,
        umidade_relativa_min_pct=plan.param_umidade_relativa_min_pct,
        velocidade_vento_max_kmh=plan.param_velocidade_vento_max_kmh,
    )


async def resolve_coordinates(
    session: AsyncSession,
    plan: OperationalPlan,
    latitude: float | None = None,
    longitude: float | None = None,
) -> tuple[float, float]:
    """Coordenada da leitura: a informada, senão a do planejamento, senão a da propriedade.

    A ordem importa. O aparelho em campo sabe onde o voo aconteceu; a propriedade só sabe
    onde fica a sede, que pode estar a quilômetros do talhão aplicado.
    """
    if latitude is not None and longitude is not None:
        return latitude, longitude

    if plan.latitude is not None and plan.longitude is not None:
        return float(plan.latitude), float(plan.longitude)

    prop = await session.get(Property, plan.property_id)
    if prop is None or prop.latitude is None or prop.longitude is None:
        raise PlanError(
            "Sem coordenada para consultar o clima. Informe a localização na captura ou "
            "cadastre as coordenadas da propriedade."
        )
    return float(prop.latitude), float(prop.longitude)


async def capture_weather(
    session: AsyncSession,
    *,
    plan: OperationalPlan,
    provider: WeatherProvider,
    data: date,
    periodo: Periodo,
    momento: Momento,
    hora: time,
    latitude: float | None = None,
    longitude: float | None = None,
) -> tuple[WeatherReading, list[str]]:
    """Busca a leitura daquele instante e a grava com a procedência e o veredito.

    Regravar a mesma posição do formulário substitui a leitura anterior: o operador que
    corrige um horário errado não deve ficar com duas leituras conflitantes no documento.
    """
    lat, lon = await resolve_coordinates(session, plan, latitude, longitude)
    observation: Observation = await provider.observe(
        latitude=lat, longitude=lon, moment=datetime.combine(data, hora)
    )

    problems = evaluate(observation, limits_of(plan))

    existing = await session.scalar(
        select(WeatherReading).where(
            WeatherReading.plan_id == plan.id,
            WeatherReading.data == data,
            WeatherReading.periodo == periodo,
            WeatherReading.momento == momento,
        )
    )
    reading = existing or WeatherReading(
        tenant_id=plan.tenant_id,
        plan_id=plan.id,
        data=data,
        periodo=periodo,
        momento=momento,
    )

    reading.hora = hora
    reading.temperatura_c = observation.temperatura_c
    reading.umidade_relativa_pct = observation.umidade_relativa_pct
    reading.velocidade_vento_kmh = observation.velocidade_vento_kmh
    reading.source = WeatherSource.API
    reading.provider = observation.provider
    reading.payload_bruto = observation.payload
    reading.latitude = lat
    reading.longitude = lon
    reading.captured_at = observation.observed_at
    reading.violou_parametro = bool(problems)

    if existing is None:
        session.add(reading)
    await session.flush()

    return reading, problems
