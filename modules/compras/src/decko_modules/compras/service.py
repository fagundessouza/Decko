"""Importar a nota, reconhecer os itens e dar entrada no estoque.

Quem sabe dizer se dois itens são o mesmo produto é o módulo comercial — ver
``decko_modules.comercial.identidade``. Quem escreve na razão de estoque também é ele.
Este módulo orquestra: lê o XML, pergunta, guarda a decisão e manda lançar.

Nada entra no estoque antes de a nota ser confirmada. Ver
``docs/adr/0009-identidade-de-produto-e-entrada-por-nota.md``, decisão 4.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from decko_modules.comercial import identidade
from decko_modules.comercial import service as comercial
from decko_modules.comercial.models import Produto, TipoMovimento, Unidade
from decko_modules.compras.models import (
    Nota,
    NotaItem,
    OrigemVinculo,
    StatusNota,
    documento_de,
)
from decko_modules.compras.nfe import ler


class ComprasError(Exception):
    """Erro de regra da entrada de nota. Vira 422 na borda."""


class NotaDuplicadaError(ComprasError):
    """A mesma nota já foi importada. Lançar duas vezes dobraria o estoque."""


# ------------------------------------------------------------------ importar


async def importar(session: AsyncSession, *, tenant_id: uuid.UUID, xml: str | bytes) -> Nota:
    """Lê o XML, grava a nota em rascunho e tenta reconhecer cada item.

    O que o GTIN ou uma equivalência já confirmada resolvem, entra ligado. O resto fica
    esperando o lojista — e é por isso que a nota nasce em rascunho.
    """
    lida = ler(xml)

    ja_existe = await session.scalar(select(Nota).where(Nota.chave == lida.chave))
    if ja_existe is not None:
        raise NotaDuplicadaError(
            f"A nota {lida.numero or lida.chave} já foi importada nesta empresa."
        )

    texto = xml.decode("utf-8", errors="replace") if isinstance(xml, bytes) else xml
    nota = Nota(
        tenant_id=tenant_id,
        chave=lida.chave,
        numero=lida.numero,
        serie=lida.serie,
        emitente_cnpj=lida.emitente_cnpj,
        emitente_nome=lida.emitente_nome,
        emitida_em=lida.emitida_em,
        valor_total=lida.valor_total,
        status=StatusNota.RASCUNHO,
        xml_origem=texto,
    )
    session.add(nota)
    await session.flush()

    for lido in lida.itens:
        item = NotaItem(
            tenant_id=tenant_id,
            nota_id=nota.id,
            numero_item=lido.numero,
            codigo_fornecedor=lido.codigo_fornecedor,
            descricao=lido.descricao,
            gtin=lido.gtin,
            ncm=lido.ncm,
            cest=lido.cest,
            unidade_comercial=lido.unidade_comercial,
            quantidade=lido.quantidade,
            valor_unitario=lido.valor_unitario,
            valor_total=lido.valor_total,
        )

        candidatos = await identidade.identificar(
            session,
            descricao=lido.descricao,
            gtin=lido.gtin,
            ncm=lido.ncm,
            fornecedor_cnpj=lida.emitente_cnpj,
            codigo_fornecedor=lido.codigo_fornecedor,
        )
        # Só chave de identidade liga sozinha. Semelhança de nome vira sugestão na tela.
        if candidatos and candidatos[0].automatico:
            item.produto_id = candidatos[0].produto_id
            item.origem_vinculo = OrigemVinculo(candidatos[0].origem.value)

        session.add(item)

    await session.flush()
    # Carrega a coleção de uma vez. Sem isto, qualquer acesso a `nota.itens` dispararia
    # carregamento preguiçoso, que em sessão assíncrona estoura fora do greenlet.
    await session.refresh(nota, ["itens"])
    return nota


async def sugestoes_para(
    session: AsyncSession, nota: Nota, item: NotaItem
) -> list[identidade.Candidato]:
    """Os produtos que este item pode ser. Vazio quando já está resolvido."""
    if item.produto_id is not None:
        return []
    return await identidade.identificar(
        session,
        descricao=item.descricao,
        gtin=item.gtin,
        ncm=item.ncm,
        fornecedor_cnpj=nota.emitente_cnpj,
        codigo_fornecedor=item.codigo_fornecedor,
    )


# ------------------------------------------------------------------ conferir


def _exige_rascunho(nota: Nota) -> None:
    if nota.status is not StatusNota.RASCUNHO:
        raise ComprasError(f"A nota já está {nota.status.value}; não aceita mais alteração.")


async def vincular(
    session: AsyncSession,
    *,
    nota: Nota,
    item: NotaItem,
    produto_id: uuid.UUID,
    unidade_id: uuid.UUID | None = None,
) -> NotaItem:
    """Diz que este item da nota é aquele produto do cadastro."""
    _exige_rascunho(nota)

    produto = await session.get(Produto, produto_id)
    if produto is None:
        raise ComprasError("Produto não encontrado.")

    if unidade_id is not None and await session.get(Unidade, unidade_id) is None:
        raise ComprasError("Unidade não encontrada.")

    item.produto_id = produto.id
    item.unidade_id = unidade_id
    item.origem_vinculo = OrigemVinculo.MANUAL
    await session.flush()
    return item


async def marcar_como_novo(
    session: AsyncSession, *, nota: Nota, item: NotaItem, unidade_id: uuid.UUID
) -> NotaItem:
    """Diz que este item não existe no cadastro e deve virar produto novo.

    O produto não é criado agora: só na confirmação da nota, junto com o estoque. Criar
    aqui deixaria cadastro órfão quando a nota fosse descartada.
    """
    _exige_rascunho(nota)

    if await session.get(Unidade, unidade_id) is None:
        raise ComprasError("Unidade não encontrada.")

    item.produto_id = None
    item.unidade_id = unidade_id
    item.origem_vinculo = OrigemVinculo.NOVO
    await session.flush()
    return item


async def itens_de(session: AsyncSession, nota: Nota) -> list[NotaItem]:
    """Os itens da nota, lidos do banco.

    Consulta explícita em vez de ``nota.itens``: a coleção é preguiçosa, e em sessão
    assíncrona o carregamento preguiçoso estoura fora do contexto do greenlet.
    """
    resultado = await session.execute(
        select(NotaItem).where(NotaItem.nota_id == nota.id).order_by(NotaItem.numero_item)
    )
    return list(resultado.scalars().all())


async def pendentes(session: AsyncSession, nota: Nota) -> list[NotaItem]:
    """Os itens que ainda não têm destino. A nota não fecha com algum aqui."""
    return [
        item
        for item in await itens_de(session, nota)
        if item.produto_id is None and item.origem_vinculo is not OrigemVinculo.NOVO
    ]


# ------------------------------------------------------------------ confirmar


@dataclass(frozen=True)
class Resultado:
    nota: Nota
    produtos_criados: int
    itens_lancados: int


async def confirmar(
    session: AsyncSession,
    *,
    nota: Nota,
    tenant_id: uuid.UUID,
    confirmada_por: uuid.UUID | None = None,
) -> Resultado:
    """Cria o que falta, lança o estoque e aprende as equivalências.

    Tudo na mesma transação: não existe estado em que o produto foi criado e o estoque
    não entrou, nem o contrário.
    """
    _exige_rascunho(nota)

    faltando = await pendentes(session, nota)
    if faltando:
        nomes = ", ".join(item.descricao for item in faltando[:3])
        raise ComprasError(f"Ainda há item sem destino nesta nota: {nomes}.")

    criados = 0
    documento = documento_de(nota)
    itens = await itens_de(session, nota)

    for item in itens:
        if item.origem_vinculo is OrigemVinculo.NOVO:
            produto = await _criar_produto(session, tenant_id=tenant_id, item=item)
            item.produto_id = produto.id
            criados += 1

        if item.produto_id is None:  # pragma: no cover - `pendentes` já barrou acima
            raise ComprasError(f"'{item.descricao}' ficou sem produto.")

        # A decisão vira regra: a próxima nota deste fornecedor entra sozinha.
        await identidade.lembrar_equivalencia(
            session,
            tenant_id=tenant_id,
            produto_id=item.produto_id,
            fornecedor_cnpj=nota.emitente_cnpj,
            fornecedor_nome=nota.emitente_nome,
            codigo_fornecedor=item.codigo_fornecedor,
            descricao_fornecedor=item.descricao,
        )

        produto = await session.get(Produto, item.produto_id)
        if produto is None:  # pragma: no cover - acabou de ser lido ou criado
            raise ComprasError(f"'{item.descricao}' aponta para um produto que sumiu.")
        await comercial.registrar_movimento(
            session,
            tenant_id=tenant_id,
            produto_id=item.produto_id,
            tipo=TipoMovimento.ENTRADA,
            quantidade=item.quantidade,
            # Sem embalagem escolhida, entra na unidade base do produto. A nota diz "CX";
            # quantas unidades tem a caixa, só o lojista sabe.
            unidade_id=item.unidade_id or produto.unidade_id,
            documento=documento,
            registrado_por=confirmada_por,
        )

    nota.status = StatusNota.CONFIRMADA
    nota.confirmada_em = datetime.now(UTC)
    nota.confirmada_por = confirmada_por
    await session.flush()

    return Resultado(nota=nota, produtos_criados=criados, itens_lancados=len(itens))


async def _criar_produto(session: AsyncSession, *, tenant_id: uuid.UUID, item: NotaItem) -> Produto:
    """Cadastra o produto a partir da própria nota.

    Nasce com GTIN, NCM e CEST — mais do que o cadastro digitado à mão costuma receber.
    O código é o do fornecedor enquanto o lojista não puser o dele: inventar um número
    sequencial daria um SKU que não significa nada para ninguém.
    """
    if item.unidade_id is None:
        raise ComprasError(f"Falta dizer em que unidade '{item.descricao}' é contado.")

    # A unidade escolhida diz em que a **nota** veio ("10 fardos"). O produto é contado na
    # raiz daquela árvore, que é a unidade menor — assim 10 fardos de 6 entram como 60, e
    # o saldo soma na mesma medida em que a gôndola é contada. Se o produto nascesse
    # contado em fardo, a entrada seguinte em unidade não teria como somar.
    escolhida = await session.get(Unidade, item.unidade_id)
    if escolhida is None:
        raise ComprasError("Unidade não encontrada.")

    codigo = item.codigo_fornecedor
    if await session.scalar(select(Produto).where(Produto.codigo == codigo)) is not None:
        codigo = f"{codigo}-{item.numero_item}"

    produto = Produto(
        tenant_id=tenant_id,
        codigo=codigo,
        nome=item.descricao,
        gtin=item.gtin,
        ncm=item.ncm,
        cest=item.cest,
        unidade_id=escolhida.raiz_id,
        preco_custo=Decimal(item.valor_unitario),
    )
    session.add(produto)
    await session.flush()
    return produto


async def descartar(session: AsyncSession, *, nota: Nota) -> Nota:
    """Joga a nota fora sem lançar nada. Só vale enquanto for rascunho."""
    _exige_rascunho(nota)
    nota.status = StatusNota.DESCARTADA
    await session.flush()
    return nota
