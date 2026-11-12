"""As regras da venda de balcão.

A baixa de estoque não é escrita aqui: é pedida ao serviço do módulo ``comercial``. Quem
conhece conversão de embalagem, exigência de lote e razão de estoque é ele — ver
``docs/adr/0007-dependencia-entre-modulos.md``.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from decko_modules.clientes.models import Cliente
from decko_modules.comercial import service as comercial
from decko_modules.comercial.models import Produto, TipoMovimento, Unidade
from decko_modules.core import security
from decko_modules.core import service as core_service
from decko_modules.core.models import RolePermission, User, UserRole
from decko_modules.financeiro.models import ContaRecebimento
from decko_modules.pdv.models import (
    AcaoAutorizada,
    Autorizacao,
    Caixa,
    ConfiguracaoPdv,
    Contador,
    DestinoDevolucao,
    Devolucao,
    FormaPagamento,
    ItemDevolucao,
    ItemVenda,
    MovimentoCaixa,
    Pagamento,
    StatusVenda,
    TipoMovimentoCaixa,
    Venda,
)

CENTAVO = Decimal("0.01")


class PdvError(Exception):
    """Erro de regra da venda. Vira 422 na borda."""


def _dinheiro(valor: Decimal) -> Decimal:
    """Arredonda para centavo, meio para cima — como se faz no caixa."""
    return valor.quantize(CENTAVO, rounding=ROUND_HALF_UP)


async def abrir_venda(
    session: AsyncSession, *, tenant_id: uuid.UUID, operador_id: uuid.UUID | None = None
) -> Venda:
    venda = Venda(tenant_id=tenant_id, operador_id=operador_id, status=StatusVenda.ABERTA)
    session.add(venda)
    await session.flush()
    return venda


def _exige_aberta(venda: Venda) -> None:
    if venda.status is not StatusVenda.ABERTA:
        raise PdvError(f"A venda já está {venda.status.value}; não aceita mais alteração.")


async def identificar(session: AsyncSession, *, venda: Venda, cliente_id: uuid.UUID) -> Venda:
    """Diz de quem é esta venda.

    Só enquanto aberta: depois de finalizada tudo na venda é congelado — total, preço e
    descrição de cada item — porque o cupom precisa continuar dizendo o que o cliente
    pagou. Trocar a quem a venda pertence depois de fechada seria reescrever um documento
    entregue.
    """
    _exige_aberta(venda)

    cliente = await session.get(Cliente, cliente_id)
    if cliente is None:
        raise PdvError("Cliente não encontrado.")
    if not cliente.ativo:
        # Vendas antigas dele continuam intactas; desativar quer dizer "não use mais daqui
        # para frente".
        raise PdvError(f"'{cliente.nome}' está desativado e não pode entrar numa venda nova.")

    venda.cliente_id = cliente.id
    await session.flush()
    return venda


async def desidentificar(session: AsyncSession, *, venda: Venda) -> Venda:
    """Volta a venda a anônima. Errar o cliente no balcão é comum e tem de ser reversível."""
    _exige_aberta(venda)
    venda.cliente_id = None
    await session.flush()
    return venda


async def cliente_de(session: AsyncSession, venda: Venda) -> Cliente | None:
    """O cliente da venda, lido na hora.

    Ao contrário do preço e da descrição do item, que são cópia: o preço de ontem é fato
    histórico e não pode mudar, mas quem a pessoa é é cadastro, e corrigir um nome digitado
    errado precisa valer para as vendas dela também.
    """
    if venda.cliente_id is None:
        return None
    return await session.get(Cliente, venda.cliente_id)


async def adicionar_item(
    session: AsyncSession,
    *,
    venda: Venda,
    produto_id: uuid.UUID,
    quantidade: Decimal,
    unidade_id: uuid.UUID | None = None,
    lote_id: uuid.UUID | None = None,
    preco_unitario: Decimal | None = None,
    desconto: Decimal = Decimal(0),
) -> ItemVenda:
    """Lança um item na venda aberta.

    Sem ``preco_unitario``, usa o preço de venda do cadastro. Produto sem preço é recusado
    em vez de ir a zero: vender de graça por omissão é o tipo de defeito que só aparece no
    fechamento do caixa.
    """
    _exige_aberta(venda)

    if quantidade <= 0:
        raise PdvError("A quantidade precisa ser maior que zero.")
    if desconto < 0:
        raise PdvError("O desconto não pode ser negativo.")

    produto = await session.get(Produto, produto_id)
    if produto is None:
        raise PdvError("Produto não encontrado.")
    if not produto.ativo:
        raise PdvError(f"'{produto.nome}' está inativo e não pode ser vendido.")

    preco = preco_unitario if preco_unitario is not None else produto.preco_venda
    if preco is None:
        raise PdvError(f"'{produto.nome}' não tem preço de venda cadastrado.")
    if preco < 0:
        raise PdvError("O preço não pode ser negativo.")

    if produto.controla_lote and lote_id is None:
        raise PdvError(f"'{produto.nome}' controla lote: informe de qual lote é a saída.")

    total = _dinheiro(quantidade * preco) - _dinheiro(desconto)
    if total < 0:
        raise PdvError("O desconto do item é maior que o próprio item.")

    item = ItemVenda(
        tenant_id=venda.tenant_id,
        venda_id=venda.id,
        produto_id=produto_id,
        lote_id=lote_id,
        # Sem unidade informada, vende-se na unidade base do produto.
        unidade_id=unidade_id if unidade_id is not None else produto.unidade_id,
        quantidade=quantidade,
        preco_unitario=preco,
        desconto=_dinheiro(desconto),
        total=total,
        descricao=produto.nome,
    )
    session.add(item)
    await session.flush()
    return item


async def remover_item(session: AsyncSession, *, venda: Venda, item_id: uuid.UUID) -> None:
    _exige_aberta(venda)

    item = await session.get(ItemVenda, item_id)
    if item is None or item.venda_id != venda.id:
        raise PdvError("Item não encontrado nesta venda.")

    await session.delete(item)
    await session.flush()


async def definir_desconto(session: AsyncSession, *, venda: Venda, desconto: Decimal) -> Venda:
    """Desconto sobre a venda inteira, além do que cada item já tenha."""
    _exige_aberta(venda)
    if desconto < 0:
        raise PdvError("O desconto não pode ser negativo.")

    soma = await soma_dos_itens(session, venda)
    if desconto > soma:
        raise PdvError("O desconto é maior que a venda.")

    venda.desconto = _dinheiro(desconto)
    await session.flush()
    return venda


async def registrar_pagamento(
    session: AsyncSession,
    *,
    venda: Venda,
    forma: FormaPagamento,
    valor: Decimal,
    conta_id: uuid.UUID | None = None,
) -> Pagamento:
    """Registra uma forma de pagamento. Uma venda pode ter várias.

    ``conta_id`` é opcional de propósito: a loja de uma conta só não ganha nada
    preenchendo sempre a mesma, e um campo obrigatório a mais por pagamento é fila parada.
    """
    _exige_aberta(venda)
    if valor <= 0:
        raise PdvError("O valor do pagamento precisa ser maior que zero.")

    if conta_id is not None:
        conta = await session.get(ContaRecebimento, conta_id)
        if conta is None:
            raise PdvError("Conta de recebimento não encontrada.")
        if not conta.ativa:
            # Conta desativada some das escolhas novas; vendas antigas continuam nela.
            raise PdvError(f"A conta '{conta.nome}' está desativada.")

    pagamento = Pagamento(
        tenant_id=venda.tenant_id,
        venda_id=venda.id,
        forma=forma,
        valor=_dinheiro(valor),
        conta_id=conta_id,
    )
    session.add(pagamento)
    await session.flush()
    return pagamento


async def remover_pagamento(
    session: AsyncSession, *, venda: Venda, pagamento_id: uuid.UUID
) -> None:
    _exige_aberta(venda)

    pagamento = await session.get(Pagamento, pagamento_id)
    if pagamento is None or pagamento.venda_id != venda.id:
        raise PdvError("Pagamento não encontrado nesta venda.")

    await session.delete(pagamento)
    await session.flush()


async def _pagamentos(session: AsyncSession, venda: Venda) -> list[Pagamento]:
    result = await session.execute(select(Pagamento).where(Pagamento.venda_id == venda.id))
    return list(result.scalars())


async def contas_dos_pagamentos(session: AsyncSession, venda: Venda) -> dict[uuid.UUID, str]:
    """Nome de cada conta usada nos pagamentos desta venda, por id.

    Uma consulta para todas, e não uma por pagamento. O nome é lido na hora e não copiado:
    renomear a conta vale para o histórico dela também — cadastro, não fato histórico.
    """
    ids = {p.conta_id for p in await _pagamentos(session, venda) if p.conta_id is not None}
    if not ids:
        return {}

    achadas = await session.execute(
        select(ContaRecebimento.id, ContaRecebimento.nome).where(ContaRecebimento.id.in_(ids))
    )
    # `.all()` materializa as linhas antes do dict: o Result do SQLAlchemy não é um
    # iterável de pares, e `dict(resultado)` estoura.
    return dict(achadas.all())


async def soma_dos_itens(session: AsyncSession, venda: Venda) -> Decimal:
    result = await session.execute(select(ItemVenda.total).where(ItemVenda.venda_id == venda.id))
    return _dinheiro(sum(result.scalars().all(), Decimal(0)))


async def total_a_pagar(session: AsyncSession, venda: Venda) -> Decimal:
    """O que a venda custa agora.

    Venda finalizada devolve o total congelado; venda aberta, a soma dos itens menos o
    desconto — que ainda muda a cada bipada.
    """
    if venda.total is not None:
        return venda.total
    return _dinheiro(await soma_dos_itens(session, venda) - venda.desconto)


async def total_pago(session: AsyncSession, venda: Venda) -> Decimal:
    result = await session.execute(select(Pagamento.valor).where(Pagamento.venda_id == venda.id))
    return _dinheiro(sum(result.scalars().all(), Decimal(0)))


@dataclass(frozen=True)
class Fechamento:
    venda: Venda
    total: Decimal
    pago: Decimal
    troco: Decimal


async def _proximo_numero(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    """Reserva o próximo número da empresa, no banco.

    A linha do contador é travada pelo próprio ``ON CONFLICT DO UPDATE``, então dois
    caixas que fecham no mesmo instante recebem números diferentes.

    Pode haver buraco na sequência se a transação for desfeita depois de reservar. Isso é
    aceito: este número identifica a venda na operação, não é número de documento fiscal,
    que tem exigência própria e virá com o módulo fiscal.
    """
    statement = (
        pg_insert(Contador)
        .values(tenant_id=tenant_id, proximo=1)
        .on_conflict_do_update(
            index_elements=[Contador.tenant_id],
            set_={"proximo": Contador.proximo + 1},
        )
        .returning(Contador.proximo)
    )
    numero = await session.scalar(statement)
    if numero is None:  # pragma: no cover - o RETURNING sempre traz a linha
        raise PdvError("Não foi possível reservar o número da venda.")
    return int(numero)


async def finalizar_venda(
    session: AsyncSession, *, venda: Venda, registrado_por: uuid.UUID | None = None
) -> Fechamento:
    """Fecha a venda: confere o pagamento, baixa o estoque e congela o total.

    A baixa acontece na mesma transação da venda. Se o estoque recusar a saída, a venda
    não fecha — não existe estado em que o cupom saiu e o estoque não baixou.

    A venda entra na sessão de caixa **do operador dela**, se ele tiver uma aberta. Sem
    caixa aberto ela fecha mesmo assim e fica fora de sessão: vender não exige caixa
    aberto, e travar por padrão pararia o balcão.
    """
    _exige_aberta(venda)

    if venda.operador_id is not None:
        sessao = await caixa_aberto(session, operador_id=venda.operador_id)
        venda.caixa_id = sessao.id if sessao is not None else None

    itens = list(
        (await session.execute(select(ItemVenda).where(ItemVenda.venda_id == venda.id))).scalars()
    )
    if not itens:
        raise PdvError("Não dá para fechar uma venda sem itens.")

    total = await total_a_pagar(session, venda)
    pago = await total_pago(session, venda)
    if pago < total:
        falta = _dinheiro(total - pago)
        raise PdvError(f"Falta receber R$ {falta}.")

    troco = _dinheiro(pago - total)
    if troco > 0:
        # Só dinheiro devolve troco. Cobrar no cartão mais do que a venda e devolver a
        # diferença em espécie é transformar o caixa em saque, e não é o que a loja pediu.
        em_dinheiro = sum(
            (
                p.valor
                for p in await _pagamentos(session, venda)
                if p.forma is FormaPagamento.DINHEIRO
            ),
            Decimal(0),
        )
        if troco > em_dinheiro:
            raise PdvError("Só pagamento em dinheiro devolve troco; confira os valores.")

    venda.numero = await _proximo_numero(session, venda.tenant_id)
    documento = f"Venda {venda.numero}"

    for item in itens:
        await comercial.registrar_movimento(
            session,
            tenant_id=venda.tenant_id,
            produto_id=item.produto_id,
            tipo=TipoMovimento.SAIDA,
            quantidade=item.quantidade,
            unidade_id=item.unidade_id,
            lote_id=item.lote_id,
            documento=documento,
            registrado_por=registrado_por,
        )

    venda.total = total
    venda.status = StatusVenda.FINALIZADA
    venda.fechada_em = datetime.now(UTC)
    await session.flush()

    return Fechamento(venda=venda, total=total, pago=pago, troco=troco)


async def cancelar_venda(session: AsyncSession, *, venda: Venda) -> Venda:
    """Cancela uma venda que ainda não fechou.

    Venda finalizada continua não sendo cancelada: cancelar enquanto aberta é só mudar o
    status, porque nada foi lançado. Desfazer uma saída de estoque já lançada é
    **devolução**, que é documento próprio e deixa as duas pernas na razão — ver
    ``devolver`` e a atualização de 10/11/2026 da ADR 0008.
    """
    if venda.status is StatusVenda.FINALIZADA:
        raise PdvError("Venda finalizada não é cancelada; registre uma devolução.")
    if venda.status is StatusVenda.CANCELADA:
        return venda

    venda.status = StatusVenda.CANCELADA
    venda.fechada_em = datetime.now(UTC)
    await session.flush()
    return venda


__all__ = [
    "Fechamento",
    "PdvError",
    "abrir_venda",
    "adicionar_item",
    "avarias",
    "calcular_devolucao",
    "cancelar_venda",
    "definir_desconto",
    "devolucoes_da_venda",
    "devolver",
    "devolvido_por_item",
    "devolvivel",
    "finalizar_venda",
    "registrar_pagamento",
    "remover_item",
    "remover_pagamento",
    "soma_dos_itens",
    "total_a_pagar",
    "total_pago",
]


@dataclass(frozen=True)
class LinhaDaForma:
    forma: FormaPagamento
    quantidade: int
    valor: Decimal


@dataclass(frozen=True)
class LinhaDaConta:
    conta_id: uuid.UUID | None
    conta_nome: str | None
    valor: Decimal


@dataclass(frozen=True)
class LinhaDoOperador:
    operador_id: uuid.UUID | None
    operador_nome: str | None
    vendas: int
    valor: Decimal


@dataclass(frozen=True)
class LinhaDeAvaria:
    """Um produto parado por defeito, na unidade em que foi vendido.

    Agrupado por produto **e unidade**, sem converter: quem sabe converter embalagem é o
    módulo comercial, e somar "2 caixas" com "3 unidades" num número só daria um total
    que não existe — ver ``docs/adr/0007-dependencia-entre-modulos.md``.
    """

    produto_id: uuid.UUID
    descricao: str
    unidade_id: uuid.UUID
    unidade_simbolo: str | None
    quantidade: Decimal


@dataclass(frozen=True)
class Conferencia:
    """O que entrou num período, de onde veio e por quem passou."""

    de: datetime
    ate: datetime
    vendas: int
    canceladas: int
    bruto: Decimal
    descontos: Decimal
    liquido: Decimal
    recebido: Decimal
    por_forma: list[LinhaDaForma]
    por_conta: list[LinhaDaConta]
    por_operador: list[LinhaDoOperador]

    # O que voltou. Sem isto a gaveta nunca fecha numa loja que devolve: a devolução em
    # espécie sai do mesmo dinheiro que a venda colocou lá.
    devolucoes: int
    devolvido: Decimal
    devolvido_em_especie: Decimal
    # O que voltou com defeito e **não** entrou no estoque vendável. É a pilha de RMA, e
    # é por isso que ela aparece aqui e não no saldo do produto.
    avarias: list[LinhaDeAvaria]


async def conferencia(session: AsyncSession, *, de: datetime, ate: datetime) -> Conferencia:
    """Soma o que foi vendido e recebido entre dois instantes.

    O recorte é pelo **fechamento** da venda, não pela abertura: uma venda aberta às 23h55
    e fechada às 00h10 pertence ao dia em que o dinheiro entrou, que é o dia que a pessoa
    confere.

    Os instantes vêm prontos de quem chama, com fuso: o dia de quem está no balcão é o dia
    local dele, e o servidor não tem como adivinhar qual é. Mesma razão do ``todayLocal``
    no front — ver ``apps/web/src/lib/format.ts``.

    Nada aqui decide regra de caixa. É leitura do que já aconteceu, e é de propósito: a
    sessão de caixa (abrir, fechar, sangria) depende de requisito que não existe — ver
    ``docs/discovery/pdv-fechamento-de-caixa.md``.
    """
    dentro = (Venda.fechada_em >= de, Venda.fechada_em <= ate)
    finalizada = Venda.status == StatusVenda.FINALIZADA

    totais = (
        await session.execute(
            select(
                func.count(Venda.id),
                func.coalesce(func.sum(Venda.total), 0),
                func.coalesce(func.sum(Venda.desconto), 0),
            ).where(finalizada, *dentro)
        )
    ).one()

    canceladas = (
        await session.execute(
            select(func.count(Venda.id)).where(Venda.status == StatusVenda.CANCELADA, *dentro)
        )
    ).scalar_one()

    # O bruto é a soma dos itens, antes do desconto da venda. Somar os itens aqui, e não
    # guardar um campo, evita um total que pode divergir do que as linhas dizem.
    bruto = (
        await session.execute(
            select(func.coalesce(func.sum(ItemVenda.total), 0))
            .join(Venda, Venda.id == ItemVenda.venda_id)
            .where(finalizada, *dentro)
        )
    ).scalar_one()

    formas = (
        await session.execute(
            select(
                Pagamento.forma,
                func.count(Pagamento.id),
                func.coalesce(func.sum(Pagamento.valor), 0),
            )
            .join(Venda, Venda.id == Pagamento.venda_id)
            .where(finalizada, *dentro)
            .group_by(Pagamento.forma)
            .order_by(func.sum(Pagamento.valor).desc())
        )
    ).all()

    contas = (
        await session.execute(
            select(
                Pagamento.conta_id,
                ContaRecebimento.nome,
                func.coalesce(func.sum(Pagamento.valor), 0),
            )
            .join(Venda, Venda.id == Pagamento.venda_id)
            .outerjoin(ContaRecebimento, ContaRecebimento.id == Pagamento.conta_id)
            .where(finalizada, *dentro)
            .group_by(Pagamento.conta_id, ContaRecebimento.nome)
            .order_by(func.sum(Pagamento.valor).desc())
        )
    ).all()

    # Nome do operador lido na hora, nunca copiado: mesma razão do nome da conta logo acima.
    operadores = (
        await session.execute(
            select(
                Venda.operador_id,
                User.full_name,
                func.count(Venda.id),
                func.coalesce(func.sum(Venda.total), 0),
            )
            .outerjoin(User, User.id == Venda.operador_id)
            .where(finalizada, *dentro)
            .group_by(Venda.operador_id, User.full_name)
            .order_by(func.sum(Venda.total).desc())
        )
    ).all()

    recebido = sum((linha[2] for linha in formas), Decimal(0))

    # A devolução é recortada pelo instante em que foi registrada: ela não tem "fechada
    # em", e o dinheiro saiu da gaveta na hora em que o operador a lançou.
    no_periodo = (Devolucao.created_at >= de, Devolucao.created_at <= ate)

    devolucoes, devolvido = (
        await session.execute(
            select(func.count(Devolucao.id), func.coalesce(func.sum(Devolucao.total), 0)).where(
                *no_periodo
            )
        )
    ).one()

    devolvido_em_especie = (
        await session.execute(
            select(func.coalesce(func.sum(Devolucao.total), 0)).where(
                Devolucao.forma == FormaPagamento.DINHEIRO, *no_periodo
            )
        )
    ).scalar_one()

    return Conferencia(
        de=de,
        ate=ate,
        vendas=totais[0],
        canceladas=canceladas,
        bruto=_dinheiro(bruto),
        descontos=_dinheiro(totais[2]),
        liquido=_dinheiro(totais[1]),
        recebido=_dinheiro(recebido),
        por_forma=[LinhaDaForma(f, q, _dinheiro(v)) for f, q, v in formas],
        por_conta=[LinhaDaConta(i, n, _dinheiro(v)) for i, n, v in contas],
        por_operador=[LinhaDoOperador(i, n, q, _dinheiro(v)) for i, n, q, v in operadores],
        devolucoes=devolucoes,
        devolvido=_dinheiro(devolvido),
        devolvido_em_especie=_dinheiro(devolvido_em_especie),
        avarias=await avarias(session, de=de, ate=ate),
    )


# ---------------------------------------------------------------- sessão de caixa
#
# O caixa pertence ao operador, não à máquina, e vender não exige caixa aberto. As duas
# decisões e o porquê estão na atualização de 10/11/2026 da docs/adr/0008-ponto-de-venda.md.


async def caixa_aberto(session: AsyncSession, *, operador_id: uuid.UUID) -> Caixa | None:
    """A sessão aberta deste operador, se houver. Aberto é derivado de ``fechado_em``."""
    return (
        await session.execute(
            select(Caixa).where(Caixa.operador_id == operador_id, Caixa.fechado_em.is_(None))
        )
    ).scalar_one_or_none()


async def abrir_caixa(
    session: AsyncSession, *, tenant_id: uuid.UUID, operador_id: uuid.UUID, abertura: Decimal
) -> Caixa:
    """Abre a sessão com o fundo de troco com que a gaveta começa."""
    if abertura < 0:
        raise PdvError("O valor de abertura não pode ser negativo.")
    if await caixa_aberto(session, operador_id=operador_id) is not None:
        raise PdvError("Este operador já tem um caixa aberto.")

    caixa = Caixa(tenant_id=tenant_id, operador_id=operador_id, abertura=_dinheiro(abertura))
    session.add(caixa)
    await session.flush()
    return caixa


def _exige_caixa_aberto(caixa: Caixa) -> None:
    if caixa.fechado_em is not None:
        raise PdvError("Este caixa já foi fechado.")


async def movimentar_caixa(
    session: AsyncSession,
    *,
    caixa: Caixa,
    tipo: TipoMovimentoCaixa,
    valor: Decimal,
    motivo: str,
) -> MovimentoCaixa:
    """Retirada ou entrada de dinheiro fora de venda.

    O motivo é obrigatório: sangria sem motivo é a linha que ninguém consegue explicar
    depois, e é justamente a que importa explicar.
    """
    _exige_caixa_aberto(caixa)
    if valor <= 0:
        raise PdvError("O valor precisa ser maior que zero.")
    if not motivo.strip():
        raise PdvError("Diga o motivo da sangria ou do suprimento.")

    movimento = MovimentoCaixa(
        tenant_id=caixa.tenant_id,
        caixa_id=caixa.id,
        tipo=tipo,
        valor=_dinheiro(valor),
        motivo=motivo.strip(),
    )
    session.add(movimento)
    await session.flush()
    return movimento


async def esperado_do_caixa(session: AsyncSession, caixa: Caixa) -> Decimal:
    """Quanto deveria haver na gaveta.

    ``abertura + espécie recebida + suprimentos - sangrias - devoluções em espécie``.

    Só espécie entra e só espécie sai, porque só espécie está na gaveta: devolução no
    cartão é estorno da adquirente e não tira dinheiro daqui. É conta feita na leitura e
    não coluna guardada: um total gravado pode divergir das linhas que o compõem, e é a
    linha que se audita.
    """
    em_especie = (
        await session.execute(
            select(func.coalesce(func.sum(Pagamento.valor), 0))
            .join(Venda, Venda.id == Pagamento.venda_id)
            .where(
                Venda.caixa_id == caixa.id,
                Venda.status == StatusVenda.FINALIZADA,
                Pagamento.forma == FormaPagamento.DINHEIRO,
            )
        )
    ).scalar_one()

    movimentos = (
        await session.execute(
            select(MovimentoCaixa.tipo, func.coalesce(func.sum(MovimentoCaixa.valor), 0))
            .where(MovimentoCaixa.caixa_id == caixa.id)
            .group_by(MovimentoCaixa.tipo)
        )
    ).all()

    devolvido = (
        await session.execute(
            select(func.coalesce(func.sum(Devolucao.total), 0)).where(
                Devolucao.caixa_id == caixa.id,
                Devolucao.forma == FormaPagamento.DINHEIRO,
            )
        )
    ).scalar_one()

    total = Decimal(caixa.abertura) + Decimal(em_especie) - Decimal(devolvido)
    for tipo, valor in movimentos:
        total += Decimal(valor) if tipo is TipoMovimentoCaixa.SUPRIMENTO else -Decimal(valor)
    return _dinheiro(total)


async def fechar_caixa(
    session: AsyncSession, *, caixa: Caixa, contado: Decimal, observacao: str | None = None
) -> Caixa:
    """Fecha com o valor contado, e guarda a diferença.

    **Não bater nunca impede fechar.** A divergência é o produto da conferência: travar
    destruiria o único dado que ela gera, e ensinaria o operador a ajustar a contagem até
    bater — que é o que a conferência cega existe para impedir.
    """
    _exige_caixa_aberto(caixa)
    if contado < 0:
        raise PdvError("O valor contado não pode ser negativo.")

    esperado = await esperado_do_caixa(session, caixa)
    caixa.esperado = esperado
    caixa.contado = _dinheiro(contado)
    caixa.diferenca = _dinheiro(Decimal(contado) - esperado)
    caixa.observacao = (observacao or "").strip() or None
    caixa.fechado_em = datetime.now(UTC)
    await session.flush()
    return caixa


# ------------------------------------------------------------------- devolução de venda
#
# A devolução é documento novo, nunca edição da venda: a venda segue `finalizada` e
# congelada. No estoque ela lança **entrada**, porque a razão do módulo comercial não
# aceita edição do passado. Cada linha devolvida tem destino — volta vendável, ou é avaria
# e não entra. Decisão e motivos: atualização de 10/11/2026 da
# docs/adr/0008-ponto-de-venda.md e docs/discovery/pdv-devolucao-de-venda.md.


@dataclass(frozen=True)
class LinhaDevolver:
    """Uma linha da venda voltando. ``destino`` é o que separa avaria de estoque."""

    venda_item_id: uuid.UUID
    quantidade: Decimal
    destino: DestinoDevolucao = DestinoDevolucao.ESTOQUE


@dataclass(frozen=True)
class Previa:
    """Quanto cada linha devolve, e o total — conferido, e sem gravar nada.

    Existe para o operador ver o valor **antes** de abrir a gaveta. Vem do servidor pelo
    mesmo motivo que o total da venda vem: duas somas do mesmo dinheiro em lugares
    diferentes divergem, e a que sai do caixa é esta.
    """

    valores: list[Decimal]
    total: Decimal


@dataclass(frozen=True)
class LinhaDevolvivel:
    """Uma linha da venda e o que dela ainda dá para devolver."""

    venda_item_id: uuid.UUID
    descricao: str
    unidade_id: uuid.UUID
    quantidade: Decimal
    devolvida: Decimal
    resta: Decimal
    valor_resta: Decimal


async def _itens_da_venda(session: AsyncSession, venda: Venda) -> list[ItemVenda]:
    result = await session.execute(
        select(ItemVenda).where(ItemVenda.venda_id == venda.id).order_by(ItemVenda.created_at)
    )
    return list(result.scalars())


async def _rateio_da_venda(session: AsyncSession, venda: Venda) -> dict[uuid.UUID, Decimal]:
    """Quanto cada linha da venda custou **ao cliente**, com o desconto da venda rateado.

    A linha não pode ser devolvida pelo seu próprio total: o desconto da venda inteira não
    está nela, então devolver ``item.total`` devolveria mais do que o cliente pagou.

    A soma deste rateio é **exatamente** ``venda.total``. O resíduo do arredondamento fica
    na maior linha — e é por isso que devolver mais do que a venda custou é aritmeticamente
    impossível, em vez de ser uma validação que alguém pode esquecer de chamar.
    """
    itens = await _itens_da_venda(session, venda)
    soma = _dinheiro(sum((item.total for item in itens), Decimal(0)))
    total = _dinheiro(venda.total if venda.total is not None else soma - venda.desconto)

    if soma <= 0:
        return {item.id: Decimal("0.00") for item in itens}

    rateio = {item.id: _dinheiro(item.total * total / soma) for item in itens}

    residuo = total - _dinheiro(sum(rateio.values(), Decimal(0)))
    if residuo != 0:
        maior = max(itens, key=lambda item: item.total)
        rateio[maior.id] = _dinheiro(rateio[maior.id] + residuo)
    return rateio


def _fatia(rateio: Decimal, quantidade: Decimal, de: Decimal) -> Decimal:
    """A parte do rateio que corresponde a ``quantidade`` de um item de ``de`` unidades."""
    return _dinheiro(rateio * quantidade / de)


async def devolvido_por_item(
    session: AsyncSession, venda: Venda
) -> dict[uuid.UUID, tuple[Decimal, Decimal]]:
    """Quanto de cada linha da venda já voltou: ``(quantidade, valor)``.

    Soma **todas** as devoluções daquela venda, porque o limite é a venda e não a
    devolução: três devoluções parciais não podem passar do que foi vendido.
    """
    linhas = (
        await session.execute(
            select(
                ItemDevolucao.venda_item_id,
                func.coalesce(func.sum(ItemDevolucao.quantidade), 0),
                func.coalesce(func.sum(ItemDevolucao.valor), 0),
            )
            .join(Devolucao, Devolucao.id == ItemDevolucao.devolucao_id)
            .where(Devolucao.venda_id == venda.id)
            .group_by(ItemDevolucao.venda_item_id)
        )
    ).all()
    return {item_id: (Decimal(qtd), Decimal(valor)) for item_id, qtd, valor in linhas}


async def devolucoes_da_venda(session: AsyncSession, venda: Venda) -> list[Devolucao]:
    """As devoluções desta venda, da mais antiga para a mais nova."""
    result = await session.execute(
        select(Devolucao).where(Devolucao.venda_id == venda.id).order_by(Devolucao.created_at)
    )
    return list(result.scalars())


async def devolvivel(session: AsyncSession, venda: Venda) -> list[LinhaDevolvivel]:
    """O que ainda dá para devolver desta venda, linha por linha.

    É o que a tela mostra antes de o operador escolher. ``valor_resta`` é quanto sai da
    gaveta se aquela linha voltar inteira — número do servidor, não da tela.
    """
    rateio = await _rateio_da_venda(session, venda)
    ja = await devolvido_por_item(session, venda)

    linhas = []
    for item in await _itens_da_venda(session, venda):
        devolvida, valor = ja.get(item.id, (Decimal(0), Decimal("0.00")))
        linhas.append(
            LinhaDevolvivel(
                venda_item_id=item.id,
                descricao=item.descricao,
                unidade_id=item.unidade_id,
                quantidade=item.quantidade,
                devolvida=devolvida,
                resta=item.quantidade - devolvida,
                valor_resta=_dinheiro(rateio[item.id] - valor),
            )
        )
    return linhas


async def calcular_devolucao(
    session: AsyncSession, *, venda: Venda, linhas: list[LinhaDevolver]
) -> Previa:
    """Confere o que está voltando e diz quanto devolve, sem gravar.

    Toda a recusa mora aqui, e é por isso que a prévia da tela e a gravação não podem
    divergir: as duas passam por esta função.
    """
    if venda.status is not StatusVenda.FINALIZADA:
        raise PdvError(f"Só venda finalizada tem o que devolver; esta está {venda.status.value}.")
    if not linhas:
        raise PdvError("Diga o que está voltando.")

    itens = {item.id: item for item in await _itens_da_venda(session, venda)}
    rateio = await _rateio_da_venda(session, venda)
    ja_devolvido = await devolvido_por_item(session, venda)

    # Acumulado **desta** chamada, por linha: duas linhas para o mesmo item são válidas —
    # três garrafas voltam ao estoque e uma quebrou — e as duas juntas é que têm limite.
    nesta: dict[uuid.UUID, Decimal] = {}

    valores: list[Decimal] = []
    for linha in linhas:
        item = itens.get(linha.venda_item_id)
        if item is None:
            raise PdvError("Esta linha não é desta venda.")
        if linha.quantidade <= 0:
            raise PdvError("A quantidade a devolver precisa ser maior que zero.")

        devolvida_antes, valor_antes = ja_devolvido.get(item.id, (Decimal(0), Decimal("0.00")))
        nesta_linha = nesta.get(item.id, Decimal(0))
        resta = item.quantidade - devolvida_antes - nesta_linha

        if linha.quantidade > resta:
            if resta <= 0:
                raise PdvError(f"'{item.descricao}' já foi devolvido por inteiro.")
            raise PdvError(f"De '{item.descricao}' resta devolver {resta.normalize()}.")

        if linha.quantidade == resta:
            # Fecha a linha com o que sobra do rateio dela: senão o centavo perdido na
            # divisão fica preso e nunca volta ao cliente.
            valor = _dinheiro(
                rateio[item.id]
                - valor_antes
                - _fatia(rateio[item.id], nesta_linha, item.quantidade)
            )
        else:
            valor = _fatia(rateio[item.id], linha.quantidade, item.quantidade)

        valores.append(valor)
        nesta[item.id] = nesta_linha + linha.quantidade

    return Previa(valores=valores, total=_dinheiro(sum(valores, Decimal(0))))


async def devolver(
    session: AsyncSession,
    *,
    venda: Venda,
    linhas: list[LinhaDevolver],
    forma: FormaPagamento,
    motivo: str,
    operador_id: uuid.UUID | None = None,
    registrado_por: uuid.UUID | None = None,
) -> Devolucao:
    """Registra o que o cliente trouxe de volta e quanto recebeu por isso.

    O que volta ao estoque entra na razão na **mesma transação**, pelo mesmo motivo que a
    baixa da venda: não existe estado em que o dinheiro voltou e o estoque não.

    A devolução cai na sessão de caixa **de quem a registrou**, se ele tiver uma aberta.
    Sem caixa aberto ela fica fora de sessão — registrada e visível, pela mesma razão que
    a venda fora de sessão não é absorvida depois.
    """
    if not motivo.strip():
        raise PdvError("Diga o motivo da devolução.")

    previa = await calcular_devolucao(session, venda=venda, linhas=linhas)
    itens = {item.id: item for item in await _itens_da_venda(session, venda)}

    devolucao = Devolucao(
        tenant_id=venda.tenant_id,
        venda_id=venda.id,
        operador_id=operador_id,
        forma=forma,
        motivo=motivo.strip(),
        total=previa.total,
    )

    if operador_id is not None:
        sessao = await caixa_aberto(session, operador_id=operador_id)
        devolucao.caixa_id = sessao.id if sessao is not None else None

    session.add(devolucao)
    await session.flush()

    for linha, valor in zip(linhas, previa.valores, strict=True):
        item = itens[linha.venda_item_id]
        session.add(
            ItemDevolucao(
                tenant_id=venda.tenant_id,
                devolucao_id=devolucao.id,
                venda_item_id=item.id,
                quantidade=linha.quantidade,
                valor=valor,
                destino=linha.destino,
            )
        )

        if linha.destino is DestinoDevolucao.ESTOQUE:
            # Entrada, e não estorno da saída: a razão não aceita edição do passado, e são
            # as duas pernas que contam a história para quem auditar.
            await comercial.registrar_movimento(
                session,
                tenant_id=venda.tenant_id,
                produto_id=item.produto_id,
                tipo=TipoMovimento.ENTRADA,
                quantidade=linha.quantidade,
                unidade_id=item.unidade_id,
                lote_id=item.lote_id,
                documento=f"Devolução da venda {venda.numero}",
                motivo=motivo.strip(),
                registrado_por=registrado_por,
            )

    await session.flush()
    return devolucao


async def avarias(session: AsyncSession, *, de: datetime, ate: datetime) -> list[LinhaDeAvaria]:
    """O que voltou com defeito e não entrou no estoque vendável, somado por produto.

    É a pilha que espera o fornecedor. Não é saldo de estoque, de propósito: contar avaria
    como estoque faria o sistema dizer que dá para vender o que está quebrado.

    O nome vem do cadastro e não da linha da venda, ao contrário do cupom: quem vai
    conversar com o fornecedor precisa do nome que o produto tem hoje.
    """
    linhas = (
        await session.execute(
            select(
                ItemVenda.produto_id,
                Produto.nome,
                ItemVenda.unidade_id,
                Unidade.simbolo,
                func.coalesce(func.sum(ItemDevolucao.quantidade), 0),
            )
            .join(Devolucao, Devolucao.id == ItemDevolucao.devolucao_id)
            .join(ItemVenda, ItemVenda.id == ItemDevolucao.venda_item_id)
            .join(Produto, Produto.id == ItemVenda.produto_id)
            .outerjoin(Unidade, Unidade.id == ItemVenda.unidade_id)
            .where(
                ItemDevolucao.destino == DestinoDevolucao.AVARIA,
                Devolucao.created_at >= de,
                Devolucao.created_at <= ate,
            )
            .group_by(ItemVenda.produto_id, Produto.nome, ItemVenda.unidade_id, Unidade.simbolo)
            .order_by(func.sum(ItemDevolucao.quantidade).desc())
        )
    ).all()
    return [
        LinhaDeAvaria(
            produto_id=produto_id,
            descricao=nome,
            unidade_id=unidade_id,
            unidade_simbolo=simbolo,
            quantidade=Decimal(quantidade),
        )
        for produto_id, nome, unidade_id, simbolo, quantidade in linhas
    ]


# ------------------------------------------------------- autorização do supervisor
#
# O operador não faz sozinho o que a loja decidiu que precisa de supervisor. A credencial
# de quem libera vai **junto com a ação**, e o servidor confere antes de executar: nunca
# "destravar a tela". Destravar tela é teatro — quem abre o inspetor passa por cima, e o
# controle que existe para impedir fraude seria burlável por quem tem mais motivo para
# burlá-lo. Ver docs/adr/0020-operador-supervisor-e-papeis.md, decisão 4.

# A permissão de liberar. Uma só, e não uma por ação: é assim que a loja pensa — "o
# supervisor libera" —, e seis permissões para a mesma autoridade seriam seis chances de
# configurar errado.
PERMISSAO_AUTORIZAR = "pdv.autorizar"


@dataclass(frozen=True)
class Credencial:
    """Quem está liberando, e o segredo dele. Nunca viaja para lugar nenhum além daqui."""

    autorizador_id: uuid.UUID
    senha: str | None = None
    pin: str | None = None


class AutorizacaoExigidaError(Exception):
    """A ação precisa de credencial de quem pode liberar, e ela não veio.

    É erro de pré-condição, não de regra: a borda responde 428 para a tela saber que deve
    pedir a credencial e repetir a ação, em vez de mostrar um erro ao operador.
    """

    def __init__(self, acao: AcaoAutorizada, mensagem: str) -> None:
        super().__init__(mensagem)
        self.acao = acao


async def configuracao(session: AsyncSession, tenant_id: uuid.UUID) -> ConfiguracaoPdv:
    """A configuração desta loja, criada com os padrões na primeira vez que for lida."""
    atual = await session.get(ConfiguracaoPdv, tenant_id)
    if atual is not None:
        return atual

    atual = ConfiguracaoPdv(tenant_id=tenant_id)
    session.add(atual)
    await session.flush()
    return atual


def _exige(config: ConfiguracaoPdv, acao: AcaoAutorizada, valor: Decimal | None) -> bool:
    """Se esta loja exige supervisor para esta ação, com este valor."""
    match acao:
        case AcaoAutorizada.CANCELAR_ITEM:
            return config.exige_cancelar_item
        case AcaoAutorizada.CANCELAR_VENDA:
            return config.exige_cancelar_venda
        case AcaoAutorizada.SANGRIA:
            return config.exige_sangria
        case AcaoAutorizada.DEVOLUCAO:
            return config.exige_devolucao
        case AcaoAutorizada.DESCONTO:
            return config.exige_desconto and (valor or Decimal(0)) > config.desconto_livre
        case AcaoAutorizada.FECHAR_CAIXA:
            return config.exige_diferenca and abs(valor or Decimal(0)) > config.diferenca_livre
    return False  # pragma: no cover - o enum acima é exaustivo


async def exigir_autorizacao(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    acao: AcaoAutorizada,
    solicitante_id: uuid.UUID | None,
    solicitante_autoriza: bool,
    credencial: Credencial | None = None,
    referencia: str | None = None,
    valor: Decimal | None = None,
    motivo: str | None = None,
) -> Autorizacao | None:
    """Confere a liberação antes da ação, e a registra. Devolve ``None`` quando não cabia.

    ``solicitante_autoriza`` dispensa a pergunta: o supervisor que opera o próprio caixa
    não precisa chamar a si mesmo. Quem fez continua registrado na ação.

    A conferência da permissão do autorizador é feita **no banco**, e não a partir de
    token: quem pede a liberação não pode ser a fonte do que o liberador pode.
    """
    config = await configuracao(session, tenant_id)
    if solicitante_autoriza or not _exige(config, acao, valor):
        return None

    if credencial is None:
        raise AutorizacaoExigidaError(acao, "Esta ação precisa da liberação de um supervisor.")

    autorizador = await session.get(User, credencial.autorizador_id)
    if autorizador is None or autorizador.tenant_id != tenant_id or not autorizador.is_active:
        raise PdvError("Supervisor não encontrado.")

    if PERMISSAO_AUTORIZAR not in await core_service.permissoes_de(session, autorizador.id):
        raise PdvError(f"{autorizador.full_name} não pode liberar esta ação.")

    if credencial.pin is not None:
        # Pelo `conferir_pin` do núcleo, e não por uma conferência própria: PIN curto só
        # se sustenta com bloqueio, e duas contagens separadas para o mesmo segredo
        # dariam a quem adivinha o dobro de tentativas.
        try:
            await core_service.conferir_pin(session, user=autorizador, pin=credencial.pin)
        except core_service.AuthError as exc:
            raise PdvError(str(exc)) from exc
    elif not security.verify_password(credencial.senha or "", autorizador.password_hash):
        # Mensagem igual à do supervisor inexistente seria pior aqui do que no login: o
        # operador sabe quem escolheu na lista, e "senha não confere" é o que ele precisa
        # para chamar a pessoa de novo.
        raise PdvError("A senha do supervisor não confere.")

    autorizacao = Autorizacao(
        tenant_id=tenant_id,
        acao=acao,
        solicitante_id=solicitante_id,
        autorizador_id=autorizador.id,
        referencia=referencia,
        valor=None if valor is None else _dinheiro(valor),
        motivo=(motivo or "").strip() or None,
    )
    session.add(autorizacao)
    await session.flush()
    return autorizacao


@dataclass(frozen=True)
class Autorizador:
    id: uuid.UUID
    nome: str


async def autorizadores(session: AsyncSession, tenant_id: uuid.UUID) -> list[Autorizador]:
    """Quem pode liberar, para o operador escolher pelo nome e só pedir a senha.

    Só o nome sai daqui. Dentro de uma loja, saber quem é o supervisor não é segredo — é
    a pessoa ao lado —, e obrigar o operador a digitar o e-mail do chefe a cada
    cancelamento transformaria uma trava em fila.
    """
    linhas = (
        await session.execute(
            select(User.id, User.full_name)
            .join(UserRole, UserRole.user_id == User.id)
            .join(RolePermission, RolePermission.role_id == UserRole.role_id)
            .where(
                User.tenant_id == tenant_id,
                User.is_active.is_(True),
                RolePermission.permission == PERMISSAO_AUTORIZAR,
            )
            .distinct()
            .order_by(User.full_name)
        )
    ).all()
    return [Autorizador(id=user_id, nome=nome) for user_id, nome in linhas]
