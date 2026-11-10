"""A equipe da loja: o dono cria quem opera e escolhe o que a pessoa alcança.

Até 10/11/2026 as permissões `core.user.*` e `core.role.*` existiam no manifesto e não
tinham rota nenhuma por trás — só a linha de comando do servidor criava gente. O que estes
testes guardam é o que a `docs/adr/0020-operador-supervisor-e-papeis.md` decidiu:

- o papel semeado é **ponto de partida**, e a subida seguinte da aplicação não o desfaz;
- quem o dono cria **tem de trocar a senha**, senão a trilha não diz quem fez;
- ninguém se tranca do lado de fora mexendo nos próprios papéis.
"""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from decko.db import SessionFactory, bind_tenant
from decko.main import create_app
from decko_modules.core.activation import garantir_papeis_sugeridos
from decko_modules.core.cli import _bootstrap
from decko_modules.core.models import AuditLog, Role, RolePermission, Tenant

SENHA = "senha-local-de-teste-123"
NOVA_SENHA = "outra-senha-local-de-teste-456"
BASE = "/api/v1/core"

OPERADOR = "Operador de caixa"
SUPERVISOR = "Supervisor de caixa"


@dataclass
class Loja:
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


@pytest_asyncio.fixture
async def loja(client: AsyncClient) -> AsyncIterator[Loja]:
    sufixo = uuid.uuid4().hex[:8]
    slug = f"equipe-{sufixo}"
    email = f"dono-{sufixo}@teste-decko.com.br"

    async with SessionFactory() as session, session.begin():
        tenant, _user, _ = await _bootstrap(
            session,
            tenant_name="Loja da Equipe",
            tenant_slug=slug,
            admin_email=email,
            admin_name="Dono da Loja",
            password=SENHA,
            modules=["comercial", "pdv"],
        )
        tenant_id = tenant.id

    entrada = await client.post(
        f"{BASE}/auth/login",
        json={"tenant_slug": slug, "email": email, "password": SENHA},
    )
    assert entrada.status_code == 200, entrada.text

    try:
        yield Loja(
            tenant_id=tenant_id,
            slug=slug,
            email=email,
            token=entrada.json()["access_token"],
        )
    finally:
        async with SessionFactory() as session, session.begin():
            await session.execute(delete(Tenant).where(Tenant.id == tenant_id))


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _papel(client: AsyncClient, loja: Loja, nome: str) -> dict:
    papeis = await client.get(f"{BASE}/papeis", headers=_auth(loja.token))
    assert papeis.status_code == 200, papeis.text
    return next(p for p in papeis.json() if p["name"] == nome)


async def _criar(
    client: AsyncClient, loja: Loja, *, papel: str | None = OPERADOR, email: str | None = None
):
    papeis = [] if papel is None else [(await _papel(client, loja, papel))["id"]]
    return await client.post(
        f"{BASE}/users",
        headers=_auth(loja.token),
        json={
            "email": email or f"caixa-{uuid.uuid4().hex[:8]}@teste-decko.com.br",
            "full_name": "Operador de Teste",
            "senha_inicial": SENHA,
            "papeis": papeis,
        },
    )


async def test_contratar_o_pdv_semeia_os_papeis(client: AsyncClient, loja: Loja) -> None:
    """Sem papel semeado o dono não tem o que dar a quem contrata."""
    papeis = (await client.get(f"{BASE}/papeis", headers=_auth(loja.token))).json()
    nomes = {p["name"] for p in papeis}
    assert {OPERADOR, SUPERVISOR} <= nomes


async def test_operador_vende_mas_nao_cancela_nem_fecha(client: AsyncClient, loja: Loja) -> None:
    """O papel é a fronteira: o que o operador não pode nem chega no token dele."""
    operador = await _papel(client, loja, OPERADOR)
    concede = set(operador["permissoes"])

    assert "pdv.venda.finalizar" in concede
    assert "pdv.caixa.abrir" in concede
    # Ler produto vem junto: sem isso ele não bipa nada.
    assert "comercial.produto.read" in concede

    # O que exige supervisor, ele não tem.
    assert "pdv.venda.cancelar" not in concede
    assert "pdv.venda.devolver" not in concede
    assert "pdv.caixa.fechar" not in concede
    # Nem o relatório do dia: ele soma todos os operadores e mostra o esperado em
    # espécie, que é justamente o número que quem conta não pode ver antes.
    assert "pdv.caixa.conferir" not in concede
    # E nada de administração.
    assert not any(p.startswith("core.user.") for p in concede)

    supervisor = set((await _papel(client, loja, SUPERVISOR))["permissoes"])
    assert {
        "pdv.venda.cancelar",
        "pdv.venda.devolver",
        "pdv.caixa.fechar",
        "pdv.caixa.conferir",
    } <= supervisor


async def test_papel_semeado_nao_e_refeito_na_subida_seguinte(
    client: AsyncClient, loja: Loja
) -> None:
    """Semente é ponto de partida, não configuração imposta para sempre — ADR 0010.

    Sem isto, a primeira vez que a loja ajustasse o papel do operador, a subida seguinte
    desfaria o ajuste e ninguém entenderia por quê.
    """
    operador = await _papel(client, loja, OPERADOR)

    async with SessionFactory() as session, session.begin():
        await bind_tenant(session, loja.tenant_id)
        # A loja decide tirar a abertura de caixa do operador.
        await session.execute(
            delete(RolePermission).where(
                RolePermission.role_id == uuid.UUID(operador["id"]),
                RolePermission.permission == "pdv.caixa.abrir",
            )
        )

    async with SessionFactory() as session, session.begin():
        await bind_tenant(session, loja.tenant_id)
        criados = await garantir_papeis_sugeridos(
            session, tenant_id=loja.tenant_id, ativos=["comercial", "pdv"]
        )

    assert criados == []
    depois = await _papel(client, loja, OPERADOR)
    assert "pdv.caixa.abrir" not in depois["permissoes"]


async def test_papel_que_falta_e_criado_em_empresa_que_ja_existia(
    client: AsyncClient, loja: Loja
) -> None:
    """É o caso de quem já usava o PDV antes de ele passar a sugerir papéis."""
    async with SessionFactory() as session, session.begin():
        await bind_tenant(session, loja.tenant_id)
        await session.execute(
            delete(Role).where(Role.tenant_id == loja.tenant_id, Role.name == OPERADOR)
        )

    async with SessionFactory() as session, session.begin():
        await bind_tenant(session, loja.tenant_id)
        criados = await garantir_papeis_sugeridos(
            session, tenant_id=loja.tenant_id, ativos=["comercial", "pdv"]
        )

    assert criados == [OPERADOR]


async def test_dono_cria_operador_e_ele_entra_com_o_que_o_papel_da(
    client: AsyncClient, loja: Loja
) -> None:
    criado = await _criar(client, loja)
    assert criado.status_code == 201, criado.text
    corpo = criado.json()
    assert corpo["must_change_password"] is True
    assert [p["name"] for p in corpo["papeis"]] == [OPERADOR]

    entrada = await client.post(
        f"{BASE}/auth/login",
        json={"tenant_slug": loja.slug, "email": corpo["email"], "password": SENHA},
    )
    assert entrada.status_code == 200, entrada.text

    sessao = (
        await client.get(f"{BASE}/auth/me", headers=_auth(entrada.json()["access_token"]))
    ).json()
    assert "pdv.venda.finalizar" in sessao["permissions"]
    assert "pdv.caixa.fechar" not in sessao["permissions"]
    # A tela precisa saber na entrada que a senha ainda é a que o dono escolheu.
    assert sessao["user"]["must_change_password"] is True


async def test_operador_nao_administra_a_equipe(client: AsyncClient, loja: Loja) -> None:
    corpo = (await _criar(client, loja)).json()
    entrada = await client.post(
        f"{BASE}/auth/login",
        json={"tenant_slug": loja.slug, "email": corpo["email"], "password": SENHA},
    )
    token = entrada.json()["access_token"]

    recusado = await client.post(
        f"{BASE}/users",
        headers=_auth(token),
        json={
            "email": f"outro-{uuid.uuid4().hex[:6]}@teste-decko.com.br",
            "full_name": "Outro",
            "senha_inicial": SENHA,
            "papeis": [],
        },
    )
    assert recusado.status_code == 403, recusado.text


async def test_operador_nao_alcanca_o_relatorio_do_dia(client: AsyncClient, loja: Loja) -> None:
    """O papel some do menu, mas quem recusa de verdade é o servidor.

    O relatório soma o dia inteiro entre operadores e mostra o esperado em espécie. Deixar
    o operador alcançá-lo entregaria o número antes da contagem, que é o mesmo vazamento
    que a conferência cega da ADR 0008 existe para impedir.
    """
    corpo = (await _criar(client, loja)).json()
    entrada = await client.post(
        f"{BASE}/auth/login",
        json={"tenant_slug": loja.slug, "email": corpo["email"], "password": SENHA},
    )
    token = entrada.json()["access_token"]
    periodo = {"de": "2026-11-10T00:00:00-03:00", "ate": "2026-11-10T23:59:59-03:00"}

    recusado = await client.get("/api/v1/pdv/conferencia", headers=_auth(token), params=periodo)
    assert recusado.status_code == 403, recusado.text

    # E o dono alcança, para o teste não passar por o endpoint estar quebrado para todos.
    permitido = await client.get(
        "/api/v1/pdv/conferencia", headers=_auth(loja.token), params=periodo
    )
    assert permitido.status_code == 200, permitido.text


async def test_troca_de_senha_tira_a_senha_que_o_dono_escolheu(
    client: AsyncClient, loja: Loja
) -> None:
    """Enquanto o dono souber a senha do operador, "quem fez" é sempre contestável."""
    corpo = (await _criar(client, loja)).json()
    entrada = await client.post(
        f"{BASE}/auth/login",
        json={"tenant_slug": loja.slug, "email": corpo["email"], "password": SENHA},
    )
    token = entrada.json()["access_token"]

    trocada = await client.post(
        f"{BASE}/auth/senha",
        headers=_auth(token),
        json={"senha_atual": SENHA, "nova_senha": NOVA_SENHA},
    )
    assert trocada.status_code == 204, trocada.text

    # A senha antiga, que o dono conhece, deixa de servir.
    velha = await client.post(
        f"{BASE}/auth/login",
        json={"tenant_slug": loja.slug, "email": corpo["email"], "password": SENHA},
    )
    assert velha.status_code == 401

    nova = await client.post(
        f"{BASE}/auth/login",
        json={"tenant_slug": loja.slug, "email": corpo["email"], "password": NOVA_SENHA},
    )
    assert nova.status_code == 200, nova.text
    sessao = (
        await client.get(f"{BASE}/auth/me", headers=_auth(nova.json()["access_token"]))
    ).json()
    assert sessao["user"]["must_change_password"] is False


async def test_troca_de_senha_confere_a_atual(client: AsyncClient, loja: Loja) -> None:
    """Terminal deixado aberto no balcão não pode virar tomada de conta."""
    corpo = (await _criar(client, loja)).json()
    entrada = await client.post(
        f"{BASE}/auth/login",
        json={"tenant_slug": loja.slug, "email": corpo["email"], "password": SENHA},
    )

    recusada = await client.post(
        f"{BASE}/auth/senha",
        headers=_auth(entrada.json()["access_token"]),
        json={"senha_atual": "chute", "nova_senha": NOVA_SENHA},
    )
    assert recusada.status_code == 422, recusada.text


async def test_email_repetido_na_mesma_empresa_e_recusado(client: AsyncClient, loja: Loja) -> None:
    email = f"repetido-{uuid.uuid4().hex[:6]}@teste-decko.com.br"
    assert (await _criar(client, loja, email=email)).status_code == 201

    segunda = await _criar(client, loja, email=email)
    assert segunda.status_code == 422
    assert "Já existe" in segunda.json()["detail"]


async def test_ninguem_troca_os_proprios_papeis(client: AsyncClient, loja: Loja) -> None:
    """Quem tirasse de si a administração ficaria trancado fora da própria empresa."""
    usuarios = (await client.get(f"{BASE}/users", headers=_auth(loja.token))).json()
    dono = next(u for u in usuarios if u["email"] == loja.email)

    recusado = await client.put(
        f"{BASE}/users/{dono['id']}/papeis", headers=_auth(loja.token), json={"papeis": []}
    )
    assert recusado.status_code == 422

    desligar = await client.post(
        f"{BASE}/users/{dono['id']}/situacao", headers=_auth(loja.token), params={"ativo": False}
    )
    assert desligar.status_code == 422


async def test_desligar_o_acesso_impede_a_entrada(client: AsyncClient, loja: Loja) -> None:
    corpo = (await _criar(client, loja)).json()

    desligado = await client.post(
        f"{BASE}/users/{corpo['id']}/situacao",
        headers=_auth(loja.token),
        params={"ativo": False},
    )
    assert desligado.status_code == 200, desligado.text
    assert desligado.json()["is_active"] is False

    recusado = await client.post(
        f"{BASE}/auth/login",
        json={"tenant_slug": loja.slug, "email": corpo["email"], "password": SENHA},
    )
    assert recusado.status_code == 401


async def test_trocar_o_papel_muda_o_que_a_pessoa_alcanca(client: AsyncClient, loja: Loja) -> None:
    corpo = (await _criar(client, loja)).json()
    supervisor = await _papel(client, loja, SUPERVISOR)

    trocado = await client.put(
        f"{BASE}/users/{corpo['id']}/papeis",
        headers=_auth(loja.token),
        json={"papeis": [supervisor["id"]]},
    )
    assert trocado.status_code == 200, trocado.text
    # Substitui, não acrescenta: quem desmarca na tela espera que saia.
    assert [p["name"] for p in trocado.json()["papeis"]] == [SUPERVISOR]

    entrada = await client.post(
        f"{BASE}/auth/login",
        json={"tenant_slug": loja.slug, "email": corpo["email"], "password": SENHA},
    )
    sessao = (
        await client.get(f"{BASE}/auth/me", headers=_auth(entrada.json()["access_token"]))
    ).json()
    assert "pdv.caixa.fechar" in sessao["permissions"]


async def test_a_trilha_registra_quem_criou_e_nunca_a_senha(
    client: AsyncClient, loja: Loja
) -> None:
    corpo = (await _criar(client, loja)).json()

    async with SessionFactory() as session:
        await bind_tenant(session, loja.tenant_id)
        linha = (
            await session.execute(
                select(AuditLog).where(
                    AuditLog.tenant_id == loja.tenant_id,
                    AuditLog.action == "user.create",
                    AuditLog.entity_id == corpo["id"],
                )
            )
        ).scalar_one()

    assert linha.data is not None
    assert linha.data["email"] == corpo["email"]
    # Senha não entra na trilha em forma nenhuma — ver o cabeçalho de `audit.py`.
    assert SENHA not in str(linha.data)
