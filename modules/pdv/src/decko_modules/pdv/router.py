import uuid
from datetime import datetime
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
from decko_modules.pdv.models import (
    AcaoAutorizada,
    Caixa,
    ConfiguracaoPdv,
    Devolucao,
    MovimentoCaixa,
    StatusVenda,
    TipoMovimentoCaixa,
    Venda,
)
from decko_modules.pdv.schemas import (
    AberturaIn,
    AutorizadorOut,
    CaixaOut,
    CancelarVendaIn,
    ConferenciaOut,
    ConfiguracaoIn,
    ConfiguracaoOut,
    CredencialIn,
    DescontoIn,
    DevolucaoIn,
    DevolucaoOut,
    DevolucoesDaVendaOut,
    FechamentoCaixaIn,
    IdentificarIn,
    ItemIn,
    ItemOut,
    LinhaDevolverIn,
    LinhaDevolvivelOut,
    MovimentoCaixaIn,
    PagamentoIn,
    PagamentoOut,
    PreviaDevolucaoIn,
    PreviaDevolucaoOut,
    RetirarItemIn,
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

    cliente = await service.cliente_de(session, venda)
    contas = await service.contas_dos_pagamentos(session, venda)

    return VendaOut(
        id=venda.id,
        numero=venda.numero,
        status=venda.status,
        aberta_em=venda.aberta_em,
        fechada_em=venda.fechada_em,
        observacao=venda.observacao,
        cliente_id=venda.cliente_id,
        cliente_nome=cliente.nome if cliente else None,
        itens=[ItemOut.model_validate(item) for item in venda.itens],
        pagamentos=[
            PagamentoOut(
                id=p.id,
                forma=p.forma,
                valor=p.valor,
                conta_id=p.conta_id,
                conta_nome=contas.get(p.conta_id),
            )
            for p in venda.pagamentos
        ],
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
    numero: Annotated[int | None, Query(ge=1, description="O número do cupom.")] = None,
    limite: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[Venda]:
    consulta = select(Venda).order_by(Venda.aberta_em.desc()).limit(limite)
    if status_filtro is not None:
        consulta = consulta.where(Venda.status == status_filtro)
    if numero is not None:
        # É por aqui que a devolução acha a venda: o cliente traz o cupom, não o id.
        consulta = consulta.where(Venda.numero == numero)
    return list((await session.execute(consulta)).scalars().all())


async def _caixa_visto(session: SessionDep, caixa) -> dict:
    """Monta a saída do caixa, com o esperado calculado enquanto ele estiver aberto."""
    movimentos = (
        (
            await session.execute(
                select(MovimentoCaixa)
                .where(MovimentoCaixa.caixa_id == caixa.id)
                .order_by(MovimentoCaixa.created_at)
            )
        )
        .scalars()
        .all()
    )
    # O esperado NÃO sai enquanto o caixa está aberto, e isso é a conferência cega da
    # ADR 0008 valendo também na rede: devolvê-lo aqui bastaria abrir o inspetor para ver
    # o número antes de contar. Ele aparece no fechamento, depois da contagem, e fica
    # guardado na sessão fechada para quem for auditar.
    # Campo a campo, e não varrendo `__table__.columns`: `updated_at` tem valor gerado
    # pelo banco na atualização, então fica expirado depois do flush do fechamento. Lê-lo
    # dispara uma busca síncrona dentro de função assíncrona, que é o MissingGreenlet.
    # A saída não precisa dele.
    return {
        "id": caixa.id,
        "operador_id": caixa.operador_id,
        "aberto_em": caixa.aberto_em,
        "fechado_em": caixa.fechado_em,
        "abertura": caixa.abertura,
        "contado": caixa.contado,
        "esperado": caixa.esperado,
        "diferenca": caixa.diferenca,
        "observacao": caixa.observacao,
        "movimentos": list(movimentos),
    }


async def _carregar_caixa(session: SessionDep, caixa_id: uuid.UUID):
    caixa = await session.get(Caixa, caixa_id)
    if caixa is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Caixa não encontrado.")
    return caixa


@router.get("/caixa/aberto", response_model=CaixaOut | None)
async def caixa_aberto(
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("pdv.caixa.abrir"))],
) -> dict | None:
    """O caixa aberto de quem está pedindo. Nulo quando não há — e isso não é erro."""
    caixa = await service.caixa_aberto(session, operador_id=principal.user_id)
    return None if caixa is None else await _caixa_visto(session, caixa)


@router.post("/caixa", response_model=CaixaOut, status_code=status.HTTP_201_CREATED)
async def abrir_caixa(
    payload: AberturaIn,
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("pdv.caixa.abrir"))],
) -> dict:
    try:
        caixa = await service.abrir_caixa(
            session,
            tenant_id=principal.tenant_id,
            operador_id=principal.user_id,
            abertura=payload.abertura,
        )
    except service.PdvError as exc:
        raise _invalido(exc) from exc
    return await _caixa_visto(session, caixa)


@router.post("/caixa/{caixa_id}/movimentos", response_model=CaixaOut)
async def movimentar_caixa(
    caixa_id: uuid.UUID,
    payload: MovimentoCaixaIn,
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("pdv.caixa.abrir"))],
) -> dict:
    caixa = await _carregar_caixa(session, caixa_id)
    try:
        if payload.tipo is TipoMovimentoCaixa.SANGRIA:
            # Só a retirada pede liberação: dinheiro **entrando** na gaveta não é o que
            # se desvia, e pedir supervisor para repor troco pararia o balcão à toa.
            await service.exigir_autorizacao(
                session,
                tenant_id=principal.tenant_id,
                acao=AcaoAutorizada.SANGRIA,
                solicitante_id=principal.user_id,
                solicitante_autoriza=principal.can(service.PERMISSAO_AUTORIZAR),
                credencial=_credencial(payload.autorizacao),
                referencia=str(caixa.id),
                valor=payload.valor,
                motivo=payload.motivo,
            )
        await service.movimentar_caixa(
            session, caixa=caixa, tipo=payload.tipo, valor=payload.valor, motivo=payload.motivo
        )
    except service.AutorizacaoExigidaError as exc:
        raise _pedir_autorizacao(exc) from exc
    except service.PdvError as exc:
        raise _invalido(exc) from exc
    return await _caixa_visto(session, caixa)


@router.post("/caixa/{caixa_id}/fechar", response_model=CaixaOut)
async def fechar_caixa(
    caixa_id: uuid.UUID,
    payload: FechamentoCaixaIn,
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("pdv.caixa.fechar"))],
) -> dict:
    """Fecha com o valor contado. Não bater nunca impede fechar — ver ADR 0008.

    Diferença grande pode exigir supervisor, se a loja ligar isso: é a única trava deste
    tipo que o Odoo tem de fábrica. **Continua não impedindo fechar** — exige uma segunda
    pessoa, que é coisa diferente de travar.
    """
    caixa = await _carregar_caixa(session, caixa_id)
    try:
        # O esperado é recalculado aqui só para medir a diferença. Ele **não** entra na
        # resposta do 428: a tela precisa saber que falta supervisor, não quanto deveria
        # haver na gaveta — isso continua aparecendo só depois da contagem enviada.
        esperado = await service.esperado_do_caixa(session, caixa)
        await service.exigir_autorizacao(
            session,
            tenant_id=principal.tenant_id,
            acao=AcaoAutorizada.FECHAR_CAIXA,
            solicitante_id=principal.user_id,
            solicitante_autoriza=principal.can(service.PERMISSAO_AUTORIZAR),
            credencial=_credencial(payload.autorizacao),
            referencia=str(caixa.id),
            valor=payload.contado - esperado,
        )
        await service.fechar_caixa(
            session, caixa=caixa, contado=payload.contado, observacao=payload.observacao
        )
    except service.AutorizacaoExigidaError as exc:
        raise _pedir_autorizacao(exc) from exc
    except service.PdvError as exc:
        raise _invalido(exc) from exc
    return await _caixa_visto(session, caixa)


@router.get("/conferencia", response_model=ConferenciaOut)
async def conferencia(
    session: SessionDep,
    # Permissão própria, e não `pdv.venda.read`: este relatório soma o dia inteiro entre
    # operadores e mostra o esperado em espécie. Quem opera precisa ler venda para vender,
    # e isso lhe entregaria o número antes da contagem — ver ADR 0008 e ADR 0020.
    _: Annotated[object, Depends(require("pdv.caixa.conferir"))],
    de: Annotated[datetime, Query(description="Início do período, com fuso.")],
    ate: Annotated[datetime, Query(description="Fim do período, com fuso.")],
) -> service.Conferencia:
    """O que entrou no período: por forma de pagamento, por conta e por operador.

    Vem antes de ``/vendas/{id}`` na ordem das rotas de propósito: ``conferencia`` seria
    lido como um id de venda se viesse depois.
    """
    if ate < de:
        raise _invalido(ValueError("O fim do período é antes do início."))
    return await service.conferencia(session, de=de, ate=ate)


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


@router.post("/vendas/{venda_id}/itens/{item_id}/retirar", response_model=VendaOut)
async def retirar_item(
    venda_id: uuid.UUID,
    item_id: uuid.UUID,
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("pdv.venda.write"))],
    payload: RetirarItemIn | None = None,
) -> VendaOut:
    """Tira um item da venda em andamento.

    `POST` e não `DELETE`: a credencial do supervisor precisa viajar no corpo, e corpo em
    `DELETE` é mal suportado por intermediário — senha em parâmetro de URL acaba em log.
    """
    venda = await _carregar(session, venda_id)
    try:
        await service.exigir_autorizacao(
            session,
            tenant_id=principal.tenant_id,
            acao=AcaoAutorizada.CANCELAR_ITEM,
            solicitante_id=principal.user_id,
            solicitante_autoriza=principal.can(service.PERMISSAO_AUTORIZAR),
            credencial=_credencial(payload.autorizacao if payload else None),
            referencia=str(venda.id),
        )
        await service.remover_item(session, venda=venda, item_id=item_id)
    except service.AutorizacaoExigidaError as exc:
        raise _pedir_autorizacao(exc) from exc
    except service.PdvError as exc:
        raise _invalido(exc) from exc
    return await _ver(session, venda)


@router.put("/vendas/{venda_id}/desconto", response_model=VendaOut)
async def definir_desconto(
    venda_id: uuid.UUID,
    payload: DescontoIn,
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("pdv.venda.write"))],
) -> VendaOut:
    venda = await _carregar(session, venda_id)
    try:
        await service.exigir_autorizacao(
            session,
            tenant_id=principal.tenant_id,
            acao=AcaoAutorizada.DESCONTO,
            solicitante_id=principal.user_id,
            solicitante_autoriza=principal.can(service.PERMISSAO_AUTORIZAR),
            credencial=_credencial(payload.autorizacao),
            referencia=str(venda.id),
            valor=payload.desconto,
        )
        await service.definir_desconto(session, venda=venda, desconto=payload.desconto)
    except service.AutorizacaoExigidaError as exc:
        raise _pedir_autorizacao(exc) from exc
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
            session,
            venda=venda,
            forma=payload.forma,
            valor=payload.valor,
            conta_id=payload.conta_id,
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


@router.put("/vendas/{venda_id}/cliente", response_model=VendaOut)
async def identificar_venda(
    venda_id: uuid.UUID,
    payload: IdentificarIn,
    session: SessionDep,
    _: Annotated[object, Depends(require("pdv.venda.identificar"))],
) -> VendaOut:
    """Diz de quem é esta venda.

    Permissão própria, separada de `pdv.venda.write`: quem opera o caixa nem sempre é quem
    pode ver e escolher na carteira de clientes da loja.
    """
    venda = await _carregar(session, venda_id)
    try:
        await service.identificar(session, venda=venda, cliente_id=payload.cliente_id)
    except service.PdvError as exc:
        raise _invalido(exc) from exc
    return await _ver(session, venda)


@router.delete("/vendas/{venda_id}/cliente", response_model=VendaOut)
async def desidentificar_venda(
    venda_id: uuid.UUID,
    session: SessionDep,
    _: Annotated[object, Depends(require("pdv.venda.identificar"))],
) -> VendaOut:
    """Volta a venda a anônima. Errar o cliente no balcão é comum."""
    venda = await _carregar(session, venda_id)
    try:
        await service.desidentificar(session, venda=venda)
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
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("pdv.venda.cancelar"))],
    payload: CancelarVendaIn | None = None,
) -> VendaOut:
    venda = await _carregar(session, venda_id)
    try:
        await service.exigir_autorizacao(
            session,
            tenant_id=principal.tenant_id,
            acao=AcaoAutorizada.CANCELAR_VENDA,
            solicitante_id=principal.user_id,
            solicitante_autoriza=principal.can(service.PERMISSAO_AUTORIZAR),
            credencial=_credencial(payload.autorizacao if payload else None),
            referencia=str(venda.id),
        )
        await service.cancelar_venda(session, venda=venda)
    except service.AutorizacaoExigidaError as exc:
        raise _pedir_autorizacao(exc) from exc
    except service.PdvError as exc:
        raise _invalido(exc) from exc
    return await _ver(session, venda)


# ------------------------------------------------------------------- devolução de venda
#
# `pdv.venda.devolver` é permissão própria: devolver dinheiro não é a mesma autoridade que
# vender. Ver a atualização de 10/11/2026 da docs/adr/0008-ponto-de-venda.md.


async def _devolucao_vista(session: AsyncSession, devolucao_id: uuid.UUID) -> Devolucao:
    """Relê a devolução com as linhas, depois de gravada.

    Reler em vez de confiar no objeto em memória: `created_at` tem valor gerado pelo
    banco, então fica expirado depois do flush, e lê-lo dispararia uma busca síncrona
    dentro de função assíncrona — o MissingGreenlet.
    """
    devolucao = await session.scalar(
        select(Devolucao)
        .where(Devolucao.id == devolucao_id)
        .options(selectinload(Devolucao.itens))
        .execution_options(populate_existing=True)
    )
    if devolucao is None:  # pragma: no cover - acabou de ser gravada
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Devolução não encontrada."
        )
    return devolucao


def _linhas(payload: list[LinhaDevolverIn]) -> list[service.LinhaDevolver]:
    return [
        service.LinhaDevolver(
            venda_item_id=linha.venda_item_id,
            quantidade=linha.quantidade,
            destino=linha.destino,
        )
        for linha in payload
    ]


@router.get("/vendas/{venda_id}/devolucoes", response_model=DevolucoesDaVendaOut)
async def ver_devolucoes(
    venda_id: uuid.UUID,
    session: SessionDep,
    _: Annotated[object, Depends(require("pdv.venda.read"))],
) -> DevolucoesDaVendaOut:
    """O que ainda dá para devolver desta venda, e o que já foi devolvido.

    Leitura: quem pode ver a venda pode ver o que voltou dela. Devolver é outra permissão.
    """
    venda = await _carregar(session, venda_id)
    devolucoes = await service.devolucoes_da_venda(session, venda)
    for devolucao in devolucoes:
        await session.refresh(devolucao, ["itens"])

    return DevolucoesDaVendaOut(
        venda_id=venda.id,
        numero=venda.numero,
        fechada_em=venda.fechada_em,
        total=await service.total_a_pagar(session, venda),
        linhas=[
            LinhaDevolvivelOut.model_validate(linha)
            for linha in await service.devolvivel(session, venda)
        ],
        devolucoes=[DevolucaoOut.model_validate(d) for d in devolucoes],
        devolvido=sum((d.total for d in devolucoes), Decimal(0)),
    )


@router.post("/vendas/{venda_id}/devolucoes/previa", response_model=PreviaDevolucaoOut)
async def prever_devolucao(
    venda_id: uuid.UUID,
    payload: PreviaDevolucaoIn,
    session: SessionDep,
    _: Annotated[object, Depends(require("pdv.venda.devolver"))],
) -> PreviaDevolucaoOut:
    """Quanto sairia da gaveta, sem gravar nada.

    Existe para o operador ver o valor antes de devolver o dinheiro. Passa pela **mesma**
    função que a gravação, então a prévia e o que sai não podem divergir.
    """
    venda = await _carregar(session, venda_id)
    try:
        previa = await service.calcular_devolucao(
            session, venda=venda, linhas=_linhas(payload.itens)
        )
    except service.PdvError as exc:
        raise _invalido(exc) from exc
    return PreviaDevolucaoOut(total=previa.total, valores=previa.valores)


@router.post(
    "/vendas/{venda_id}/devolucoes",
    response_model=DevolucaoOut,
    status_code=status.HTTP_201_CREATED,
)
async def devolver(
    venda_id: uuid.UUID,
    payload: DevolucaoIn,
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("pdv.venda.devolver"))],
) -> Devolucao:
    """Registra a devolução e devolve o produto ao estoque na mesma transação.

    O que vem marcado como avaria **não** volta ao estoque: fica na lista de avarias, que
    é a pilha esperando o fornecedor. Ver `docs/discovery/pdv-devolucao-de-venda.md`.
    """
    venda = await _carregar(session, venda_id)
    try:
        previa = await service.calcular_devolucao(
            session, venda=venda, linhas=_linhas(payload.itens)
        )
        await service.exigir_autorizacao(
            session,
            tenant_id=principal.tenant_id,
            acao=AcaoAutorizada.DEVOLUCAO,
            solicitante_id=principal.user_id,
            solicitante_autoriza=principal.can(service.PERMISSAO_AUTORIZAR),
            credencial=_credencial(payload.autorizacao),
            referencia=str(venda.id),
            valor=previa.total,
            motivo=payload.motivo,
        )
        devolucao = await service.devolver(
            session,
            venda=venda,
            linhas=_linhas(payload.itens),
            forma=payload.forma,
            motivo=payload.motivo,
            operador_id=principal.user_id,
            registrado_por=principal.user_id,
        )
    except service.AutorizacaoExigidaError as exc:
        raise _pedir_autorizacao(exc) from exc
    except (service.PdvError, comercial.ComercialError) as exc:
        raise _invalido(exc) from exc
    return await _devolucao_vista(session, devolucao.id)


# ------------------------------------------------------- autorização do supervisor
#
# A credencial de quem libera viaja junto com a ação, e a conferência acontece no servidor
# antes de executar. Ver docs/adr/0020-operador-supervisor-e-papeis.md, decisão 4.


def _credencial(payload: CredencialIn | None) -> service.Credencial | None:
    if payload is None:
        return None
    return service.Credencial(autorizador_id=payload.autorizador_id, senha=payload.senha)


def _pedir_autorizacao(exc: service.AutorizacaoExigidaError) -> HTTPException:
    """428, e não 403: a tela deve **pedir a credencial e repetir**, não mostrar erro.

    403 diria ao operador que ele não pode — e ele pode, com a liberação de alguém. A
    distinção precisa chegar na tela, e o código de estado é como ela chega.
    """
    return HTTPException(
        status_code=status.HTTP_428_PRECONDITION_REQUIRED,
        detail={"detail": str(exc), "acao": exc.acao.value},
    )


@router.get("/autorizadores", response_model=list[AutorizadorOut])
async def listar_autorizadores(
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("pdv.venda.write"))],
) -> list[AutorizadorOut]:
    """Quem pode liberar, para o operador escolher pelo nome e a pessoa só digitar a senha.

    Quem opera precisa desta lista para chamar alguém; por isso a permissão é a de operar,
    e não a de administrar. Só o nome sai daqui.
    """
    return [
        AutorizadorOut(id=linha.id, nome=linha.nome)
        for linha in await service.autorizadores(session, principal.tenant_id)
    ]


@router.get("/configuracao", response_model=ConfiguracaoOut)
async def ver_configuracao(
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("pdv.venda.read"))],
) -> ConfiguracaoPdv:
    """O que esta loja exige, e a partir de quanto.

    Leitura liberada a quem opera de propósito: a tela precisa saber o que vai pedir antes
    de pedir, e nada aqui é segredo — a trava não depende de o operador desconhecê-la.
    """
    return await service.configuracao(session, principal.tenant_id)


@router.put("/configuracao", response_model=ConfiguracaoOut)
async def salvar_configuracao(
    payload: ConfiguracaoIn,
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("pdv.config.write"))],
) -> ConfiguracaoPdv:
    config = await service.configuracao(session, principal.tenant_id)
    for campo, valor in payload.model_dump().items():
        setattr(config, campo, valor)
    await session.flush()
    return config
