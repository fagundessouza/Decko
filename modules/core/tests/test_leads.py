"""O pedido de contato vindo da página pública.

É a porta mais aberta do sistema: formulário sem login, na internet. Quem preenche ainda
não tem conta — é o começo da conversa, não o uso do sistema.

O que está sob teste é o que essa abertura exige em troca: a armadilha que pega robô sem
castigar gente, o teto por IP, o consentimento que autoriza o contato depois, e o silêncio
da resposta — uma rota pública que contasse o que já existe aqui dentro viraria um jeito
de descobrir quem é cliente do Decko perguntando de fora.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from decko.db import SessionFactory
from decko.main import create_app
from decko_modules.core import service
from decko_modules.core.cli import _bootstrap
from decko_modules.core.models import Lead, Tenant, User

CORE = "/api/v1/core"
SENHA = "senha-local-de-teste-123"


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as http:
        yield http


@pytest_asyncio.fixture(autouse=True)
async def sem_leads() -> AsyncIterator[None]:
    """A tabela vive fora da fronteira de empresa: a limpeza é explícita."""
    async with SessionFactory() as session, session.begin():
        await session.execute(delete(Lead))
    yield
    async with SessionFactory() as session, session.begin():
        await session.execute(delete(Lead))


@pytest_asyncio.fixture
async def dono(client: AsyncClient) -> AsyncIterator[dict[str, str]]:
    """Quem vende o Decko: é só ele que enxerga os pedidos de contato."""
    sufixo = uuid.uuid4().hex[:8]
    slug = f"plataforma-{sufixo}"
    email = f"dono-{sufixo}@teste-decko.com.br"

    async with SessionFactory() as session, session.begin():
        tenant, user, _ = await _bootstrap(
            session,
            tenant_name="Dona da plataforma",
            tenant_slug=slug,
            admin_email=email,
            admin_name="Dono",
            password=SENHA,
            modules=[],
        )
        tenant_id = tenant.id
        usuario = await session.get(User, user.id)
        assert usuario is not None
        usuario.is_platform_admin = True

    entrada = await client.post(
        f"{CORE}/auth/login",
        json={"tenant_slug": slug, "email": email, "password": SENHA},
    )
    assert entrada.status_code == 200, entrada.text
    try:
        yield {"Authorization": f"Bearer {entrada.json()['access_token']}"}
    finally:
        async with SessionFactory() as session, session.begin():
            await session.execute(delete(Tenant).where(Tenant.id == tenant_id))


def _pedido(**sobre: object) -> dict[str, object]:
    return {
        "nome": "Maria da Lavoura",
        "email": "maria@fazendadoteste.com.br",
        "empresa": "Fazenda do Teste",
        "telefone": "64999990000",
        "segmento": "agro",
        "mensagem": "Quero conhecer o sistema.",
        "origem": "busca-google",
        "consentimento": True,
        **sobre,
    }


# ----------------------------------------------------------------- receber


async def test_o_pedido_de_contato_entra_sem_login(client: AsyncClient) -> None:
    """Quem preenche ainda não tem conta: exigir login aqui seria exigir que o cliente
    já fosse cliente para poder virar cliente."""
    resposta = await client.post(f"{CORE}/leads", json=_pedido())

    assert resposta.status_code == 201, resposta.text
    assert resposta.json() == {"recebido": True}

    async with SessionFactory() as session:
        lead = (await session.execute(select(Lead))).scalars().one()
    assert lead.nome == "Maria da Lavoura"
    assert lead.origem == "busca-google"
    # A hora do consentimento é o que autoriza o contato depois.
    assert lead.consentimento_em is not None


async def test_sem_consentimento_nao_entra(client: AsyncClient) -> None:
    """Sem aceite não há base legal para ligar de volta, então não há o que guardar."""
    resposta = await client.post(f"{CORE}/leads", json=_pedido(consentimento=False))

    assert resposta.status_code == 422, resposta.text
    async with SessionFactory() as session:
        assert (await session.execute(select(Lead))).scalars().all() == []


async def test_e_mail_que_nao_e_e_mail_e_recusado(client: AsyncClient) -> None:
    resposta = await client.post(f"{CORE}/leads", json=_pedido(email="isto nao e email"))

    assert resposta.status_code == 422, resposta.text


# ----------------------------------------------------------------- conter robô


async def test_o_campo_armadilha_engole_o_robo(client: AsyncClient) -> None:
    """Resposta de sucesso, e nada gravado.

    Devolver erro ensinaria o robô a contornar; devolver "obrigado" o manda embora achando
    que conseguiu. É o oposto do CAPTCHA, que empurra o custo do nosso spam para a
    paciência de quem quer falar com a gente.
    """
    resposta = await client.post(
        f"{CORE}/leads", json=_pedido(site="http://spam.exemplo")
    )

    assert resposta.status_code == 201, resposta.text
    assert resposta.json() == {"recebido": True}
    async with SessionFactory() as session:
        assert (await session.execute(select(Lead))).scalars().all() == []


async def test_enxurrada_do_mesmo_lugar_e_contida(client: AsyncClient) -> None:
    """Gente não manda dez pedidos numa hora; robô manda mil."""
    cabecalho = {"CF-Connecting-IP": "203.0.113.7"}
    for _ in range(service.LEADS_POR_HORA):
        aceito = await client.post(f"{CORE}/leads", json=_pedido(), headers=cabecalho)
        assert aceito.status_code == 201, aceito.text

    recusado = await client.post(f"{CORE}/leads", json=_pedido(), headers=cabecalho)

    assert recusado.status_code == 422, recusado.text
    assert "vários pedidos" in recusado.json()["detail"]


async def test_o_teto_e_por_lugar_e_nao_global(client: AsyncClient) -> None:
    """Um robô não pode calar a página para o resto do mundo."""
    for _ in range(service.LEADS_POR_HORA):
        await client.post(
            f"{CORE}/leads", json=_pedido(), headers={"CF-Connecting-IP": "203.0.113.7"}
        )

    de_outro = await client.post(
        f"{CORE}/leads", json=_pedido(), headers={"CF-Connecting-IP": "198.51.100.9"}
    )

    assert de_outro.status_code == 201, de_outro.text


# ----------------------------------------------------------------- ver e exportar


async def test_so_quem_vende_o_decko_enxerga_os_pedidos(
    client: AsyncClient, dono: dict[str, str]
) -> None:
    await client.post(f"{CORE}/leads", json=_pedido())

    sem_credencial = await client.get(f"{CORE}/plataforma/leads")
    assert sem_credencial.status_code == 401, sem_credencial.text

    com_credencial = await client.get(f"{CORE}/plataforma/leads", headers=dono)
    assert com_credencial.status_code == 200, com_credencial.text
    assert com_credencial.json()[0]["email"] == "maria@fazendadoteste.com.br"


async def test_a_lista_de_pendentes_e_a_pergunta_da_manha(
    client: AsyncClient, dono: dict[str, str]
) -> None:
    await client.post(f"{CORE}/leads", json=_pedido())
    await client.post(f"{CORE}/leads", json=_pedido(email="outro@fazendadoteste.com.br"))

    primeiro = (await client.get(f"{CORE}/plataforma/leads", headers=dono)).json()[0]
    atendido = await client.put(
        f"{CORE}/plataforma/leads/{primeiro['id']}",
        headers=dono,
        json={"atendido": True, "observacao": "Falei por WhatsApp; quer demonstração."},
    )
    assert atendido.status_code == 200, atendido.text
    assert atendido.json()["atendido_em"] is not None

    pendentes = await client.get(f"{CORE}/plataforma/leads?pendentes=true", headers=dono)
    assert [lead["id"] for lead in pendentes.json()] == [
        lead["id"]
        for lead in (await client.get(f"{CORE}/plataforma/leads", headers=dono)).json()
        if lead["atendido_em"] is None
    ]
    assert len(pendentes.json()) == 1


async def test_a_planilha_abre_no_excel_em_portugues(
    client: AsyncClient, dono: dict[str, str]
) -> None:
    """Ponto e vírgula e BOM: é o que faz o Excel abrir sem o passo de importação."""
    await client.post(f"{CORE}/leads", json=_pedido())

    planilha = await client.get(f"{CORE}/plataforma/leads.csv", headers=dono)

    assert planilha.status_code == 200, planilha.text
    assert planilha.headers["content-disposition"].endswith('filename="leads-decko.csv"')
    assert planilha.content.startswith("﻿".encode())
    texto = planilha.content.decode("utf-8-sig")
    assert "Nome;Empresa;E-mail" in texto.replace("Recebido em;", "")
    assert "Maria da Lavoura" in texto


async def test_a_resposta_publica_nao_conta_nada_de_dentro(client: AsyncClient) -> None:
    """Dois pedidos com o mesmo e-mail recebem a mesma resposta.

    Dizer "já existe um cadastro com este e-mail" transformaria a página numa forma de
    descobrir quem fala com o Decko, perguntando de fora.
    """
    primeiro = await client.post(f"{CORE}/leads", json=_pedido())
    segundo = await client.post(f"{CORE}/leads", json=_pedido())

    assert primeiro.json() == segundo.json() == {"recebido": True}


# ----------------------------------------------------------------- esquecer o IP


async def test_o_ip_velho_e_esquecido_e_o_pedido_fica(client: AsyncClient) -> None:
    """O IP serve para conter robô na hora; depois é rastro de gente guardado sem motivo."""
    await client.post(
        f"{CORE}/leads", json=_pedido(), headers={"CF-Connecting-IP": "203.0.113.7"}
    )

    async with SessionFactory() as session, session.begin():
        lead = (await session.execute(select(Lead))).scalars().one()
        lead.created_at = datetime.now(UTC) - timedelta(days=service.DIAS_DE_IP + 1)

    async with SessionFactory() as session, session.begin():
        quantos = await service.esquecer_ip_antigo(session)

    assert quantos == 1
    async with SessionFactory() as session:
        lead = (await session.execute(select(Lead))).scalars().one()
    assert lead.ip is None
    assert lead.nome == "Maria da Lavoura"
