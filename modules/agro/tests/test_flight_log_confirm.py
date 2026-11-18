"""Confirmar o registro de voo importado: voos, horímetro, estoque e planejamento.

Fatia de confirmação da importação do DJI SmartFarm. O preview lê e propõe; aqui a pessoa
confirmou, e o que acontece passa a valer — vai para o documento do produtor e para o
relatório mensal do MAPA.

Duas decisões do dono do projeto, de 17/11/2026, estão sob teste aqui:

- **O executado prevalece sobre o planejado.** A área e o volume que o equipamento mediu
  são os que ficam, e a divergência com o planejamento aparece em aviso.
- **Voo auxiliar não é descartado.** Translado e calibração não entram no relatório e
  entram no horímetro, porque é o desgaste deles que faz a revisão vencer.

Além disso, duas coisas que só um teste contra banco de verdade pega: a transação única
(estoque e voo entram juntos ou não entram) e a reimportação do mesmo arquivo, que não
pode dobrar hora de voo.
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
from decko_modules.agro import service
from decko_modules.agro.models import Aircraft, Client, Flight, OperationalPlan, Property
from decko_modules.comercial import service as comercial
from decko_modules.comercial.models import Produto, TipoMovimento, Unidade
from decko_modules.core.models import Tenant


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        await session.begin()
        try:
            yield session
        finally:
            await session.rollback()


class Operacao:
    def __init__(
        self,
        tenant: Tenant,
        aircraft: Aircraft,
        plano: OperationalPlan,
        produto: Produto,
        unidade: Unidade,
    ) -> None:
        self.tenant = tenant
        self.aircraft = aircraft
        self.plano = plano
        self.produto = produto
        self.unidade = unidade


async def _operacao(session: AsyncSession, *, estoque: str = "100") -> Operacao:
    tenant = Tenant(name="Pulverização do teste", slug=f"pulv-{uuid.uuid4().hex[:8]}")
    session.add(tenant)
    await session.flush()
    await bind_tenant(session, tenant.id)

    aircraft = Aircraft(
        tenant_id=tenant.id, prefixo=f"PP-{uuid.uuid4().hex[:3].upper()}", numero_serie="SERIE-1"
    )
    cliente = Client(tenant_id=tenant.id, nome="Fazenda do teste", cpf_cnpj="12345678000195")
    session.add_all([aircraft, cliente])
    await session.flush()

    propriedade = Property(
        tenant_id=tenant.id,
        client_id=cliente.id,
        nome="Talhão do teste",
        municipio="Jataí",
        uf="GO",
    )
    session.add(propriedade)
    await session.flush()

    plano = OperationalPlan(
        tenant_id=tenant.id,
        numero=await service.next_plan_number(session, tenant.id),
        client_id=cliente.id,
        property_id=propriedade.id,
        area_ha=Decimal("30.0000"),
    )
    session.add(plano)

    unidade = await comercial.criar_unidade(
        session, tenant_id=tenant.id, nome=f"Litro {uuid.uuid4().hex[:4]}", simbolo="L"
    )
    produto = Produto(
        tenant_id=tenant.id,
        codigo=f"DEF-{uuid.uuid4().hex[:6]}",
        nome="Herbicida do teste",
        unidade_id=unidade.id,
        preco_venda=Decimal("100.00"),
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

    return Operacao(tenant, aircraft, plano, produto, unidade)


NO_ARQUIVO = datetime(2026, 8, 15, 18, 51, 36)


def _voo(
    *,
    minutos_depois: int = 0,
    duracao: int = 407,
    serie: str | None = "SERIE-1",
    aircraft_id: uuid.UUID | None = None,
) -> service.VooParaGravar:
    """Um voo como o operador confirmou: com fuso escolhido, e o instante do arquivo."""
    no_arquivo = NO_ARQUIVO + timedelta(minutes=minutos_depois)
    # Três horas a menos: é o deslocamento que a tela propõe para este arquivo.
    local = no_arquivo.replace(tzinfo=UTC) - timedelta(hours=3)
    return service.VooParaGravar(
        comecou_em=local,
        terminou_em=local + timedelta(seconds=duracao),
        comecou_em_arquivo=no_arquivo,
        duracao_segundos=duracao,
        equipamento_serie=serie,
        equipamento_apelido="Valkyria",
        piloto="Piloto de teste",
        aircraft_id=aircraft_id,
    )


def _aplicacao(
    operacao: Operacao,
    *,
    area: str = "32.2000",
    volume: str = "290.34",
    voos: list[service.VooParaGravar] | None = None,
    insumos: list[service.InsumoParaBaixar] | None = None,
    plan_id: uuid.UUID | None = None,
) -> service.AplicacaoParaGravar:
    return service.AplicacaoParaGravar(
        plot_id="plot-a",
        talhao="Milho 1",
        aircraft_id=operacao.aircraft.id,
        plan_id=plan_id,
        area_ha=Decimal(area),
        volume_l=Decimal(volume),
        largura_faixa_m=Decimal("14.12"),
        altura_voo_m=Decimal("6.00"),
        voos=voos or [_voo(), _voo(minutos_depois=12)],
        insumos=insumos or [],
    )


# ----------------------------------------------------------------- gravar os voos


async def test_a_aplicacao_e_os_voos_dela_sao_gravados(session: AsyncSession) -> None:
    operacao = await _operacao(session)

    resultado = await service.confirmar_voos(
        session,
        tenant_id=operacao.tenant.id,
        aplicacoes=[_aplicacao(operacao)],
        auxiliares=[],
    )

    assert resultado.aplicacoes == 1
    assert resultado.voos_gravados == 2
    linhas = (await session.execute(select(Flight))).scalars().all()
    assert len(linhas) == 2
    assert all(linha.is_spraying for linha in linhas)
    assert all(linha.aircraft_id == operacao.aircraft.id for linha in linhas)
    # A área fica na primeira linha da aplicação: ratear por voo inventaria precisão que o
    # arquivo não dá, e somar em todas contaria a área duas vezes.
    assert sum(linha.area_ha or Decimal(0) for linha in linhas) == Decimal("32.2000")


async def test_o_voo_auxiliar_entra_marcado_como_quem_nao_pulverizou(
    session: AsyncSession,
) -> None:
    """Translado e calibração não vão ao relatório do MAPA, e não são descartados."""
    operacao = await _operacao(session)

    await service.confirmar_voos(
        session,
        tenant_id=operacao.tenant.id,
        aplicacoes=[],
        auxiliares=[_voo(minutos_depois=40, duracao=501, aircraft_id=operacao.aircraft.id)],
    )

    linha = (await session.execute(select(Flight))).scalars().one()
    assert linha.is_spraying is False
    assert linha.area_ha is None
    assert linha.duracao_segundos == 501


async def test_o_instante_do_arquivo_fica_guardado_junto_com_o_escolhido(
    session: AsyncSession,
) -> None:
    """O bruto continua verdadeiro se amanhã se descobrir que o fuso do arquivo era outro."""
    operacao = await _operacao(session)

    await service.confirmar_voos(
        session,
        tenant_id=operacao.tenant.id,
        aplicacoes=[_aplicacao(operacao, voos=[_voo()])],
        auxiliares=[],
    )

    linha = (await session.execute(select(Flight))).scalars().one()
    assert linha.comecou_em_arquivo == NO_ARQUIVO
    assert linha.comecou_em.hour == 15, "o escolhido é o do arquivo menos três horas"


# ----------------------------------------------------------------- reimportar


async def test_reimportar_o_mesmo_arquivo_nao_dobra_hora_de_voo(
    session: AsyncSession,
) -> None:
    """O caso normal: o operador reimporta o mês inteiro para corrigir uma linha.

    Sem isto, as horas da frota dobrariam — e horímetro errado é revisão vencida sem
    ninguém saber.
    """
    operacao = await _operacao(session)
    await service.confirmar_voos(
        session,
        tenant_id=operacao.tenant.id,
        aplicacoes=[_aplicacao(operacao)],
        auxiliares=[],
    )

    segunda = await service.confirmar_voos(
        session,
        tenant_id=operacao.tenant.id,
        aplicacoes=[_aplicacao(operacao)],
        auxiliares=[],
    )

    assert segunda.voos_gravados == 0
    assert segunda.voos_repetidos == 2
    assert any("não entraram de novo" in aviso for aviso in segunda.avisos)
    assert len((await session.execute(select(Flight))).scalars().all()) == 2


async def test_voo_de_outro_horario_entra_mesmo_com_o_equipamento_igual(
    session: AsyncSession,
) -> None:
    """A conferência é por equipamento **e** instante: o dia seguinte é outro voo."""
    operacao = await _operacao(session)
    await service.confirmar_voos(
        session, tenant_id=operacao.tenant.id, aplicacoes=[_aplicacao(operacao)], auxiliares=[]
    )

    outro = await service.confirmar_voos(
        session,
        tenant_id=operacao.tenant.id,
        aplicacoes=[_aplicacao(operacao, voos=[_voo(minutos_depois=1440)])],
        auxiliares=[],
    )

    assert outro.voos_gravados == 1


# ----------------------------------------------------------------- o planejamento


async def test_o_executado_prevalece_e_a_divergencia_aparece(session: AsyncSession) -> None:
    """Decisão do dono do projeto: o que o equipamento mediu é o que vale.

    E a divergência é dita, não escondida: trinta hectares planejados viraram 32,2
    medidos, e quem confirmou precisa ver isso agora — não no fechamento do mês.
    """
    operacao = await _operacao(session)

    resultado = await service.confirmar_voos(
        session,
        tenant_id=operacao.tenant.id,
        aplicacoes=[_aplicacao(operacao, plan_id=operacao.plano.id)],
        auxiliares=[],
    )

    assert operacao.plano.area_ha == Decimal("32.2000")
    assert operacao.plano.ha_aplicado == Decimal("32.2000")
    # Horas de execução, que o relatório mensal exige: 814 segundos são 0,23 h.
    assert operacao.plano.tempo_servico == Decimal("0.23")
    assert operacao.plano.param_largura_faixa_m == Decimal("14.12")
    assert resultado.planos_atualizados == [operacao.plano.id]
    assert any("30.0000 ha" in aviso and "32.2000 ha" in aviso for aviso in resultado.avisos)


async def test_sem_divergencia_nao_inventa_aviso(session: AsyncSession) -> None:
    operacao = await _operacao(session)

    resultado = await service.confirmar_voos(
        session,
        tenant_id=operacao.tenant.id,
        aplicacoes=[_aplicacao(operacao, area="30.0000", plan_id=operacao.plano.id)],
        auxiliares=[],
    )

    assert not any("dizia" in aviso for aviso in resultado.avisos)


async def test_planejamento_inexistente_e_recusado(session: AsyncSession) -> None:
    operacao = await _operacao(session)

    with pytest.raises(service.PlanError, match="não encontrado"):
        await service.confirmar_voos(
            session,
            tenant_id=operacao.tenant.id,
            aplicacoes=[_aplicacao(operacao, plan_id=uuid.uuid4())],
            auxiliares=[],
        )


# ----------------------------------------------------------------- o estoque


async def test_o_insumo_escolhido_sai_do_estoque(session: AsyncSession) -> None:
    """A baixa é pelo serviço do `comercial`, com a quantidade que o operador confirmou.

    Não é o volume de calda: calda é mistura, e quase toda ela é água. Deduzir produto a
    partir de litro de calda poria no estoque uma baixa que não aconteceu.
    """
    operacao = await _operacao(session, estoque="100")

    resultado = await service.confirmar_voos(
        session,
        tenant_id=operacao.tenant.id,
        aplicacoes=[
            _aplicacao(
                operacao,
                insumos=[
                    service.InsumoParaBaixar(
                        produto_id=operacao.produto.id, quantidade=Decimal("48.3")
                    )
                ],
            )
        ],
        auxiliares=[],
    )

    assert resultado.baixas_de_estoque == 1
    saldo = await comercial.saldo_do_produto(session, operacao.produto.id)
    assert saldo == Decimal("51.7")


async def test_estoque_que_recusa_derruba_a_importacao_inteira(session: AsyncSession) -> None:
    """Estoque baixado sem registro da aplicação é pior do que a importação falhar.

    O caso aqui é o produto que controla lote sem lote informado — o `comercial` recusa, e
    a recusa sobe como erro de regra da pulverização, com a transação inteira intacta.
    """
    operacao = await _operacao(session)
    operacao.produto.controla_lote = True
    await session.flush()

    with pytest.raises(service.PlanError, match="baixa no estoque"):
        await service.confirmar_voos(
            session,
            tenant_id=operacao.tenant.id,
            aplicacoes=[
                _aplicacao(
                    operacao,
                    insumos=[
                        service.InsumoParaBaixar(
                            produto_id=operacao.produto.id, quantidade=Decimal("10")
                        )
                    ],
                )
            ],
            auxiliares=[],
        )


async def test_produto_inexistente_e_recusado_antes_de_mexer_no_estoque(
    session: AsyncSession,
) -> None:
    operacao = await _operacao(session)

    with pytest.raises(service.PlanError, match="Produto não encontrado"):
        await service.confirmar_voos(
            session,
            tenant_id=operacao.tenant.id,
            aplicacoes=[
                _aplicacao(
                    operacao,
                    insumos=[
                        service.InsumoParaBaixar(
                            produto_id=uuid.uuid4(), quantidade=Decimal("1")
                        )
                    ],
                )
            ],
            auxiliares=[],
        )


# ----------------------------------------------------------------- o horímetro


async def test_o_horimetro_soma_aplicacao_e_translado_separados(
    session: AsyncSession,
) -> None:
    """É o que alimenta a manutenção: o desgaste não distingue aplicação de translado."""
    operacao = await _operacao(session)

    await service.confirmar_voos(
        session,
        tenant_id=operacao.tenant.id,
        aplicacoes=[_aplicacao(operacao, voos=[_voo(duracao=407)])],
        auxiliares=[
            _voo(minutos_depois=40, duracao=501, aircraft_id=operacao.aircraft.id),
        ],
    )

    horas = await service.horimetro_da_aeronave(session, operacao.aircraft.id)

    assert horas.voos == 2
    assert horas.segundos_aplicando == 407
    assert horas.segundos_auxiliar == 501
    assert horas.segundos_total == 908
    assert horas.area_ha == Decimal("32.2000")
    assert horas.primeiro_voo is not None


async def test_aeronave_sem_voo_tem_horimetro_zerado(session: AsyncSession) -> None:
    """Zero é resposta; erro não é. A tela de manutenção abre antes do primeiro voo."""
    operacao = await _operacao(session)

    horas = await service.horimetro_da_aeronave(session, operacao.aircraft.id)

    assert horas.voos == 0
    assert horas.segundos_total == 0
    assert horas.ultimo_voo is None
