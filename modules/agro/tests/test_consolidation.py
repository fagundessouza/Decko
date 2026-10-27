"""Consolidação mensal: o fechamento que hoje é retranscrito à mão para o Excel.

O cenário tem três planejamentos de propósito — dois no mês consultado e um no mês
seguinte —, além de um sem data. O que está sob teste é principalmente o que **não** pode
acontecer: mês vizinho entrando na conta, planejamento sumindo em silêncio por não ter
data, e violação de parâmetro passando despercebida no fechamento.
"""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import date, time
from decimal import Decimal
from typing import Any

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from decko.db import SessionFactory
from decko.main import create_app
from decko_modules.agro.consolidation import CSV_ENCODING
from decko_modules.agro.enums import (
    Cultura,
    Momento,
    Periodo,
    PlanStatus,
    WeatherSource,
)
from decko_modules.agro.models import (
    Aircraft,
    Client,
    OperationalPlan,
    PlanProduct,
    Product,
    Property,
    WeatherReading,
)
from decko_modules.core.cli import _bootstrap
from decko_modules.core.models import Tenant

BASE = "/api/v1/agro"
PASSWORD = "senha-local-de-teste-123"

ANO = 2026
MES = 10


@dataclass
class Scenario:
    client: AsyncClient
    token: str
    tenant_id: uuid.UUID

    @property
    def auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


@pytest_asyncio.fixture
async def scenario() -> AsyncIterator[Scenario]:
    suffix = uuid.uuid4().hex[:8]
    slug = f"teste-{suffix}"
    email = f"admin-{suffix}@teste-decko.com.br"

    async with SessionFactory() as session, session.begin():
        tenant, _user, _granted = await _bootstrap(
            session,
            tenant_name="AgroDrone Teste",
            tenant_slug=slug,
            admin_email=email,
            admin_name="Responsavel",
            password=PASSWORD,
            # A empresa nasce so com o nucleo; o modulo de segmento e contratado.
            modules=["agro"],
        )
        tenant_id = tenant.id

        contratante = Client(
            tenant_id=tenant_id, nome="Fazenda Santa Clara", cpf_cnpj="12345678000195"
        )
        aeronave = Aircraft(tenant_id=tenant_id, prefixo="PP-DRN")
        glifosato = Product(tenant_id=tenant_id, nome_comercial="Glifosato Tecnico")
        adjuvante = Product(tenant_id=tenant_id, nome_comercial="Oleo Mineral")
        session.add_all([contratante, aeronave, glifosato, adjuvante])
        await session.flush()

        propriedade = Property(
            tenant_id=tenant_id,
            client_id=contratante.id,
            nome="Talhao Norte",
            municipio="Jatai",
            uf="GO",
        )
        session.add(propriedade)
        await session.flush()

        def make_plan(numero: int, dia: date | None, area: str, status: PlanStatus) -> Any:
            return OperationalPlan(
                tenant_id=tenant_id,
                numero=numero,
                status=status,
                client_id=contratante.id,
                property_id=propriedade.id,
                aircraft_id=aeronave.id,
                data_aplicacao=dia,
                cultura=Cultura.SOJA,
                area_ha=Decimal(area),
                param_velocidade_vento_max_kmh=Decimal("15"),
            )

        dentro_1 = make_plan(1, date(ANO, MES, 9), "120.50", PlanStatus.ASSINADO)
        dentro_2 = make_plan(2, date(ANO, MES, 28), "80.25", PlanStatus.RASCUNHO)
        # Mês seguinte: não pode entrar na conta de outubro.
        fora = make_plan(3, date(ANO, MES + 1, 2), "999.00", PlanStatus.ASSINADO)
        # Sem data: não cabe em mês nenhum, mas não pode sumir da conferência.
        sem_data = make_plan(4, None, "50.00", PlanStatus.RASCUNHO)
        session.add_all([dentro_1, dentro_2, fora, sem_data])
        await session.flush()

        session.add_all(
            [
                PlanProduct(
                    tenant_id=tenant_id,
                    plan_id=dentro_1.id,
                    product_id=glifosato.id,
                    total_produto=Decimal("301.25"),
                ),
                PlanProduct(
                    tenant_id=tenant_id,
                    plan_id=dentro_1.id,
                    product_id=adjuvante.id,
                    total_produto=Decimal("12.00"),
                ),
                PlanProduct(
                    tenant_id=tenant_id,
                    plan_id=dentro_2.id,
                    product_id=glifosato.id,
                    total_produto=Decimal("200.75"),
                ),
                # Produto do mês seguinte: não entra no total de outubro.
                PlanProduct(
                    tenant_id=tenant_id,
                    plan_id=fora.id,
                    product_id=glifosato.id,
                    total_produto=Decimal("5000.00"),
                ),
                WeatherReading(
                    tenant_id=tenant_id,
                    plan_id=dentro_1.id,
                    data=date(ANO, MES, 9),
                    periodo=Periodo.MATUTINO,
                    momento=Momento.INICIO,
                    hora=time(7, 30),
                    velocidade_vento_kmh=Decimal("6.1"),
                    source=WeatherSource.API,
                ),
                WeatherReading(
                    tenant_id=tenant_id,
                    plan_id=dentro_1.id,
                    data=date(ANO, MES, 9),
                    periodo=Periodo.VESPERTINO,
                    momento=Momento.FINAL,
                    hora=time(16, 0),
                    velocidade_vento_kmh=Decimal("22.4"),
                    source=WeatherSource.API,
                    violou_parametro=True,
                ),
            ]
        )
        await session.flush()

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        login = await http.post(
            "/api/v1/core/auth/login",
            json={"tenant_slug": slug, "email": email, "password": PASSWORD},
        )
        token = login.json()["access_token"]
        try:
            yield Scenario(client=http, token=token, tenant_id=tenant_id)
        finally:
            async with SessionFactory() as session, session.begin():
                await session.execute(delete(Tenant).where(Tenant.id == tenant_id))


async def _month(scenario: Scenario, ano: int = ANO, mes: int = MES) -> dict:
    response = await scenario.client.get(f"{BASE}/consolidation/{ano}/{mes}", headers=scenario.auth)
    assert response.status_code == 200, response.text
    return response.json()


async def test_only_the_months_own_applications_are_counted(scenario: Scenario) -> None:
    body = await _month(scenario)

    assert body["quantidade"] == 2
    assert [plano["numero"] for plano in body["planos"]] == [1, 2]


async def test_the_total_area_adds_up_the_month(scenario: Scenario) -> None:
    body = await _month(scenario)

    assert Decimal(body["area_total_ha"]) == Decimal("200.75")


async def test_a_plan_without_a_date_is_counted_apart_instead_of_vanishing(
    scenario: Scenario,
) -> None:
    """Sumiço silencioso num relatório de prestação de contas é pior que número feio."""
    body = await _month(scenario)

    assert body["planos_sem_data"] == 1
    assert 4 not in [plano["numero"] for plano in body["planos"]]


async def test_the_breach_is_visible_in_the_closing(scenario: Scenario) -> None:
    """É o número que a empresa precisa ver antes de enviar o mês, não depois da autuação."""
    body = await _month(scenario)

    assert body["planos_com_violacao"] == 1
    primeiro = next(p for p in body["planos"] if p["numero"] == 1)
    assert primeiro["leituras"] == 2
    assert primeiro["violacoes"] == 1


async def test_product_totals_cover_the_month_only(scenario: Scenario) -> None:
    body = await _month(scenario)
    totais = {item["produto"]: Decimal(item["total"]) for item in body["totais_por_produto"]}

    assert totais["Glifosato Tecnico"] == Decimal("502.00")
    assert totais["Oleo Mineral"] == Decimal("12.00")


async def test_a_draft_appears_with_its_status_showing(scenario: Scenario) -> None:
    """Rascunho entra na lista; escondê-lo faria o fechamento mentir por omissão."""
    body = await _month(scenario)

    rascunho = next(p for p in body["planos"] if p["numero"] == 2)
    assert rascunho["status"] == "rascunho"


async def test_a_month_without_applications_is_empty_not_an_error(scenario: Scenario) -> None:
    body = await _month(scenario, mes=1)

    assert body["quantidade"] == 0
    assert Decimal(body["area_total_ha"]) == 0
    assert body["totais_por_produto"] == []


async def test_an_impossible_month_is_refused(scenario: Scenario) -> None:
    response = await scenario.client.get(f"{BASE}/consolidation/{ANO}/13", headers=scenario.auth)

    assert response.status_code == 422


async def test_the_csv_opens_in_a_portuguese_spreadsheet(scenario: Scenario) -> None:
    """Ponto e vírgula, vírgula decimal e BOM: sem isso o Excel brasileiro abre errado."""
    response = await scenario.client.get(
        f"{BASE}/consolidation/{ANO}/{MES}/csv", headers=scenario.auth
    )

    assert response.status_code == 200, response.text
    assert "attachment" in response.headers["content-disposition"]
    assert "consolidacao-2026-10.csv" in response.headers["content-disposition"]

    assert response.content.startswith(b"\xef\xbb\xbf")
    texto = response.content.decode(CSV_ENCODING)
    linhas = texto.splitlines()

    assert linhas[0].startswith("Nº;Status;Data;Contratante")
    assert "120,50" in linhas[1]
    assert "09/10/2026" in linhas[1]
    assert "Fazenda Santa Clara" in linhas[1]
    # Com máscara: catorze algarismos corridos viram notação científica no Excel.
    assert "12.345.678/0001-95" in linhas[1]
    # Uma linha por planejamento, como uma via do talão.
    assert len(linhas) == 3


async def test_the_csv_lists_the_products_of_each_plan(scenario: Scenario) -> None:
    response = await scenario.client.get(
        f"{BASE}/consolidation/{ANO}/{MES}/csv", headers=scenario.auth
    )
    texto = response.content.decode(CSV_ENCODING)

    assert "Glifosato Tecnico | Oleo Mineral" in texto


async def test_the_consolidation_requires_authentication(scenario: Scenario) -> None:
    response = await scenario.client.get(f"{BASE}/consolidation/{ANO}/{MES}")

    assert response.status_code == 401


async def test_the_export_requires_authentication(scenario: Scenario) -> None:
    response = await scenario.client.get(f"{BASE}/consolidation/{ANO}/{MES}/csv")

    assert response.status_code == 401


# ------------------------------------------------------------ relatório mensal do MAPA


async def _relatorio(scenario: Scenario, ano: int = ANO, mes: int = MES) -> dict:
    response = await scenario.client.get(
        f"{BASE}/monthly-report/{ano}/{mes}", headers=scenario.auth
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_o_relatorio_traz_o_que_a_portaria_298_pede(scenario: Scenario) -> None:
    """Município/UF, aeronave, tipo de atividade, área e horas — art. 11, incisos I a V."""
    body = await _relatorio(scenario)

    assert len(body["linhas"]) == 1
    linha = body["linhas"][0]
    assert linha["municipio"] == "Jatai"
    assert linha["uf"] == "GO"
    assert linha["aeronave"] == "PP-DRN"
    # Só o planejamento assinado: o outro do mês está em rascunho.
    assert Decimal(linha["area_ha"]) == Decimal("120.50")


async def test_rascunho_fica_de_fora_mas_e_contado(scenario: Scenario) -> None:
    """O relatório presta contas do que foi feito; rascunho é intenção, não atividade.

    E não pode sumir calado: quem fecha o mês precisa saber que deixou um por assinar.
    """
    body = await _relatorio(scenario)

    assert body["rascunhos_no_mes"] == 1
    assert Decimal(body["area_total_ha"]) == Decimal("120.50")


async def test_o_mes_seguinte_nao_entra(scenario: Scenario) -> None:
    body = await _relatorio(scenario)

    assert all(Decimal(linha["area_ha"]) != Decimal("999.00") for linha in body["linhas"])


async def test_os_produtos_saem_com_volume_e_dosagem(scenario: Scenario) -> None:
    """Inciso V: marca comercial, volume e dosagem aplicada."""
    body = await _relatorio(scenario)

    produtos = body["linhas"][0]["produtos"]
    assert produtos, "o relatório precisa listar os produtos aplicados"
    assert any("Glifosato Tecnico" in produto for produto in produtos)
    assert any("dose" in produto for produto in produtos)


async def test_o_prazo_e_o_dia_quinze_do_mes_seguinte(scenario: Scenario) -> None:
    """Portaria 298/2021, art. 11, parágrafo único."""
    body = await _relatorio(scenario)

    assert body["prazo"] == f"{ANO}-{MES + 1:02d}-15"


async def test_prazo_de_dezembro_vira_janeiro_do_ano_seguinte(scenario: Scenario) -> None:
    body = await _relatorio(scenario, ano=ANO, mes=12)

    assert body["prazo"] == f"{ANO + 1}-01-15"


async def test_o_csv_sai_na_ordem_dos_incisos(scenario: Scenario) -> None:
    """A ordem das colunas é a dos incisos, porque é a ordem da tela do SIPEAGRO."""
    response = await scenario.client.get(
        f"{BASE}/monthly-report/{ANO}/{MES}/csv", headers=scenario.auth
    )

    assert response.status_code == 200, response.text
    linhas = response.content.decode(CSV_ENCODING).splitlines()
    assert linhas[0].split(";") == [
        "Município",
        "UF",
        "Aeronave (ARP)",
        "Tipo de atividade",
        "Área aplicada (ha)",
        "Horas de execução",
        "Produtos (marca, volume e dosagem)",
    ]
    assert "Jatai;GO;PP-DRN" in linhas[1]


async def test_a_conferencia_continua_sendo_outra_coisa(scenario: Scenario) -> None:
    """Os dois relatórios convivem: um é da empresa, o outro é do MAPA.

    A conferência conta os dois planejamentos do mês, com rascunho à mostra; o relatório
    conta só o realizado. Confundir os dois é mandar rascunho para o órgão.
    """
    conferencia = await _month(scenario)
    relatorio = await _relatorio(scenario)

    assert conferencia["quantidade"] == 2
    assert len(relatorio["linhas"]) == 1
