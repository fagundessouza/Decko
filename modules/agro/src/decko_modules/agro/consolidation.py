"""Consolidação mensal das aplicações.

Fecha a dor nº 6 do discovery: hoje o mês inteiro é retranscrito do talão para uma planilha
Excel à mão. Aqui o mês é montado a partir do que já foi registrado, e sai em CSV que o
Excel abre direto.

**O que isto não é.** Não é o arquivo que sobe para o MAPA. A questão Q1 do discovery —
qual sistema recebe o envio mensal e em que formato — continua sem resposta, e produzir um
layout "do MAPA" por dedução seria inventar regra num domínio regulado. O que sai daqui é
a consolidação do que a própria empresa emitiu, para conferência e para alimentar a
planilha que ela já usa.

Nada é descartado em silêncio: planejamento sem data de aplicação não pertence a mês
nenhum, então é contado à parte em vez de sumir da contagem, e rascunho entra na lista com
o seu status à mostra. Num relatório que presta contas, sumiço silencioso é pior do que
número feio.
"""

import csv
import io
import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from decko.documents import format_cpf_cnpj
from decko_modules.agro.models import (
    Aircraft,
    Client,
    OperationalPlan,
    PlanProduct,
    Product,
    Property,
    WeatherReading,
)

# Separador e BOM para o Excel em português: ele usa a vírgula como separador decimal, e
# por isso espera ponto e vírgula entre as colunas. Sem o BOM, abre os acentos corrompidos.
CSV_DELIMITER = ";"
CSV_ENCODING = "utf-8-sig"

COLUMNS = (
    "Nº",
    "Status",
    "Data",
    "Contratante",
    "CPF/CNPJ",
    "Propriedade",
    "Município",
    "UF",
    "Cultura",
    "Área (ha)",
    "Aeronave",
    "Produtos",
    "Leituras",
    "Fora dos parâmetros",
)


@dataclass
class PlanRow:
    """Uma linha da consolidação: um planejamento, como no talão."""

    id: uuid.UUID
    numero: int
    status: str
    data_aplicacao: date | None
    contratante: str
    contratante_documento: str
    propriedade: str
    municipio: str
    uf: str
    cultura: str
    area_ha: Decimal | None
    aeronave: str
    produtos: list[str] = field(default_factory=list)
    leituras: int = 0
    # Quantas leituras daquele planejamento romperam um limite planejado. É o número que
    # a empresa precisa ver antes de enviar o mês, não depois de ser autuada.
    violacoes: int = 0


@dataclass
class ProductTotal:
    produto: str
    total: Decimal


@dataclass
class MonthlyConsolidation:
    ano: int
    mes: int
    planos: list[PlanRow]
    area_total_ha: Decimal
    planos_com_violacao: int
    # Planejamento sem data não cabe em mês nenhum. Contado para não sumir da conferência.
    planos_sem_data: int
    totais_por_produto: list[ProductTotal]

    @property
    def quantidade(self) -> int:
        return len(self.planos)


async def monthly(session: AsyncSession, *, ano: int, mes: int) -> MonthlyConsolidation:
    """Monta o mês. O recorte é pela data da aplicação, que é a data do fato.

    Não filtra por empresa: quem filtra é a política de RLS, a partir do tenant amarrado
    à sessão — o mesmo caminho de todas as outras consultas do módulo.
    """
    rows = (
        await session.execute(
            select(OperationalPlan, Client, Property, Aircraft)
            .join(Client, Client.id == OperationalPlan.client_id)
            .join(Property, Property.id == OperationalPlan.property_id)
            .outerjoin(Aircraft, Aircraft.id == OperationalPlan.aircraft_id)
            .where(
                extract("year", OperationalPlan.data_aplicacao) == ano,
                extract("month", OperationalPlan.data_aplicacao) == mes,
            )
            .order_by(OperationalPlan.data_aplicacao, OperationalPlan.numero)
        )
    ).all()

    plan_ids = [plan.id for plan, _client, _prop, _aircraft in rows]
    products = await _products_by_plan(session, plan_ids)
    readings = await _readings_by_plan(session, plan_ids)

    planos = [
        PlanRow(
            id=plan.id,
            numero=plan.numero,
            status=plan.status.value,
            data_aplicacao=plan.data_aplicacao,
            contratante=client.nome,
            contratante_documento=client.cpf_cnpj,
            propriedade=prop.nome,
            municipio=prop.municipio,
            uf=prop.uf,
            cultura=_cultura(plan),
            area_ha=plan.area_ha,
            aeronave=aircraft.prefixo if aircraft else "",
            produtos=[name for name, _total in products.get(plan.id, [])],
            leituras=readings.get(plan.id, (0, 0))[0],
            violacoes=readings.get(plan.id, (0, 0))[1],
        )
        for plan, client, prop, aircraft in rows
    ]

    sem_data = await session.scalar(
        select(func.count())
        .select_from(OperationalPlan)
        .where(OperationalPlan.data_aplicacao.is_(None))
    )

    return MonthlyConsolidation(
        ano=ano,
        mes=mes,
        planos=planos,
        area_total_ha=sum((row.area_ha or Decimal(0) for row in planos), Decimal(0)),
        planos_com_violacao=sum(1 for row in planos if row.violacoes > 0),
        planos_sem_data=int(sem_data or 0),
        totais_por_produto=_product_totals(products, plan_ids),
    )


async def _products_by_plan(
    session: AsyncSession, plan_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[tuple[str, Decimal]]]:
    if not plan_ids:
        return {}

    rows = (
        await session.execute(
            select(PlanProduct.plan_id, Product.nome_comercial, PlanProduct.total_produto)
            .join(Product, Product.id == PlanProduct.product_id)
            .where(PlanProduct.plan_id.in_(plan_ids))
            .order_by(Product.nome_comercial)
        )
    ).all()

    by_plan: dict[uuid.UUID, list[tuple[str, Decimal]]] = {}
    for plan_id, nome, total in rows:
        by_plan.setdefault(plan_id, []).append((nome, total or Decimal(0)))
    return by_plan


async def _readings_by_plan(
    session: AsyncSession, plan_ids: list[uuid.UUID]
) -> dict[uuid.UUID, tuple[int, int]]:
    """Leituras e violações por planejamento, em uma consulta só."""
    if not plan_ids:
        return {}

    rows = (
        await session.execute(
            select(
                WeatherReading.plan_id,
                func.count(),
                func.count().filter(WeatherReading.violou_parametro),
            )
            .where(WeatherReading.plan_id.in_(plan_ids))
            .group_by(WeatherReading.plan_id)
        )
    ).all()
    return {plan_id: (int(total), int(breached)) for plan_id, total, breached in rows}


def _product_totals(
    products: dict[uuid.UUID, list[tuple[str, Decimal]]], plan_ids: list[uuid.UUID]
) -> list[ProductTotal]:
    """Quanto de cada produto saiu no mês.

    Soma ``total_produto`` das linhas, que é um valor digitado a partir do receituário —
    ver questão Q9. Linha sem total entra como zero, e não como estimativa: calcular o que
    falta mudaria um número de relatório sem que ninguém tivesse dito qual é a conta.
    """
    somas: dict[str, Decimal] = {}
    for plan_id in plan_ids:
        for nome, total in products.get(plan_id, []):
            somas[nome] = somas.get(nome, Decimal(0)) + total
    return [ProductTotal(produto=nome, total=somas[nome]) for nome in sorted(somas)]


def _cultura(plan: OperationalPlan) -> str:
    if plan.cultura is None:
        return ""
    if plan.cultura.value == "outras":
        return plan.cultura_outras_texto or "Outras"
    return plan.cultura.value.replace("_", " ").title()


def _number(value: Decimal | None) -> str:
    """Vírgula decimal: a planilha de destino está em português."""
    return "" if value is None else f"{value:.2f}".replace(".", ",")


def to_csv(consolidation: MonthlyConsolidation) -> bytes:
    """Serializa o mês para o CSV que a planilha abre."""
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, delimiter=CSV_DELIMITER, lineterminator="\r\n")
    writer.writerow(COLUMNS)

    for row in consolidation.planos:
        writer.writerow(
            [
                row.numero,
                row.status,
                row.data_aplicacao.strftime("%d/%m/%Y") if row.data_aplicacao else "",
                row.contratante,
                # Com máscara: sem ela o Excel lê catorze algarismos como número e
                # mostra o documento em notação científica.
                format_cpf_cnpj(row.contratante_documento),
                row.propriedade,
                row.municipio,
                row.uf,
                row.cultura,
                _number(row.area_ha),
                row.aeronave,
                " | ".join(row.produtos),
                row.leituras,
                row.violacoes,
            ]
        )

    return buffer.getvalue().encode(CSV_ENCODING)
