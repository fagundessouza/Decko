"""Captura de clima pela API, do login até a leitura gravada.

O provedor externo é substituído pelo ponto de injeção do próprio módulo, devolvendo os
valores gravados da Open-Meteo em ``fixtures/``. O que está sob teste aqui é o caminho da
aplicação — permissão, isolamento, gravação e alerta —, não a rede.
"""

import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from decko.db import SessionFactory
from decko.main import create_app
from decko_modules.agro.models import Client, OperationalPlan, Property
from decko_modules.agro.router import get_weather_provider
from decko_modules.agro.weather import Observation
from decko_modules.core.cli import _bootstrap
from decko_modules.core.models import Tenant

BASE = "/api/v1/agro"
PASSWORD = "senha-local-de-teste-123"

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "open_meteo_archive_jatai.json").read_text(
        encoding="utf-8"
    )
)
RECORDED_DAY = FIXTURE["hourly"]["time"][12][:10]
RECORDED_TEMPERATURE = Decimal(str(FIXTURE["hourly"]["temperature_2m"][12]))
RECORDED_HUMIDITY = Decimal(str(FIXTURE["hourly"]["relative_humidity_2m"][12]))
RECORDED_WIND = Decimal(str(FIXTURE["hourly"]["wind_speed_10m"][12]))


class RecordedProvider:
    """Devolve a observação gravada, registrando com que coordenada foi chamado."""

    def __init__(self) -> None:
        self.calls: list[tuple[float, float, datetime]] = []

    async def observe(
        self, *, latitude: Decimal, longitude: Decimal, moment: datetime
    ) -> Observation:
        self.calls.append((float(latitude), float(longitude), moment))
        return Observation(
            temperatura_c=RECORDED_TEMPERATURE,
            umidade_relativa_pct=RECORDED_HUMIDITY,
            velocidade_vento_kmh=RECORDED_WIND,
            observed_at=datetime.now(UTC),
            provider="open-meteo/archive",
            payload={"observation": {"time": f"{RECORDED_DAY}T12:00"}},
        )


@dataclass
class Scenario:
    tenant_id: uuid.UUID
    plan_id: uuid.UUID
    token: str
    provider: RecordedProvider
    client: AsyncClient


@pytest_asyncio.fixture
async def scenario() -> AsyncIterator[Scenario]:
    suffix = uuid.uuid4().hex[:8]
    slug = f"teste-{suffix}"
    email = f"admin-{suffix}@teste-decko.com.br"

    async with SessionFactory() as session, session.begin():
        tenant, _user, _granted = await _bootstrap(
            session,
            tenant_name="Pulverizacao de Teste",
            tenant_slug=slug,
            admin_email=email,
            admin_name="Piloto de Teste",
            password=PASSWORD,
        )
        tenant_id = tenant.id

        contratante = Client(tenant_id=tenant_id, nome="Fazenda Teste", cpf_cnpj="12345678000199")
        session.add(contratante)
        await session.flush()

        propriedade = Property(
            tenant_id=tenant_id,
            client_id=contratante.id,
            nome="Talhao Norte",
            municipio="Jatai",
            uf="GO",
            latitude=Decimal("-17.8814"),
            longitude=Decimal("-51.7214"),
        )
        session.add(propriedade)
        await session.flush()

        plan = OperationalPlan(
            tenant_id=tenant_id,
            numero=1,
            client_id=contratante.id,
            property_id=propriedade.id,
            # Limites conservadores: as condições gravadas os violam.
            param_temperatura_maxima_c=Decimal("30"),
            param_umidade_relativa_min_pct=Decimal("50"),
            param_velocidade_vento_max_kmh=Decimal("15"),
        )
        session.add(plan)
        await session.flush()
        plan_id = plan.id

    provider = RecordedProvider()
    app = create_app()
    app.dependency_overrides[get_weather_provider] = lambda: provider

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http_client:
        login = await http_client.post(
            "/api/v1/core/auth/login",
            json={"tenant_slug": slug, "email": email, "password": PASSWORD},
        )
        token = login.json()["access_token"]

        try:
            yield Scenario(
                tenant_id=tenant_id,
                plan_id=plan_id,
                token=token,
                provider=provider,
                client=http_client,
            )
        finally:
            async with SessionFactory() as session, session.begin():
                await session.execute(delete(Tenant).where(Tenant.id == tenant_id))


def _auth(scenario: Scenario) -> dict[str, str]:
    return {"Authorization": f"Bearer {scenario.token}"}


async def _capture(scenario: Scenario, hora: str = "12:00") -> dict:
    response = await scenario.client.post(
        f"{BASE}/plans/{scenario.plan_id}/weather",
        headers=_auth(scenario),
        json={
            "data": RECORDED_DAY,
            "periodo": "matutino",
            "momento": "inicio",
            "hora": hora,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_capture_stores_the_reading_and_its_source(scenario: Scenario) -> None:
    body = await _capture(scenario)
    leitura = body["leitura"]

    assert Decimal(leitura["temperatura_c"]) == RECORDED_TEMPERATURE
    assert Decimal(leitura["umidade_relativa_pct"]) == RECORDED_HUMIDITY
    assert Decimal(leitura["velocidade_vento_kmh"]) == RECORDED_WIND
    # A origem é o que distingue registro probatório de anotação feita de memória.
    assert leitura["source"] == "api"
    assert leitura["provider"] == "open-meteo/archive"


async def test_capture_flags_the_violated_limits(scenario: Scenario) -> None:
    body = await _capture(scenario)

    assert body["leitura"]["violou_parametro"] is True
    # 34,5 °C contra limite de 30, e 26% contra mínimo de 50. O vento estava dentro.
    assert len(body["alertas"]) == 2
    assert any("Temperatura" in alerta for alerta in body["alertas"])
    assert any("Umidade" in alerta for alerta in body["alertas"])


async def test_coordinates_fall_back_to_the_property(scenario: Scenario) -> None:
    await _capture(scenario)

    latitude, longitude, _moment = scenario.provider.calls[0]
    assert (round(latitude, 4), round(longitude, 4)) == (-17.8814, -51.7214)


async def test_recapturing_the_same_slot_replaces_the_reading(scenario: Scenario) -> None:
    """Corrigir um horário errado não pode deixar duas leituras conflitantes no documento."""
    first = await _capture(scenario, hora="12:00")
    second = await _capture(scenario, hora="13:00")

    assert first["leitura"]["id"] == second["leitura"]["id"]

    listing = await scenario.client.get(
        f"{BASE}/plans/{scenario.plan_id}/weather", headers=_auth(scenario)
    )
    assert listing.status_code == 200
    assert len(listing.json()) == 1
    assert listing.json()[0]["hora"] == "13:00:00"


async def test_capture_requires_authentication(scenario: Scenario) -> None:
    response = await scenario.client.post(
        f"{BASE}/plans/{scenario.plan_id}/weather",
        json={
            "data": RECORDED_DAY,
            "periodo": "matutino",
            "momento": "inicio",
            "hora": "12:00",
        },
    )

    assert response.status_code == 401


async def test_unknown_plan_is_not_found(scenario: Scenario) -> None:
    response = await scenario.client.post(
        f"{BASE}/plans/{uuid.uuid4()}/weather",
        headers=_auth(scenario),
        json={
            "data": RECORDED_DAY,
            "periodo": "matutino",
            "momento": "inicio",
            "hora": "12:00",
        },
    )

    assert response.status_code == 404
