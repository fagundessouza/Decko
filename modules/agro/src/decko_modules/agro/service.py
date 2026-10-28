"""Regra de negócio do módulo agro. Não conhece HTTP."""

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from decko.documents import format_cpf_cnpj
from decko_modules.agro import croqui
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

    geometria = plan.croqui_geometria or {}
    # A seta do vento usa a primeira leitura que tenha direção: o croqui é um desenho da
    # aplicação, não de cada instante dela.
    vento = next(
        (r.direcao_vento_graus for r in readings if r.direcao_vento_graus is not None), None
    )

    return PlanDocument(
        croqui_limite=[tuple(ponto) for ponto in geometria.get("limite", [])],
        croqui_faixas=[[tuple(ponto) for ponto in faixa] for faixa in geometria.get("faixas", [])],
        croqui_vento_graus=vento,
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
                traco=[
                    [(float(x), float(y)) for x, y in linha]
                    for linha in (signature.traco or {}).get("linhas", [])
                ],
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
        direcao_vento_graus=reading.direcao_vento_graus,
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
    reading.direcao_vento_graus = observation.direcao_vento_graus
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


# ------------------------------------------------------------------ croqui


@dataclass(frozen=True)
class CroquiImportado:
    """O que foi lido do arquivo, com o que dele se deduz.

    ``area_sugerida_ha`` é sugestão: a área do documento é a declarada pelo agrônomo
    responsável, e um desenho não muda campo de documento legal — ver
    ``decko_modules.agro.croqui``.
    """

    faixas: int
    tem_limite: bool
    area_sugerida_ha: Decimal | None
    direcao_tiros_graus: Decimal | None
    latitude: Decimal | None
    longitude: Decimal | None


async def importar_croqui(
    session: AsyncSession, *, plan: OperationalPlan, conteudo: str | bytes, origem: str | None
) -> CroquiImportado:
    """Lê o KML do voo e guarda a geometria no planejamento.

    Não escreve área nem coordenada do planejamento: devolve o que deduziu para a tela
    mostrar ao lado do que está declarado, e quem decide é quem assina.
    """
    desenho = croqui.ler(conteudo, origem=origem)
    centro = desenho.centro()

    plan.croqui_geometria = {
        "limite": [list(ponto) for ponto in desenho.limite],
        "faixas": [[list(ponto) for ponto in faixa] for faixa in desenho.faixas],
        "origem": desenho.origem,
    }
    await session.flush()

    return CroquiImportado(
        faixas=len(desenho.faixas),
        tem_limite=bool(desenho.limite),
        area_sugerida_ha=desenho.area_ha(),
        direcao_tiros_graus=desenho.direcao_dos_tiros(),
        latitude=Decimal(str(round(centro[1], 6))) if centro else None,
        longitude=Decimal(str(round(centro[0], 6))) if centro else None,
    )


# ------------------------------------------------------------------ assinatura


class AssinaturaError(Exception):
    """Erro de regra da assinatura. Vira 422 na borda."""


# Quantos pontos uma assinatura pode ter. Um traço de dedo numa tela de celular fica na
# casa das centenas; o limite existe para um envio malformado não virar linha gigante no
# banco, não para apertar o desenho.
MAX_PONTOS = 4_000


def hash_do_documento(doc: PlanDocument) -> str:
    """A impressão digital do que foi assinado.

    Calculada sobre os dados do documento **sem as assinaturas** — senão cada assinatura
    mudaria o que a seguinte assina, e nenhuma delas poderia ser conferida depois.

    Serve a uma pergunta só, e é a que importa numa fiscalização: *este documento é o
    mesmo que a pessoa assinou?* Se alguém editar a área, o produto ou o clima depois da
    assinatura, o hash deixa de bater e o sistema diz isso.
    """
    conteudo = asdict(doc)
    conteudo.pop("assinaturas", None)
    canonico = json.dumps(_canonico(conteudo), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def _canonico(valor: object) -> object:
    """Deixa a estrutura serializável, com chave sempre em texto.

    O bloco meteorológico é indexado por ``(periodo, momento)``, e ``json.dumps`` não
    aceita tupla como chave — ``default=str`` resolve o valor, nunca a chave. Converter
    aqui, e de forma recursiva, é o que faz o hash funcionar para qualquer documento, e
    não só para os que não têm leitura.
    """
    if isinstance(valor, dict):
        return {str(chave): _canonico(item) for chave, item in valor.items()}
    if isinstance(valor, list | tuple):
        return [_canonico(item) for item in valor]
    if isinstance(valor, str | int | float | bool) or valor is None:
        return valor
    return str(valor)


def _validar_traco(traco: list[list[list[float]]]) -> dict[str, object]:
    """Confere o desenho e o guarda numa caixa de 0 a 1.

    Normalizado para a tela que assinou não entrar no documento: o mesmo traço feito num
    celular estreito e num tablet grande tem de imprimir igual.
    """
    if not traco or not any(linha for linha in traco):
        raise AssinaturaError("A assinatura está em branco.")

    pontos = sum(len(linha) for linha in traco)
    if pontos > MAX_PONTOS:
        raise AssinaturaError("A assinatura tem pontos demais; desenhe de novo.")

    limpo: list[list[list[float]]] = []
    for linha in traco:
        pontos_linha = [
            [round(min(max(float(x), 0.0), 1.0), 4), round(min(max(float(y), 0.0), 1.0), 4)]
            for ponto in linha
            if len(ponto) >= 2
            for x, y in [ponto[:2]]
        ]
        if len(pontos_linha) >= 2:
            limpo.append(pontos_linha)

    if not limpo:
        raise AssinaturaError("A assinatura está em branco.")
    return {"linhas": limpo}


async def assinar(
    session: AsyncSession,
    *,
    plan: OperationalPlan,
    papel: SignatureRole,
    nome: str,
    traco: list[list[list[float]]],
    registro: str | None = None,
    assinado_por: uuid.UUID | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> Signature:
    """Registra a assinatura de um papel do formulário.

    Assinar de novo o mesmo papel é recusado. Trocar uma assinatura em silêncio é o tipo
    de coisa que, num documento com efeito legal, ninguém descobre a tempo.
    """
    existente = await session.scalar(
        select(Signature).where(Signature.plan_id == plan.id, Signature.papel == papel)
    )
    if existente is not None and existente.assinado_em is not None:
        raise AssinaturaError(
            f"{SIGNATURE_TITLES[papel]} já assinou este planejamento em "
            f"{existente.assinado_em.strftime('%d/%m/%Y')}."
        )

    desenho = _validar_traco(traco)
    documento = await build_document(session, plan)

    assinatura = existente or Signature(tenant_id=plan.tenant_id, plan_id=plan.id, papel=papel)
    assinatura.nome = nome.strip()
    assinatura.registro = registro.strip() if registro else None
    assinatura.traco = desenho
    assinatura.documento_hash = hash_do_documento(documento)
    assinatura.assinado_em = datetime.now(UTC)
    assinatura.assinado_por = assinado_por
    assinatura.assinado_ip = ip
    assinatura.assinado_user_agent = (user_agent or "")[:300] or None

    session.add(assinatura)
    await session.flush()
    return assinatura


async def conferir_assinaturas(session: AsyncSession, plan: OperationalPlan) -> list[SignatureRole]:
    """Os papéis cuja assinatura não corresponde mais ao documento.

    Lista vazia é o caso bom. Nome na lista significa que o planejamento mudou depois de
    assinado — e quem for conferir precisa saber disso antes do fiscal.
    """
    atual = hash_do_documento(await build_document(session, plan))
    assinaturas = (
        (await session.execute(select(Signature).where(Signature.plan_id == plan.id)))
        .scalars()
        .all()
    )
    return [
        assinatura.papel
        for assinatura in assinaturas
        if assinatura.assinado_em is not None
        and assinatura.documento_hash is not None
        and assinatura.documento_hash != atual
    ]
