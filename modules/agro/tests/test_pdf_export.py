"""Emissão do Planejamento Operacional em PDF.

Verifica o que o documento precisa conter para substituir o talão: identificação da
empresa, do contratante, da área, os produtos, os parâmetros e as leituras meteorológicas
nas posições certas — além das quatro assinaturas que a lei exige.
"""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import date, time
from decimal import Decimal
from io import BytesIO

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pypdf import PdfReader
from sqlalchemy import delete

from decko.db import SessionFactory
from decko.main import create_app
from decko_modules.agro.enums import (
    Cultura,
    EquipamentoTipo,
    Momento,
    Periodo,
    SignatureRole,
    TipoAplicacao,
    WeatherSource,
)
from decko_modules.agro.models import (
    Aircraft,
    Client,
    OperationalPlan,
    PlanProduct,
    Product,
    Property,
    Signature,
    WeatherReading,
)
from decko_modules.core.cli import _bootstrap
from decko_modules.core.models import Tenant

PASSWORD = "senha-local-de-teste-123"
APPLICATION_DAY = date(2026, 10, 9)


@dataclass
class Scenario:
    plan_id: uuid.UUID
    tenant_id: uuid.UUID
    client: AsyncClient
    token: str


@pytest_asyncio.fixture
async def scenario() -> AsyncIterator[Scenario]:
    suffix = uuid.uuid4().hex[:8]
    slug = f"teste-{suffix}"
    email = f"admin-{suffix}@teste-decko.com.br"

    async with SessionFactory() as session, session.begin():
        tenant, _user, _granted = await _bootstrap(
            session,
            tenant_name="AgroPulverizacao Teste",
            tenant_slug=slug,
            admin_email=email,
            admin_name="Responsavel",
            password=PASSWORD,
        )
        tenant_id = tenant.id

        contratante = Client(
            tenant_id=tenant_id, nome="Fazenda Santa Clara", cpf_cnpj="12345678000199"
        )
        aeronave = Aircraft(tenant_id=tenant_id, prefixo="PP-DRN", modelo="T40")
        produto = Product(
            tenant_id=tenant_id,
            nome_comercial="Glifosato Tecnico",
            formulacao="SL",
            classe_toxicologica="IV",
        )
        session.add_all([contratante, aeronave, produto])
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
            numero=42,
            client_id=contratante.id,
            property_id=propriedade.id,
            aircraft_id=aeronave.id,
            data_aplicacao=APPLICATION_DAY,
            cultura=Cultura.SOJA,
            tipos_aplicacao=[TipoAplicacao.HERBICIDA],
            area_ha=Decimal("120.5"),
            equipamento_tipo=EquipamentoTipo.BARRAS_BICOS,
            param_temperatura_maxima_c=Decimal("30"),
            param_umidade_relativa_min_pct=Decimal("50"),
            param_velocidade_vento_max_kmh=Decimal("15"),
            param_altura_voo_m=Decimal("4"),
            observacoes="Aplicacao concluida sem intercorrencias.",
        )
        session.add(plan)
        await session.flush()

        session.add_all(
            [
                PlanProduct(
                    tenant_id=tenant_id,
                    plan_id=plan.id,
                    product_id=produto.id,
                    formulacao="SL",
                    classe_toxicologica="IV",
                    dosagem_ha=Decimal("2.5"),
                    volume_ha=Decimal("10"),
                    total_produto=Decimal("301.25"),
                ),
                WeatherReading(
                    tenant_id=tenant_id,
                    plan_id=plan.id,
                    data=APPLICATION_DAY,
                    periodo=Periodo.MATUTINO,
                    momento=Momento.INICIO,
                    hora=time(7, 30),
                    temperatura_c=Decimal("24.3"),
                    umidade_relativa_pct=Decimal("72"),
                    velocidade_vento_kmh=Decimal("6.1"),
                    source=WeatherSource.API,
                    provider="open-meteo/archive",
                ),
                WeatherReading(
                    tenant_id=tenant_id,
                    plan_id=plan.id,
                    data=APPLICATION_DAY,
                    periodo=Periodo.VESPERTINO,
                    momento=Momento.FINAL,
                    hora=time(16, 0),
                    temperatura_c=Decimal("34.5"),
                    umidade_relativa_pct=Decimal("26"),
                    velocidade_vento_kmh=Decimal("10.2"),
                    source=WeatherSource.API,
                    provider="open-meteo/archive",
                    violou_parametro=True,
                ),
                Signature(
                    tenant_id=tenant_id,
                    plan_id=plan.id,
                    papel=SignatureRole.PILOTO_AGRICOLA,
                    nome="Nathan Gomes",
                    registro="CANAC 123456",
                ),
            ]
        )
        await session.flush()
        plan_id = plan.id

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        login = await http.post(
            "/api/v1/core/auth/login",
            json={"tenant_slug": slug, "email": email, "password": PASSWORD},
        )
        token = login.json()["access_token"]
        try:
            yield Scenario(plan_id=plan_id, tenant_id=tenant_id, client=http, token=token)
        finally:
            async with SessionFactory() as session, session.begin():
                await session.execute(delete(Tenant).where(Tenant.id == tenant_id))


async def _pdf_text(scenario: Scenario) -> str:
    response = await scenario.client.get(
        f"/api/v1/agro/plans/{scenario.plan_id}/pdf",
        headers={"Authorization": f"Bearer {scenario.token}"},
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"

    reader = PdfReader(BytesIO(response.content))
    return "\n".join(page.extract_text() for page in reader.pages)


async def test_document_identifies_the_operation(scenario: Scenario) -> None:
    text = await _pdf_text(scenario)

    assert "PLANEJAMENTO OPERACIONAL" in text
    assert "42" in text
    assert "Fazenda Santa Clara" in text
    assert "Talhao Norte" in text
    assert "Jatai" in text


async def test_coordinates_are_printed_in_degrees_minutes_seconds(
    scenario: Scenario,
) -> None:
    """O formulário pede DMS; guardamos decimal. A conversão tem de aparecer impressa."""
    text = await _pdf_text(scenario)

    assert "17" in text and "52" in text and "53.04" in text
    assert "S" in text and "W" in text


async def test_products_and_parameters_are_printed(scenario: Scenario) -> None:
    text = await _pdf_text(scenario)

    assert "Glifosato Tecnico" in text
    assert "Soja" in text
    assert "PP-DRN" in text
    # Limites planejados pelo responsável técnico.
    assert "30,00" in text
    assert "50,00" in text


async def test_weather_readings_appear_with_their_values(scenario: Scenario) -> None:
    text = await _pdf_text(scenario)

    assert "07:30" in text
    assert "24,3" in text
    assert "16:00" in text
    assert "34,5" in text


async def test_violations_are_reported_in_the_observations_field(
    scenario: Scenario,
) -> None:
    """Sem inventar campo no formulário legal: o aviso vai onde o talão já prevê texto."""
    text = await _pdf_text(scenario)

    assert "Aplicacao concluida sem intercorrencias." in text
    assert "fora dos par" in text  # "fora dos parâmetros planejados"
    assert "Temperatura" in text


async def test_all_four_signature_blocks_are_present(scenario: Scenario) -> None:
    text = await _pdf_text(scenario)

    for titulo in ("Agr", "Piloto", "Executor", "Propriet"):
        assert titulo in text
    assert "Nathan Gomes" in text
    assert "CANAC 123456" in text


async def test_export_requires_authentication(scenario: Scenario) -> None:
    response = await scenario.client.get(f"/api/v1/agro/plans/{scenario.plan_id}/pdf")

    assert response.status_code == 401
