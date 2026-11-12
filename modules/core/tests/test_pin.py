"""Entrada rápida no balcão: crachá identifica, PIN autentica.

O que estes testes guardam é o que torna um PIN de quatro dígitos defensável
(`docs/adr/0020-operador-supervisor-e-papeis.md`, decisão 1):

- ele **só vale a partir de uma estação já autenticada** na empresa — é o login completo
  que diz "este aparelho é da loja"; o PIN diz apenas quem está nele agora;
- erra cinco vezes e **bloqueia**, senão quem ficar sozinho com a estação percorre dez mil
  combinações sem pressa;
- o PIN é **da pessoa**: para gravá-lo é preciso a senha dela, e o dono só consegue
  **apagá-lo**, nunca escolhê-lo.
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

SENHA_DONO = "senha-local-de-teste-123"
SENHA_OPERADOR = "senha-da-operadora-456"
PIN = "4731"
BASE = "/api/v1/core"


@dataclass
class Loja:
    tenant_id: uuid.UUID
    slug: str
    dono: str
    token_dono: str
    operador_id: str
    operador_email: str
    token_operador: str


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as http:
        yield http


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _entrar(client: AsyncClient, slug: str, email: str, senha: str):
    return await client.post(
        f"{BASE}/auth/login", json={"tenant_slug": slug, "email": email, "password": senha}
    )


@pytest_asyncio.fixture
async def loja(client: AsyncClient) -> AsyncIterator[Loja]:
    sufixo = uuid.uuid4().hex[:8]
    slug = f"pin-{sufixo}"
    dono = f"dono-{sufixo}@teste-decko.com.br"
    operador = f"caixa-{sufixo}@teste-decko.com.br"

    async with SessionFactory() as session, session.begin():
        tenant, _user, _ = await _bootstrap(
            session,
            tenant_name="Loja do PIN",
            tenant_slug=slug,
            admin_email=dono,
            admin_name="Dono da Loja",
            password=SENHA_DONO,
            modules=["comercial", "pdv"],
        )
        tenant_id = tenant.id

    token_dono = (await _entrar(client, slug, dono, SENHA_DONO)).json()["access_token"]
    papeis = (await client.get(f"{BASE}/papeis", headers=_auth(token_dono))).json()
    operador_papel = next(p for p in papeis if p["name"] == "Operador de caixa")

    criado = await client.post(
        f"{BASE}/users",
        headers=_auth(token_dono),
        json={
            "email": operador,
            "full_name": "Maria Operadora",
            "senha_inicial": SENHA_DONO,
            "papeis": [operador_papel["id"]],
        },
    )
    assert criado.status_code == 201, criado.text

    token = (await _entrar(client, slug, operador, SENHA_DONO)).json()["access_token"]
    trocada = await client.post(
        f"{BASE}/auth/senha",
        headers=_auth(token),
        json={"senha_atual": SENHA_DONO, "nova_senha": SENHA_OPERADOR},
    )
    assert trocada.status_code == 204, trocada.text
    token = (await _entrar(client, slug, operador, SENHA_OPERADOR)).json()["access_token"]

    try:
        yield Loja(
            tenant_id=tenant_id,
            slug=slug,
            dono=dono,
            token_dono=token_dono,
            operador_id=criado.json()["id"],
            operador_email=operador,
            token_operador=token,
        )
    finally:
        async with SessionFactory() as session, session.begin():
            await session.execute(delete(Tenant).where(Tenant.id == tenant_id))


async def _definir_pin(client: AsyncClient, token: str, senha: str, pin: str = PIN):
    return await client.put(
        f"{BASE}/auth/pin", headers=_auth(token), json={"senha": senha, "pin": pin}
    )


async def test_a_pessoa_define_o_proprio_pin_com_a_senha_dela(
    client: AsyncClient, loja: Loja
) -> None:
    """Sem a senha, um terminal aberto no balcão viraria PIN gravado em conta alheia."""
    assert (await _definir_pin(client, loja.token_operador, SENHA_OPERADOR)).status_code == 204

    recusado = await _definir_pin(client, loja.token_operador, "chute", "9999")
    assert recusado.status_code == 422
    assert "senha não confere" in recusado.json()["detail"]


async def test_pin_e_so_numero_de_quatro_a_oito_digitos(client: AsyncClient, loja: Loja) -> None:
    """É o formato do teclado numérico do balcão."""
    for ruim in ("12a4", "123", "123456789"):
        recusado = await _definir_pin(client, loja.token_operador, SENHA_OPERADOR, ruim)
        assert recusado.status_code == 422, ruim


async def test_troca_de_operador_pelo_nome_a_partir_da_estacao(
    client: AsyncClient, loja: Loja
) -> None:
    await _definir_pin(client, loja.token_operador, SENHA_OPERADOR)

    # A estação está logada com o dono; a operadora assume com o PIN dela.
    entrou = await client.post(
        f"{BASE}/auth/pin",
        headers=_auth(loja.token_dono),
        json={"user_id": loja.operador_id, "pin": PIN},
    )
    assert entrou.status_code == 200, entrou.text

    sessao = (
        await client.get(f"{BASE}/auth/me", headers=_auth(entrou.json()["access_token"]))
    ).json()
    assert sessao["user"]["email"] == loja.operador_email
    # O token é dela: o que ela faz dali para a frente é dela na trilha.
    assert "pdv.venda.finalizar" in sessao["permissions"]
    assert "core.user.create" not in sessao["permissions"]


async def test_sem_estacao_autenticada_o_pin_nao_vale(client: AsyncClient, loja: Loja) -> None:
    """É esta âncora que sustenta quatro dígitos: sem ela, o PIN seria a porta da frente."""
    await _definir_pin(client, loja.token_operador, SENHA_OPERADOR)

    recusado = await client.post(f"{BASE}/auth/pin", json={"user_id": loja.operador_id, "pin": PIN})
    assert recusado.status_code == 401


async def test_entra_passando_o_cracha(client: AsyncClient, loja: Loja) -> None:
    """O crachá é lido pelo mesmo leitor das vendas, que se apresenta como teclado."""
    await _definir_pin(client, loja.token_operador, SENHA_OPERADOR)
    emitido = await client.put(
        f"{BASE}/users/{loja.operador_id}/cracha",
        headers=_auth(loja.token_dono),
        json={"cracha": "CRACHA-0042"},
    )
    assert emitido.status_code == 200, emitido.text
    assert emitido.json()["cracha"] == "CRACHA-0042"
    assert emitido.json()["tem_pin"] is True

    entrou = await client.post(
        f"{BASE}/auth/pin",
        headers=_auth(loja.token_dono),
        json={"cracha": "CRACHA-0042", "pin": PIN},
    )
    assert entrou.status_code == 200, entrou.text


async def test_cracha_sozinho_nao_entra(client: AsyncClient, loja: Loja) -> None:
    """Identifica, não autentica. Cartão perdido não pode ser a conta de ninguém."""
    await _definir_pin(client, loja.token_operador, SENHA_OPERADOR)
    await client.put(
        f"{BASE}/users/{loja.operador_id}/cracha",
        headers=_auth(loja.token_dono),
        json={"cracha": "CRACHA-0042"},
    )

    recusado = await client.post(
        f"{BASE}/auth/pin",
        headers=_auth(loja.token_dono),
        json={"cracha": "CRACHA-0042", "pin": "0000"},
    )
    assert recusado.status_code == 401


async def test_dois_crachas_iguais_na_mesma_loja_sao_recusados(
    client: AsyncClient, loja: Loja
) -> None:
    await client.put(
        f"{BASE}/users/{loja.operador_id}/cracha",
        headers=_auth(loja.token_dono),
        json={"cracha": "CRACHA-0042"},
    )
    usuarios = (await client.get(f"{BASE}/users", headers=_auth(loja.token_dono))).json()
    dono_id = next(u["id"] for u in usuarios if u["email"] == loja.dono)

    repetido = await client.put(
        f"{BASE}/users/{dono_id}/cracha",
        headers=_auth(loja.token_dono),
        json={"cracha": "CRACHA-0042"},
    )
    assert repetido.status_code == 422, repetido.text


async def test_cinco_erros_bloqueiam_e_a_senha_continua_valendo(
    client: AsyncClient, loja: Loja
) -> None:
    """Sem bloqueio, quem ficar sozinho com a estação percorre dez mil combinações."""
    await _definir_pin(client, loja.token_operador, SENHA_OPERADOR)

    for _ in range(5):
        errado = await client.post(
            f"{BASE}/auth/pin",
            headers=_auth(loja.token_dono),
            json={"user_id": loja.operador_id, "pin": "0000"},
        )
        assert errado.status_code == 401

    # Agora nem o PIN certo entra, e a mensagem diz o que fazer.
    bloqueado = await client.post(
        f"{BASE}/auth/pin",
        headers=_auth(loja.token_dono),
        json={"user_id": loja.operador_id, "pin": PIN},
    )
    assert bloqueado.status_code == 401
    assert "bloqueado" in bloqueado.json()["detail"].lower()

    # O bloqueio é do atalho, não da conta: quem sabe a senha continua entrando.
    assert (
        await _entrar(client, loja.slug, loja.operador_email, SENHA_OPERADOR)
    ).status_code == 200


async def test_acesso_desligado_nao_entra_pelo_pin(client: AsyncClient, loja: Loja) -> None:
    """O caso é o funcionário desligado: o PIN dele não pode ser a porta dos fundos."""
    await _definir_pin(client, loja.token_operador, SENHA_OPERADOR)

    desligado = await client.post(
        f"{BASE}/users/{loja.operador_id}/situacao",
        headers=_auth(loja.token_dono),
        params={"ativo": False},
    )
    assert desligado.status_code == 200, desligado.text

    recusado = await client.post(
        f"{BASE}/auth/pin",
        headers=_auth(loja.token_dono),
        json={"user_id": loja.operador_id, "pin": PIN},
    )
    assert recusado.status_code == 401
    # E some da lista de quem dá para escolher no balcão.
    lista = (await client.get(f"{BASE}/operadores", headers=_auth(loja.token_dono))).json()
    assert lista == []


async def test_o_dono_apaga_o_pin_de_quem_esqueceu(client: AsyncClient, loja: Loja) -> None:
    """Apagar ele pode; escolher, não — senão o PIN deixaria de ser da pessoa."""
    await _definir_pin(client, loja.token_operador, SENHA_OPERADOR)

    apagado = await client.delete(
        f"{BASE}/users/{loja.operador_id}/pin", headers=_auth(loja.token_dono)
    )
    assert apagado.status_code == 200, apagado.text
    assert apagado.json()["tem_pin"] is False

    recusado = await client.post(
        f"{BASE}/auth/pin",
        headers=_auth(loja.token_dono),
        json={"user_id": loja.operador_id, "pin": PIN},
    )
    assert recusado.status_code == 401


async def test_a_lista_de_operadores_so_traz_quem_tem_pin(client: AsyncClient, loja: Loja) -> None:
    vazia = await client.get(f"{BASE}/operadores", headers=_auth(loja.token_dono))
    assert vazia.status_code == 200
    assert vazia.json() == []

    await _definir_pin(client, loja.token_operador, SENHA_OPERADOR)

    lista = (await client.get(f"{BASE}/operadores", headers=_auth(loja.token_dono))).json()
    assert [linha["nome"] for linha in lista] == ["Maria Operadora"]
    # Só o nome: o resto não ajuda quem está no balcão e ajuda quem não deveria.
    assert set(lista[0]) == {"id", "nome"}


async def test_a_trilha_liga_a_troca_a_quem_estava_na_estacao(
    client: AsyncClient, loja: Loja
) -> None:
    await _definir_pin(client, loja.token_operador, SENHA_OPERADOR)
    dono_id = next(
        u["id"]
        for u in (await client.get(f"{BASE}/users", headers=_auth(loja.token_dono))).json()
        if u["email"] == loja.dono
    )

    await client.post(
        f"{BASE}/auth/pin",
        headers=_auth(loja.token_dono),
        json={"user_id": loja.operador_id, "pin": PIN},
    )

    async with SessionFactory() as session:
        await bind_tenant(session, loja.tenant_id)
        linha = (
            await session.execute(
                select(AuditLog).where(
                    AuditLog.tenant_id == loja.tenant_id, AuditLog.action == "auth.pin"
                )
            )
        ).scalar_one()

    assert str(linha.user_id) == loja.operador_id
    # Quem estava antes: é o que liga uma troca de operador à anterior.
    assert linha.data == {"estacao_de": dono_id}


async def test_tentativa_errada_fica_na_trilha(client: AsyncClient, loja: Loja) -> None:
    """É a sequência de tentativas que se investiga depois, e ela não pode sumir."""
    await _definir_pin(client, loja.token_operador, SENHA_OPERADOR)

    await client.post(
        f"{BASE}/auth/pin",
        headers=_auth(loja.token_dono),
        json={"user_id": loja.operador_id, "pin": "0000"},
    )

    async with SessionFactory() as session:
        await bind_tenant(session, loja.tenant_id)
        linha = (
            await session.execute(
                select(AuditLog).where(
                    AuditLog.tenant_id == loja.tenant_id, AuditLog.action == "auth.pin.failed"
                )
            )
        ).scalar_one()

    assert str(linha.user_id) == loja.operador_id
    assert linha.data == {"motivo": "pin_errado"}
    # O PIN digitado não entra na trilha, em forma nenhuma.
    assert "0000" not in str(linha.data)
