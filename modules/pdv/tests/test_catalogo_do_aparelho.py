"""O recorte do catálogo que viaja para o aparelho.

Vender sem rede exige o catálogo no aparelho, e "o catálogo inteiro" não é resposta: uma
distribuidora tem dezenas de milhares de itens, e o alvo deste projeto inclui celular
fraco e PC de caixa antigo. A ADR 0019 deixou isso em aberto de propósito; a resposta
está na `docs/adr/0022-offline-first-as-respostas.md`, decisão 3.

O recorte é **por uso**, e não por tamanho do cadastro: catálogo que cabe vai inteiro, e
catálogo grande manda o que o balcão alcança de verdade num dia sem rede.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from decko.db import SessionFactory, bind_tenant
from decko_modules.comercial import service as comercial
from decko_modules.comercial.models import Produto, Unidade
from decko_modules.core.models import Tenant
from decko_modules.pdv import service
from decko_modules.pdv.models import ItemVenda, Venda


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        await session.begin()
        try:
            yield session
        finally:
            await session.rollback()


async def _loja(session: AsyncSession) -> tuple[Tenant, Unidade]:
    tenant = Tenant(name="Loja do catálogo", slug=f"catalogo-{uuid.uuid4().hex[:8]}")
    session.add(tenant)
    await session.flush()
    await bind_tenant(session, tenant.id)

    unidade = await comercial.criar_unidade(
        session, tenant_id=tenant.id, nome=f"Unidade {uuid.uuid4().hex[:4]}", simbolo="un"
    )
    return tenant, unidade


async def _produto(
    session: AsyncSession, tenant: Tenant, unidade: Unidade, nome: str, *, ativo: bool = True
) -> Produto:
    produto = Produto(
        tenant_id=tenant.id,
        codigo=f"COD-{uuid.uuid4().hex[:8]}",
        nome=nome,
        unidade_id=unidade.id,
        preco_venda=Decimal("10.00"),
        ativo=ativo,
    )
    session.add(produto)
    await session.flush()
    return produto


async def _vendido_em(
    session: AsyncSession, tenant: Tenant, produto: Produto, quando: datetime
) -> None:
    """Uma venda com data escolhida, para medir o recorte dos noventa dias."""
    venda = Venda(tenant_id=tenant.id)
    session.add(venda)
    await session.flush()
    venda.created_at = quando

    session.add(
        ItemVenda(
            tenant_id=tenant.id,
            venda_id=venda.id,
            produto_id=produto.id,
            descricao=produto.nome,
            quantidade=Decimal(1),
            preco_unitario=Decimal("10.00"),
            total=Decimal("10.00"),
            unidade_id=produto.unidade_id,
        )
    )
    await session.flush()


async def test_catalogo_que_cabe_vai_inteiro(session: AsyncSession) -> None:
    """Numa padaria o catálogo inteiro cabe, e aí não falta nada no balcão."""
    tenant, unidade = await _loja(session)
    await _produto(session, tenant, unidade, "Pão francês")
    await _produto(session, tenant, unidade, "Leite integral")

    catalogo = await service.catalogo_do_aparelho(session, tenant_id=tenant.id)

    assert {produto.nome for produto in catalogo} == {"Pão francês", "Leite integral"}


async def test_produto_desativado_nao_viaja(session: AsyncSession) -> None:
    """Desativado não é vendido no balcão, e peso de pacote é requisito."""
    tenant, unidade = await _loja(session)
    await _produto(session, tenant, unidade, "Vendido hoje")
    await _produto(session, tenant, unidade, "Saiu de linha", ativo=False)

    catalogo = await service.catalogo_do_aparelho(session, tenant_id=tenant.id)

    assert [produto.nome for produto in catalogo] == ["Vendido hoje"]


async def test_catalogo_grande_manda_so_o_que_vendeu(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Passando do teto, o recorte é o que o balcão alcança: o que vendeu de verdade.

    O teto real são dois mil itens; aqui ele é abaixado para o teste não precisar criar
    dois mil produtos para afirmar uma regra que não depende do número.
    """
    monkeypatch.setattr(service, "TETO_DO_CATALOGO", 2)
    tenant, unidade = await _loja(session)

    recente = await _produto(session, tenant, unidade, "Vende toda semana")
    antigo = await _produto(session, tenant, unidade, "Vendeu no ano passado")
    await _produto(session, tenant, unidade, "Nunca vendeu")

    agora = datetime.now(UTC)
    await _vendido_em(session, tenant, recente, agora - timedelta(days=10))
    await _vendido_em(session, tenant, antigo, agora - timedelta(days=200))

    catalogo = await service.catalogo_do_aparelho(session, tenant_id=tenant.id)

    nomes = {produto.nome for produto in catalogo}
    assert nomes == {"Vende toda semana"}
    assert "Vendeu no ano passado" not in nomes, "noventa dias é o recorte, e ele vale"
    assert "Nunca vendeu" not in nomes


async def test_a_borda_dos_noventa_dias(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ontem dentro da janela entra; ontem fora dela, não. A borda é onde se erra."""
    monkeypatch.setattr(service, "TETO_DO_CATALOGO", 1)
    tenant, unidade = await _loja(session)

    dentro = await _produto(session, tenant, unidade, "Dentro da janela")
    fora = await _produto(session, tenant, unidade, "Fora da janela")

    agora = datetime.now(UTC)
    await _vendido_em(session, tenant, dentro, agora - timedelta(days=89))
    await _vendido_em(session, tenant, fora, agora - timedelta(days=91))

    catalogo = await service.catalogo_do_aparelho(session, tenant_id=tenant.id)

    assert {produto.nome for produto in catalogo} == {"Dentro da janela"}


async def test_o_catalogo_e_so_desta_empresa(session: AsyncSession) -> None:
    """O isolamento vale aqui como em todo o resto: é o banco que o garante."""
    tenant, unidade = await _loja(session)
    await _produto(session, tenant, unidade, "Da loja certa")

    outra, outra_unidade = await _loja(session)
    await _produto(session, outra, outra_unidade, "Da loja vizinha")

    # A sessão está amarrada na segunda loja depois de `_loja`.
    catalogo = await service.catalogo_do_aparelho(session, tenant_id=outra.id)

    assert [produto.nome for produto in catalogo] == ["Da loja vizinha"]
