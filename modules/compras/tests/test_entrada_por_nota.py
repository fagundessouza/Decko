"""Entrada de mercadoria pela nota do fornecedor.

O que precisa funcionar, nesta ordem de importância:

1. O mesmo produto, escrito de dois jeitos por dois fornecedores, **não** vira dois
   cadastros.
2. Nada entra no estoque antes de a nota ser conferida.
3. A decisão do lojista é lembrada, e a nota seguinte daquele fornecedor entra sozinha.

Decisões: ``docs/adr/0009-identidade-de-produto-e-entrada-por-nota.md``.
"""

import uuid
from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from decko.db import SessionFactory, bind_tenant
from decko_modules.comercial import service as comercial
from decko_modules.comercial.models import Produto, Unidade
from decko_modules.compras import service
from decko_modules.compras.models import OrigemVinculo, StatusNota
from decko_modules.compras.nfe import NotaInvalidaError, ler
from decko_modules.core.models import Tenant

from .fixtures import (
    CNPJ_DISTRIBUIDOR_A,
    GTIN_COCA,
    NAO_E_NOTA,
    NOTA_DISTRIBUIDOR_A,
    NOTA_DISTRIBUIDOR_B,
    NOTA_SEM_GTIN,
)


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        await session.begin()
        try:
            yield session
        finally:
            await session.rollback()


async def _loja(session: AsyncSession) -> tuple[Tenant, Unidade]:
    tenant = Tenant(name="Mercado de Teste", slug=f"compras-{uuid.uuid4().hex[:8]}")
    session.add(tenant)
    await session.flush()
    await bind_tenant(session, tenant.id)

    unidade = await comercial.criar_unidade(
        session, tenant_id=tenant.id, nome=f"Unidade {uuid.uuid4().hex[:4]}", simbolo="un"
    )
    return tenant, unidade


async def _conferir_tudo_como_novo(session: AsyncSession, nota, unidade: Unidade) -> None:
    """Marca todo item pendente como produto novo, que é o caso da primeira nota."""
    for item in nota.itens:
        if item.produto_id is None:
            await service.marcar_como_novo(session, nota=nota, item=item, unidade_id=unidade.id)


# --------------------------------------------------------------- leitura do XML


def test_le_a_nota_inteira() -> None:
    lida = ler(NOTA_DISTRIBUIDOR_A)

    assert lida.emitente_cnpj == CNPJ_DISTRIBUIDOR_A
    assert lida.emitente_nome == "Distribuidora Alfa Ltda"
    assert lida.numero == "1001"
    assert lida.valor_total == Decimal("360.00")
    assert [item.descricao for item in lida.itens] == [
        "COCA COLA 2L RET",
        "ARROZ TIO JOAO 5KG",
    ]
    assert lida.itens[0].gtin == GTIN_COCA
    assert lida.itens[0].ncm == "22021000"


def test_sem_gtin_vira_ausencia_e_nao_texto() -> None:
    """``SEM GTIN`` é como o emitente diz que o produto não tem código de barras."""
    lida = ler(NOTA_DISTRIBUIDOR_A)
    assert lida.itens[1].gtin is None


def test_arquivo_que_nao_e_nota_diz_o_que_fazer() -> None:
    with pytest.raises(NotaInvalidaError, match="XML da nota"):
        ler(NAO_E_NOTA)


# --------------------------------------------------------------- importar e conferir


async def test_nada_entra_no_estoque_antes_de_confirmar(session: AsyncSession) -> None:
    tenant, _unidade = await _loja(session)

    nota = await service.importar(session, tenant_id=tenant.id, xml=NOTA_DISTRIBUIDOR_A)

    assert nota.status is StatusNota.RASCUNHO
    assert len(await service.pendentes(session, nota)) == 2
    assert (await session.execute(select(Produto))).scalars().all() == []


async def test_nota_nao_fecha_com_item_sem_destino(session: AsyncSession) -> None:
    tenant, _unidade = await _loja(session)
    nota = await service.importar(session, tenant_id=tenant.id, xml=NOTA_DISTRIBUIDOR_A)

    with pytest.raises(service.ComprasError, match="sem destino"):
        await service.confirmar(session, nota=nota, tenant_id=tenant.id)


async def test_mesma_nota_nao_entra_duas_vezes(session: AsyncSession) -> None:
    """O arquivo fica no e-mail; importar de novo dobraria o estoque."""
    tenant, _unidade = await _loja(session)
    await service.importar(session, tenant_id=tenant.id, xml=NOTA_DISTRIBUIDOR_A)

    with pytest.raises(service.NotaDuplicadaError):
        await service.importar(session, tenant_id=tenant.id, xml=NOTA_DISTRIBUIDOR_A)


async def test_confirmar_cadastra_e_lanca(session: AsyncSession) -> None:
    tenant, unidade = await _loja(session)
    nota = await service.importar(session, tenant_id=tenant.id, xml=NOTA_DISTRIBUIDOR_A)
    await _conferir_tudo_como_novo(session, nota, unidade)

    resultado = await service.confirmar(session, nota=nota, tenant_id=tenant.id)

    assert resultado.produtos_criados == 2
    assert resultado.itens_lancados == 2
    assert nota.status is StatusNota.CONFIRMADA

    coca = await session.scalar(select(Produto).where(Produto.gtin == GTIN_COCA))
    assert coca is not None
    # Nasce com o que a nota trouxe, que é mais do que o cadastro à mão costuma receber.
    assert coca.ncm == "22021000"
    assert coca.preco_custo == Decimal("7.5000")
    assert await comercial.saldo_do_produto(session, coca.id) == Decimal(24)


# --------------------------------------------------------------- o caso central


async def test_mesmo_produto_de_dois_fornecedores_nao_duplica(session: AsyncSession) -> None:
    """O caso que motivou o módulo.

    Fornecedor A manda ``COCA COLA 2L RET``; fornecedor B manda
    ``Refrigerante Coca-Cola 2 Litros Retornável``. É o mesmo refrigerante, e o estoque
    não pode nascer com dois cadastros e meio saldo em cada.
    """
    tenant, unidade = await _loja(session)

    primeira = await service.importar(session, tenant_id=tenant.id, xml=NOTA_DISTRIBUIDOR_A)
    await _conferir_tudo_como_novo(session, primeira, unidade)
    await service.confirmar(session, nota=primeira, tenant_id=tenant.id)

    segunda = await service.importar(session, tenant_id=tenant.id, xml=NOTA_DISTRIBUIDOR_B)

    # Reconhecido pelo código de barras, sem perguntar nada.
    assert await service.pendentes(session, segunda) == []
    assert segunda.itens[0].origem_vinculo is OrigemVinculo.GTIN

    await service.confirmar(session, nota=segunda, tenant_id=tenant.id)

    produtos = (
        (await session.execute(select(Produto).where(Produto.gtin == GTIN_COCA))).scalars().all()
    )
    assert len(produtos) == 1
    # 24 da primeira nota mais 12 da segunda, num cadastro só.
    assert await comercial.saldo_do_produto(session, produtos[0].id) == Decimal(36)


async def test_sem_gtin_o_sistema_sugere_mas_nao_decide(session: AsyncSession) -> None:
    """Sem código de barras sobra o nome, e nome é palpite: quem decide é o lojista."""
    tenant, unidade = await _loja(session)

    primeira = await service.importar(session, tenant_id=tenant.id, xml=NOTA_DISTRIBUIDOR_A)
    await _conferir_tudo_como_novo(session, primeira, unidade)
    await service.confirmar(session, nota=primeira, tenant_id=tenant.id)

    terceira = await service.importar(session, tenant_id=tenant.id, xml=NOTA_SEM_GTIN)
    item = terceira.itens[0]

    assert item.produto_id is None, "palpite de nome não pode ligar sozinho"

    sugestoes = await service.sugestoes_para(session, terceira, item)
    assert sugestoes, "mas tem de sugerir o refrigerante que já existe"
    assert sugestoes[0].nome == "COCA COLA 2L RET"
    assert sugestoes[0].automatico is False


async def test_decisao_do_lojista_vale_para_a_proxima_nota(session: AsyncSession) -> None:
    """É o que faz a ferramenta melhorar com o uso em vez de perguntar todo mês."""
    tenant, unidade = await _loja(session)

    primeira = await service.importar(session, tenant_id=tenant.id, xml=NOTA_DISTRIBUIDOR_A)
    await _conferir_tudo_como_novo(session, primeira, unidade)
    await service.confirmar(session, nota=primeira, tenant_id=tenant.id)
    coca = await session.scalar(select(Produto).where(Produto.gtin == GTIN_COCA))
    assert coca is not None

    # O lojista liga o item sem GTIN ao refrigerante que já existe.
    terceira = await service.importar(session, tenant_id=tenant.id, xml=NOTA_SEM_GTIN)
    await service.vincular(session, nota=terceira, item=terceira.itens[0], produto_id=coca.id)
    await service.confirmar(session, nota=terceira, tenant_id=tenant.id)

    # A mesma nota, do mesmo fornecedor, chega de novo no mês seguinte.
    repetida = NOTA_SEM_GTIN.replace("3003", "3004").replace(
        "35240199888777000166550010000000031000000039",
        "35240199888777000166550010000000041000000040",
    )
    seguinte = await service.importar(session, tenant_id=tenant.id, xml=repetida)

    assert await service.pendentes(session, seguinte) == []
    assert seguinte.itens[0].produto_id == coca.id
    assert seguinte.itens[0].origem_vinculo is OrigemVinculo.FORNECEDOR


async def test_entrada_em_caixa_converte_para_a_unidade_base(session: AsyncSession) -> None:
    """A nota diz ``FD``; quantas unidades tem o fardo, só o lojista sabe dizer."""
    tenant, unidade = await _loja(session)
    fardo = await comercial.criar_unidade(
        session,
        tenant_id=tenant.id,
        nome=f"Fardo 6 {uuid.uuid4().hex[:4]}",
        referencia_id=unidade.id,
        fator_relativo=Decimal(6),
    )

    nota = await service.importar(session, tenant_id=tenant.id, xml=NOTA_DISTRIBUIDOR_A)
    arroz = nota.itens[1]
    await service.marcar_como_novo(session, nota=nota, item=arroz, unidade_id=fardo.id)
    await service.marcar_como_novo(session, nota=nota, item=nota.itens[0], unidade_id=unidade.id)

    await service.confirmar(session, nota=nota, tenant_id=tenant.id)

    produto = await session.scalar(select(Produto).where(Produto.nome == "ARROZ TIO JOAO 5KG"))
    assert produto is not None
    # 10 fardos de 6 entram como 60 na unidade base.
    assert await comercial.saldo_do_produto(session, produto.id) == Decimal(60)


async def test_nota_descartada_nao_lanca_nada(session: AsyncSession) -> None:
    tenant, _unidade = await _loja(session)
    nota = await service.importar(session, tenant_id=tenant.id, xml=NOTA_DISTRIBUIDOR_A)

    await service.descartar(session, nota=nota)

    assert nota.status is StatusNota.DESCARTADA
    assert (await session.execute(select(Produto))).scalars().all() == []

    with pytest.raises(service.ComprasError, match="descartada"):
        await service.confirmar(session, nota=nota, tenant_id=tenant.id)
