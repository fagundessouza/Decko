"""Dado-semente com identidade estável.

O que estes testes existem para provar não é que a semente entra — é que ela entra **uma
vez** e que o que o cliente faz depois vale mais que ela. Daí os casos centrais serem os
três de não-escrita: reativar não duplica, linha apagada não volta, e linha renomeada não
é recriada nem reivindicada.

A importação de ``decko_modules.comercial`` é a premissa, não enfeite: é ela que registra
o carregador na porta do host. Fora de teste quem importa é a aplicação, ao montar as
rotas, ou o comando administrativo.

Decisão: ``docs/adr/0010-dado-semente-com-identidade-estavel.md``.
"""

import uuid
from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

# Importado pelo efeito: é a importação do pacote que registra o carregador de semente.
import decko_modules.comercial  # noqa: F401
from decko.db import SessionFactory, bind_tenant
from decko_modules.comercial.models import Unidade
from decko_modules.core import activation, seed
from decko_modules.core.cli import _bootstrap
from decko_modules.core.models import SeedRecord, SeedStatus, Tenant

PASSWORD = "senha-local-de-teste-123"
COMERCIAL = "comercial"
NOMES = ("Unidade", "Quilograma", "Litro")


async def _empresa(session: AsyncSession, *, modules: list[str]) -> uuid.UUID:
    sufixo = uuid.uuid4().hex[:8]
    tenant, _user, _granted = await _bootstrap(
        session,
        tenant_name="Empresa de Teste",
        tenant_slug=f"semente-{sufixo}",
        admin_email=f"admin-{sufixo}@teste-decko.com.br",
        admin_name="Administrador",
        password=PASSWORD,
        modules=modules,
    )
    return tenant.id


async def _unidades(session: AsyncSession, tenant_id: uuid.UUID) -> list[Unidade]:
    resultado = await session.execute(
        select(Unidade).where(Unidade.tenant_id == tenant_id).order_by(Unidade.nome)
    )
    return list(resultado.scalars().all())


async def _registros(session: AsyncSession, tenant_id: uuid.UUID) -> list[SeedRecord]:
    resultado = await session.execute(
        select(SeedRecord).where(SeedRecord.tenant_id == tenant_id).order_by(SeedRecord.ref)
    )
    return list(resultado.scalars().all())


async def _reativar(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Desliga e liga de novo. É o caminho pelo qual a carga roda uma segunda vez."""
    await activation.deactivate(session, tenant_id=tenant_id, module_name=COMERCIAL)
    await activation.activate(session, tenant_id=tenant_id, module_name=COMERCIAL)


@pytest_asyncio.fixture
async def criadas() -> AsyncIterator[list[uuid.UUID]]:
    tenants: list[uuid.UUID] = []
    yield tenants
    async with SessionFactory() as session, session.begin():
        for tenant_id in tenants:
            await session.execute(delete(Tenant).where(Tenant.id == tenant_id))


async def test_ativar_comercial_semeia_as_unidades_raiz(criadas: list[uuid.UUID]) -> None:
    async with SessionFactory() as session, session.begin():
        tenant_id = await _empresa(session, modules=[COMERCIAL])
        criadas.append(tenant_id)

        unidades = await _unidades(session, tenant_id)

        assert sorted(unidade.nome for unidade in unidades) == sorted(NOMES)
        # Raiz: fator 1 e apontando para si mesma. É o que o serviço resolve e um INSERT
        # direto erraria em silêncio, para converter errado depois.
        for unidade in unidades:
            assert unidade.fator == 1
            assert unidade.raiz_id == unidade.id
            assert unidade.referencia_id is None


async def test_reativar_nao_duplica(criadas: list[uuid.UUID]) -> None:
    async with SessionFactory() as session, session.begin():
        tenant_id = await _empresa(session, modules=[COMERCIAL])
        criadas.append(tenant_id)

        await _reativar(session, tenant_id)

        assert len(await _unidades(session, tenant_id)) == 3
        assert len(await _registros(session, tenant_id)) == 3


async def test_unidade_semeada_apagada_nao_volta(criadas: list[uuid.UUID]) -> None:
    """Ressuscitar o que alguém apagou de propósito é a falha pior: volta sem explicação."""
    async with SessionFactory() as session, session.begin():
        tenant_id = await _empresa(session, modules=[COMERCIAL])
        criadas.append(tenant_id)

        litro = next(u for u in await _unidades(session, tenant_id) if u.nome == "Litro")
        await session.execute(delete(Unidade).where(Unidade.id == litro.id))

        await _reativar(session, tenant_id)

        assert sorted(u.nome for u in await _unidades(session, tenant_id)) == [
            "Quilograma",
            "Unidade",
        ]
        removido = next(r for r in await _registros(session, tenant_id) if r.ref.endswith(".l"))
        assert removido.status is SeedStatus.REMOVIDO


async def test_renomear_a_unidade_nao_a_recria(criadas: list[uuid.UUID]) -> None:
    """Quem reconhece a semente é o ``ref``, não o nome — senão renomear criaria duplicata."""
    async with SessionFactory() as session, session.begin():
        tenant_id = await _empresa(session, modules=[COMERCIAL])
        criadas.append(tenant_id)

        unidade = next(u for u in await _unidades(session, tenant_id) if u.nome == "Unidade")
        unidade.nome = "Un"
        await session.flush()

        await _reativar(session, tenant_id)

        nomes = sorted(u.nome for u in await _unidades(session, tenant_id))
        assert nomes == ["Litro", "Quilograma", "Un"]


async def test_fingerprint_acusa_o_ajuste_do_cliente(criadas: list[uuid.UUID]) -> None:
    """É o que substitui o ``noupdate`` do Odoo: o sistema confere em vez de adivinhar."""
    async with SessionFactory() as session, session.begin():
        tenant_id = await _empresa(session, modules=[COMERCIAL])
        criadas.append(tenant_id)

        registro = next(r for r in await _registros(session, tenant_id) if r.ref.endswith(".kg"))
        quilograma = await session.get(Unidade, registro.row_id)
        assert quilograma is not None

        intacta_antes = seed.intacta(
            registro, {"nome": quilograma.nome, "simbolo": quilograma.simbolo}
        )
        quilograma.simbolo = "Kg"
        await session.flush()
        intacta_depois = seed.intacta(
            registro, {"nome": quilograma.nome, "simbolo": quilograma.simbolo}
        )

        assert intacta_antes is True
        assert intacta_depois is False


async def test_unidade_criada_a_mao_nao_e_reivindicada(criadas: list[uuid.UUID]) -> None:
    """A empresa que já montou o sistema de medidas fica com o dela.

    O nome é único por empresa, então sem a conferência a carga quebraria na restrição. E
    adotar a linha do cliente como semente seria pior: ela não é nossa para atualizar.
    """
    async with SessionFactory() as session, session.begin():
        tenant_id = await _empresa(session, modules=[])
        criadas.append(tenant_id)
        await bind_tenant(session, tenant_id)

        from decko_modules.comercial import service

        propria = await service.criar_unidade(
            session, tenant_id=tenant_id, nome="Unidade", simbolo="un"
        )

        await activation.activate(session, tenant_id=tenant_id, module_name=COMERCIAL)

        unidades = await _unidades(session, tenant_id)
        assert sorted(u.nome for u in unidades) == sorted(NOMES)
        # A dela continua sendo a dela: mesma linha, símbolo como ela escreveu.
        intacta = next(u for u in unidades if u.nome == "Unidade")
        assert intacta.id == propria.id
        assert intacta.simbolo == "un"
        # E não há registro de semente reivindicando-a.
        refs = [registro.ref for registro in await _registros(session, tenant_id)]
        assert refs == ["comercial.unidade.kg", "comercial.unidade.l"]


async def test_semente_de_uma_empresa_nao_aparece_na_outra(criadas: list[uuid.UUID]) -> None:
    # Uma transação por empresa: o tenant da transação é um só, e cadastrar duas de uma
    # vez deixaria a gravação da segunda sair sob o tenant da primeira.
    async with SessionFactory() as session, session.begin():
        criadas.append(await _empresa(session, modules=[COMERCIAL]))
    async with SessionFactory() as session, session.begin():
        criadas.append(await _empresa(session, modules=[COMERCIAL]))

    async with SessionFactory() as session, session.begin():
        await bind_tenant(session, criadas[-2])
        visiveis = await session.scalar(select(func.count()).select_from(SeedRecord))

        # Seis linhas existem no banco; a empresa vê três. Saber que módulo semeou o quê
        # é informação da composição comercial de quem contratou.
        assert visiveis == 3


async def test_seed_record_tem_rls_forcada() -> None:
    """A lista de tabelas de empresa em ``models.py`` promete isto; aqui ela é cobrada."""
    from decko_modules.core.models import TENANT_SCOPED_TABLES

    async with SessionFactory() as session, session.begin():
        linhas = await session.execute(
            text(
                """
                SELECT relname, relrowsecurity, relforcerowsecurity
                FROM pg_class
                WHERE relname = ANY(:tabelas)
                """
            ),
            {"tabelas": list(TENANT_SCOPED_TABLES)},
        )
        estado = {nome: (ligada, forcada) for nome, ligada, forcada in linhas}

    assert set(estado) == set(TENANT_SCOPED_TABLES), "tabela declarada que não existe no banco"
    desprotegidas = [nome for nome, (ligada, forcada) in estado.items() if not (ligada and forcada)]
    assert desprotegidas == []
