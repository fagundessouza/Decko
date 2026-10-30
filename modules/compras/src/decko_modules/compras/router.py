import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from decko.db import get_session
from decko_modules.compras import service
from decko_modules.compras.models import Nota, NotaItem, StatusNota
from decko_modules.compras.nfe import NotaInvalidaError
from decko_modules.compras.schemas import (
    CandidatoOut,
    ConfirmacaoOut,
    ItemConferidoOut,
    ItemOut,
    NotaOut,
    NotaResumoOut,
    NovoProdutoIn,
    VincularIn,
    XmlIn,
)
from decko_modules.core.deps import CurrentPrincipal, require

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _invalido(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))


async def _carregar(session: AsyncSession, nota_id: uuid.UUID) -> Nota:
    nota = await session.scalar(
        select(Nota).where(Nota.id == nota_id).options(selectinload(Nota.itens))
    )
    if nota is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nota não encontrada.")
    return nota


async def _item_de(session: AsyncSession, nota: Nota, item_id: uuid.UUID) -> NotaItem:
    item = await session.get(NotaItem, item_id)
    if item is None or item.nota_id != nota.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Item não encontrado nesta nota."
        )
    return item


async def _ver(session: AsyncSession, nota: Nota) -> NotaOut:
    """Monta a nota com os palpites de cada item pendente."""
    itens: list[ItemConferidoOut] = []
    for item in await service.itens_de(session, nota):
        sugestoes = await service.sugestoes_para(session, nota, item)
        itens.append(
            ItemConferidoOut(
                **ItemOut.model_validate(item).model_dump(),
                sugestoes=[
                    CandidatoOut(
                        produto_id=candidato.produto_id,
                        nome=candidato.nome,
                        origem=candidato.origem,
                        pontuacao=candidato.pontuacao,
                        automatico=candidato.automatico,
                    )
                    for candidato in sugestoes
                ],
            )
        )

    return NotaOut(
        **NotaResumoOut.model_validate(nota).model_dump(),
        itens=itens,
        pendentes=len(await service.pendentes(session, nota)),
    )


@router.get("/notas", response_model=list[NotaResumoOut])
async def listar_notas(
    session: SessionDep,
    _: Annotated[object, Depends(require("compras.nota.read"))],
    status_filtro: Annotated[StatusNota | None, Query(alias="status")] = None,
    limite: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[Nota]:
    consulta = select(Nota).order_by(Nota.created_at.desc()).limit(limite)
    if status_filtro is not None:
        consulta = consulta.where(Nota.status == status_filtro)
    return list((await session.execute(consulta)).scalars().all())


@router.post("/notas", response_model=NotaOut, status_code=status.HTTP_201_CREATED)
async def importar_nota(
    payload: XmlIn,
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("compras.nota.importar"))],
) -> NotaOut:
    """Lê o XML e deixa a nota em rascunho, com o que deu para reconhecer já ligado."""
    try:
        nota = await service.importar(session, tenant_id=principal.tenant_id, xml=payload.xml)
    except (NotaInvalidaError, service.ComprasError) as exc:
        raise _invalido(exc) from exc
    return await _ver(session, nota)


@router.get("/notas/{nota_id}", response_model=NotaOut)
async def ver_nota(
    nota_id: uuid.UUID,
    session: SessionDep,
    _: Annotated[object, Depends(require("compras.nota.read"))],
) -> NotaOut:
    return await _ver(session, await _carregar(session, nota_id))


@router.put("/notas/{nota_id}/itens/{item_id}/produto", response_model=NotaOut)
async def vincular_item(
    nota_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: VincularIn,
    session: SessionDep,
    _: Annotated[object, Depends(require("compras.nota.conferir"))],
) -> NotaOut:
    """Diz que este item da nota é aquele produto do cadastro."""
    nota = await _carregar(session, nota_id)
    item = await _item_de(session, nota, item_id)
    try:
        await service.vincular(
            session,
            nota=nota,
            item=item,
            produto_id=payload.produto_id,
            unidade_id=payload.unidade_id,
        )
    except service.ComprasError as exc:
        raise _invalido(exc) from exc
    return await _ver(session, nota)


@router.put("/notas/{nota_id}/itens/{item_id}/novo", response_model=NotaOut)
async def marcar_item_como_novo(
    nota_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: NovoProdutoIn,
    session: SessionDep,
    _: Annotated[object, Depends(require("compras.nota.conferir"))],
) -> NotaOut:
    """Diz que este item ainda não existe e deve virar produto novo."""
    nota = await _carregar(session, nota_id)
    item = await _item_de(session, nota, item_id)
    try:
        await service.marcar_como_novo(session, nota=nota, item=item, unidade_id=payload.unidade_id)
    except service.ComprasError as exc:
        raise _invalido(exc) from exc
    return await _ver(session, nota)


@router.post("/notas/{nota_id}/confirmar", response_model=ConfirmacaoOut)
async def confirmar_nota(
    nota_id: uuid.UUID,
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("compras.nota.confirmar"))],
) -> ConfirmacaoOut:
    """Cria o que falta, lança o estoque e guarda as equivalências. Tudo junto."""
    nota = await _carregar(session, nota_id)
    try:
        resultado = await service.confirmar(
            session,
            nota=nota,
            tenant_id=principal.tenant_id,
            confirmada_por=principal.user_id,
        )
    except service.ComprasError as exc:
        raise _invalido(exc) from exc

    return ConfirmacaoOut(
        nota=NotaResumoOut.model_validate(resultado.nota),
        produtos_criados=resultado.produtos_criados,
        itens_lancados=resultado.itens_lancados,
    )


@router.post("/notas/{nota_id}/descartar", response_model=NotaResumoOut)
async def descartar_nota(
    nota_id: uuid.UUID,
    session: SessionDep,
    _: Annotated[object, Depends(require("compras.nota.conferir"))],
) -> Nota:
    nota = await _carregar(session, nota_id)
    try:
        return await service.descartar(session, nota=nota)
    except service.ComprasError as exc:
        raise _invalido(exc) from exc
