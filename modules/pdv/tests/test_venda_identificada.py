"""A venda que aponta para quem comprou.

Venda anônima continua sendo o caso normal — exigir CPF para vender um pão travaria o
balcão. O que estes testes cobrem é o que a identificação **recusa**, que é onde ela
ganha valor: cliente desativado não entra em venda nova, e venda fechada não troca de
dono, porque o cupom precisa continuar dizendo o que o cliente pagou.

Decisão: `docs/adr/0008-ponto-de-venda.md`, atualização de 29/10/2026.
"""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from decko.db import SessionFactory
from decko.main import create_app
from decko_modules.core.cli import _bootstrap
from decko_modules.core.models import Tenant

PASSWORD = "senha-local-de-teste-123"
CORE = "/api/v1/core"
CLIENTES = "/api/v1/clientes"
COMERCIAL = "/api/v1/comercial"
PDV = "/api/v1/pdv"


@dataclass
class Loja:
    client: AsyncClient
    tenant_id: uuid.UUID
    token: str

    @property
    def auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


@pytest_asyncio.fixture
async def loja() -> AsyncIterator[Loja]:
    sufixo = uuid.uuid4().hex[:8]
    slug = f"balcao-{sufixo}"
    email = f"caixa-{sufixo}@teste-decko.com.br"

    async with SessionFactory() as session, session.begin():
        tenant, _user, _granted = await _bootstrap(
            session,
            tenant_name="Loja de Teste",
            tenant_slug=slug,
            admin_email=email,
            admin_name="Operador",
            password=PASSWORD,
            # O PDV passou a depender de `clientes`; aqui os três são ativados à mão
            # porque o bootstrap não resolve a árvore — quem resolve é a vitrine.
            modules=["comercial", "clientes", "pdv"],
        )
        tenant_id = tenant.id

    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as http:
        login = await http.post(
            f"{CORE}/auth/login",
            json={"tenant_slug": slug, "email": email, "password": PASSWORD},
        )
        assert login.status_code == 200, login.text
        try:
            yield Loja(client=http, tenant_id=tenant_id, token=login.json()["access_token"])
        finally:
            async with SessionFactory() as session, session.begin():
                await session.execute(delete(Tenant).where(Tenant.id == tenant_id))


async def _cliente(loja: Loja, nome: str = "Maria Souza") -> str:
    criado = await loja.client.post(
        f"{CLIENTES}/clientes", headers=loja.auth, json={"nome": nome, "tipo": "fisica"}
    )
    assert criado.status_code == 201, criado.text
    return str(criado.json()["id"])


async def _venda(loja: Loja) -> str:
    aberta = await loja.client.post(f"{PDV}/vendas", headers=loja.auth, json={})
    assert aberta.status_code == 201, aberta.text
    return str(aberta.json()["id"])


async def _vendavel(loja: Loja, venda_id: str) -> None:
    """Põe a venda em condição de ser fechada: um item e o dinheiro na mesa.

    Fechar venda vazia é recusado — e deve ser mesmo.
    """
    unidades = await loja.client.get(f"{COMERCIAL}/unidades", headers=loja.auth)
    unidade_id = next(u["id"] for u in unidades.json() if u["nome"] == "Unidade")

    produto = await loja.client.post(
        f"{COMERCIAL}/produtos",
        headers=loja.auth,
        json={
            "codigo": f"COD-{uuid.uuid4().hex[:6]}",
            "nome": "Pão francês",
            "unidade_id": unidade_id,
            "preco_venda": "1.00",
        },
    )
    assert produto.status_code == 201, produto.text

    item = await loja.client.post(
        f"{PDV}/vendas/{venda_id}/itens",
        headers=loja.auth,
        json={"produto_id": produto.json()["id"], "quantidade": "1"},
    )
    assert item.status_code == 200, item.text

    pago = await loja.client.post(
        f"{PDV}/vendas/{venda_id}/pagamentos",
        headers=loja.auth,
        json={"forma": "dinheiro", "valor": "1.00"},
    )
    assert pago.status_code == 200, pago.text


async def _identificar(loja: Loja, venda_id: str, cliente_id: str):
    return await loja.client.put(
        f"{PDV}/vendas/{venda_id}/cliente",
        headers=loja.auth,
        json={"cliente_id": cliente_id},
    )


async def test_venda_nasce_anonima(loja: Loja) -> None:
    """O balcão vende sem perguntar quem é. Identificar é opção, não etapa."""
    venda = await loja.client.post(f"{PDV}/vendas", headers=loja.auth, json={})

    assert venda.json()["cliente_id"] is None
    assert venda.json()["cliente_nome"] is None


async def test_identificar_a_venda(loja: Loja) -> None:
    cliente_id = await _cliente(loja)
    venda_id = await _venda(loja)

    identificada = await _identificar(loja, venda_id, cliente_id)

    assert identificada.status_code == 200, identificada.text
    assert identificada.json()["cliente_id"] == cliente_id
    assert identificada.json()["cliente_nome"] == "Maria Souza"


async def test_desidentificar(loja: Loja) -> None:
    """Errar o cliente no balcão é comum, e tem de ser reversível."""
    cliente_id = await _cliente(loja)
    venda_id = await _venda(loja)
    await _identificar(loja, venda_id, cliente_id)

    anonima = await loja.client.delete(f"{PDV}/vendas/{venda_id}/cliente", headers=loja.auth)

    assert anonima.status_code == 200, anonima.text
    assert anonima.json()["cliente_id"] is None


async def test_trocar_o_cliente_da_venda(loja: Loja) -> None:
    primeiro = await _cliente(loja, "Maria Souza")
    segundo = await _cliente(loja, "Joao Lima")
    venda_id = await _venda(loja)
    await _identificar(loja, venda_id, primeiro)

    trocada = await _identificar(loja, venda_id, segundo)

    assert trocada.json()["cliente_nome"] == "Joao Lima"


async def test_cliente_desativado_nao_entra_em_venda_nova(loja: Loja) -> None:
    """Desativar quer dizer "não use mais daqui para frente"."""
    cliente_id = await _cliente(loja)
    desativado = await loja.client.post(
        f"{CLIENTES}/clientes/{cliente_id}/desativar", headers=loja.auth
    )
    assert desativado.status_code == 200, desativado.text
    venda_id = await _venda(loja)

    recusada = await _identificar(loja, venda_id, cliente_id)

    assert recusada.status_code == 422
    assert "desativado" in recusada.json()["detail"]


async def test_venda_fechada_nao_troca_de_dono(loja: Loja) -> None:
    """Depois de fechada, a venda é documento entregue: o cupom diz o que foi pago."""
    cliente_id = await _cliente(loja)
    venda_id = await _venda(loja)
    await _vendavel(loja, venda_id)
    fechada = await loja.client.post(f"{PDV}/vendas/{venda_id}/finalizar", headers=loja.auth)
    assert fechada.status_code == 200, fechada.text

    recusada = await _identificar(loja, venda_id, cliente_id)

    assert recusada.status_code == 422
    assert "finalizada" in recusada.json()["detail"]


async def test_venda_identificada_continua_identificada_depois_de_fechada(loja: Loja) -> None:
    cliente_id = await _cliente(loja)
    venda_id = await _venda(loja)
    await _identificar(loja, venda_id, cliente_id)
    await _vendavel(loja, venda_id)

    fechada = await loja.client.post(f"{PDV}/vendas/{venda_id}/finalizar", headers=loja.auth)

    assert fechada.status_code == 200, fechada.text
    assert fechada.json()["cliente_id"] == cliente_id
    assert fechada.json()["cliente_nome"] == "Maria Souza"


async def test_o_nome_e_lido_na_hora_e_nao_copiado(loja: Loja) -> None:
    """Corrigir um nome digitado errado precisa valer para as vendas da pessoa também.

    É a diferença para o preço e a descrição do item, que são cópia: aquilo é fato
    histórico, isto é cadastro.
    """
    cliente_id = await _cliente(loja, "Maira Souza")
    venda_id = await _venda(loja)
    await _identificar(loja, venda_id, cliente_id)

    corrigido = await loja.client.put(
        f"{CLIENTES}/clientes/{cliente_id}",
        headers=loja.auth,
        json={"nome": "Maria Souza", "tipo": "fisica"},
    )
    assert corrigido.status_code == 200, corrigido.text

    venda = await loja.client.get(f"{PDV}/vendas/{venda_id}", headers=loja.auth)
    assert venda.json()["cliente_nome"] == "Maria Souza"


async def test_cliente_inexistente_e_recusado(loja: Loja) -> None:
    venda_id = await _venda(loja)

    recusada = await _identificar(loja, venda_id, str(uuid.uuid4()))

    assert recusada.status_code == 422
    assert "não encontrado" in recusada.json()["detail"]


async def test_identificar_exige_autenticacao(loja: Loja) -> None:
    venda_id = await _venda(loja)

    sem_token = await loja.client.put(
        f"{PDV}/vendas/{venda_id}/cliente", json={"cliente_id": str(uuid.uuid4())}
    )

    assert sem_token.status_code == 401
