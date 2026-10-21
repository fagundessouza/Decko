"""Regra de negócio do módulo agro. Não conhece HTTP."""

import uuid
from datetime import UTC, date, datetime, time
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from decko.documents import format_cpf_cnpj
from decko_modules.agro.enums import (
    Cultura,
    MaintenanceMoment,
    Momento,
    Periodo,
    SignatureRole,
    WeatherSource,
)
from decko_modules.agro.models import (
    Aircraft,
    Client,
    MaintenanceLog,
    OperationalPlan,
    PlanProduct,
    Prescription,
    Product,
    Property,
    Signature,
    WeatherReading,
)
from decko_modules.agro.pdf import (
    PlanDocument,
    ProductLine,
    SignatureLine,
    WeatherBlock,
    WeatherCell,
)
from decko_modules.agro.weather import (
    Observation,
    ParameterLimits,
    WeatherProvider,
    evaluate,
)
from decko_modules.core.models import Tenant


class PlanError(Exception):
    pass


SIGNATURE_TITLES = {
    SignatureRole.ENG_AGRONOMO: "Eng. Agrônomo",
    SignatureRole.PILOTO_AGRICOLA: "Piloto Agrícola",
    SignatureRole.TEC_AGRICOLA_EXECUTOR: "Téc. Agrícola Executor",
    SignatureRole.PROPRIETARIO_PREPOSTO: "Proprietário ou Preposto",
}

SIGNATURE_LABELS = {
    SignatureRole.ENG_AGRONOMO: "Nome / Assinatura / CREA",
    SignatureRole.PILOTO_AGRICOLA: "Nome / Assinatura / CANAC",
    SignatureRole.TEC_AGRICOLA_EXECUTOR: "Nome / Assinatura / CREA",
    SignatureRole.PROPRIETARIO_PREPOSTO: "Nome completo / Assinatura",
}


async def build_document(session: AsyncSession, plan: OperationalPlan) -> PlanDocument:
    """Reúne tudo o que o documento imprime.

    A montagem acontece aqui e não no gerador de PDF para que o gerador permaneça uma
    função de dados para bytes, testável sem banco.
    """
    tenant = await session.get(Tenant, plan.tenant_id)
    client = await session.get(Client, plan.client_id)
    prop = await session.get(Property, plan.property_id)
    aircraft = await session.get(Aircraft, plan.aircraft_id) if plan.aircraft_id else None
    prescription = (
        await session.get(Prescription, plan.prescription_id) if plan.prescription_id else None
    )

    items = (
        await session.execute(
            select(PlanProduct, Product)
            .join(Product, Product.id == PlanProduct.product_id)
            .where(PlanProduct.plan_id == plan.id)
        )
    ).all()
    readings = (
        (
            await session.execute(
                select(WeatherReading)
                .where(WeatherReading.plan_id == plan.id)
                .order_by(WeatherReading.data)
            )
        )
        .scalars()
        .all()
    )
    logs = (
        (await session.execute(select(MaintenanceLog).where(MaintenanceLog.plan_id == plan.id)))
        .scalars()
        .all()
    )
    signatures = (
        (await session.execute(select(Signature).where(Signature.plan_id == plan.id)))
        .scalars()
        .all()
    )

    blocks: dict[date, WeatherBlock] = {}
    alerts: list[str] = []
    for reading in readings:
        block = blocks.setdefault(reading.data, WeatherBlock(data=reading.data))
        block.cells[(reading.periodo, reading.momento)] = WeatherCell(
            hora=reading.hora.strftime("%H:%M") if reading.hora else "",
            temperatura=_decimal_text(reading.temperatura_c),
            umidade=_decimal_text(reading.umidade_relativa_pct),
            vento=_decimal_text(reading.velocidade_vento_kmh),
        )
        if reading.violou_parametro:
            alerts.extend(evaluate(_observation_of(reading), limits_of(plan)))

    maintenance = {log.momento: log for log in logs}

    return PlanDocument(
        numero=plan.numero,
        empresa_nome=tenant.name if tenant else "",
        # O cabeçalho do formulário identifica a empresa aplicadora: registro no MAPA,
        # conselho e inscrições. Antes nada disto era preenchido e o bloco saía em branco.
        empresa_cnpj=format_cpf_cnpj(tenant.cnpj) if tenant and tenant.cnpj else "",
        registro_mapa=tenant.registro_mapa or "" if tenant else "",
        crea=tenant.crea or "" if tenant else "",
        cda=tenant.cda or "" if tenant else "",
        inscricao_estadual=tenant.inscricao_estadual or "" if tenant else "",
        inscricao_municipal=tenant.inscricao_municipal or "" if tenant else "",
        rodape=tenant.rodape or "" if tenant else "",
        contratante=client.nome if client else "",
        contratante_documento=format_cpf_cnpj(client.cpf_cnpj) if client else "",
        propriedade=prop.nome if prop else "",
        municipio=prop.municipio if prop else "",
        uf=prop.uf if prop else "",
        latitude=plan.latitude or (prop.latitude if prop else None),
        longitude=plan.longitude or (prop.longitude if prop else None),
        cotacao=plan.cotacao or "",
        cultura=_cultura_text(plan),
        tipos_aplicacao=_tipos_text(plan),
        area_ha=plan.area_ha,
        produtos=[
            ProductLine(
                produto=product.nome_comercial,
                formulacao=item.formulacao or product.formulacao or "",
                classe_toxicologica=item.classe_toxicologica or product.classe_toxicologica or "",
                dosagem_ha=item.dosagem_ha,
                volume_ha=item.volume_ha,
                total_produto=item.total_produto,
                adjuvante=item.adjuvante or "",
            )
            for item, product in items
        ],
        receituario_numero=prescription.numero if prescription else "",
        receituario_emitido_em=prescription.emitido_em if prescription else None,
        equipamento_tipo=plan.equipamento_tipo.value if plan.equipamento_tipo else "",
        equipamento_modelo=plan.equipamento_modelo or "",
        equipamento_bico_tipo=plan.equipamento_bico_tipo or "",
        equipamento_bico_angulo=plan.equipamento_bico_angulo or "",
        temperatura_maxima=plan.param_temperatura_maxima_c,
        umidade_minima=plan.param_umidade_relativa_min_pct,
        largura_faixa=plan.param_largura_faixa_m,
        altura_voo=plan.param_altura_voo_m,
        velocidade_vento_max=plan.param_velocidade_vento_max_kmh,
        aeronave_prefixo=aircraft.prefixo if aircraft else "",
        manutencao_inicial=_maintenance_values(maintenance.get(MaintenanceMoment.INICIAL)),
        manutencao_final=_maintenance_values(maintenance.get(MaintenanceMoment.FINAL)),
        tempo_servico=plan.tempo_servico,
        ha_aplicado=plan.ha_aplicado,
        emitiu_dgps=plan.emitiu_relatorio_dgps,
        termo_higrometro=plan.termo_higrometro_utilizado or "",
        blocos_meteorologicos=[blocks[key] for key in sorted(blocks)],
        observacoes=plan.observacoes or "",
        alertas=alerts,
        assinaturas=[
            SignatureLine(
                titulo=SIGNATURE_TITLES[signature.papel],
                rotulo=SIGNATURE_LABELS[signature.papel],
                nome=signature.nome,
                registro=signature.registro or "",
            )
            for signature in signatures
        ],
    )


def _decimal_text(value: Decimal | None) -> str:
    return "" if value is None else f"{value:.1f}".replace(".", ",")


def _cultura_text(plan: OperationalPlan) -> str:
    if plan.cultura is None:
        return ""
    if plan.cultura is Cultura.OUTRAS:
        return plan.cultura_outras_texto or "Outras"
    return plan.cultura.value.replace("_", " ").title()


def _tipos_text(plan: OperationalPlan) -> str:
    tipos = [tipo.value.title() for tipo in plan.tipos_aplicacao or []]
    if plan.tipo_outros_texto:
        tipos.append(plan.tipo_outros_texto)
    return ", ".join(tipos)


def _maintenance_values(log: MaintenanceLog | None) -> dict[str, Decimal | None]:
    if log is None:
        return {}
    return {
        "voo": log.voo,
        "translado_ida": log.translado_ida,
        "operacao": log.operacao,
        "translado_volta": log.translado_volta,
        "total": log.total,
    }


def _observation_of(reading: WeatherReading) -> Observation:
    return Observation(
        temperatura_c=reading.temperatura_c,
        umidade_relativa_pct=reading.umidade_relativa_pct,
        velocidade_vento_kmh=reading.velocidade_vento_kmh,
        observed_at=reading.captured_at or datetime.now(UTC),
        provider=reading.provider or "",
        payload={},
    )


async def add_plan_product(
    session: AsyncSession,
    *,
    plan: OperationalPlan,
    product_id: uuid.UUID,
    dosagem_ha: Decimal | None = None,
    volume_ha: Decimal | None = None,
    total_produto: Decimal | None = None,
    adjuvante: str | None = None,
) -> PlanProduct:
    """Acrescenta uma linha à tabela de produtos do planejamento.

    ``formulacao`` e ``classe_toxicologica`` são copiadas do cadastro aqui, e não lidas na
    emissão: corrigir o cadastro depois não pode mudar o conteúdo de um documento já
    emitido. É o mesmo motivo pelo qual a linha guarda os valores em vez de referenciá-los.

    O produto é buscado antes da inserção porque a consulta roda sob Row Level Security:
    um identificador de outra empresa simplesmente não existe nesta sessão, e a resposta
    é "não encontrado" em vez de um erro de chave estrangeira.
    """
    product = await session.get(Product, product_id)
    if product is None:
        raise PlanError("Produto não encontrado.")

    item = PlanProduct(
        tenant_id=plan.tenant_id,
        plan_id=plan.id,
        product_id=product.id,
        formulacao=product.formulacao,
        classe_toxicologica=product.classe_toxicologica,
        dosagem_ha=dosagem_ha,
        volume_ha=volume_ha,
        total_produto=total_produto,
        adjuvante=adjuvante,
    )
    session.add(item)
    await session.flush()
    return item


async def link_prescription(
    session: AsyncSession, *, plan: OperationalPlan, prescription_id: uuid.UUID | None
) -> None:
    """Amarra o receituário ao planejamento, validando que ele existe nesta empresa."""
    if prescription_id is not None and await session.get(Prescription, prescription_id) is None:
        raise PlanError("Receituário não encontrado.")
    plan.prescription_id = prescription_id


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
