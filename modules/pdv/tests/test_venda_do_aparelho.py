"""A venda que aconteceu sem rede chegando ao servidor.

Fatia 4 da `docs/adr/0022-offline-first-as-respostas.md`.

A diferença para `finalizar_venda` não é técnica, é de tempo verbal: lá a venda está
sendo feita e pode ser recusada; aqui ela **foi feita**, o cliente levou a mercadoria e
foi embora. O servidor registra o que aconteceu.

É daí que sai a regra mais contraintuitiva destes testes — o estoque pode ficar negativo,
e isso não é falha. A decisão é de 04/11/2026, do dono do projeto: recusar a venda por
divergência criaria exatamente o que o controle de estoque existe para impedir,
mercadoria saindo sem registro. *"Se não bater a conta é aí que tá o pulo do gato."*
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from decko.db import SessionFactory, bind_tenant
from decko_modules.comercial import service as comercial
from decko_modules.comercial.models import Produto, TipoMovimento, Unidade
from decko_modules.core.models import Tenant
from decko_modules.pdv import service
from decko_modules.pdv.models import FormaPagamento, ItemVenda, StatusVenda, Venda


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        await session.begin()
        try:
            yield session
        finally:
            await session.rollback()


class Loja:
    def __init__(self, tenant: Tenant, unidade: Unidade, produto: Produto) -> None:
        self.tenant = tenant
        self.unidade = unidade
        self.produto = produto


async def _loja(session: AsyncSession, estoque: str = "10") -> Loja:
    tenant = Tenant(name="Loja do aparelho", slug=f"aparelho-{uuid.uuid4().hex[:8]}")
    session.add(tenant)
    await session.flush()
    await bind_tenant(session, tenant.id)

    unidade = await comercial.criar_unidade(
        session, tenant_id=tenant.id, nome=f"Unidade {uuid.uuid4().hex[:4]}", simbolo="un"
    )
    produto = Produto(
        tenant_id=tenant.id,
        codigo=f"COD-{uuid.uuid4().hex[:8]}",
        nome="Refrigerante 2L",
        unidade_id=unidade.id,
        preco_venda=Decimal("10.00"),
    )
    session.add(produto)
    await session.flush()

    if Decimal(estoque) > 0:
        await comercial.registrar_movimento(
            session,
            tenant_id=tenant.id,
            produto_id=produto.id,
            tipo=TipoMovimento.ENTRADA,
            quantidade=Decimal(estoque),
            unidade_id=unidade.id,
            documento="Carga do teste",
        )

    return Loja(tenant, unidade, produto)


def _pacote(loja: Loja, *, quantidade: str = "2", venda_id: uuid.UUID | None = None):
    """O que o aparelho manda: a venda inteira, já fechada."""
    total = Decimal(quantidade) * Decimal("10.00")
    return {
        "venda_id": venda_id or uuid.uuid4(),
        "itens": [
            service.ItemDoAparelho(
                id=uuid.uuid4(),
                produto_id=loja.produto.id,
                unidade_id=loja.unidade.id,
                quantidade=Decimal(quantidade),
                preco_unitario=Decimal("10.00"),
                descricao=loja.produto.nome,
            )
        ],
        "pagamentos": [
            service.PagamentoDoAparelho(id=uuid.uuid4(), forma=FormaPagamento.DINHEIRO, valor=total)
        ],
    }


async def test_a_venda_entra_fechada_e_baixa_o_estoque(session: AsyncSession) -> None:
    loja = await _loja(session, "10")
    quando = datetime.now(UTC) - timedelta(hours=3)

    resultado = await service.sincronizar_venda(
        session,
        tenant_id=loja.tenant.id,
        registrada_no_aparelho_em=quando,
        **_pacote(loja, quantidade="2"),
    )

    assert resultado.venda.status is StatusVenda.FINALIZADA
    assert resultado.venda.total == Decimal("20.00")
    assert await comercial.saldo_do_produto(session, loja.produto.id) == Decimal(8)


async def test_as_duas_horas_ficam_guardadas(session: AsyncSession) -> None:
    """A do balcão e a do servidor. Guardar só uma faz a trilha mentir."""
    loja = await _loja(session)
    no_balcao = datetime.now(UTC) - timedelta(hours=3)

    resultado = await service.sincronizar_venda(
        session,
        tenant_id=loja.tenant.id,
        registrada_no_aparelho_em=no_balcao,
        **_pacote(loja),
    )

    assert resultado.venda.registrada_no_aparelho_em == no_balcao
    # `fechada_em` é a hora do servidor, e ela é bem depois.
    assert resultado.venda.fechada_em is not None
    assert resultado.venda.fechada_em > no_balcao


async def test_o_numero_nasce_no_servidor(session: AsyncSession) -> None:
    """Dois caixas sem rede não têm como combinar um contador — ADR 0019."""
    loja = await _loja(session, "20")

    primeira = await service.sincronizar_venda(
        session,
        tenant_id=loja.tenant.id,
        registrada_no_aparelho_em=datetime.now(UTC),
        **_pacote(loja, quantidade="1"),
    )
    segunda = await service.sincronizar_venda(
        session,
        tenant_id=loja.tenant.id,
        registrada_no_aparelho_em=datetime.now(UTC),
        **_pacote(loja, quantidade="1"),
    )

    assert primeira.venda.numero is not None
    assert segunda.venda.numero == primeira.venda.numero + 1


async def test_reenviar_a_mesma_venda_nao_vende_duas_vezes(session: AsyncSession) -> None:
    """O caso normal de quem opera sem sinal: a resposta se perde e o aparelho repete.

    Sem isto, o estoque baixaria duas vezes e o cliente apareceria devendo uma venda que
    nunca fez.
    """
    loja = await _loja(session, "10")
    pacote = _pacote(loja, quantidade="3")

    primeira = await service.sincronizar_venda(
        session, tenant_id=loja.tenant.id, registrada_no_aparelho_em=datetime.now(UTC), **pacote
    )
    segunda = await service.sincronizar_venda(
        session, tenant_id=loja.tenant.id, registrada_no_aparelho_em=datetime.now(UTC), **pacote
    )

    assert segunda.ja_existia is True
    assert segunda.venda.id == primeira.venda.id
    assert segunda.venda.numero == primeira.venda.numero
    assert await comercial.saldo_do_produto(session, loja.produto.id) == Decimal(7)

    quantas = len(
        (await session.execute(select(Venda.id).where(Venda.id == pacote["venda_id"]))).all()
    )
    assert quantas == 1


async def test_estoque_fica_negativo_em_vez_de_recusar(session: AsyncSession) -> None:
    """A regra que o dono do projeto escolheu, e ela é o contrário do instinto.

    O cliente levou a mercadoria. Recusar aqui não devolve o produto à prateleira — só
    apaga o registro de que ele saiu.
    """
    loja = await _loja(session, "1")

    resultado = await service.sincronizar_venda(
        session,
        tenant_id=loja.tenant.id,
        registrada_no_aparelho_em=datetime.now(UTC),
        **_pacote(loja, quantidade="4"),
    )

    assert resultado.venda.status is StatusVenda.FINALIZADA
    assert await comercial.saldo_do_produto(session, loja.produto.id) == Decimal(-3)


async def test_a_divergencia_vem_com_endereco(session: AsyncSession) -> None:
    """Saldo negativo escondido seria um furo invisível. Ele precisa dizer onde doeu."""
    loja = await _loja(session, "1")

    resultado = await service.sincronizar_venda(
        session,
        tenant_id=loja.tenant.id,
        registrada_no_aparelho_em=datetime.now(UTC),
        **_pacote(loja, quantidade="4"),
    )

    assert len(resultado.divergencias) == 1
    divergencia = resultado.divergencias[0]
    assert divergencia.produto_id == loja.produto.id
    assert divergencia.descricao == "Refrigerante 2L"
    assert divergencia.vendido == Decimal(4)
    assert divergencia.saldo_depois == Decimal(-3)


async def test_venda_que_bate_o_estoque_nao_inventa_divergencia(session: AsyncSession) -> None:
    loja = await _loja(session, "10")

    resultado = await service.sincronizar_venda(
        session,
        tenant_id=loja.tenant.id,
        registrada_no_aparelho_em=datetime.now(UTC),
        **_pacote(loja, quantidade="2"),
    )

    assert resultado.divergencias == []


async def test_o_preco_e_o_que_foi_cobrado_no_balcao(session: AsyncSession) -> None:
    """Reprecificar na chegada reescreveria o que aconteceu com o cliente."""
    loja = await _loja(session, "10")
    pacote = _pacote(loja, quantidade="2")
    pacote["itens"] = [
        service.ItemDoAparelho(
            id=uuid.uuid4(),
            produto_id=loja.produto.id,
            unidade_id=loja.unidade.id,
            quantidade=Decimal(2),
            # O catálogo do aparelho estava com o preço antigo.
            preco_unitario=Decimal("8.50"),
            descricao=loja.produto.nome,
        )
    ]
    pacote["pagamentos"] = [
        service.PagamentoDoAparelho(
            id=uuid.uuid4(), forma=FormaPagamento.DINHEIRO, valor=Decimal("17.00")
        )
    ]

    resultado = await service.sincronizar_venda(
        session,
        tenant_id=loja.tenant.id,
        registrada_no_aparelho_em=datetime.now(UTC),
        **pacote,
    )

    assert resultado.venda.total == Decimal("17.00")
    item = (
        await session.execute(select(ItemVenda).where(ItemVenda.venda_id == resultado.venda.id))
    ).scalar_one()
    assert item.preco_unitario == Decimal("8.50")


async def test_venda_sem_item_e_recusada_antes_de_escrever_nada(
    session: AsyncSession,
) -> None:
    """Pacote vazio não é venda offline: é defeito do aparelho.

    A recusa é **na entrada**, e a mensagem diz isso. Deixar seguir até o fechamento
    também recusaria, mas depois de já ter inserido a venda — e com a frase errada,
    "não dá para fechar", que fala de uma venda que ninguém está fechando aqui.
    """
    loja = await _loja(session)

    with pytest.raises(service.PdvError, match="registrar"):
        await service.sincronizar_venda(
            session,
            tenant_id=loja.tenant.id,
            venda_id=uuid.uuid4(),
            itens=[],
            pagamentos=[],
            registrada_no_aparelho_em=datetime.now(UTC),
        )


async def test_pagamento_menor_que_a_venda_e_recusado(session: AsyncSession) -> None:
    """Aqui a recusa vale: isso não é divergência de estoque, é conta que não fecha."""
    loja = await _loja(session, "10")
    pacote = _pacote(loja, quantidade="2")
    pacote["pagamentos"] = [
        service.PagamentoDoAparelho(
            id=uuid.uuid4(), forma=FormaPagamento.DINHEIRO, valor=Decimal("5.00")
        )
    ]

    with pytest.raises(service.PdvError):
        await service.sincronizar_venda(
            session,
            tenant_id=loja.tenant.id,
            registrada_no_aparelho_em=datetime.now(UTC),
            **pacote,
        )


# -------------------------------------- a rede caiu no meio do atendimento, e a venda era
# -------------------------------------- um rascunho aberto aqui


async def test_a_venda_aberta_aqui_e_a_mesma_que_o_aparelho_termina(
    session: AsyncSession,
) -> None:
    """O caso mais comum de todos: a rede cai com a venda já aberta no servidor.

    O balcão abriu a venda com rede, bipou um item, perdeu o sinal e terminou a venda no
    aparelho. O pacote chega com o id que o servidor já tinha dado.

    Sem o tratamento disto o pacote batia no reenvio, respondia "já existia" e sumia: o
    rascunho ficava aberto para sempre, o estoque não baixava, e o operador via "enviado"
    tendo perdido a venda.
    """
    loja = await _loja(session, "10")
    rascunho = await service.abrir_venda(session, tenant_id=loja.tenant.id)
    await service.adicionar_item(
        session, venda=rascunho, produto_id=loja.produto.id, quantidade=Decimal(1)
    )
    assert rascunho.status is StatusVenda.ABERTA

    resultado = await service.sincronizar_venda(
        session,
        tenant_id=loja.tenant.id,
        registrada_no_aparelho_em=datetime.now(UTC),
        **_pacote(loja, quantidade="3", venda_id=rascunho.id),
    )

    assert resultado.ja_existia is False, "o rascunho não é reenvio: a venda não estava aqui"
    assert resultado.venda.id == rascunho.id, "uma venda só, e não duas"
    assert resultado.venda.status is StatusVenda.FINALIZADA
    assert resultado.venda.numero is not None
    # O que vale é o que o aparelho terminou: três, e não o item do rascunho.
    assert resultado.venda.total == Decimal("30.00")
    assert await comercial.saldo_do_produto(session, loja.produto.id) == Decimal(7)


async def test_o_item_do_rascunho_nao_fica_somado_duas_vezes(session: AsyncSession) -> None:
    """O item bipado com rede está nos dois lados, e só pode contar uma vez.

    O aparelho manda a venda inteira — inclusive o que já havia sido bipado antes de a
    rede cair, porque ele não tem como saber o que chegou. Então o conteúdo do rascunho é
    substituído, e não acrescentado.
    """
    loja = await _loja(session, "10")
    rascunho = await service.abrir_venda(session, tenant_id=loja.tenant.id)
    await service.adicionar_item(
        session, venda=rascunho, produto_id=loja.produto.id, quantidade=Decimal(2)
    )

    resultado = await service.sincronizar_venda(
        session,
        tenant_id=loja.tenant.id,
        registrada_no_aparelho_em=datetime.now(UTC),
        **_pacote(loja, quantidade="2", venda_id=rascunho.id),
    )

    linhas = (
        (
            await session.execute(
                select(ItemVenda).where(ItemVenda.venda_id == resultado.venda.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(linhas) == 1, "o item do rascunho sobrou junto com o do aparelho"
    assert resultado.venda.total == Decimal("20.00")
    assert await comercial.saldo_do_produto(session, loja.produto.id) == Decimal(8)


async def test_o_rascunho_nao_sobra_aberto(session: AsyncSession) -> None:
    """Rascunho aberto esquecido é retomado na próxima abertura do PDV.

    O operador veria uma venda com itens que o cliente já levou e pagou. Por isso não
    pode sobrar nenhuma venda aberta depois da sincronização.
    """
    loja = await _loja(session, "10")
    rascunho = await service.abrir_venda(session, tenant_id=loja.tenant.id)
    await service.adicionar_item(
        session, venda=rascunho, produto_id=loja.produto.id, quantidade=Decimal(1)
    )

    await service.sincronizar_venda(
        session,
        tenant_id=loja.tenant.id,
        registrada_no_aparelho_em=datetime.now(UTC),
        **_pacote(loja, quantidade="1", venda_id=rascunho.id),
    )

    abertas = (
        (
            await session.execute(
                select(Venda).where(Venda.status == StatusVenda.ABERTA)
            )
        )
        .scalars()
        .all()
    )
    assert abertas == []


async def test_o_pagamento_do_rascunho_nao_fica_para_tras(session: AsyncSession) -> None:
    """Pagamento parcial lançado com rede, e o aparelho termina a venda inteira.

    Somar os dois faria a venda parecer paga em dobro e o caixa esperar dinheiro que não
    existe na gaveta.
    """
    loja = await _loja(session, "10")
    rascunho = await service.abrir_venda(session, tenant_id=loja.tenant.id)
    await service.adicionar_item(
        session, venda=rascunho, produto_id=loja.produto.id, quantidade=Decimal(2)
    )
    await service.registrar_pagamento(
        session, venda=rascunho, forma=FormaPagamento.DINHEIRO, valor=Decimal("5.00")
    )

    resultado = await service.sincronizar_venda(
        session,
        tenant_id=loja.tenant.id,
        registrada_no_aparelho_em=datetime.now(UTC),
        **_pacote(loja, quantidade="2", venda_id=rascunho.id),
    )

    assert await service.total_pago(session, resultado.venda) == Decimal("20.00")


async def test_venda_cancelada_aqui_e_recusada_com_motivo(session: AsyncSession) -> None:
    """Duas pessoas discordaram sobre a mesma venda, e isso precisa aparecer.

    Ressuscitar calada a venda que alguém cancelou esconderia a divergência — e a
    divergência é o produto, não o defeito. A recusa fica na fila do aparelho com o
    motivo, para alguém olhar.
    """
    loja = await _loja(session, "10")
    rascunho = await service.abrir_venda(session, tenant_id=loja.tenant.id)
    await service.adicionar_item(
        session, venda=rascunho, produto_id=loja.produto.id, quantidade=Decimal(1)
    )
    await service.cancelar_venda(session, venda=rascunho)

    with pytest.raises(service.PdvError, match="cancelada"):
        await service.sincronizar_venda(
            session,
            tenant_id=loja.tenant.id,
            registrada_no_aparelho_em=datetime.now(UTC),
            **_pacote(loja, quantidade="1", venda_id=rascunho.id),
        )
