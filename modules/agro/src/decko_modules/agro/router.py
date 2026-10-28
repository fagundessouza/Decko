import uuid
from base64 import b64decode
from binascii import Error as BinasciiError
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from decko.db import get_session
from decko_modules.agro import consolidation, croqui, pdf, service
from decko_modules.agro.models import (
    Aircraft,
    Client,
    OperationalPlan,
    Pilot,
    PlanProduct,
    Prescription,
    Product,
    Property,
    WeatherReading,
)
from decko_modules.agro.schemas import (
    AircraftIn,
    AircraftOut,
    ClientIn,
    ClientOut,
    ConsolidationOut,
    CroquiIn,
    CroquiOut,
    MonthlyReportOut,
    MonthlyReportRowOut,
    PilotIn,
    PilotOut,
    PlanIn,
    PlanOut,
    PlanPrescriptionIn,
    PlanProductIn,
    PlanProductOut,
    PrescriptionIn,
    PrescriptionOut,
    ProductIn,
    ProductOut,
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
            detail="Contratante, propriedade, aeronave ou receituário não encontrados.",
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
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
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


@router.get("/pilots", response_model=list[PilotOut])
async def list_pilots(
    session: SessionDep,
    _: Annotated[object, Depends(require("agro.pilot.read"))],
) -> list[Pilot]:
    """Os pilotos da empresa.

    Pedido do Nathan: antes o nome do piloto só existia como texto dentro da assinatura,
    redigitado a cada documento.
    """
    result = await session.execute(select(Pilot).order_by(Pilot.nome))
    return list(result.scalars().all())


@router.post("/pilots", response_model=PilotOut, status_code=status.HTTP_201_CREATED)
async def create_pilot(
    payload: PilotIn,
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("agro.pilot.write"))],
) -> Pilot:
    pilot = Pilot(tenant_id=principal.tenant_id, **payload.model_dump())
    session.add(pilot)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe um piloto com este código ANAC.",
        ) from exc
    return pilot


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


@router.get("/products", response_model=list[ProductOut])
async def list_products(
    session: SessionDep,
    _: Annotated[object, Depends(require("agro.product.read"))],
) -> list[Product]:
    result = await session.execute(select(Product).order_by(Product.nome_comercial))
    return list(result.scalars().all())


@router.post("/products", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductIn,
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("agro.product.write"))],
) -> Product:
    product = Product(tenant_id=principal.tenant_id, **payload.model_dump())
    session.add(product)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe um produto com este nome comercial.",
        ) from exc
    return product


@router.get("/prescriptions", response_model=list[PrescriptionOut])
async def list_prescriptions(
    session: SessionDep,
    _: Annotated[object, Depends(require("agro.prescription.read"))],
) -> list[Prescription]:
    # Mais recente primeiro: é o receituário que está em uso na aplicação de hoje.
    result = await session.execute(select(Prescription).order_by(Prescription.emitido_em.desc()))
    return list(result.scalars().all())


@router.post("/prescriptions", response_model=PrescriptionOut, status_code=status.HTTP_201_CREATED)
async def create_prescription(
    payload: PrescriptionIn,
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("agro.prescription.write"))],
) -> Prescription:
    prescription = Prescription(tenant_id=principal.tenant_id, **payload.model_dump())
    session.add(prescription)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe um receituário com este número.",
        ) from exc
    return prescription


async def _plan_or_404(session: AsyncSession, plan_id: uuid.UUID) -> OperationalPlan:
    plan = await session.get(OperationalPlan, plan_id)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Planejamento não encontrado."
        )
    return plan


@router.post("/plans/{plan_id}/croqui", response_model=CroquiOut)
async def import_croqui(
    plan_id: uuid.UUID,
    payload: CroquiIn,
    session: SessionDep,
    _: Annotated[object, Depends(require("agro.plan.write"))],
) -> CroquiOut:
    """Lê o KML exportado pelo aplicativo do drone e guarda a geometria do croqui.

    Não altera a área nem a coordenada do planejamento: devolve o que deduziu para a tela
    mostrar ao lado do que está declarado — ver docs/discovery/agro-normas-mapa.md.
    """
    plan = await _plan_or_404(session, plan_id)

    conteudo: str | bytes = payload.kml
    if payload.base64:
        try:
            conteudo = b64decode(payload.kml, validate=True)
        except BinasciiError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="O arquivo chegou corrompido. Tente enviar de novo.",
            ) from exc

    try:
        lido = await service.importar_croqui(
            session, plan=plan, conteudo=conteudo, origem=payload.origem
        )
    except croqui.CroquiInvalidoError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc

    return CroquiOut(
        faixas=lido.faixas,
        tem_limite=lido.tem_limite,
        area_sugerida_ha=lido.area_sugerida_ha,
        direcao_tiros_graus=lido.direcao_tiros_graus,
        latitude=lido.latitude,
        longitude=lido.longitude,
    )


@router.get("/plans/{plan_id}/products", response_model=list[PlanProductOut])
async def list_plan_products(
    plan_id: uuid.UUID,
    session: SessionDep,
    _: Annotated[object, Depends(require("agro.plan.read"))],
) -> list[PlanProduct]:
    result = await session.execute(
        select(PlanProduct).where(PlanProduct.plan_id == plan_id).order_by(PlanProduct.id)
    )
    return list(result.scalars().all())


@router.post(
    "/plans/{plan_id}/products",
    response_model=PlanProductOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_plan_product(
    plan_id: uuid.UUID,
    payload: PlanProductIn,
    session: SessionDep,
    _: Annotated[object, Depends(require("agro.plan.write"))],
) -> PlanProduct:
    """Acrescenta uma linha à tabela de produtos, que é o que o receituário determina."""
    plan = await _plan_or_404(session, plan_id)
    try:
        return await service.add_plan_product(session, plan=plan, **payload.model_dump())
    except service.PlanError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


@router.delete("/plans/{plan_id}/products/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_plan_product(
    plan_id: uuid.UUID,
    item_id: uuid.UUID,
    session: SessionDep,
    _: Annotated[object, Depends(require("agro.plan.write"))],
) -> None:
    item = await session.get(PlanProduct, item_id)
    # A conferência do plano evita que um identificador de linha de outro planejamento
    # apague a linha errada por engano de digitação.
    if item is None or item.plan_id != plan_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Linha de produto não encontrada."
        )
    await session.delete(item)
    await session.flush()


@router.put("/plans/{plan_id}/prescription", response_model=PlanOut)
async def set_plan_prescription(
    plan_id: uuid.UUID,
    payload: PlanPrescriptionIn,
    session: SessionDep,
    _: Annotated[object, Depends(require("agro.plan.write"))],
) -> OperationalPlan:
    """Amarra o receituário ao planejamento depois que ele foi criado.

    O planejamento nasce em campo, muitas vezes antes de o receituário estar digitalizado;
    exigi-lo na criação travaria o preenchimento no momento em que ele precisa ser rápido.
    """
    plan = await _plan_or_404(session, plan_id)
    try:
        await service.link_prescription(session, plan=plan, prescription_id=payload.prescription_id)
    except service.PlanError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    await session.flush()
    return plan


# Recorte do mês. O limite inferior evita que um erro de digitação no ano produza uma
# varredura inútil; o superior não existe, porque data futura é planejamento legítimo.
ANO_MINIMO = 2000


@router.get("/consolidation/{ano}/{mes}", response_model=ConsolidationOut)
async def read_consolidation(
    ano: int,
    mes: int,
    session: SessionDep,
    _: Annotated[object, Depends(require("agro.plan.read"))],
) -> consolidation.MonthlyConsolidation:
    """Fecha o mês: o que foi aplicado, onde, com o quê, e o que saiu do planejado."""
    _check_month(ano, mes)
    return await consolidation.monthly(session, ano=ano, mes=mes)


# Sufixo em segmento próprio, como em /plans/{id}/pdf: um ".csv" colado ao mês seria
# lido como parte dele, e o pedido morreria antes de chegar aqui.
@router.get("/consolidation/{ano}/{mes}/csv", response_class=Response)
async def export_consolidation(
    ano: int,
    mes: int,
    session: SessionDep,
    _: Annotated[object, Depends(require("agro.plan.export"))],
) -> Response:
    """O mês em CSV, para conferência da própria empresa.

    Não é o relatório do MAPA: esse é o ``/monthly-report``, com o conteúdo que a Portaria
    298/2021 exige.
    """
    _check_month(ano, mes)
    month = await consolidation.monthly(session, ano=ano, mes=mes)
    return Response(
        content=consolidation.to_csv(month),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="consolidacao-{ano}-{mes:02d}.csv"'},
    )


@router.get("/monthly-report/{ano}/{mes}", response_model=MonthlyReportOut)
async def read_monthly_report(
    ano: int,
    mes: int,
    session: SessionDep,
    _: Annotated[object, Depends(require("agro.plan.read"))],
) -> MonthlyReportOut:
    """O relatório mensal do operador de ARP, como a Portaria MAPA 298/2021 pede.

    Agregado por município/UF, aeronave e tipo de atividade, com área aplicada, horas de
    execução e os produtos com volume e dosagem. Entregue pelo SIPEAGRO até o dia 15 do
    mês seguinte — ver docs/discovery/agro-normas-mapa.md.
    """
    _check_month(ano, mes)
    report = await consolidation.monthly_report(session, ano=ano, mes=mes)
    return MonthlyReportOut(
        ano=report.ano,
        mes=report.mes,
        linhas=[
            MonthlyReportRowOut(
                municipio=linha.municipio,
                uf=linha.uf,
                aeronave=linha.aeronave,
                tipo_atividade=linha.tipo_atividade,
                area_ha=linha.area_ha,
                horas=linha.horas,
                produtos=[str(produto) for produto in linha.produtos],
            )
            for linha in report.linhas
        ],
        area_total_ha=report.area_total_ha,
        horas_totais=report.horas_totais,
        rascunhos_no_mes=report.rascunhos_no_mes,
        prazo=report.prazo,
    )


@router.get("/monthly-report/{ano}/{mes}/csv", response_class=Response)
async def export_monthly_report(
    ano: int,
    mes: int,
    session: SessionDep,
    _: Annotated[object, Depends(require("agro.plan.export"))],
) -> Response:
    """O relatório mensal em CSV, na ordem dos incisos, para digitar no SIPEAGRO."""
    _check_month(ano, mes)
    report = await consolidation.monthly_report(session, ano=ano, mes=mes)
    return Response(
        content=consolidation.report_to_csv(report),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="relatorio-mensal-mapa-{ano}-{mes:02d}.csv"'
            )
        },
    )


def _check_month(ano: int, mes: int) -> None:
    if not 1 <= mes <= 12:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Mês deve estar entre 1 e 12.",
        )
    if ano < ANO_MINIMO:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Ano deve ser {ANO_MINIMO} ou posterior.",
        )
