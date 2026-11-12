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

    # `POST .../retirar` e não `DELETE`: a credencial do supervisor viaja no corpo, e
    # corpo em `DELETE` é mal suportado — ver ADR 0020.
    sem_item = await client.post(
        f"{PDV}/vendas/{venda_id}/itens/{item_id}/retirar", headers=_auth(loja)
    )

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
    # O esperado não sai com o caixa aberto: é a conferência cega valendo na rede também.
    assert "esperado_agora" not in atual

    # Ele aparece no fechamento, depois da contagem: abertura zero mais dez em espécie.
    fechado = (
        await client.post(
            f"{PDV}/caixa/{caixa['id']}/fechar", headers=_auth(loja), json={"contado": "10.00"}
        )
    ).json()
    assert Decimal(fechado["esperado"]) == Decimal("10.00")


async def test_venda_fora_de_sessao_nao_e_absorvida_depois(client: AsyncClient) -> None:
    loja = await _loja(client)
    produto_id = await _produto(client, loja, preco="10.00")

    # Vendida antes de existir caixa: vender não exige caixa aberto.
    await _venda_fechada(client, loja, produto_id, forma="dinheiro", valor="10.00")

    caixa = await _abrir_caixa(client, loja, "0.00")
    fechado = (
        await client.post(
            f"{PDV}/caixa/{caixa['id']}/fechar", headers=_auth(loja), json={"contado": "0.00"}
        )
    ).json()

    # Abrir o caixa depois não puxa para dentro dele o que foi vendido antes: o
    # fechamento mentiria sobre o próprio período, e a diferença apareceria num caixa
    # que não a produziu.
    assert Decimal(fechado["esperado"]) == Decimal("0.00")


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
    assert len(depois.json()["movimentos"]) == 2

    # 100 de abertura, menos 30 de sangria, mais 5 de suprimento.
    fechado = (
        await client.post(
            f"{PDV}/caixa/{caixa['id']}/fechar", headers=_auth(loja), json={"contado": "75.00"}
        )
    ).json()
    assert Decimal(fechado["esperado"]) == Decimal("75.00")
    assert Decimal(fechado["diferenca"]) == Decimal("0.00")


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
    fechado = (
        await client.post(
            f"{PDV}/caixa/{atual['id']}/fechar", headers=_auth(loja), json={"contado": "10.00"}
        )
    ).json()

    # Só espécie está na gaveta. Conferir o que não se conta é ruído.
    assert Decimal(fechado["esperado"]) == Decimal("10.00")


# ------------------------------------------------------------------- devolução de venda


async def _devolver(
    client: AsyncClient,
    loja: Loja,
    venda: dict,
    *,
    quantidade: str = "1",
    destino: str = "estoque",
    forma: str = "dinheiro",
    motivo: str = "Cliente trouxe de volta",
):
    return await client.post(
        f"{PDV}/vendas/{venda['id']}/devolucoes",
        headers=_auth(loja),
        json={
            "itens": [
                {
                    "venda_item_id": venda["itens"][0]["id"],
                    "quantidade": quantidade,
                    "destino": destino,
                }
            ],
            "forma": forma,
            "motivo": motivo,
        },
    )


async def test_devolucao_em_especie_sai_da_gaveta(client: AsyncClient) -> None:
    """O dinheiro devolvido sai do mesmo lugar em que a venda o pôs."""
    loja = await _loja(client)
    caixa = await _abrir_caixa(client, loja, "0.00")
    produto_id = await _produto(client, loja, preco="10.00")

    venda = await _venda_fechada(client, loja, produto_id, forma="dinheiro", valor="10.00")
    devolvida = await _devolver(client, loja, venda)

    assert devolvida.status_code == 201, devolvida.text
    assert Decimal(devolvida.json()["total"]) == Decimal("10.00")
    # A devolução cai na sessão de quem a registrou.
    assert devolvida.json()["caixa_id"] == caixa["id"]

    fechado = (
        await client.post(
            f"{PDV}/caixa/{caixa['id']}/fechar", headers=_auth(loja), json={"contado": "0.00"}
        )
    ).json()
    # Entrou dez e saiu dez: a gaveta volta a zero, e bate.
    assert Decimal(fechado["esperado"]) == Decimal("0.00")
    assert Decimal(fechado["diferenca"]) == Decimal("0.00")


async def test_devolucao_no_cartao_nao_mexe_na_gaveta(client: AsyncClient) -> None:
    """Estorno no cartão é da adquirente: não há dinheiro saindo daqui."""
    loja = await _loja(client)
    caixa = await _abrir_caixa(client, loja, "0.00")
    produto_id = await _produto(client, loja, preco="10.00")

    venda = await _venda_fechada(client, loja, produto_id, forma="dinheiro", valor="10.00")
    devolvida = await _devolver(client, loja, venda, forma="credito")
    assert devolvida.status_code == 201, devolvida.text

    fechado = (
        await client.post(
            f"{PDV}/caixa/{caixa['id']}/fechar", headers=_auth(loja), json={"contado": "10.00"}
        )
    ).json()
    # Os dez da venda continuam na gaveta, porque não foi de lá que o cliente recebeu.
    assert Decimal(fechado["esperado"]) == Decimal("10.00")


async def test_devolucao_sem_caixa_aberto_fica_fora_de_sessao(client: AsyncClient) -> None:
    """Mesma regra da venda: devolver não exige caixa aberto, e não é absorvido depois."""
    loja = await _loja(client)
    produto_id = await _produto(client, loja, preco="10.00")

    venda = await _venda_fechada(client, loja, produto_id, forma="dinheiro", valor="10.00")
    devolvida = await _devolver(client, loja, venda)

    assert devolvida.status_code == 201, devolvida.text
    assert devolvida.json()["caixa_id"] is None

    caixa = await _abrir_caixa(client, loja, "0.00")
    fechado = (
        await client.post(
            f"{PDV}/caixa/{caixa['id']}/fechar", headers=_auth(loja), json={"contado": "0.00"}
        )
    ).json()
    assert Decimal(fechado["esperado"]) == Decimal("0.00")


async def test_previa_diz_o_valor_e_nao_grava_nada(client: AsyncClient) -> None:
    """O operador vê quanto sai antes de abrir a gaveta — e ver não é devolver."""
    loja = await _loja(client)
    produto_id = await _produto(client, loja, preco="10.00")
    venda = await _venda_fechada(client, loja, produto_id, forma="dinheiro", valor="10.00")

    previa = await client.post(
        f"{PDV}/vendas/{venda['id']}/devolucoes/previa",
        headers=_auth(loja),
        json={"itens": [{"venda_item_id": venda["itens"][0]["id"], "quantidade": "1"}]},
    )
    assert previa.status_code == 200, previa.text
    assert Decimal(previa.json()["total"]) == Decimal("10.00")

    depois = (
        await client.get(f"{PDV}/vendas/{venda['id']}/devolucoes", headers=_auth(loja))
    ).json()
    assert depois["devolucoes"] == []
    assert Decimal(depois["linhas"][0]["resta"]) == Decimal(1)


async def test_ver_devolucoes_mostra_o_que_ainda_da_para_devolver(client: AsyncClient) -> None:
    loja = await _loja(client)
    produto_id = await _produto(client, loja, preco="10.00")

    venda = await client.post(f"{PDV}/vendas", headers=_auth(loja))
    venda_id = venda.json()["id"]
    await client.post(
        f"{PDV}/vendas/{venda_id}/itens",
        headers=_auth(loja),
        json={"produto_id": produto_id, "quantidade": "3"},
    )
    await client.post(
        f"{PDV}/vendas/{venda_id}/pagamentos",
        headers=_auth(loja),
        json={"forma": "dinheiro", "valor": "30.00"},
    )
    fechada = (await client.post(f"{PDV}/vendas/{venda_id}/finalizar", headers=_auth(loja))).json()

    await _devolver(client, loja, fechada, quantidade="1")

    corpo = (await client.get(f"{PDV}/vendas/{venda_id}/devolucoes", headers=_auth(loja))).json()
    assert Decimal(corpo["devolvido"]) == Decimal("10.00")
    assert Decimal(corpo["linhas"][0]["devolvida"]) == Decimal(1)
    assert Decimal(corpo["linhas"][0]["resta"]) == Decimal(2)
    assert Decimal(corpo["linhas"][0]["valor_resta"]) == Decimal("20.00")


async def test_conferencia_mostra_o_que_voltou_e_as_avarias(client: AsyncClient) -> None:
    """Sem isto a gaveta não fecha numa loja que devolve: o dinheiro saiu e ninguém viu."""
    loja = await _loja(client)
    produto_id = await _produto(client, loja, preco="10.00")

    venda = await _venda_fechada(client, loja, produto_id, forma="dinheiro", valor="10.00")
    await _devolver(client, loja, venda, destino="avaria", motivo="Veio trincada")

    corpo = (
        await client.get(f"{PDV}/conferencia", headers=_auth(loja), params=_periodo_de_hoje())
    ).json()

    assert corpo["devolucoes"] == 1
    assert Decimal(corpo["devolvido"]) == Decimal("10.00")
    assert Decimal(corpo["devolvido_em_especie"]) == Decimal("10.00")
    # A avaria aparece aqui, e não no saldo do produto: é a pilha que espera o fornecedor.
    assert corpo["avarias"] == [
        {
            "produto_id": produto_id,
            "descricao": "Pão francês",
            "unidade_id": await _unidade_base(client, loja),
            "unidade_simbolo": "UN",
            "quantidade": "1.000000",
        }
    ]


async def test_venda_achada_pelo_numero_do_cupom(client: AsyncClient) -> None:
    """É assim que a tela de devolução acha a venda: o cliente traz o cupom, não o id."""
    loja = await _loja(client)
    produto_id = await _produto(client, loja, preco="10.00")

    primeira = await _venda_fechada(client, loja, produto_id, forma="pix", valor="10.00")
    await _venda_fechada(client, loja, produto_id, forma="pix", valor="10.00")

    achadas = (
        await client.get(
            f"{PDV}/vendas", headers=_auth(loja), params={"numero": primeira["numero"]}
        )
    ).json()
    assert [v["id"] for v in achadas] == [primeira["id"]]


async def test_devolucao_sem_motivo_e_recusada(client: AsyncClient) -> None:
    loja = await _loja(client)
    produto_id = await _produto(client, loja, preco="10.00")
    venda = await _venda_fechada(client, loja, produto_id, forma="dinheiro", valor="10.00")

    recusada = await _devolver(client, loja, venda, motivo="")
    # Recusa do próprio esquema: motivo vazio não chega ao serviço.
    assert recusada.status_code == 422, recusada.text
