"""Cadastro de clientes, pela API.

O que precisa valer: documento conferido e único, cliente de balcão sem documento
permitido, cadastro que não some, e trilha de auditoria sem o dado pessoal dentro.
"""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from decko.db import SessionFactory, bind_tenant
from decko.main import create_app
from decko_modules.core.cli import _bootstrap
from decko_modules.core.models import AuditLog, Tenant

PASSWORD = "senha-local-de-teste-123"
CORE = "/api/v1/core"
CLIENTES = "/api/v1/clientes"

# CPF e CNPJ de teste, válidos no dígito verificador.
CPF = "52998224725"
CNPJ = "11222333000181"


@dataclass
class Loja:
    tenant_id: uuid.UUID
    token: str


@pytest_asyncio.fixture
async def loja() -> AsyncIterator[tuple[AsyncClient, Loja]]:
    sufixo = uuid.uuid4().hex[:8]
    slug = f"cli-{sufixo}"
    email = f"dono-{sufixo}@teste-decko.com.br"

    async with SessionFactory() as session, session.begin():
        tenant, _user, _granted = await _bootstrap(
            session,
            tenant_name="Loja de Teste",
            tenant_slug=slug,
            admin_email=email,
            admin_name="Dono",
            password=PASSWORD,
            modules=["clientes"],
        )
        tenant_id = tenant.id

    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        login = await client.post(
            f"{CORE}/auth/login",
            json={"tenant_slug": slug, "email": email, "password": PASSWORD},
        )
        assert login.status_code == 200, login.text
        try:
            yield client, Loja(tenant_id=tenant_id, token=login.json()["access_token"])
        finally:
            async with SessionFactory() as session, session.begin():
                await session.execute(delete(Tenant).where(Tenant.id == tenant_id))


def _auth(dados: Loja) -> dict[str, str]:
    return {"Authorization": f"Bearer {dados.token}"}


async def test_cria_pessoa_fisica_com_cpf(loja: tuple[AsyncClient, Loja]) -> None:
    client, dados = loja

    criado = await client.post(
        f"{CLIENTES}/clientes",
        headers=_auth(dados),
        json={"nome": "Maria Souza", "cpf_cnpj": "529.982.247-25", "telefone": "64999990000"},
    )

    assert criado.status_code == 201, criado.text
    # Entra com máscara, guarda só os dígitos.
    assert criado.json()["cpf_cnpj"] == CPF
    assert criado.json()["ativo"] is True


async def test_cria_empresa_com_cnpj_e_fantasia(loja: tuple[AsyncClient, Loja]) -> None:
    client, dados = loja

    criado = await client.post(
        f"{CLIENTES}/clientes",
        headers=_auth(dados),
        json={
            "tipo": "juridica",
            "nome": "Comercial Alfa Ltda",
            "apelido": "Mercadinho do Zé",
            "cpf_cnpj": "11.222.333/0001-81",
            "uf": "go",
        },
    )

    assert criado.status_code == 201, criado.text
    assert criado.json()["cpf_cnpj"] == CNPJ
    # "go" e "GO" são a mesma unidade federativa.
    assert criado.json()["uf"] == "GO"


async def test_cliente_de_balcao_sem_documento_e_aceito(loja: tuple[AsyncClient, Loja]) -> None:
    """Exigir CPF para vender um pão travaria a loja."""
    client, dados = loja

    criado = await client.post(
        f"{CLIENTES}/clientes", headers=_auth(dados), json={"nome": "Cliente do balcão"}
    )

    assert criado.status_code == 201, criado.text
    assert criado.json()["cpf_cnpj"] is None


async def test_documento_que_nao_fecha_e_recusado(loja: tuple[AsyncClient, Loja]) -> None:
    """Aceitar um CPF inventado é pior que não ter CPF: vai parar na nota."""
    client, dados = loja

    recusado = await client.post(
        f"{CLIENTES}/clientes",
        headers=_auth(dados),
        json={"nome": "Fulano", "cpf_cnpj": "111.111.111-11"},
    )

    assert recusado.status_code == 422


async def test_mesmo_documento_duas_vezes_e_recusado(loja: tuple[AsyncClient, Loja]) -> None:
    client, dados = loja
    corpo = {"nome": "Maria Souza", "cpf_cnpj": CPF}

    assert (
        await client.post(f"{CLIENTES}/clientes", headers=_auth(dados), json=corpo)
    ).status_code == 201
    repetido = await client.post(f"{CLIENTES}/clientes", headers=_auth(dados), json=corpo)

    assert repetido.status_code == 422
    assert "já existe" in repetido.json()["detail"].lower()


async def test_busca_por_nome_e_por_documento(loja: tuple[AsyncClient, Loja]) -> None:
    client, dados = loja
    await client.post(
        f"{CLIENTES}/clientes",
        headers=_auth(dados),
        json={"nome": "Maria Souza", "cpf_cnpj": CPF},
    )
    await client.post(f"{CLIENTES}/clientes", headers=_auth(dados), json={"nome": "João Lima"})

    por_nome = await client.get(f"{CLIENTES}/clientes?busca=maria", headers=_auth(dados))
    assert [c["nome"] for c in por_nome.json()] == ["Maria Souza"]

    # O vendedor digita com ponto e traço; o banco guarda sem.
    por_documento = await client.get(
        f"{CLIENTES}/clientes?busca=529.982.247-25", headers=_auth(dados)
    )
    assert [c["nome"] for c in por_documento.json()] == ["Maria Souza"]


async def test_desativado_sai_da_busca_mas_continua_existindo(
    loja: tuple[AsyncClient, Loja],
) -> None:
    """Quem comprou aparece em venda e em nota: apagar deixaria documento órfão."""
    client, dados = loja
    criado = await client.post(
        f"{CLIENTES}/clientes", headers=_auth(dados), json={"nome": "Maria Souza"}
    )
    cliente_id = criado.json()["id"]

    desativado = await client.post(
        f"{CLIENTES}/clientes/{cliente_id}/desativar", headers=_auth(dados)
    )
    assert desativado.status_code == 200
    assert desativado.json()["ativo"] is False

    assert (await client.get(f"{CLIENTES}/clientes", headers=_auth(dados))).json() == []
    com_inativos = await client.get(
        f"{CLIENTES}/clientes?incluir_inativos=true", headers=_auth(dados)
    )
    assert [c["nome"] for c in com_inativos.json()] == ["Maria Souza"]

    # E continua alcançável pelo id, que é o que o documento guarda.
    assert (
        await client.get(f"{CLIENTES}/clientes/{cliente_id}", headers=_auth(dados))
    ).status_code == 200


async def test_reativar_devolve_a_busca(loja: tuple[AsyncClient, Loja]) -> None:
    client, dados = loja
    criado = await client.post(
        f"{CLIENTES}/clientes", headers=_auth(dados), json={"nome": "Maria Souza"}
    )
    cliente_id = criado.json()["id"]

    await client.post(f"{CLIENTES}/clientes/{cliente_id}/desativar", headers=_auth(dados))
    await client.post(f"{CLIENTES}/clientes/{cliente_id}/reativar", headers=_auth(dados))

    assert len((await client.get(f"{CLIENTES}/clientes", headers=_auth(dados))).json()) == 1


async def test_trilha_registra_a_alteracao_sem_guardar_o_dado(
    loja: tuple[AsyncClient, Loja],
) -> None:
    """Copiar CPF para a trilha o espalharia para uma tabela que ninguém apaga."""
    client, dados = loja
    criado = await client.post(
        f"{CLIENTES}/clientes", headers=_auth(dados), json={"nome": "Maria Souza"}
    )
    cliente_id = criado.json()["id"]

    await client.put(
        f"{CLIENTES}/clientes/{cliente_id}",
        headers=_auth(dados),
        json={"nome": "Maria Souza", "cpf_cnpj": CPF},
    )

    async with SessionFactory() as session:
        await bind_tenant(session, dados.tenant_id)
        linhas = list(
            (
                await session.execute(
                    select(AuditLog)
                    .where(AuditLog.entity == "cliente", AuditLog.entity_id == cliente_id)
                    .order_by(AuditLog.created_at)
                )
            )
            .scalars()
            .all()
        )

    assert [linha.action for linha in linhas] == ["cliente.create", "cliente.update"]
    atualizacao = linhas[1].data or {}
    assert atualizacao["campos_alterados"] == ["cpf_cnpj"]
    # O número não entra na trilha, em lugar nenhum da linha.
    assert CPF not in str(atualizacao)


async def test_uma_loja_nao_ve_o_cliente_da_outra(loja: tuple[AsyncClient, Loja]) -> None:
    client, dados = loja
    await client.post(f"{CLIENTES}/clientes", headers=_auth(dados), json={"nome": "Maria Souza"})

    sufixo = uuid.uuid4().hex[:8]
    slug = f"cli-vizinha-{sufixo}"
    email = f"dono-{sufixo}@teste-decko.com.br"
    async with SessionFactory() as session, session.begin():
        vizinha, _user, _granted = await _bootstrap(
            session,
            tenant_name="Loja Vizinha",
            tenant_slug=slug,
            admin_email=email,
            admin_name="Dono",
            password=PASSWORD,
            modules=["clientes"],
        )
        vizinha_id = vizinha.id

    try:
        login = await client.post(
            f"{CORE}/auth/login",
            json={"tenant_slug": slug, "email": email, "password": PASSWORD},
        )
        token = {"Authorization": f"Bearer {login.json()['access_token']}"}

        assert (await client.get(f"{CLIENTES}/clientes", headers=token)).json() == []
    finally:
        async with SessionFactory() as session, session.begin():
            await session.execute(delete(Tenant).where(Tenant.id == vizinha_id))
