import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from decko.db import get_session
from decko.fiscal import NCM_LENGTH, strip_mask
from decko_modules.comercial import service
from decko_modules.comercial.models import Categoria, Lote, Movimento, Produto, Unidade
from decko_modules.comercial.schemas import (
    CategoriaIn,
    CategoriaOut,
    LoteIn,
    LoteOut,
    MovimentoIn,
    MovimentoOut,
    ProdutoIn,
    ProdutoOut,
    SaldoLoteOut,
    SaldoOut,
    UnidadeIn,
    UnidadeOut,
)
from decko_modules.core.deps import CurrentPrincipal, require

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _conflito(detalhe: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detalhe)


def _invalido(exc: service.ComercialError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))


# ---------------------------------------------------------------- unidades


@router.get("/unidades", response_model=list[UnidadeOut])
async def listar_unidades(
    session: SessionDep,
    _: Annotated[object, Depends(require("comercial.unidade.read"))],
) -> list[Unidade]:
    result = await session.execute(select(Unidade).order_by(Unidade.fator, Unidade.nome))
    return list(result.scalars().all())


@router.post("/unidades", response_model=UnidadeOut, status_code=status.HTTP_201_CREATED)
async def criar_unidade(
    payload: UnidadeIn,
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("comercial.unidade.write"))],
) -> Unidade:
    try:
        return await service.criar_unidade(
            session,
            tenant_id=principal.tenant_id,
            nome=payload.nome,
            simbolo=payload.simbolo,
            referencia_id=payload.referencia_id,
            fator_relativo=payload.fator_relativo,
        )
    except service.ComercialError as exc:
        raise _invalido(exc) from exc
    except IntegrityError as exc:
        raise _conflito("Já existe uma unidade com esse nome.") from exc


# ---------------------------------------------------------------- categorias


@router.get("/categorias", response_model=list[CategoriaOut])
async def listar_categorias(
    session: SessionDep,
    _: Annotated[object, Depends(require("comercial.categoria.read"))],
) -> list[Categoria]:
    result = await session.execute(select(Categoria).order_by(Categoria.nome))
    return list(result.scalars().all())


@router.post("/categorias", response_model=CategoriaOut, status_code=status.HTTP_201_CREATED)
async def criar_categoria(
    payload: CategoriaIn,
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("comercial.categoria.write"))],
) -> Categoria:
    categoria = Categoria(tenant_id=principal.tenant_id, **payload.model_dump())
    session.add(categoria)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise _conflito("Já existe uma categoria com esse nome sob o mesmo pai.") from exc
    return categoria


# ---------------------------------------------------------------- produtos


@router.get("/produtos", response_model=list[ProdutoOut])
async def listar_produtos(
    session: SessionDep,
    _: Annotated[object, Depends(require("comercial.produto.read"))],
    busca: Annotated[str | None, Query(max_length=120)] = None,
    limite: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[Produto]:
    """Lista produtos, filtrando por código, código de barras, NCM ou nome.

    A busca acontece no banco e não na tela porque o caixa de um supermercado tem dezenas
    de milhares de produtos, e baixar o catálogo inteiro a cada abertura de venda é o tipo
    de peso que o projeto trata como defeito.
    """
    consulta = select(Produto).order_by(Produto.nome).limit(limite)

    if busca:
        termo = busca.strip()
        # "O que vocês têm no NCM 8544.42.00?" é pergunta de comprador de licitação, e
        # chega com máscara. O campo guarda só os dígitos.
        digitos = strip_mask(termo)
        criterios = [
            # Código e código de barras são exatos: o leitor não erra, e casar por
            # aproximação traria o produto errado para a frente do cliente.
            Produto.codigo == termo,
            Produto.gtin == termo,
            Produto.nome.ilike(f"%{termo}%"),
        ]
        if len(digitos) == NCM_LENGTH:
            criterios.append(Produto.ncm == digitos)

        consulta = consulta.where(or_(*criterios))

    result = await session.execute(consulta)
    return list(result.scalars().all())


@router.post("/produtos", response_model=ProdutoOut, status_code=status.HTTP_201_CREATED)
async def criar_produto(
    payload: ProdutoIn,
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("comercial.produto.write"))],
) -> Produto:
    produto = Produto(tenant_id=principal.tenant_id, **payload.model_dump())
    session.add(produto)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise _conflito("Já existe produto com esse código ou código de barras.") from exc
    return produto


# ---------------------------------------------------------------- lotes


@router.get("/lotes", response_model=list[LoteOut])
async def listar_lotes(
    session: SessionDep,
    _: Annotated[object, Depends(require("comercial.lote.read"))],
    produto_id: uuid.UUID | None = None,
) -> list[Lote]:
    consulta = select(Lote).order_by(Lote.validade.nulls_last(), Lote.codigo)
    if produto_id is not None:
        consulta = consulta.where(Lote.produto_id == produto_id)
    result = await session.execute(consulta)
    return list(result.scalars().all())


@router.post("/lotes", response_model=LoteOut, status_code=status.HTTP_201_CREATED)
async def criar_lote(
    payload: LoteIn,
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("comercial.lote.write"))],
) -> Lote:
    lote = Lote(tenant_id=principal.tenant_id, **payload.model_dump())
    session.add(lote)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise _conflito("Já existe esse lote para o produto.") from exc
    return lote


# ---------------------------------------------------------------- estoque


@router.post("/movimentos", response_model=MovimentoOut, status_code=status.HTTP_201_CREATED)
async def registrar_movimento(
    payload: MovimentoIn,
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("comercial.estoque.movimentar"))],
) -> Movimento:
    """Lança na razão de estoque. Não existe edição: correção é um lançamento de ajuste."""
    try:
        return await service.registrar_movimento(
            session,
            tenant_id=principal.tenant_id,
            produto_id=payload.produto_id,
            tipo=payload.tipo,
            quantidade=payload.quantidade,
            unidade_id=payload.unidade_id,
            lote_id=payload.lote_id,
            documento=payload.documento,
            motivo=payload.motivo,
            ocorrido_em=payload.ocorrido_em,
            registrado_por=principal.user_id,
        )
    except service.ComercialError as exc:
        raise _invalido(exc) from exc


@router.get("/produtos/{produto_id}/movimentos", response_model=list[MovimentoOut])
async def listar_movimentos(
    produto_id: uuid.UUID,
    session: SessionDep,
    _: Annotated[object, Depends(require("comercial.estoque.read"))],
) -> list[Movimento]:
    """A razão do produto: é o que responde por que o saldo é esse."""
    result = await session.execute(
        select(Movimento)
        .where(Movimento.produto_id == produto_id)
        .order_by(Movimento.ocorrido_em, Movimento.registrado_em)
    )
    return list(result.scalars().all())


@router.get("/produtos/{produto_id}/saldo", response_model=SaldoOut)
async def saldo(
    produto_id: uuid.UUID,
    session: SessionDep,
    _: Annotated[object, Depends(require("comercial.estoque.read"))],
) -> SaldoOut:
    produto = await session.get(Produto, produto_id)
    if produto is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Produto não encontrado.")

    lotes = {
        lote.id: lote
        for lote in (await session.execute(select(Lote).where(Lote.produto_id == produto_id)))
        .scalars()
        .all()
    }

    por_lote = await service.saldo_por_lote(session, produto_id)
    return SaldoOut(
        produto_id=produto_id,
        unidade_id=produto.unidade_id,
        quantidade=sum((item.quantidade for item in por_lote), start=Decimal(0)),
        por_lote=[
            SaldoLoteOut(
                lote_id=item.lote_id,
                codigo=lotes[item.lote_id].codigo if item.lote_id in lotes else None,
                validade=lotes[item.lote_id].validade if item.lote_id in lotes else None,
                quantidade=item.quantidade,
            )
            for item in por_lote
        ],
    )
