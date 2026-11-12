"""O que o operador não faz sozinho.

O pedido do dono do projeto, em 10/11/2026: *"quando tem que cancelar algum produto sendo
vendido ele precisa da credencial do supervisor sendo batido, aquilo tem que ter um log de
registro pra evitar fraudes, caixa 2 entre outras coisas."*

O que estes testes guardam, da `docs/adr/0020-operador-supervisor-e-papeis.md`:

- a credencial vai **junto com a ação** e o servidor confere antes de executar — nunca
  "destravar a tela", que quem abre o inspetor burla;
- quem libera precisa **poder** liberar, conferido no banco e não no token de quem pediu;
- a trilha guarda **as duas pessoas**, porque "sangria de R$ 200" sozinho não responde
  nada numa investigação.
"""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from decimal import Decimal

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from decko.db import SessionFactory, bind_tenant
from decko.main import create_app
from decko_modules.core.cli import _bootstrap
from decko_modules.core.models import Role, RolePermission, Tenant
from decko_modules.pdv.models import Autorizacao

SENHA_DONO = "senha-local-de-teste-123"
SENHA_OPERADOR = "senha-da-operadora-456"
SENHA_SUPERVISOR = "senha-do-supervisor-789"

CORE = "/api/v1/core"
COMERCIAL = "/api/v1/comercial"
PDV = "/api/v1/pdv"

OPERADOR = "Operador de caixa"
SUPERVISOR = "Supervisor de caixa"


@dataclass
class Loja:
    tenant_id: uuid.UUID
    slug: str
    dono: str
    operador: str
    supervisor: str
    supervisor_id: str
    operador_id: str


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as http:
        yield http


async def _entrar(client: AsyncClient, slug: str, email: str, senha: str) -> str:
    resposta = await client.post(
        f"{CORE}/auth/login", json={"tenant_slug": slug, "email": email, "password": senha}
    )
    assert resposta.status_code == 200, resposta.text
    return str(resposta.json()["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _trocar_senha(client: AsyncClient, token: str, atual: str, nova: str) -> str:
    """Quem o dono cria entra com senha inicial e é obrigado a trocá-la — ADR 0020."""
    resposta = await client.post(
        f"{CORE}/auth/senha",
        headers=_auth(token),
        json={"senha_atual": atual, "nova_senha": nova},
    )
    assert resposta.status_code == 204, resposta.text
    return nova


@pytest_asyncio.fixture
async def loja(client: AsyncClient) -> AsyncIterator[Loja]:
    sufixo = uuid.uuid4().hex[:8]
    slug = f"autoriza-{sufixo}"
    dono = f"dono-{sufixo}@teste-decko.com.br"

    async with SessionFactory() as session, session.begin():
        tenant, _user, _ = await _bootstrap(
            session,
            tenant_name="Loja da Autorizacao",
            tenant_slug=slug,
            admin_email=dono,
            admin_name="Dono da Loja",
            password=SENHA_DONO,
            modules=["comercial", "pdv"],
        )
        tenant_id = tenant.id

    token_dono = await _entrar(client, slug, dono, SENHA_DONO)
    papeis = (await client.get(f"{CORE}/papeis", headers=_auth(token_dono))).json()
    por_nome = {p["name"]: p["id"] for p in papeis}

    criados = {}
    for nome, papel, senha in (
        ("operador", OPERADOR, SENHA_OPERADOR),
        ("supervisor", SUPERVISOR, SENHA_SUPERVISOR),
    ):
        email = f"{nome}-{sufixo}@teste-decko.com.br"
        resposta = await client.post(
            f"{CORE}/users",
            headers=_auth(token_dono),
            json={
                "email": email,
                "full_name": f"{nome.capitalize()} de Teste",
                "senha_inicial": SENHA_DONO,
                "papeis": [por_nome[papel]],
            },
        )
        assert resposta.status_code == 201, resposta.text
        token = await _entrar(client, slug, email, SENHA_DONO)
        await _trocar_senha(client, token, SENHA_DONO, senha)
        criados[nome] = (email, resposta.json()["id"])

    try:
        yield Loja(
            tenant_id=tenant_id,
            slug=slug,
            dono=dono,
            operador=criados["operador"][0],
            supervisor=criados["supervisor"][0],
            operador_id=criados["operador"][1],
            supervisor_id=criados["supervisor"][1],
        )
    finally:
        async with SessionFactory() as session, session.begin():
            await session.execute(delete(Tenant).where(Tenant.id == tenant_id))


async def _como_operador(client: AsyncClient, loja: Loja) -> str:
    return await _entrar(client, loja.slug, loja.operador, SENHA_OPERADOR)


async def _como_supervisor(client: AsyncClient, loja: Loja) -> str:
    return await _entrar(client, loja.slug, loja.supervisor, SENHA_SUPERVISOR)


def _credencial(loja: Loja, senha: str = SENHA_SUPERVISOR) -> dict:
    return {"autorizador_id": loja.supervisor_id, "senha": senha}


async def _produto(client: AsyncClient, loja: Loja) -> str:
    token = await _entrar(client, loja.slug, loja.dono, SENHA_DONO)
    unidades = (await client.get(f"{COMERCIAL}/unidades", headers=_auth(token))).json()
    unidade_id = next(u["id"] for u in unidades if u["nome"] == "Unidade")

    produto = await client.post(
        f"{COMERCIAL}/produtos",
        headers=_auth(token),
        json={
            "codigo": f"COD-{uuid.uuid4().hex[:6]}",
            "nome": "Refrigerante 2L",
            "unidade_id": unidade_id,
            "preco_venda": "10.00",
        },
    )
    assert produto.status_code == 201, produto.text
    entrada = await client.post(
        f"{COMERCIAL}/movimentos",
        headers=_auth(token),
        json={
            "produto_id": produto.json()["id"],
            "tipo": "entrada",
            "quantidade": "50",
            "unidade_id": unidade_id,
            "documento": "Carga do teste",
        },
    )
    assert entrada.status_code == 201, entrada.text
    return str(produto.json()["id"])


async def _venda_com_item(client: AsyncClient, token: str, produto_id: str) -> tuple[str, str]:
    venda_id = (await client.post(f"{PDV}/vendas", headers=_auth(token))).json()["id"]
    com_item = await client.post(
        f"{PDV}/vendas/{venda_id}/itens",
        headers=_auth(token),
        json={"produto_id": produto_id, "quantidade": "2"},
    )
    assert com_item.status_code == 200, com_item.text
    return venda_id, str(com_item.json()["itens"][0]["id"])


async def _autorizacoes(loja: Loja) -> list[Autorizacao]:
    async with SessionFactory() as session:
        await bind_tenant(session, loja.tenant_id)
        return list(
            (
                await session.execute(
                    select(Autorizacao).where(Autorizacao.tenant_id == loja.tenant_id)
                )
            )
            .scalars()
            .all()
        )


async def test_a_loja_nasce_exigindo_o_que_foi_escolhido(client: AsyncClient, loja: Loja) -> None:
    """As quatro escolhidas nascem ligadas; as que dependem de um número, não."""
    token = await _como_operador(client, loja)
    config = (await client.get(f"{PDV}/configuracao", headers=_auth(token))).json()

    assert config["exige_cancelar_item"] is True
    assert config["exige_cancelar_venda"] is True
    assert config["exige_sangria"] is True
    assert config["exige_devolucao"] is True
    # Ligar estas duas exige escolher o limite, e inventar o limite seria inventar regra.
    assert config["exige_desconto"] is False
    assert config["exige_diferenca"] is False


async def test_operador_sozinho_nao_retira_item(client: AsyncClient, loja: Loja) -> None:
    """428 e não 403: ele **pode**, com a liberação de alguém — e a tela precisa saber."""
    produto_id = await _produto(client, loja)
    token = await _como_operador(client, loja)
    venda_id, item_id = await _venda_com_item(client, token, produto_id)

    recusado = await client.post(
        f"{PDV}/vendas/{venda_id}/itens/{item_id}/retirar", headers=_auth(token)
    )
    assert recusado.status_code == 428, recusado.text
    assert recusado.json()["detail"]["acao"] == "cancelar_item"
    assert await _autorizacoes(loja) == []


async def test_com_a_credencial_do_supervisor_retira_e_fica_registrado(
    client: AsyncClient, loja: Loja
) -> None:
    produto_id = await _produto(client, loja)
    token = await _como_operador(client, loja)
    venda_id, item_id = await _venda_com_item(client, token, produto_id)

    liberado = await client.post(
        f"{PDV}/vendas/{venda_id}/itens/{item_id}/retirar",
        headers=_auth(token),
        json={"autorizacao": _credencial(loja)},
    )
    assert liberado.status_code == 200, liberado.text
    assert liberado.json()["itens"] == []

    # As duas pessoas: uma linha que diz só "item retirado" não responde nada depois.
    registradas = await _autorizacoes(loja)
    assert len(registradas) == 1
    assert str(registradas[0].solicitante_id) == loja.operador_id
    assert str(registradas[0].autorizador_id) == loja.supervisor_id
    assert registradas[0].acao.value == "cancelar_item"


async def test_senha_errada_do_supervisor_nao_libera(client: AsyncClient, loja: Loja) -> None:
    produto_id = await _produto(client, loja)
    token = await _como_operador(client, loja)
    venda_id, item_id = await _venda_com_item(client, token, produto_id)

    recusado = await client.post(
        f"{PDV}/vendas/{venda_id}/itens/{item_id}/retirar",
        headers=_auth(token),
        json={"autorizacao": _credencial(loja, senha="chute")},
    )
    assert recusado.status_code == 422, recusado.text
    assert "senha do supervisor" in recusado.json()["detail"]
    assert await _autorizacoes(loja) == []


async def test_quem_nao_pode_liberar_nao_libera(client: AsyncClient, loja: Loja) -> None:
    """O operador conhece a própria senha. Se ela servisse, a trava não existiria."""
    produto_id = await _produto(client, loja)
    token = await _como_operador(client, loja)
    venda_id, item_id = await _venda_com_item(client, token, produto_id)

    recusado = await client.post(
        f"{PDV}/vendas/{venda_id}/itens/{item_id}/retirar",
        headers=_auth(token),
        json={"autorizacao": {"autorizador_id": loja.operador_id, "senha": SENHA_OPERADOR}},
    )
    assert recusado.status_code == 422, recusado.text
    assert "não pode liberar" in recusado.json()["detail"]


async def test_supervisor_operando_nao_chama_a_si_mesmo(client: AsyncClient, loja: Loja) -> None:
    produto_id = await _produto(client, loja)
    token = await _como_supervisor(client, loja)
    venda_id, item_id = await _venda_com_item(client, token, produto_id)

    direto = await client.post(
        f"{PDV}/vendas/{venda_id}/itens/{item_id}/retirar", headers=_auth(token)
    )
    assert direto.status_code == 200, direto.text
    # Nada a registrar: quem fez já continua registrado na própria ação.
    assert await _autorizacoes(loja) == []


async def test_cancelar_a_venda_pede_supervisor(client: AsyncClient, loja: Loja) -> None:
    produto_id = await _produto(client, loja)
    token = await _como_operador(client, loja)
    venda_id, _item_id = await _venda_com_item(client, token, produto_id)

    recusado = await client.post(f"{PDV}/vendas/{venda_id}/cancelar", headers=_auth(token))
    assert recusado.status_code == 428, recusado.text

    liberado = await client.post(
        f"{PDV}/vendas/{venda_id}/cancelar",
        headers=_auth(token),
        json={"autorizacao": _credencial(loja)},
    )
    assert liberado.status_code == 200, liberado.text
    assert liberado.json()["status"] == "cancelada"


async def test_sangria_pede_supervisor_e_suprimento_nao(client: AsyncClient, loja: Loja) -> None:
    """Dinheiro entrando na gaveta não é o que se desvia; parar o balcão por isso é à toa."""
    token = await _como_operador(client, loja)
    caixa_id = (
        await client.post(f"{PDV}/caixa", headers=_auth(token), json={"abertura": "100.00"})
    ).json()["id"]

    suprimento = await client.post(
        f"{PDV}/caixa/{caixa_id}/movimentos",
        headers=_auth(token),
        json={"tipo": "suprimento", "valor": "20.00", "motivo": "Troco do mercado"},
    )
    assert suprimento.status_code == 200, suprimento.text

    sangria = await client.post(
        f"{PDV}/caixa/{caixa_id}/movimentos",
        headers=_auth(token),
        json={"tipo": "sangria", "valor": "50.00", "motivo": "Depósito no banco"},
    )
    assert sangria.status_code == 428, sangria.text

    liberada = await client.post(
        f"{PDV}/caixa/{caixa_id}/movimentos",
        headers=_auth(token),
        json={
            "tipo": "sangria",
            "valor": "50.00",
            "motivo": "Depósito no banco",
            "autorizacao": _credencial(loja),
        },
    )
    assert liberada.status_code == 200, liberada.text

    registradas = await _autorizacoes(loja)
    assert [a.acao.value for a in registradas] == ["sangria"]
    assert registradas[0].valor == Decimal("50.00")
    # O motivo entra na liberação: é ele que explica a linha meses depois.
    assert registradas[0].motivo == "Depósito no banco"


async def test_desconto_so_pede_acima_do_limite(client: AsyncClient, loja: Loja) -> None:
    produto_id = await _produto(client, loja)
    dono = await _entrar(client, loja.slug, loja.dono, SENHA_DONO)

    atual = (await client.get(f"{PDV}/configuracao", headers=_auth(dono))).json()
    ligada = await client.put(
        f"{PDV}/configuracao",
        headers=_auth(dono),
        json={**atual, "exige_desconto": True, "desconto_livre": "2.00"},
    )
    assert ligada.status_code == 200, ligada.text

    token = await _como_operador(client, loja)
    venda_id, _item = await _venda_com_item(client, token, produto_id)

    dentro = await client.put(
        f"{PDV}/vendas/{venda_id}/desconto", headers=_auth(token), json={"desconto": "2.00"}
    )
    assert dentro.status_code == 200, dentro.text

    acima = await client.put(
        f"{PDV}/vendas/{venda_id}/desconto", headers=_auth(token), json={"desconto": "5.00"}
    )
    assert acima.status_code == 428, acima.text


async def _supervisor_sem_liberar(loja: Loja) -> None:
    """Tira `pdv.autorizar` do papel de supervisor desta loja.

    Existe porque o supervisor semeado **pode liberar a si mesmo**, e um teste que o usa
    para provar a trava do fechamento não prova nada: ele passa pelo caminho de quem não
    precisa de ninguém. Aqui o que se quer é alguém que **fecha e não libera**.
    """
    async with SessionFactory() as session, session.begin():
        await bind_tenant(session, loja.tenant_id)
        papel = (
            await session.execute(
                select(Role).where(Role.tenant_id == loja.tenant_id, Role.name == SUPERVISOR)
            )
        ).scalar_one()
        await session.execute(
            delete(RolePermission).where(
                RolePermission.role_id == papel.id,
                RolePermission.permission == "pdv.autorizar",
            )
        )


async def _id_do_dono(client: AsyncClient, loja: Loja, token: str) -> str:
    usuarios = (await client.get(f"{CORE}/users", headers=_auth(token))).json()
    return str(next(u["id"] for u in usuarios if u["email"] == loja.dono))


async def test_fechamento_com_diferenca_grande_pede_supervisor(
    client: AsyncClient, loja: Loja
) -> None:
    """Exigir uma segunda pessoa é diferente de travar: o caixa fecha, com ela junto.

    É a única trava deste tipo que o Odoo tem de fábrica (*Set Maximum Difference*).
    """
    dono = await _entrar(client, loja.slug, loja.dono, SENHA_DONO)
    atual = (await client.get(f"{PDV}/configuracao", headers=_auth(dono))).json()
    await client.put(
        f"{PDV}/configuracao",
        headers=_auth(dono),
        json={**atual, "exige_diferenca": True, "diferenca_livre": "5.00"},
    )
    dono_id = await _id_do_dono(client, loja, dono)
    await _supervisor_sem_liberar(loja)

    token = await _como_supervisor(client, loja)
    caixa_id = (
        await client.post(f"{PDV}/caixa", headers=_auth(token), json={"abertura": "100.00"})
    ).json()["id"]

    # Noventa reais a menos: muito acima dos cinco que a loja aceita sem segunda pessoa.
    recusado = await client.post(
        f"{PDV}/caixa/{caixa_id}/fechar", headers=_auth(token), json={"contado": "10.00"}
    )
    assert recusado.status_code == 428, recusado.text
    assert recusado.json()["detail"]["acao"] == "fechar_caixa"

    # Dentro do limite, fecha sozinho: a trava é sobre a diferença, não sobre fechar.
    dentro = await client.post(
        f"{PDV}/caixa/{caixa_id}/fechar", headers=_auth(token), json={"contado": "97.00"}
    )
    assert dentro.status_code == 200, dentro.text
    assert Decimal(dentro.json()["diferenca"]) == Decimal("-3.00")

    # E com a segunda pessoa, a diferença grande fecha — e fica registrada.
    outro = (
        await client.post(f"{PDV}/caixa", headers=_auth(token), json={"abertura": "100.00"})
    ).json()["id"]
    com_dono = await client.post(
        f"{PDV}/caixa/{outro}/fechar",
        headers=_auth(token),
        json={
            "contado": "10.00",
            "autorizacao": {"autorizador_id": dono_id, "senha": SENHA_DONO},
        },
    )
    assert com_dono.status_code == 200, com_dono.text
    assert Decimal(com_dono.json()["diferenca"]) == Decimal("-90.00")

    registradas = await _autorizacoes(loja)
    assert [a.acao.value for a in registradas] == ["fechar_caixa"]
    assert str(registradas[0].autorizador_id) == dono_id


async def test_o_428_do_fechamento_nao_entrega_o_esperado(client: AsyncClient, loja: Loja) -> None:
    """A conferência é cega, e a trava do fechamento não pode furá-la por outra porta.

    O servidor **precisa** calcular o esperado para medir a diferença. O que ele não pode
    é devolvê-lo: bastaria pedir um fechamento qualquer para ver o número antes de contar.
    """
    dono = await _entrar(client, loja.slug, loja.dono, SENHA_DONO)
    atual = (await client.get(f"{PDV}/configuracao", headers=_auth(dono))).json()
    await client.put(
        f"{PDV}/configuracao",
        headers=_auth(dono),
        json={**atual, "exige_diferenca": True, "diferenca_livre": "1.00"},
    )
    await _supervisor_sem_liberar(loja)

    token = await _como_supervisor(client, loja)
    caixa_id = (
        await client.post(f"{PDV}/caixa", headers=_auth(token), json={"abertura": "137.42"})
    ).json()["id"]

    recusado = await client.post(
        f"{PDV}/caixa/{caixa_id}/fechar", headers=_auth(token), json={"contado": "0.00"}
    )
    assert recusado.status_code == 428, recusado.text
    # Nem o esperado, nem a diferença: os dois dariam o número da gaveta por subtração.
    assert "137" not in recusado.text
    assert "esperado" not in recusado.text.lower()


async def test_a_lista_de_quem_libera_traz_so_nome_e_so_quem_pode(
    client: AsyncClient, loja: Loja
) -> None:
    token = await _como_operador(client, loja)
    lista = await client.get(f"{PDV}/autorizadores", headers=_auth(token))

    assert lista.status_code == 200, lista.text
    nomes = {linha["nome"] for linha in lista.json()}
    assert "Supervisor de Teste" in nomes
    # O operador não aparece: ele não pode liberar nada.
    assert "Operador de Teste" not in nomes
    # E o e-mail não sai daqui: a senha é o que libera, não a lista.
    assert all(set(linha) == {"id", "nome"} for linha in lista.json())


async def test_desligar_a_exigencia_devolve_a_acao_ao_operador(
    client: AsyncClient, loja: Loja
) -> None:
    """Cada loja liga o que quiser. Quem decide isso é o dono, não o fornecedor."""
    produto_id = await _produto(client, loja)
    dono = await _entrar(client, loja.slug, loja.dono, SENHA_DONO)
    atual = (await client.get(f"{PDV}/configuracao", headers=_auth(dono))).json()
    await client.put(
        f"{PDV}/configuracao", headers=_auth(dono), json={**atual, "exige_cancelar_item": False}
    )

    token = await _como_operador(client, loja)
    venda_id, item_id = await _venda_com_item(client, token, produto_id)

    direto = await client.post(
        f"{PDV}/vendas/{venda_id}/itens/{item_id}/retirar", headers=_auth(token)
    )
    assert direto.status_code == 200, direto.text
    assert await _autorizacoes(loja) == []
