"""A venda pela API, do jeito que a tela do caixa a faz.

O serviço já é testado contra o banco em ``test_pdv.py``. Aqui o que se prova é o caminho
inteiro: abrir, bipar, receber, fechar — e que o total que o caixa mostra vem do servidor,
não de uma soma feita na tela.
"""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from decko.db import SessionFactory
from decko.main import create_app
from decko_modules.core.cli import _bootstrap
from decko_modules.core.models import Tenant

PASSWORD = "senha-local-de-teste-123"
CORE = "/api/v1/core"
COMERCIAL = "/api/v1/comercial"
PDV = "/api/v1/pdv"


@dataclass
class Loja:
    tenant_id: uuid.UUID
    token: str


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    criadas: list[uuid.UUID] = []
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as http:
        http.criadas = criadas  # type: ignore[attr-defined]
        try:
            yield http
        finally:
            async with SessionFactory() as session, session.begin():
                for tenant_id in criadas:
                    await session.execute(delete(Tenant).where(Tenant.id == tenant_id))


async def _loja(client: AsyncClient) -> Loja:
    sufixo = uuid.uuid4().hex[:8]
    slug = f"loja-{sufixo}"
    email = f"caixa-{sufixo}@teste-decko.com.br"

    async with SessionFactory() as session, session.begin():
        tenant, _user, _granted = await _bootstrap(
            session,
            tenant_name="Loja de Teste",
            tenant_slug=slug,
            admin_email=email,
            admin_name="Operador",
            password=PASSWORD,
            modules=["comercial", "pdv"],
        )
        tenant_id = tenant.id

    login = await client.post(
        f"{CORE}/auth/login",
        json={"tenant_slug": slug, "email": email, "password": PASSWORD},
    )
    assert login.status_code == 200, login.text

    client.criadas.append(tenant_id)  # type: ignore[attr-defined]
    return Loja(tenant_id=tenant_id, token=login.json()["access_token"])


def _auth(loja: Loja) -> dict[str, str]:
    return {"Authorization": f"Bearer {loja.token}"}


async def _unidade_base(client: AsyncClient, loja: Loja) -> str:
    """A unidade raiz chega com o módulo: `comercial` a semeia ao ser contratado.

    Antes este teste a criava. Criar agora bate na restrição de nome único, e isso é o
    comportamento certo — ver docs/adr/0010-dado-semente-com-identidade-estavel.md.
    """
    resposta = await client.get(f"{COMERCIAL}/unidades", headers=_auth(loja))
    assert resposta.status_code == 200, resposta.text
    return str(next(u["id"] for u in resposta.json() if u["nome"] == "Unidade"))


async def _produto(client: AsyncClient, loja: Loja, *, preco: str = "7.50") -> str:
    unidade_id = await _unidade_base(client, loja)

    produto = await client.post(
        f"{COMERCIAL}/produtos",
        headers=_auth(loja),
        json={
            "codigo": f"COD-{uuid.uuid4().hex[:6]}",
            "nome": "Pão francês",
            "unidade_id": unidade_id,
            "preco_venda": preco,
        },
    )
    assert produto.status_code == 201, produto.text

    entrada = await client.post(
        f"{COMERCIAL}/movimentos",
        headers=_auth(loja),
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


async def test_venda_completa_pela_api(client: AsyncClient) -> None:
    loja = await _loja(client)
    produto_id = await _produto(client, loja, preco="7.50")

    aberta = await client.post(f"{PDV}/vendas", headers=_auth(loja))
    assert aberta.status_code == 201, aberta.text
    venda_id = aberta.json()["id"]
    assert aberta.json()["numero"] is None

    com_item = await client.post(
        f"{PDV}/vendas/{venda_id}/itens",
        headers=_auth(loja),
        json={"produto_id": produto_id, "quantidade": "4"},
    )
    assert com_item.status_code == 200, com_item.text
    assert Decimal(com_item.json()["total"]) == Decimal("30.00")
    assert Decimal(com_item.json()["falta"]) == Decimal("30.00")
    assert com_item.json()["itens"][0]["descricao"] == "Pão francês"

    pago = await client.post(
        f"{PDV}/vendas/{venda_id}/pagamentos",
        headers=_auth(loja),
        json={"forma": "dinheiro", "valor": "50.00"},
    )
    assert pago.status_code == 200, pago.text
    assert Decimal(pago.json()["falta"]) == Decimal("0.00")
    assert Decimal(pago.json()["troco"]) == Decimal("20.00")

    fechada = await client.post(f"{PDV}/vendas/{venda_id}/finalizar", headers=_auth(loja))
    assert fechada.status_code == 200, fechada.text
    assert fechada.json()["status"] == "finalizada"
    assert fechada.json()["numero"] == 1

    saldo = await client.get(f"{COMERCIAL}/produtos/{produto_id}/saldo", headers=_auth(loja))
    assert saldo.status_code == 200, saldo.text
    assert Decimal(saldo.json()["quantidade"]) == Decimal(46)


async def test_fechar_sem_pagar_e_recusado_com_motivo(client: AsyncClient) -> None:
    loja = await _loja(client)
    produto_id = await _produto(client, loja)

    venda_id = (await client.post(f"{PDV}/vendas", headers=_auth(loja))).json()["id"]
    await client.post(
        f"{PDV}/vendas/{venda_id}/itens",
        headers=_auth(loja),
        json={"produto_id": produto_id, "quantidade": "1"},
    )

    recusa = await client.post(f"{PDV}/vendas/{venda_id}/finalizar", headers=_auth(loja))

    assert recusa.status_code == 422
    assert "Falta receber" in recusa.json()["detail"]


async def test_item_removido_sai_do_total(client: AsyncClient) -> None:
    loja = await _loja(client)
    produto_id = await _produto(client, loja, preco="10.00")

    venda_id = (await client.post(f"{PDV}/vendas", headers=_auth(loja))).json()["id"]
    com_item = await client.post(
        f"{PDV}/vendas/{venda_id}/itens",
        headers=_auth(loja),
        json={"produto_id": produto_id, "quantidade": "2"},
    )
    item_id = com_item.json()["itens"][0]["id"]

    sem_item = await client.delete(f"{PDV}/vendas/{venda_id}/itens/{item_id}", headers=_auth(loja))

    assert sem_item.status_code == 200, sem_item.text
    assert sem_item.json()["itens"] == []
    assert Decimal(sem_item.json()["total"]) == Decimal("0.00")


async def test_pdv_nao_contratado_nao_existe(client: AsyncClient) -> None:
    """A loja que não contratou o PDV não enxerga a rota — ver ADR 0004."""
    sufixo = uuid.uuid4().hex[:8]
    slug = f"sem-pdv-{sufixo}"
    email = f"dono-{sufixo}@teste-decko.com.br"

    async with SessionFactory() as session, session.begin():
        tenant, _user, _granted = await _bootstrap(
            session,
            tenant_name="Loja sem PDV",
            tenant_slug=slug,
            admin_email=email,
            admin_name="Dono",
            password=PASSWORD,
            modules=["comercial"],
        )
        client.criadas.append(tenant.id)  # type: ignore[attr-defined]

    login = await client.post(
        f"{CORE}/auth/login",
        json={"tenant_slug": slug, "email": email, "password": PASSWORD},
    )
    token = {"Authorization": f"Bearer {login.json()['access_token']}"}

    assert (await client.get(f"{PDV}/vendas", headers=token)).status_code == 404


async def _venda_fechada(
    client: AsyncClient, loja: Loja, produto_id: str, *, forma: str, valor: str
) -> dict:
    """Abre, lança um item, recebe e fecha. É o caminho que a conferência soma."""
    venda = await client.post(f"{PDV}/vendas", headers=_auth(loja))
    assert venda.status_code == 201, venda.text
    venda_id = venda.json()["id"]

    item = await client.post(
        f"{PDV}/vendas/{venda_id}/itens",
        headers=_auth(loja),
        json={"produto_id": produto_id, "quantidade": "1"},
    )
    assert item.status_code == 200, item.text

    pago = await client.post(
        f"{PDV}/vendas/{venda_id}/pagamentos",
        headers=_auth(loja),
        json={"forma": forma, "valor": valor},
    )
    assert pago.status_code == 200, pago.text

    fechada = await client.post(f"{PDV}/vendas/{venda_id}/finalizar", headers=_auth(loja))
    assert fechada.status_code == 200, fechada.text
    return fechada.json()


def _periodo_de_hoje() -> dict[str, str]:
    """O dia inteiro, com fuso, como a tela manda.

    O servidor não adivinha o dia de quem está no balcão: quem chama envia os instantes.
    """
    agora = datetime.now(UTC)
    inicio = agora - timedelta(days=1)
    fim = agora + timedelta(days=1)
    return {"de": inicio.isoformat(), "ate": fim.isoformat()}


async def test_conferencia_soma_o_que_entrou_por_forma(client: AsyncClient) -> None:
    loja = await _loja(client)
    produto_id = await _produto(client, loja, preco="10.00")

    await _venda_fechada(client, loja, produto_id, forma="dinheiro", valor="10.00")
    await _venda_fechada(client, loja, produto_id, forma="pix", valor="10.00")
    await _venda_fechada(client, loja, produto_id, forma="pix", valor="10.00")

    resposta = await client.get(
        f"{PDV}/conferencia", headers=_auth(loja), params=_periodo_de_hoje()
    )
    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()

    assert corpo["vendas"] == 3
    assert Decimal(corpo["recebido"]) == Decimal("30.00")

    por_forma = {linha["forma"]: linha for linha in corpo["por_forma"]}
    # Pix vem primeiro: a lista é ordenada por valor, porque é isso que se procura.
    assert corpo["por_forma"][0]["forma"] == "pix"
    assert por_forma["pix"]["quantidade"] == 2
    assert Decimal(por_forma["pix"]["valor"]) == Decimal("20.00")
    assert Decimal(por_forma["dinheiro"]["valor"]) == Decimal("10.00")


async def test_conferencia_separa_desconto_do_bruto(client: AsyncClient) -> None:
    loja = await _loja(client)
    produto_id = await _produto(client, loja, preco="10.00")

    venda = await client.post(f"{PDV}/vendas", headers=_auth(loja))
    venda_id = venda.json()["id"]
    await client.post(
        f"{PDV}/vendas/{venda_id}/itens",
        headers=_auth(loja),
        json={"produto_id": produto_id, "quantidade": "1"},
    )
    await client.put(
        f"{PDV}/vendas/{venda_id}/desconto", headers=_auth(loja), json={"desconto": "2.50"}
    )
    await client.post(
        f"{PDV}/vendas/{venda_id}/pagamentos",
        headers=_auth(loja),
        json={"forma": "dinheiro", "valor": "7.50"},
    )
    await client.post(f"{PDV}/vendas/{venda_id}/finalizar", headers=_auth(loja))

    corpo = (
        await client.get(f"{PDV}/conferencia", headers=_auth(loja), params=_periodo_de_hoje())
    ).json()

    # O bruto é a soma dos itens; o líquido já desconta. Ver os dois separados é o que
    # mostra quanto desconto foi dado no dia.
    assert Decimal(corpo["bruto"]) == Decimal("10.00")
    assert Decimal(corpo["descontos"]) == Decimal("2.50")
    assert Decimal(corpo["liquido"]) == Decimal("7.50")


async def test_conferencia_nao_conta_venda_cancelada_no_total(client: AsyncClient) -> None:
    loja = await _loja(client)
    produto_id = await _produto(client, loja, preco="10.00")

    await _venda_fechada(client, loja, produto_id, forma="dinheiro", valor="10.00")

    cancelada = await client.post(f"{PDV}/vendas", headers=_auth(loja))
    await client.post(f"{PDV}/vendas/{cancelada.json()['id']}/cancelar", headers=_auth(loja))

    corpo = (
        await client.get(f"{PDV}/conferencia", headers=_auth(loja), params=_periodo_de_hoje())
    ).json()

    # Cancelada não entra no dinheiro, mas aparece contada: sumir com ela esconderia que
    # houve cancelamento no dia, que é justamente o que o dono quer enxergar.
    assert corpo["vendas"] == 1
    assert Decimal(corpo["liquido"]) == Decimal("10.00")
    assert corpo["canceladas"] == 1


async def test_conferencia_diz_quem_operou(client: AsyncClient) -> None:
    loja = await _loja(client)
    produto_id = await _produto(client, loja, preco="10.00")
    await _venda_fechada(client, loja, produto_id, forma="dinheiro", valor="10.00")

    corpo = (
        await client.get(f"{PDV}/conferencia", headers=_auth(loja), params=_periodo_de_hoje())
    ).json()

    assert len(corpo["por_operador"]) == 1
    linha = corpo["por_operador"][0]
    # O nome é lido na hora, não copiado para dentro da venda: renomear vale para o
    # histórico também, porque é cadastro e não fato histórico.
    assert linha["operador_nome"] == "Operador"
    assert linha["vendas"] == 1


async def test_conferencia_recusa_periodo_invertido(client: AsyncClient) -> None:
    loja = await _loja(client)
    agora = datetime.now(UTC)

    resposta = await client.get(
        f"{PDV}/conferencia",
        headers=_auth(loja),
        params={"de": agora.isoformat(), "ate": (agora - timedelta(days=1)).isoformat()},
    )

    assert resposta.status_code == 422, resposta.text


async def test_conferencia_de_outra_loja_nao_vaza(client: AsyncClient) -> None:
    uma = await _loja(client)
    outra = await _loja(client)
    produto_id = await _produto(client, uma, preco="10.00")
    await _venda_fechada(client, uma, produto_id, forma="dinheiro", valor="10.00")

    corpo = (
        await client.get(f"{PDV}/conferencia", headers=_auth(outra), params=_periodo_de_hoje())
    ).json()

    # O isolamento é do banco, não da consulta — mas uma agregação é exatamente onde um
    # vazamento passaria despercebido, porque o número sai somado.
    assert corpo["vendas"] == 0
    assert Decimal(corpo["recebido"]) == Decimal("0.00")


async def _abrir_caixa(client: AsyncClient, loja: Loja, abertura: str = "100.00") -> dict:
    resposta = await client.post(f"{PDV}/caixa", headers=_auth(loja), json={"abertura": abertura})
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


async def test_caixa_abre_uma_vez_so_por_operador(client: AsyncClient) -> None:
    loja = await _loja(client)
    await _abrir_caixa(client, loja)

    segunda = await client.post(f"{PDV}/caixa", headers=_auth(loja), json={"abertura": "50.00"})

    # Quem recusa de verdade é o índice parcial no banco; o serviço só dá a mensagem.
    # Duas abas abertas tentariam as duas ao mesmo tempo.
    assert segunda.status_code == 422, segunda.text


async def test_venda_fechada_entra_na_sessao_aberta(client: AsyncClient) -> None:
    loja = await _loja(client)
    caixa = await _abrir_caixa(client, loja, "0.00")
    produto_id = await _produto(client, loja, preco="10.00")

    await _venda_fechada(client, loja, produto_id, forma="dinheiro", valor="10.00")

    atual = (await client.get(f"{PDV}/caixa/aberto", headers=_auth(loja))).json()
    assert atual["id"] == caixa["id"]
    # Abertura zero mais dez em espécie.
    assert Decimal(atual["esperado_agora"]) == Decimal("10.00")


async def test_venda_fora_de_sessao_nao_e_absorvida_depois(client: AsyncClient) -> None:
    loja = await _loja(client)
    produto_id = await _produto(client, loja, preco="10.00")

    # Vendida antes de existir caixa: vender não exige caixa aberto.
    await _venda_fechada(client, loja, produto_id, forma="dinheiro", valor="10.00")

    await _abrir_caixa(client, loja, "0.00")
    atual = (await client.get(f"{PDV}/caixa/aberto", headers=_auth(loja))).json()

    # Abrir o caixa depois não puxa para dentro dele o que foi vendido antes: o
    # fechamento mentiria sobre o próprio período, e a diferença apareceria num caixa
    # que não a produziu.
    assert Decimal(atual["esperado_agora"]) == Decimal("0.00")


async def test_sangria_e_suprimento_mudam_o_esperado(client: AsyncClient) -> None:
    loja = await _loja(client)
    caixa = await _abrir_caixa(client, loja, "100.00")

    await client.post(
        f"{PDV}/caixa/{caixa['id']}/movimentos",
        headers=_auth(loja),
        json={"tipo": "sangria", "valor": "30.00", "motivo": "Depósito no banco"},
    )
    depois = await client.post(
        f"{PDV}/caixa/{caixa['id']}/movimentos",
        headers=_auth(loja),
        json={"tipo": "suprimento", "valor": "5.00", "motivo": "Troco do mercado"},
    )

    assert depois.status_code == 200, depois.text
    assert Decimal(depois.json()["esperado_agora"]) == Decimal("75.00")
    assert len(depois.json()["movimentos"]) == 2


async def test_sangria_exige_motivo(client: AsyncClient) -> None:
    loja = await _loja(client)
    caixa = await _abrir_caixa(client, loja)

    resposta = await client.post(
        f"{PDV}/caixa/{caixa['id']}/movimentos",
        headers=_auth(loja),
        json={"tipo": "sangria", "valor": "10.00", "motivo": "   "},
    )

    # Sangria sem motivo é a linha que ninguém consegue explicar depois.
    assert resposta.status_code == 422, resposta.text


async def test_fechar_guarda_contado_esperado_e_diferenca(client: AsyncClient) -> None:
    loja = await _loja(client)
    caixa = await _abrir_caixa(client, loja, "100.00")
    produto_id = await _produto(client, loja, preco="10.00")
    await _venda_fechada(client, loja, produto_id, forma="dinheiro", valor="10.00")

    fechado = await client.post(
        f"{PDV}/caixa/{caixa['id']}/fechar",
        headers=_auth(loja),
        json={"contado": "108.00", "observacao": "Faltaram dois reais"},
    )

    assert fechado.status_code == 200, fechado.text
    corpo = fechado.json()
    assert Decimal(corpo["esperado"]) == Decimal("110.00")
    assert Decimal(corpo["contado"]) == Decimal("108.00")
    # Negativa é falta. Guardar os três é o que permite auditar depois sem refazer a conta.
    assert Decimal(corpo["diferenca"]) == Decimal("-2.00")
    assert corpo["fechado_em"] is not None
    # Fechado, o esperado congela: o que vale é o do instante da contagem.
    assert corpo["esperado_agora"] is None


async def test_diferenca_nunca_impede_fechar(client: AsyncClient) -> None:
    loja = await _loja(client)
    caixa = await _abrir_caixa(client, loja, "100.00")

    fechado = await client.post(
        f"{PDV}/caixa/{caixa['id']}/fechar", headers=_auth(loja), json={"contado": "0.00"}
    )

    # Travar destruiria o único dado que a conferência gera, e ensinaria o operador a
    # ajustar a contagem até bater — ver ADR 0008, atualização de 10/11/2026.
    assert fechado.status_code == 200, fechado.text
    assert Decimal(fechado.json()["diferenca"]) == Decimal("-100.00")


async def test_caixa_fechado_nao_recebe_mais_nada(client: AsyncClient) -> None:
    loja = await _loja(client)
    caixa = await _abrir_caixa(client, loja)
    await client.post(
        f"{PDV}/caixa/{caixa['id']}/fechar", headers=_auth(loja), json={"contado": "100.00"}
    )

    movimento = await client.post(
        f"{PDV}/caixa/{caixa['id']}/movimentos",
        headers=_auth(loja),
        json={"tipo": "sangria", "valor": "10.00", "motivo": "tarde demais"},
    )
    refechar = await client.post(
        f"{PDV}/caixa/{caixa['id']}/fechar", headers=_auth(loja), json={"contado": "90.00"}
    )

    assert movimento.status_code == 422, movimento.text
    assert refechar.status_code == 422, refechar.text


async def test_caixa_de_outra_loja_nao_aparece(client: AsyncClient) -> None:
    uma = await _loja(client)
    outra = await _loja(client)
    await _abrir_caixa(client, uma)

    aberto = await client.get(f"{PDV}/caixa/aberto", headers=_auth(outra))

    assert aberto.status_code == 200, aberto.text
    assert aberto.json() is None


async def test_cartao_nao_entra_na_conta_da_gaveta(client: AsyncClient) -> None:
    loja = await _loja(client)
    await _abrir_caixa(client, loja, "0.00")
    produto_id = await _produto(client, loja, preco="10.00")

    await _venda_fechada(client, loja, produto_id, forma="dinheiro", valor="10.00")
    await _venda_fechada(client, loja, produto_id, forma="debito", valor="10.00")
    await _venda_fechada(client, loja, produto_id, forma="pix", valor="10.00")

    atual = (await client.get(f"{PDV}/caixa/aberto", headers=_auth(loja))).json()

    # Só espécie está na gaveta. Conferir o que não se conta é ruído.
    assert Decimal(atual["esperado_agora"]) == Decimal("10.00")
