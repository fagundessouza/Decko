"""Consolidação mensal das aplicações.

Fecha a dor nº 6 do discovery: hoje o mês inteiro é retranscrito do talão para uma planilha
Excel à mão. Aqui o mês é montado a partir do que já foi registrado, e sai em CSV que o
Excel abre direto.

**São dois relatórios diferentes, e vale não confundi-los.**

``monthly`` é a conferência da empresa: uma linha por planejamento, com contratante,
documento, leituras e violações. Serve para o dono olhar o mês antes de prestar contas.

``monthly_report`` é o **relatório mensal do operador de ARP**, com o conteúdo que o art.
11 da Portaria MAPA 298/2021 exige: agregado por município/UF, aeronave e tipo de
atividade, com área aplicada, horas de execução e os produtos com volume e dosagem. É
entregue pelo SIPEAGRO até o dia 15 do mês seguinte. Nenhuma das colunas da conferência é
pedida ali, e nenhuma das do relatório estava na conferência — ver
``docs/discovery/agro-normas-mapa.md``.

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


# ------------------------------------------------------------------ relatório mensal


# As colunas são as do art. 11 da Portaria MAPA 298/2021, na ordem dos incisos. Não são
# escolha de layout: são o conteúdo exigido do relatório mensal do operador de ARP.
REPORT_COLUMNS = (
    "Município",
    "UF",
    "Aeronave (ARP)",
    "Tipo de atividade",
    "Área aplicada (ha)",
    "Horas de execução",
    "Produtos (marca, volume e dosagem)",
)

# O relatório presta contas do que foi feito. Rascunho é intenção, não atividade.
STATUS_REALIZADOS = ("concluido", "assinado", "enviado")


@dataclass
class ProductApplied:
    """Um produto dentro de um grupo do relatório."""

    marca_comercial: str
    # Soma de ``total_produto`` das aplicações do grupo.
    volume: Decimal
    # As dosagens por hectare usadas. Mais de uma quando o grupo reúne aplicações com
    # dose diferente — somar dose não faz sentido, e escolher uma esconderia a outra.
    dosagens: list[Decimal]

    def __str__(self) -> str:
        doses = ", ".join(f"{dose:.4f}".rstrip("0").rstrip(".") for dose in self.dosagens)
        return f"{self.marca_comercial} ({_number(self.volume)}; dose {doses or '—'}/ha)"


@dataclass
class MonthlyReportRow:
    """Uma linha do relatório mensal: município, aeronave e tipo de atividade."""

    municipio: str
    uf: str
    aeronave: str
    tipo_atividade: str
    area_ha: Decimal
    horas: Decimal
    produtos: list[ProductApplied]


@dataclass
class MonthlyReport:
    """O relatório mensal do operador de ARP, como o art. 11 da Portaria 298/2021 pede.

    Entregue ao MAPA pelo SIPEAGRO até o décimo quinto dia do mês seguinte — ver
    ``docs/discovery/agro-normas-mapa.md``.
    """

    ano: int
    mes: int
    linhas: list[MonthlyReportRow]
    area_total_ha: Decimal
    horas_totais: Decimal
    # Planejamentos do mês que ficaram em rascunho. Não entram no relatório, porque não
    # são atividade realizada — e aparecem aqui para não sumirem em silêncio.
    rascunhos_no_mes: int

    @property
    def prazo(self) -> date:
        """O dia 15 do mês seguinte, que é quando a entrega vence."""
        ano, mes = (self.ano + 1, 1) if self.mes == 12 else (self.ano, self.mes + 1)
        return date(ano, mes, 15)


async def monthly_report(session: AsyncSession, *, ano: int, mes: int) -> MonthlyReport:
    """Agrega o mês por município/UF, aeronave e tipo de atividade.

    A área é a **aplicada**: ``ha_aplicado`` quando preenchido, e a planejada como reserva.
    A norma pede o total aplicado, e confundir os dois num relatório de prestação de contas
    é o erro que ninguém percebe.
    """
    rows = (
        await session.execute(
            select(OperationalPlan, Property, Aircraft)
            .join(Property, Property.id == OperationalPlan.property_id)
            .outerjoin(Aircraft, Aircraft.id == OperationalPlan.aircraft_id)
            .where(
                extract("year", OperationalPlan.data_aplicacao) == ano,
                extract("month", OperationalPlan.data_aplicacao) == mes,
            )
            .order_by(Property.uf, Property.municipio, OperationalPlan.numero)
        )
    ).all()

    realizados = [
        (plan, prop, aircraft)
        for plan, prop, aircraft in rows
        if plan.status.value in STATUS_REALIZADOS
    ]
    detalhes = await _product_details(session, [plan.id for plan, _p, _a in realizados])

    grupos: dict[tuple[str, str, str, str], MonthlyReportRow] = {}
    for plan, prop, aircraft in realizados:
        chave = (prop.municipio, prop.uf, aircraft.prefixo if aircraft else "", _atividade(plan))
        linha = grupos.get(chave)
        if linha is None:
            linha = MonthlyReportRow(
                municipio=prop.municipio,
                uf=prop.uf,
                aeronave=chave[2],
                tipo_atividade=chave[3],
                area_ha=Decimal(0),
                horas=Decimal(0),
                produtos=[],
            )
            grupos[chave] = linha

        linha.area_ha += plan.ha_aplicado or plan.area_ha or Decimal(0)
        linha.horas += plan.tempo_servico or Decimal(0)
        _merge_products(linha, detalhes.get(plan.id, []))

    linhas = [grupos[chave] for chave in sorted(grupos)]
    return MonthlyReport(
        ano=ano,
        mes=mes,
        linhas=linhas,
        area_total_ha=sum((linha.area_ha for linha in linhas), Decimal(0)),
        horas_totais=sum((linha.horas for linha in linhas), Decimal(0)),
        rascunhos_no_mes=len(rows) - len(realizados),
    )


def _atividade(plan: OperationalPlan) -> str:
    """O tipo de atividade do inciso IV.

    O formulário permite marcar mais de um tipo na mesma aplicação. Quando isso acontece
    os tipos viram um rótulo só, e não linhas separadas: repartir a área entre eles exigiria
    uma proporção que ninguém informou, e repeti-la em cada linha somaria a mesma área duas
    vezes no total do mês.
    """
    if not plan.tipos_aplicacao:
        return ""
    return " + ".join(sorted(tipo.value for tipo in plan.tipos_aplicacao))


def _merge_products(
    linha: MonthlyReportRow, aplicados: list[tuple[str, Decimal, Decimal | None]]
) -> None:
    for marca, total, dosagem in aplicados:
        existente = next((p for p in linha.produtos if p.marca_comercial == marca), None)
        if existente is None:
            existente = ProductApplied(marca_comercial=marca, volume=Decimal(0), dosagens=[])
            linha.produtos.append(existente)
        existente.volume += total
        if dosagem is not None and dosagem not in existente.dosagens:
            existente.dosagens.append(dosagem)
            existente.dosagens.sort()


async def _product_details(
    session: AsyncSession, plan_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[tuple[str, Decimal, Decimal | None]]]:
    """Marca comercial, volume e dosagem de cada item — o inciso V, inteiro."""
    if not plan_ids:
        return {}

    rows = (
        await session.execute(
            select(
                PlanProduct.plan_id,
                Product.nome_comercial,
                PlanProduct.total_produto,
                PlanProduct.dosagem_ha,
            )
            .join(Product, Product.id == PlanProduct.product_id)
            .where(PlanProduct.plan_id.in_(plan_ids))
            .order_by(Product.nome_comercial)
        )
    ).all()

    por_plano: dict[uuid.UUID, list[tuple[str, Decimal, Decimal | None]]] = {}
    for plan_id, marca, total, dosagem in rows:
        por_plano.setdefault(plan_id, []).append((marca, total or Decimal(0), dosagem))
    return por_plano


def report_to_csv(report: MonthlyReport) -> bytes:
    """Serializa o relatório mensal para conferência antes de lançar no SIPEAGRO.

    O SIPEAGRO é um sistema web, com digitação; não há upload de arquivo documentado. Este
    CSV existe para a pessoa ter à mão exatamente os campos que a tela vai pedir, na ordem
    dos incisos — e não para ser importado em lugar nenhum.
    """
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, delimiter=CSV_DELIMITER, lineterminator="\r\n")
    writer.writerow(REPORT_COLUMNS)

    for linha in report.linhas:
        writer.writerow(
            [
                linha.municipio,
                linha.uf,
                linha.aeronave,
                linha.tipo_atividade,
                _number(linha.area_ha),
                _number(linha.horas),
                " | ".join(str(produto) for produto in linha.produtos),
            ]
        )

    return buffer.getvalue().encode(CSV_ENCODING)
