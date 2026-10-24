import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from decko.db import get_session
from decko_modules.comercial import service as comercial
from decko_modules.core.deps import CurrentPrincipal, require
from decko_modules.pdv import service
from decko_modules.pdv.models import StatusVenda, Venda
from decko_modules.pdv.schemas import (
    DescontoIn,
    ItemIn,
    ItemOut,
    PagamentoIn,
    PagamentoOut,
    VendaOut,
    VendaResumoOut,
)

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _invalido(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))


async def _carregar(session: AsyncSession, venda_id: uuid.UUID) -> Venda:
    venda = await session.scalar(
        select(Venda)
        .where(Venda.id == venda_id)
        .options(selectinload(Venda.itens), selectinload(Venda.pagamentos))
    )
    if venda is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venda não encontrada.")
    return venda


async def _ver(session: AsyncSession, venda: Venda) -> VendaOut:
    """Monta a venda com as contas feitas no servidor."""
    await session.refresh(venda, ["itens", "pagamentos"])

    soma = await service.soma_dos_itens(session, venda)
    total = await service.total_a_pagar(session, venda)
    pago = await service.total_pago(session, venda)

    return VendaOut(
        id=venda.id,
        numero=venda.numero,
        status=venda.status,
        aberta_em=venda.aberta_em,
        fechada_em=venda.fechada_em,
        observacao=venda.observacao,
        itens=[ItemOut.model_validate(item) for item in venda.itens],
        pagamentos=[PagamentoOut.model_validate(p) for p in venda.pagamentos],
        soma_dos_itens=soma,
        desconto=venda.desconto,
        total=total,
        falta=max(total - pago, Decimal(0)),
        pago=pago,
        troco=max(pago - total, Decimal(0)),
    )


@router.get("/vendas", response_model=list[VendaResumoOut])
async def listar_vendas(
    session: SessionDep,
    _: Annotated[object, Depends(require("pdv.venda.read"))],
    status_filtro: Annotated[StatusVenda | None, Query(alias="status")] = None,
    limite: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[Venda]:
    consulta = select(Venda).order_by(Venda.aberta_em.desc()).limit(limite)
    if status_filtro is not None:
        consulta = consulta.where(Venda.status == status_filtro)
    return list((await session.execute(consulta)).scalars().all())


@router.post("/vendas", response_model=VendaOut, status_code=status.HTTP_201_CREATED)
async def abrir_venda(
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("pdv.venda.write"))],
) -> VendaOut:
    venda = await service.abrir_venda(
        session, tenant_id=principal.tenant_id, operador_id=principal.user_id
    )
    return await _ver(session, venda)


@router.get("/vendas/{venda_id}", response_model=VendaOut)
async def ver_venda(
    venda_id: uuid.UUID,
    session: SessionDep,
    _: Annotated[object, Depends(require("pdv.venda.read"))],
) -> VendaOut:
    return await _ver(session, await _carregar(session, venda_id))


@router.post("/vendas/{venda_id}/itens", response_model=VendaOut)
async def adicionar_item(
    venda_id: uuid.UUID,
    payload: ItemIn,
    session: SessionDep,
    _: Annotated[object, Depends(require("pdv.venda.write"))],
) -> VendaOut:
    venda = await _carregar(session, venda_id)
    try:
        await service.adicionar_item(
            session,
            venda=venda,
            produto_id=payload.produto_id,
            quantidade=payload.quantidade,
            unidade_id=payload.unidade_id,
            lote_id=payload.lote_id,
            preco_unitario=payload.preco_unitario,
            desconto=payload.desconto,
        )
    except service.PdvError as exc:
        raise _invalido(exc) from exc
    return await _ver(session, venda)


@router.delete("/vendas/{venda_id}/itens/{item_id}", response_model=VendaOut)
async def remover_item(
    venda_id: uuid.UUID,
    item_id: uuid.UUID,
    session: SessionDep,
    _: Annotated[object, Depends(require("pdv.venda.write"))],
) -> VendaOut:
    venda = await _carregar(session, venda_id)
    try:
        await service.remover_item(session, venda=venda, item_id=item_id)
    except service.PdvError as exc:
        raise _invalido(exc) from exc
    return await _ver(session, venda)


@router.put("/vendas/{venda_id}/desconto", response_model=VendaOut)
async def definir_desconto(
    venda_id: uuid.UUID,
    payload: DescontoIn,
    session: SessionDep,
    _: Annotated[object, Depends(require("pdv.venda.write"))],
) -> VendaOut:
    venda = await _carregar(session, venda_id)
    try:
        await service.definir_desconto(session, venda=venda, desconto=payload.desconto)
    except service.PdvError as exc:
        raise _invalido(exc) from exc
    return await _ver(session, venda)


@router.post("/vendas/{venda_id}/pagamentos", response_model=VendaOut)
async def registrar_pagamento(
    venda_id: uuid.UUID,
    payload: PagamentoIn,
    session: SessionDep,
    _: Annotated[object, Depends(require("pdv.venda.write"))],
) -> VendaOut:
    venda = await _carregar(session, venda_id)
    try:
        await service.registrar_pagamento(
            session, venda=venda, forma=payload.forma, valor=payload.valor
        )
    except service.PdvError as exc:
        raise _invalido(exc) from exc
    return await _ver(session, venda)


@router.delete("/vendas/{venda_id}/pagamentos/{pagamento_id}", response_model=VendaOut)
async def remover_pagamento(
    venda_id: uuid.UUID,
    pagamento_id: uuid.UUID,
    session: SessionDep,
    _: Annotated[object, Depends(require("pdv.venda.write"))],
) -> VendaOut:
    venda = await _carregar(session, venda_id)
    try:
        await service.remover_pagamento(session, venda=venda, pagamento_id=pagamento_id)
    except service.PdvError as exc:
        raise _invalido(exc) from exc
    return await _ver(session, venda)


@router.post("/vendas/{venda_id}/finalizar", response_model=VendaOut)
async def finalizar_venda(
    venda_id: uuid.UUID,
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("pdv.venda.finalizar"))],
) -> VendaOut:
    """Fecha a venda e baixa o estoque na mesma transação."""
    venda = await _carregar(session, venda_id)
    try:
        await service.finalizar_venda(session, venda=venda, registrado_por=principal.user_id)
    except (service.PdvError, comercial.ComercialError) as exc:
        raise _invalido(exc) from exc
    return await _ver(session, venda)


@router.post("/vendas/{venda_id}/cancelar", response_model=VendaOut)
async def cancelar_venda(
    venda_id: uuid.UUID,
    session: SessionDep,
    _: Annotated[object, Depends(require("pdv.venda.cancelar"))],
) -> VendaOut:
    venda = await _carregar(session, venda_id)
    try:
        await service.cancelar_venda(session, venda=venda)
    except service.PdvError as exc:
        raise _invalido(exc) from exc
    return await _ver(session, venda)
