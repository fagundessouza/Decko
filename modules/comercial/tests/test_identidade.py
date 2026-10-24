"""Reconhecer o mesmo item escrito de formas diferentes.

É o caso que o dono do projeto descreveu: o mesmo refrigerante chega
``COCA COLA 2L RET`` de um fornecedor e ``Refrigerante Coca-Cola 2 Litros Retornável`` de
outro, e o estoque não pode nascer com dois cadastros.

Decisões: ``docs/adr/0009-identidade-de-produto-e-entrada-por-nota.md``.
"""

import uuid
from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from decko.db import SessionFactory, bind_tenant
from decko_modules.comercial import identidade, service
from decko_modules.comercial.models import Produto, Unidade
from decko_modules.core.models import Tenant

FORNECEDOR = "00000000000100"


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        await session.begin()
        try:
            yield session
        finally:
            await session.rollback()


async def _loja(session: AsyncSession) -> tuple[Tenant, Unidade]:
    tenant = Tenant(name="Mercado de Teste", slug=f"ident-{uuid.uuid4().hex[:8]}")
    session.add(tenant)
    await session.flush()
    await bind_tenant(session, tenant.id)

    unidade = await service.criar_unidade(
        session, tenant_id=tenant.id, nome=f"Unidade {uuid.uuid4().hex[:4]}", simbolo="un"
    )
    return tenant, unidade


async def _produto(
    session: AsyncSession,
    tenant: Tenant,
    unidade: Unidade,
    nome: str,
    *,
    gtin: str | None = None,
    ncm: str | None = None,
) -> Produto:
    produto = Produto(
        tenant_id=tenant.id,
        codigo=f"SKU-{uuid.uuid4().hex[:8]}",
        nome=nome,
        unidade_id=unidade.id,
        gtin=gtin,
        ncm=ncm,
        preco_venda=Decimal("10.00"),
    )
    session.add(produto)
    await session.flush()
    return produto


# --------------------------------------------------------------- semelhança de nome


@pytest.mark.parametrize(
    ("abreviado", "completo"),
    [
        ("COCA COLA 2L RET", "Refrigerante Coca-Cola 2 Litros Retornável"),
        ("ARROZ TIO JOAO 5KG", "Arroz Tio João Tipo 1 5kg"),
        ("DET YPE NEUTRO 500ML", "Detergente Ypê Neutro 500ml"),
    ],
)
def test_abreviacao_e_nome_completo_se_parecem(abreviado: str, completo: str) -> None:
    """O caso central: a nota abrevia, o cadastro escreve por extenso."""
    assert identidade.semelhanca(abreviado, completo) >= identidade.LIMITE_SEMELHANCA


@pytest.mark.parametrize(
    ("um", "outro"),
    [
        ("COCA COLA 2L RET", "Refrigerante Pepsi 2 Litros"),
        ("ARROZ TIO JOAO 5KG", "Feijão Carioca Camil 1kg"),
        ("DET YPE NEUTRO 500ML", "Desinfetante Pinho Sol 1L"),
    ],
)
def test_produtos_diferentes_nao_se_parecem(um: str, outro: str) -> None:
    """Marca diferente é produto diferente, e o pedido foi explícito nisso."""
    assert identidade.semelhanca(um, outro) < identidade.LIMITE_SEMELHANCA


def test_acento_e_caixa_nao_atrapalham() -> None:
    assert identidade.semelhanca("RETORNAVEL", "Retornável") == 1.0


# --------------------------------------------------------------- identificação


async def test_gtin_igual_liga_sozinho(session: AsyncSession) -> None:
    """O código de barras existe para isto: dizer item, marca, modelo e tamanho."""
    tenant, unidade = await _loja(session)
    produto = await _produto(
        session, tenant, unidade, "Coca-Cola 2 Litros Retornável", gtin="7894900011517"
    )

    candidatos = await identidade.identificar(
        session, descricao="NOME QUE NAO PARECE COM NADA", gtin="7894900011517"
    )

    assert [c.produto_id for c in candidatos] == [produto.id]
    assert candidatos[0].origem is identidade.Origem.GTIN
    assert candidatos[0].automatico is True


async def test_semelhanca_sugere_mas_nao_liga_sozinho(session: AsyncSession) -> None:
    """Palpite que acerta 95% das vezes erra o estoque em 5%, e ninguém descobre qual."""
    tenant, unidade = await _loja(session)
    produto = await _produto(session, tenant, unidade, "Refrigerante Coca-Cola 2 Litros Retornável")

    candidatos = await identidade.identificar(session, descricao="COCA COLA 2L RET")

    assert [c.produto_id for c in candidatos] == [produto.id]
    assert candidatos[0].origem is identidade.Origem.SEMELHANCA
    assert candidatos[0].automatico is False


async def test_produto_novo_nao_recebe_palpite(session: AsyncSession) -> None:
    """Sem nada parecido, a lista vem vazia e o lojista cadastra a partir da nota."""
    tenant, unidade = await _loja(session)
    await _produto(session, tenant, unidade, "Refrigerante Coca-Cola 2 Litros")

    candidatos = await identidade.identificar(session, descricao="PARAFUSO SEXTAVADO 3MM")

    assert candidatos == []


async def test_ncm_diferente_derruba_o_palpite(session: AsyncSession) -> None:
    """O NCM não identifica, mas descarta: classificação diferente, item diferente."""
    tenant, unidade = await _loja(session)
    await _produto(session, tenant, unidade, "Refrigerante Coca-Cola 2 Litros", ncm="22021000")

    candidatos = await identidade.identificar(
        session, descricao="REFRIGERANTE COCA COLA 2 LITROS", ncm="84714900"
    )

    assert candidatos == []


async def test_equivalencia_confirmada_liga_sozinho_na_proxima_nota(
    session: AsyncSession,
) -> None:
    """É o que faz a ferramenta melhorar com o uso em vez de perguntar todo mês."""
    tenant, unidade = await _loja(session)
    produto = await _produto(session, tenant, unidade, "Coca-Cola 2 Litros Retornável")

    await identidade.lembrar_equivalencia(
        session,
        tenant_id=tenant.id,
        produto_id=produto.id,
        fornecedor_cnpj=FORNECEDOR,
        fornecedor_nome="Distribuidora Exemplo",
        codigo_fornecedor="CC2LRET",
        descricao_fornecedor="COCA COLA 2L RET",
    )

    candidatos = await identidade.identificar(
        session,
        descricao="QUALQUER COISA",
        fornecedor_cnpj=FORNECEDOR,
        codigo_fornecedor="CC2LRET",
    )

    assert [c.produto_id for c in candidatos] == [produto.id]
    assert candidatos[0].origem is identidade.Origem.FORNECEDOR
    assert candidatos[0].automatico is True


async def test_confirmar_de_novo_corrige_em_vez_de_duplicar(session: AsyncSession) -> None:
    """O lojista pode ter ligado ao produto errado e estar consertando."""
    tenant, unidade = await _loja(session)
    errado = await _produto(session, tenant, unidade, "Coca-Cola 600ml")
    certo = await _produto(session, tenant, unidade, "Coca-Cola 2 Litros Retornável")

    for produto in (errado, certo):
        await identidade.lembrar_equivalencia(
            session,
            tenant_id=tenant.id,
            produto_id=produto.id,
            fornecedor_cnpj=FORNECEDOR,
            fornecedor_nome="Distribuidora Exemplo",
            codigo_fornecedor="CC2LRET",
            descricao_fornecedor="COCA COLA 2L RET",
        )

    candidatos = await identidade.identificar(
        session,
        descricao="COCA COLA 2L RET",
        fornecedor_cnpj=FORNECEDOR,
        codigo_fornecedor="CC2LRET",
    )

    assert [c.produto_id for c in candidatos] == [certo.id]


async def test_equivalencia_de_uma_empresa_nao_vale_para_outra(session: AsyncSession) -> None:
    """Isolamento garantido pelo banco, como no resto do sistema."""
    primeira, unidade = await _loja(session)
    produto = await _produto(session, primeira, unidade, "Coca-Cola 2 Litros")
    await identidade.lembrar_equivalencia(
        session,
        tenant_id=primeira.id,
        produto_id=produto.id,
        fornecedor_cnpj=FORNECEDOR,
        fornecedor_nome="Distribuidora Exemplo",
        codigo_fornecedor="CC2LRET",
        descricao_fornecedor="COCA COLA 2L RET",
    )

    await _loja(session)
    session.expunge_all()

    candidatos = await identidade.identificar(
        session,
        descricao="COCA COLA 2L RET",
        fornecedor_cnpj=FORNECEDOR,
        codigo_fornecedor="CC2LRET",
    )

    assert candidatos == []
