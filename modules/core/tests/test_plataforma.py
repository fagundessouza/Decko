"""Quem vende o Decko enxerga quem o usa.

O que estes testes guardam é a `docs/adr/0021-nivel-de-plataforma.md`:

- a marca é **de pessoa**, não de papel — se fosse permissão de manifesto, o reconciliador
  a daria ao papel `Administrador` de toda empresa, e a conta do cliente ganharia a lista
  de clientes;
- ela é conferida **no banco** a cada requisição, porque token vive quinze minutos e para
  privilégio que atravessa empresas isso é atraso demais;
- e a área **não lê de dentro** de empresa alheia: a tabela `tenant` é a própria fronteira
  do isolamento, e é só ela que esta fatia toca.
"""

import argparse
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, update

from decko.db import SessionFactory, bind_tenant
from decko.main import create_app
from decko_modules.core.cli import _bootstrap, _run_plataforma_lista
from decko_modules.core.models import Tenant, User

SENHA = "senha-local-de-teste-123"
CORE = "/api/v1/core"
CLIENTES = "/api/v1/clientes"


@dataclass
class Empresa:
    tenant_id: uuid.UUID
    slug: str
    email: str
    token: str


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as http:
        yield http


async def _criar_empresa(client: AsyncClient, prefixo: str, modulos: list[str]) -> Empresa:
    sufixo = uuid.uuid4().hex[:8]
    slug = f"{prefixo}-{sufixo}"
    email = f"{prefixo}-{sufixo}@teste-decko.com.br"

    async with SessionFactory() as session, session.begin():
        tenant, _user, _ = await _bootstrap(
            session,
            tenant_name=f"Empresa {prefixo}",
            tenant_slug=slug,
            admin_email=email,
            admin_name="Dono",
            password=SENHA,
            modules=modulos,
        )
        tenant_id = tenant.id

    entrada = await client.post(
        f"{CORE}/auth/login",
        json={"tenant_slug": slug, "email": email, "password": SENHA},
    )
    assert entrada.status_code == 200, entrada.text
    return Empresa(
        tenant_id=tenant_id, slug=slug, email=email, token=entrada.json()["access_token"]
    )


@pytest_asyncio.fixture
async def plataforma(client: AsyncClient) -> AsyncIterator[Empresa]:
    """A empresa de quem vende o Decko, e mais uma que é cliente dela."""
    criadas: list[uuid.UUID] = []
    try:
        dona = await _criar_empresa(client, "plataforma", ["clientes"])
        criadas.append(dona.tenant_id)
        cliente = await _criar_empresa(client, "cliente", [])
        criadas.append(cliente.tenant_id)
        dona.cliente = cliente  # type: ignore[attr-defined]
        yield dona
    finally:
        async with SessionFactory() as session, session.begin():
            for tenant_id in criadas:
                await session.execute(delete(Tenant).where(Tenant.id == tenant_id))


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _marcar(tenant_id: uuid.UUID, email: str, *, ligada: bool) -> None:
    async with SessionFactory() as session, session.begin():
        await bind_tenant(session, tenant_id)
        await session.execute(
            update(User).where(User.email == email).values(is_platform_admin=ligada)
        )


async def test_sem_a_marca_a_area_nem_existe(client: AsyncClient, plataforma: Empresa) -> None:
    """404 e não 403: 403 confirmaria que a área existe, para quem não é dela."""
    recusado = await client.get(f"{CORE}/plataforma/empresas", headers=_auth(plataforma.token))
    assert recusado.status_code == 404


async def test_nenhum_papel_concede_a_marca(client: AsyncClient, plataforma: Empresa) -> None:
    """A conta do cliente é administradora **da empresa dela**, e nada além disso.

    É o motivo de a marca não ser permissão de manifesto: o reconciliador a daria ao papel
    `Administrador` de toda empresa, e quem compra o Decko ganharia a lista de quem compra
    o Decko.
    """
    cliente: Empresa = plataforma.cliente  # type: ignore[attr-defined]

    sessao = (await client.get(f"{CORE}/auth/me", headers=_auth(cliente.token))).json()
    assert "core.user.create" in sessao["permissions"]
    assert not any("plataforma" in p for p in sessao["permissions"])

    recusado = await client.get(f"{CORE}/plataforma/empresas", headers=_auth(cliente.token))
    assert recusado.status_code == 404


async def test_com_a_marca_enxerga_as_empresas(client: AsyncClient, plataforma: Empresa) -> None:
    cliente: Empresa = plataforma.cliente  # type: ignore[attr-defined]
    await _marcar(plataforma.tenant_id, plataforma.email, ligada=True)

    lista = await client.get(f"{CORE}/plataforma/empresas", headers=_auth(plataforma.token))
    assert lista.status_code == 200, lista.text

    slugs = [empresa["slug"] for empresa in lista.json()]
    assert {plataforma.slug, cliente.slug} <= set(slugs)
    # Da mais nova para a mais antiga: quem acabou de entrar é quem se está acompanhando.
    assert slugs.index(cliente.slug) < slugs.index(plataforma.slug)
    # Só o que a tabela `tenant` já diz: nada de dentro das empresas.
    assert set(lista.json()[0]) == {"id", "slug", "name", "is_active", "created_at"}


async def test_tirar_a_marca_vale_na_hora(client: AsyncClient, plataforma: Empresa) -> None:
    """Conferida no banco, e não no token: quinze minutos de atraso é tempo demais aqui."""
    await _marcar(plataforma.tenant_id, plataforma.email, ligada=True)
    antes = await client.get(f"{CORE}/plataforma/empresas", headers=_auth(plataforma.token))
    assert antes.status_code == 200

    await _marcar(plataforma.tenant_id, plataforma.email, ligada=False)

    # **O mesmo token**, que continua válido e ainda diz as mesmas permissões.
    depois = await client.get(f"{CORE}/plataforma/empresas", headers=_auth(plataforma.token))
    assert depois.status_code == 404


async def test_o_contato_diz_qual_empresa_ele_e(client: AsyncClient, plataforma: Empresa) -> None:
    """É o vínculo que faltava: sem ele, bloquear uma assinatura não tem o que bloquear."""
    cliente: Empresa = plataforma.cliente  # type: ignore[attr-defined]

    criado = await client.post(
        f"{CLIENTES}/clientes",
        headers=_auth(plataforma.token),
        json={
            "tipo": "juridica",
            "nome": "Empresa cliente",
            "tenant_assinante_id": str(cliente.tenant_id),
        },
    )
    assert criado.status_code == 201, criado.text
    assert criado.json()["tenant_assinante_id"] == str(cliente.tenant_id)


async def test_uma_empresa_e_apontada_por_um_contato_so(
    client: AsyncClient, plataforma: Empresa
) -> None:
    """Duas assinaturas pagando o mesmo acesso tornaria "está bloqueada?" sem resposta."""
    cliente: Empresa = plataforma.cliente  # type: ignore[attr-defined]

    primeiro = await client.post(
        f"{CLIENTES}/clientes",
        headers=_auth(plataforma.token),
        json={
            "tipo": "juridica",
            "nome": "Primeiro contato",
            "tenant_assinante_id": str(cliente.tenant_id),
        },
    )
    assert primeiro.status_code == 201, primeiro.text

    segundo = await client.post(
        f"{CLIENTES}/clientes",
        headers=_auth(plataforma.token),
        json={
            "tipo": "juridica",
            "nome": "Segundo contato",
            "tenant_assinante_id": str(cliente.tenant_id),
        },
    )
    assert segundo.status_code == 422, segundo.text
    assert "já está ligado" in segundo.json()["detail"]


async def test_contato_de_balcao_nao_aponta_para_empresa_nenhuma(
    client: AsyncClient, plataforma: Empresa
) -> None:
    """Nulo é o caso normal: quem compra no balcão não é empresa na plataforma."""
    criado = await client.post(
        f"{CLIENTES}/clientes",
        headers=_auth(plataforma.token),
        json={"tipo": "fisica", "nome": "Maria do balcão"},
    )
    assert criado.status_code == 201, criado.text
    assert criado.json()["tenant_assinante_id"] is None


async def test_a_sessao_diz_a_marca_para_o_menu_existir(
    client: AsyncClient, plataforma: Empresa
) -> None:
    """O menu precisa saber; a guarda continua sendo a conferência no banco.

    A marca viaja **fora** do `user` da sessão de propósito: `user` é o molde que a tela
    de equipe lista, e a marca não aparece lá — ver a decisão 1 da ADR.
    """
    cliente: Empresa = plataforma.cliente  # type: ignore[attr-defined]

    antes = (await client.get(f"{CORE}/auth/me", headers=_auth(plataforma.token))).json()
    assert antes["is_platform_admin"] is False
    assert "is_platform_admin" not in antes["user"]

    await _marcar(plataforma.tenant_id, plataforma.email, ligada=True)

    depois = (await client.get(f"{CORE}/auth/me", headers=_auth(plataforma.token))).json()
    assert depois["is_platform_admin"] is True
    # E a empresa cliente continua sem ela, com o próprio administrador dentro.
    dela = (await client.get(f"{CORE}/auth/me", headers=_auth(cliente.token))).json()
    assert dela["is_platform_admin"] is False


async def test_a_linha_de_comando_consegue_conferir_quem_tem_a_marca(
    plataforma: Empresa, capsys: pytest.CaptureFixture[str]
) -> None:
    """Privilégio concentrado precisa ser conferível, e conferir atravessa empresas.

    A armadilha aqui é silenciosa: `user_account` tem RLS com `FORCE` e ninguém tem
    `BYPASSRLS`, então uma consulta só por cima de todas as empresas não devolve linha
    nenhuma — e o comando responderia "ninguém administra" com a marca ligada no banco.
    Por isso ele visita uma empresa por vez, com o isolamento ligado em cada visita.
    """
    cliente: Empresa = plataforma.cliente  # type: ignore[attr-defined]
    await _marcar(plataforma.tenant_id, plataforma.email, ligada=True)

    assert await _run_plataforma_lista(argparse.Namespace()) == 0

    dito = capsys.readouterr().out
    assert plataforma.email in dito
    assert plataforma.slug in dito
    # Quem não tem a marca não entra na lista, nem sendo administrador da própria empresa.
    assert cliente.email not in dito


async def test_a_marca_nao_aparece_na_tela_de_equipe(
    client: AsyncClient, plataforma: Empresa
) -> None:
    """A tela de equipe não mostra nem mexe: quem administra a empresa não encosta nisto."""
    await _marcar(plataforma.tenant_id, plataforma.email, ligada=True)

    usuarios = (await client.get(f"{CORE}/users", headers=_auth(plataforma.token))).json()
    assert usuarios
    assert all("platform" not in campo for campo in usuarios[0])

    async with SessionFactory() as session:
        await bind_tenant(session, plataforma.tenant_id)
        marcado = await session.scalar(
            select(User.is_platform_admin).where(User.email == plataforma.email)
        )
    # A marca está no banco; o que não existe é caminho de interface para ela.
    assert marcado is True
