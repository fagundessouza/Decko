import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from decko.db import get_session
from decko_modules.core.deps import CurrentPrincipal, require
from decko_modules.custos import service
from decko_modules.custos.schemas import ConsumoIn, ConsumoOut, CustoDoCentroOut

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _invalido(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))


@router.get("/consumos", response_model=list[ConsumoOut])
async def listar_consumos(
    session: SessionDep,
    _: Annotated[object, Depends(require("custos.consumo.read"))],
    de: Annotated[date | None, Query()] = None,
    ate: Annotated[date | None, Query()] = None,
    centro_custo_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[ConsumoOut]:
    linhas = await service.listar(session, de=de, ate=ate, centro_custo_id=centro_custo_id)
    return [
        ConsumoOut(
            id=linha.id,
            centro_custo_id=linha.centro_custo_id,
            centro_nome=linha.centro_nome,
            produto_nome=linha.produto_nome,
            quantidade=linha.quantidade,
            valor=linha.valor,
            custo_unitario=linha.custo_unitario,
            ocorrido_em=linha.ocorrido_em,
            observacao=linha.observacao,
        )
        for linha in linhas
    ]


@router.get("/por-centro", response_model=list[CustoDoCentroOut])
async def custo_por_centro(
    session: SessionDep,
    _: Annotated[object, Depends(require("custos.consumo.read"))],
    de: Annotated[date, Query()],
    ate: Annotated[date, Query()],
) -> list[CustoDoCentroOut]:
    """Consumo de estoque mais despesa, por centro. Maior custo primeiro."""
    return [
        CustoDoCentroOut(
            centro_id=linha.centro_id,
            nome=linha.nome,
            consumo=linha.consumo,
            despesa=linha.despesa,
            total=linha.total,
        )
        for linha in await service.custo_por_centro(session, de=de, ate=ate)
    ]


@router.post("/consumos", response_model=ConsumoOut, status_code=status.HTTP_201_CREATED)
async def registrar_consumo(
    payload: ConsumoIn,
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("custos.consumo.write"))],
) -> ConsumoOut:
    """Dá saída no estoque e anota contra qual centro aquilo foi."""
    try:
        consumo = await service.registrar(
            session,
            tenant_id=principal.tenant_id,
            produto_id=payload.produto_id,
            centro_custo_id=payload.centro_custo_id,
            quantidade=payload.quantidade,
            unidade_id=payload.unidade_id,
            lote_id=payload.lote_id,
            valor=payload.valor,
            documento=payload.documento,
            observacao=payload.observacao,
            ocorrido_em=payload.ocorrido_em,
            registrado_por=principal.user_id,
        )
    except service.CustosError as exc:
        raise _invalido(exc) from exc

    # Relê pela mesma consulta da lista, para a resposta trazer nome do produto e do
    # centro sem o cliente precisar de uma segunda chamada.
    linha = next(linha for linha in await service.listar(session) if linha.id == consumo.id)
    return ConsumoOut(
        id=linha.id,
        centro_custo_id=linha.centro_custo_id,
        centro_nome=linha.centro_nome,
        produto_nome=linha.produto_nome,
        quantidade=linha.quantidade,
        valor=linha.valor,
        custo_unitario=linha.custo_unitario,
        ocorrido_em=linha.ocorrido_em,
        observacao=linha.observacao,
    )
