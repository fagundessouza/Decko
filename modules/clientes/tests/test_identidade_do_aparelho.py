"""A identidade vem do aparelho, e reenviar não duplica.

Primeira fatia da `docs/adr/0022-offline-first-as-respostas.md`, que implementa as
decisões 2 e 4 da `docs/adr/0019-offline-first.md`.

O caso que isto resolve não é raro: o aparelho sem sinal manda o cadastro, a requisição
chega, a resposta se perde no caminho de volta, e o aparelho — que não tem como saber a
diferença entre "não chegou" e "não voltou" — manda de novo. Antes, o segundo envio virava
um cliente repetido ou um erro de documento duplicado na tela de quem não errou nada.
"""

import uuid
from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from decko.db import SessionFactory, bind_tenant
from decko.main import create_app
from decko_modules.clientes.models import Cliente
from decko_modules.core.cli import _bootstrap
from decko_modules.core.models import Tenant

SENHA = "senha-local-de-teste-123"
CORE = "/api/v1/core"
CLIENTES = "/api/v1/clientes"


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as http:
        yield http


@pytest_asyncio.fixture
async def empresa(client: AsyncClient) -> AsyncIterator[tuple[uuid.UUID, dict[str, str]]]:
    sufixo = uuid.uuid4().hex[:8]
    slug = f"aparelho-{sufixo}"
    email = f"{slug}@teste-decko.com.br"

    async with SessionFactory() as session, session.begin():
        tenant, _user, _ = await _bootstrap(
            session,
            tenant_name="Loja do Aparelho",
            tenant_slug=slug,
            admin_email=email,
            admin_name="Dono",
            password=SENHA,
            modules=["clientes"],
        )
        tenant_id = tenant.id

    entrada = await client.post(
        f"{CORE}/auth/login",
        json={"tenant_slug": slug, "email": email, "password": SENHA},
    )
    assert entrada.status_code == 200, entrada.text
    cabecalho = {"Authorization": f"Bearer {entrada.json()['access_token']}"}
    try:
        yield tenant_id, cabecalho
    finally:
        async with SessionFactory() as session, session.begin():
            await session.execute(delete(Tenant).where(Tenant.id == tenant_id))


def _cadastro(identidade: str | None = None) -> dict[str, object]:
    corpo: dict[str, object] = {
        "tipo": "juridica",
        "nome": "Mercearia da Esquina",
        "cpf_cnpj": "11222333000181",
    }
    if identidade is not None:
        corpo["id"] = identidade
    return corpo


async def test_o_aparelho_escolhe_a_identidade(
    client: AsyncClient, empresa: tuple[uuid.UUID, dict[str, str]]
) -> None:
    _tenant_id, auth = empresa
    escolhida = str(uuid.uuid4())

    criado = await client.post(f"{CLIENTES}/clientes", headers=auth, json=_cadastro(escolhida))

    assert criado.status_code == 201, criado.text
    assert criado.json()["id"] == escolhida


async def test_reenviar_o_mesmo_cadastro_nao_duplica(
    client: AsyncClient, empresa: tuple[uuid.UUID, dict[str, str]]
) -> None:
    """O segundo envio devolve 200 com o que já existe, e não 201 nem erro."""
    tenant_id, auth = empresa
    escolhida = str(uuid.uuid4())

    primeiro = await client.post(f"{CLIENTES}/clientes", headers=auth, json=_cadastro(escolhida))
    assert primeiro.status_code == 201, primeiro.text

    segundo = await client.post(f"{CLIENTES}/clientes", headers=auth, json=_cadastro(escolhida))
    assert segundo.status_code == 200, segundo.text
    assert segundo.json()["id"] == escolhida

    async with SessionFactory() as session:
        await bind_tenant(session, tenant_id)
        quantos = len((await session.execute(select(Cliente.id))).all())
    assert quantos == 1, "o reenvio criou um segundo cadastro"


async def test_o_reenvio_nao_esbarra_na_recusa_de_documento_repetido(
    client: AsyncClient, empresa: tuple[uuid.UUID, dict[str, str]]
) -> None:
    """Era este o erro que chegava na tela: 'já existe um cliente com este CPF ou CNPJ'.

    A recusa está certa para dois cadastros diferentes com o mesmo documento, e errada
    para o mesmo cadastro chegando duas vezes. A identidade é o que separa os dois casos.
    """
    _tenant_id, auth = empresa
    escolhida = str(uuid.uuid4())

    await client.post(f"{CLIENTES}/clientes", headers=auth, json=_cadastro(escolhida))
    reenvio = await client.post(f"{CLIENTES}/clientes", headers=auth, json=_cadastro(escolhida))

    assert reenvio.status_code == 200
    assert "CPF" not in reenvio.text


async def test_documento_repetido_em_cadastro_diferente_continua_recusado(
    client: AsyncClient, empresa: tuple[uuid.UUID, dict[str, str]]
) -> None:
    """A tolerância é ao reenvio, não ao documento duplicado."""
    _tenant_id, auth = empresa

    await client.post(f"{CLIENTES}/clientes", headers=auth, json=_cadastro(str(uuid.uuid4())))
    outro = await client.post(
        f"{CLIENTES}/clientes", headers=auth, json=_cadastro(str(uuid.uuid4()))
    )

    assert outro.status_code == 422, outro.text
    assert "CPF" in outro.json()["detail"]


async def test_quem_esta_online_continua_sem_mandar_identidade(
    client: AsyncClient, empresa: tuple[uuid.UUID, dict[str, str]]
) -> None:
    """Sem `id`, o servidor gera — é o caminho de hoje, e ele não mudou."""
    _tenant_id, auth = empresa

    criado = await client.post(f"{CLIENTES}/clientes", headers=auth, json=_cadastro())

    assert criado.status_code == 201, criado.text
    assert uuid.UUID(criado.json()["id"])


async def test_editar_nao_troca_a_identidade(
    client: AsyncClient, empresa: tuple[uuid.UUID, dict[str, str]]
) -> None:
    """Trocar chave primária por formulário deixaria órfão quem aponta para o cadastro."""
    _tenant_id, auth = empresa
    escolhida = str(uuid.uuid4())
    await client.post(f"{CLIENTES}/clientes", headers=auth, json=_cadastro(escolhida))

    corpo = _cadastro(str(uuid.uuid4()))
    corpo["nome"] = "Mercearia da Esquina LTDA"
    editado = await client.put(f"{CLIENTES}/clientes/{escolhida}", headers=auth, json=corpo)

    assert editado.status_code == 200, editado.text
    assert editado.json()["id"] == escolhida
    assert editado.json()["nome"] == "Mercearia da Esquina LTDA"


async def test_identidade_de_outra_empresa_e_recusada_sem_dizer_de_quem_e(
    client: AsyncClient, empresa: tuple[uuid.UUID, dict[str, str]]
) -> None:
    """A chave primária é única no banco inteiro, e o isolamento não deixa enxergar isso.

    Sem o savepoint, esta requisição estourava como erro de integridade e virava 500 —
    defeito de servidor causado por entrada de cliente. A recusa também não conta a quem
    a identidade pertence.
    """
    _tenant_id, auth = empresa

    vizinha = uuid.uuid4()
    async with SessionFactory() as session, session.begin():
        tenant, _user, _ = await _bootstrap(
            session,
            tenant_name="Loja Vizinha",
            tenant_slug=f"vizinha-{uuid.uuid4().hex[:8]}",
            admin_email=f"vizinha-{uuid.uuid4().hex[:8]}@teste-decko.com.br",
            admin_name="Dona",
            password=SENHA,
            modules=["clientes"],
        )
        vizinha_id = tenant.id
        await bind_tenant(session, vizinha_id)
        session.add(Cliente(id=vizinha, tenant_id=vizinha_id, tipo="fisica", nome="De outra"))

    try:
        corpo = _cadastro(str(vizinha))
        corpo["cpf_cnpj"] = None
        recusado = await client.post(f"{CLIENTES}/clientes", headers=auth, json=corpo)

        assert recusado.status_code == 422, recusado.text
        detalhe = recusado.json()["detail"]
        assert "outro" in detalhe.lower()
        # Nada sobre a empresa vizinha vaza na mensagem.
        assert "Loja Vizinha" not in detalhe and "De outra" not in detalhe
    finally:
        async with SessionFactory() as session, session.begin():
            await session.execute(delete(Tenant).where(Tenant.id == vizinha_id))
