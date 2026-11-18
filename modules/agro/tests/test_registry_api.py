"""Cadastros de produto e receituário, e a tabela de produtos do planejamento.

O que está sob teste é o caminho completo pela API: antes disto as três tabelas existiam
com permissão declarada no manifesto, mas só podiam ser preenchidas escrevendo direto no
banco — o que deixava a tabela de produtos do documento legal sempre vazia na prática.

Todo o cenário é montado por HTTP, de propósito. Montá-lo pela sessão do banco provaria
que o modelo aceita os dados, não que o operador em campo consegue cadastrá-los.
"""

import uuid
import zipfile
from base64 import b64encode
from collections.abc import AsyncIterator
from dataclasses import dataclass
from io import BytesIO

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pypdf import PdfReader
from sqlalchemy import delete

from decko.db import SessionFactory
from decko.main import create_app
from decko_modules.core.cli import _bootstrap
from decko_modules.core.models import Tenant

BASE = "/api/v1/agro"
PASSWORD = "senha-local-de-teste-123"


@dataclass
class Tenancy:
    tenant_id: uuid.UUID
    token: str

    @property
    def auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


@dataclass
class Scenario:
    client: AsyncClient
    first: Tenancy
    second: Tenancy
    plan_id: uuid.UUID


async def _sign_up(http: AsyncClient, nome: str) -> Tenancy:
    suffix = uuid.uuid4().hex[:8]
    slug = f"teste-{suffix}"
    email = f"admin-{suffix}@teste-decko.com.br"

    async with SessionFactory() as session, session.begin():
        tenant, _user, _granted = await _bootstrap(
            session,
            tenant_name=nome,
            tenant_slug=slug,
            admin_email=email,
            admin_name="Responsavel",
            password=PASSWORD,
            # A empresa nasce so com o nucleo; o modulo de segmento e contratado.
            modules=["agro"],
        )
        tenant_id = tenant.id

    login = await http.post(
        "/api/v1/core/auth/login",
        json={"tenant_slug": slug, "email": email, "password": PASSWORD},
    )
    assert login.status_code == 200, login.text
    return Tenancy(tenant_id=tenant_id, token=login.json()["access_token"])


@pytest_asyncio.fixture
async def scenario() -> AsyncIterator[Scenario]:
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        first = await _sign_up(http, "Pulverizacao Teste")
        second = await _sign_up(http, "Concorrente Teste")

        contratante = await http.post(
            f"{BASE}/clients",
            headers=first.auth,
            json={"nome": "Fazenda Santa Clara", "cpf_cnpj": "12345678000195"},
        )
        assert contratante.status_code == 201, contratante.text

        propriedade = await http.post(
            f"{BASE}/properties",
            headers=first.auth,
            json={
                "client_id": contratante.json()["id"],
                "nome": "Talhao Norte",
                "municipio": "Jatai",
                "uf": "GO",
                "latitude": -17.8814,
                "longitude": -51.7214,
            },
        )
        assert propriedade.status_code == 201, propriedade.text

        plan = await http.post(
            f"{BASE}/plans",
            headers=first.auth,
            json={
                "client_id": contratante.json()["id"],
                "property_id": propriedade.json()["id"],
                "cultura": "soja",
                "area_ha": 120.5,
            },
        )
        assert plan.status_code == 201, plan.text

        try:
            yield Scenario(
                client=http, first=first, second=second, plan_id=uuid.UUID(plan.json()["id"])
            )
        finally:
            async with SessionFactory() as session, session.begin():
                await session.execute(
                    delete(Tenant).where(Tenant.id.in_([first.tenant_id, second.tenant_id]))
                )


async def _create_product(
    scenario: Scenario,
    tenancy: Tenancy | None = None,
    *,
    nome_comercial: str = "Glifosato Tecnico",
    formulacao: str = "SL",
    classe_toxicologica: str = "IV",
) -> dict[str, str]:
    response = await scenario.client.post(
        f"{BASE}/products",
        headers=(tenancy or scenario.first).auth,
        json={
            "nome_comercial": nome_comercial,
            "formulacao": formulacao,
            "classe_toxicologica": classe_toxicologica,
            "registro_mapa": "01234/2020",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _create_prescription(
    scenario: Scenario, *, numero: str = "RA-2026-0042"
) -> dict[str, str]:
    response = await scenario.client.post(
        f"{BASE}/prescriptions",
        headers=scenario.first.auth,
        json={
            "numero": numero,
            "emitido_em": "2026-10-09",
            "agronomo_nome": "Agronoma Responsavel",
            "agronomo_crea": "CREA-GO 12345",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_product_is_registered_and_listed(scenario: Scenario) -> None:
    created = await _create_product(scenario)

    listing = await scenario.client.get(f"{BASE}/products", headers=scenario.first.auth)
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()] == [created["id"]]
    assert listing.json()[0]["registro_mapa"] == "01234/2020"


async def test_repeated_commercial_name_is_refused(scenario: Scenario) -> None:
    await _create_product(scenario)

    repeated = await scenario.client.post(
        f"{BASE}/products",
        headers=scenario.first.auth,
        json={"nome_comercial": "Glifosato Tecnico"},
    )

    assert repeated.status_code == 409
    assert "nome comercial" in repeated.json()["detail"]


async def test_the_same_product_name_is_free_in_another_company(scenario: Scenario) -> None:
    """A unicidade é por empresa: duas empresas aplicam o mesmo defensivo."""
    await _create_product(scenario)

    other = await _create_product(scenario, scenario.second)

    assert other["nome_comercial"] == "Glifosato Tecnico"


async def test_prescription_is_registered_and_listed(scenario: Scenario) -> None:
    created = await _create_prescription(scenario)

    listing = await scenario.client.get(f"{BASE}/prescriptions", headers=scenario.first.auth)
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()] == [created["id"]]
    assert listing.json()[0]["agronomo_crea"] == "CREA-GO 12345"


async def test_repeated_prescription_number_is_refused(scenario: Scenario) -> None:
    await _create_prescription(scenario)

    repeated = await scenario.client.post(
        f"{BASE}/prescriptions",
        headers=scenario.first.auth,
        json={"numero": "RA-2026-0042", "emitido_em": "2026-10-10"},
    )

    assert repeated.status_code == 409


async def test_product_line_copies_the_registry_at_the_time_it_is_added(
    scenario: Scenario,
) -> None:
    """Corrigir o cadastro não pode mudar o conteúdo de um documento já emitido.

    É o motivo pelo qual a linha guarda formulação e classe toxicológica em vez de
    referenciá-las. Sem este teste, a cópia poderia virar leitura do cadastro em uma
    refatoração futura sem que nada acusasse.
    """
    product = await _create_product(scenario, formulacao="SL", classe_toxicologica="IV")

    added = await scenario.client.post(
        f"{BASE}/plans/{scenario.plan_id}/products",
        headers=scenario.first.auth,
        json={
            "product_id": product["id"],
            "dosagem_ha": 2.5,
            "volume_ha": 10,
            "total_produto": 301.25,
        },
    )
    assert added.status_code == 201, added.text
    assert added.json()["formulacao"] == "SL"
    assert added.json()["classe_toxicologica"] == "IV"

    # O cadastro é corrigido depois que a linha já entrou no planejamento.
    async with SessionFactory() as session, session.begin():
        from decko.db import bind_tenant
        from decko_modules.agro.models import Product

        await bind_tenant(session, scenario.first.tenant_id)
        registry = await session.get(Product, uuid.UUID(product["id"]))
        assert registry is not None
        registry.formulacao = "EC"
        registry.classe_toxicologica = "II"

    lines = await scenario.client.get(
        f"{BASE}/plans/{scenario.plan_id}/products", headers=scenario.first.auth
    )
    assert lines.status_code == 200
    assert lines.json()[0]["formulacao"] == "SL"
    assert lines.json()[0]["classe_toxicologica"] == "IV"


async def test_unknown_product_does_not_become_a_line(scenario: Scenario) -> None:
    response = await scenario.client.post(
        f"{BASE}/plans/{scenario.plan_id}/products",
        headers=scenario.first.auth,
        json={"product_id": str(uuid.uuid4()), "dosagem_ha": 1},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Produto não encontrado."


async def test_a_product_from_another_company_is_unreachable(scenario: Scenario) -> None:
    """Identificador vazado de outra empresa não vira linha: para esta sessão não existe."""
    foreign = await _create_product(scenario, scenario.second, nome_comercial="Defensivo Alheio")

    response = await scenario.client.post(
        f"{BASE}/plans/{scenario.plan_id}/products",
        headers=scenario.first.auth,
        json={"product_id": foreign["id"]},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Produto não encontrado."


async def test_product_line_is_removed(scenario: Scenario) -> None:
    product = await _create_product(scenario)
    added = await scenario.client.post(
        f"{BASE}/plans/{scenario.plan_id}/products",
        headers=scenario.first.auth,
        json={"product_id": product["id"]},
    )

    removed = await scenario.client.delete(
        f"{BASE}/plans/{scenario.plan_id}/products/{added.json()['id']}",
        headers=scenario.first.auth,
    )
    assert removed.status_code == 204

    lines = await scenario.client.get(
        f"{BASE}/plans/{scenario.plan_id}/products", headers=scenario.first.auth
    )
    assert lines.json() == []


async def test_removing_a_line_through_the_wrong_plan_is_refused(scenario: Scenario) -> None:
    """Erro de digitação no identificador do planejamento não pode apagar a linha certa."""
    product = await _create_product(scenario)
    added = await scenario.client.post(
        f"{BASE}/plans/{scenario.plan_id}/products",
        headers=scenario.first.auth,
        json={"product_id": product["id"]},
    )

    response = await scenario.client.delete(
        f"{BASE}/plans/{uuid.uuid4()}/products/{added.json()['id']}",
        headers=scenario.first.auth,
    )

    assert response.status_code == 404


async def test_prescription_is_linked_after_the_plan_exists(scenario: Scenario) -> None:
    """O planejamento nasce em campo, antes de o receituário estar digitalizado."""
    prescription = await _create_prescription(scenario)

    linked = await scenario.client.put(
        f"{BASE}/plans/{scenario.plan_id}/prescription",
        headers=scenario.first.auth,
        json={"prescription_id": prescription["id"]},
    )

    assert linked.status_code == 200, linked.text
    assert linked.json()["prescription_id"] == prescription["id"]


async def test_unknown_prescription_is_not_linked(scenario: Scenario) -> None:
    response = await scenario.client.put(
        f"{BASE}/plans/{scenario.plan_id}/prescription",
        headers=scenario.first.auth,
        json={"prescription_id": str(uuid.uuid4())},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Receituário não encontrado."


async def test_what_was_registered_reaches_the_printed_document(scenario: Scenario) -> None:
    """O fecho: cadastrar produto e receituário pela API preenche o talão impresso.

    É a razão de existir deste trecho. Sem ele a tabela de produtos do documento legal
    saía em branco, porque não havia como preenchê-la de fora do banco.
    """
    product = await _create_product(scenario, nome_comercial="Glifosato Tecnico")
    prescription = await _create_prescription(scenario, numero="RA-2026-0042")

    await scenario.client.post(
        f"{BASE}/plans/{scenario.plan_id}/products",
        headers=scenario.first.auth,
        json={
            "product_id": product["id"],
            "dosagem_ha": 2.5,
            "volume_ha": 10,
            "total_produto": 301.25,
        },
    )
    await scenario.client.put(
        f"{BASE}/plans/{scenario.plan_id}/prescription",
        headers=scenario.first.auth,
        json={"prescription_id": prescription["id"]},
    )

    response = await scenario.client.get(
        f"{BASE}/plans/{scenario.plan_id}/pdf", headers=scenario.first.auth
    )
    assert response.status_code == 200, response.text
    text = "\n".join(page.extract_text() for page in PdfReader(BytesIO(response.content)).pages)

    assert "Glifosato Tecnico" in text
    assert "RA-2026-0042" in text
    # Formulação e classe vêm da linha, que as copiou do cadastro.
    assert "SL" in text
    assert "IV" in text


async def test_alphanumeric_cnpj_is_accepted(scenario: Scenario) -> None:
    """Desde julho de 2026 as doze primeiras posições do CNPJ aceitam letras.

    Recusá-las rejeitaria empresa aberta de lá para cá, com CNPJ legítimo, logo na porta
    de entrada do cadastro. O número é o exemplo trabalhado da Receita Federal — a conta
    que o produz está em ``apps/api/tests/test_documents.py``.
    """
    response = await scenario.client.post(
        f"{BASE}/clients",
        headers=scenario.first.auth,
        json={"nome": "Fazenda Nova", "cpf_cnpj": "12ABC34501DE35"},
    )

    assert response.status_code == 201, response.text
    assert response.json()["cpf_cnpj"] == "12ABC34501DE35"


async def test_document_with_letters_in_the_check_digits_is_refused(
    scenario: Scenario,
) -> None:
    """Os dois dígitos verificadores continuam numéricos, mesmo no CNPJ alfanumérico."""
    response = await scenario.client.post(
        f"{BASE}/clients",
        headers=scenario.first.auth,
        json={"nome": "Fazenda Invalida", "cpf_cnpj": "12ABC34501DEFG"},
    )

    assert response.status_code == 422


async def test_document_with_the_wrong_length_is_refused(scenario: Scenario) -> None:
    """CPF tem 11 posições e CNPJ tem 14. Nada entre os dois é documento."""
    response = await scenario.client.post(
        f"{BASE}/clients",
        headers=scenario.first.auth,
        json={"nome": "Fazenda Torta", "cpf_cnpj": "123456789012"},
    )

    assert response.status_code == 422


async def test_a_wrong_check_digit_is_refused_in_words_the_operator_reads(
    scenario: Scenario,
) -> None:
    """A recusa chega como frase, não como erro interno do validador.

    O Pydantic prefixa "Value error, " na mensagem de um ValueError comum, e a interface
    mostra ao operador o primeiro ``detail`` que receber. Já aconteceu de a tela exibir
    nome interno de campo; aqui a regra fica presa.
    """
    response = await scenario.client.post(
        f"{BASE}/clients",
        headers=scenario.first.auth,
        json={"nome": "Fazenda Torta", "cpf_cnpj": "12.345.678/0001-99"},
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["msg"] == "CNPJ inválido: o dígito verificador não confere."


async def test_the_mask_is_stripped_before_storing(scenario: Scenario) -> None:
    """O documento é copiado do papel com ponto e barra; o banco guarda só o conteúdo."""
    response = await scenario.client.post(
        f"{BASE}/clients",
        headers=scenario.first.auth,
        json={"nome": "Petroleo Brasileiro", "cpf_cnpj": "33.000.167/0001-01"},
    )

    assert response.status_code == 201, response.text
    assert response.json()["cpf_cnpj"] == "33000167000101"


async def test_the_same_document_masked_is_the_same_contratante(scenario: Scenario) -> None:
    """Normalizar antes de gravar é o que faz a unicidade por documento valer de fato.

    O contratante do cenário já foi cadastrado sem máscara. Recadastrá-lo com ponto e
    barra tem de esbarrar na restrição, e não abrir um segundo cadastro do mesmo CNPJ —
    duplicata que depois apareceria como dois contratantes no relatório.
    """
    response = await scenario.client.post(
        f"{BASE}/clients",
        headers=scenario.first.auth,
        json={"nome": "Fazenda Santa Clara", "cpf_cnpj": "12.345.678/0001-95"},
    )

    assert response.status_code == 409


async def test_registering_a_product_requires_authentication(scenario: Scenario) -> None:
    response = await scenario.client.post(
        f"{BASE}/products", json={"nome_comercial": "Sem Credencial"}
    )

    assert response.status_code == 401


async def test_cadastra_piloto(scenario: Scenario) -> None:
    """Pedido do Nathan: a empresa cadastra seus pilotos, e o planejamento aponta quem voou.

    Antes o nome do piloto só existia como texto dentro da assinatura, redigitado a cada
    documento — ver docs/discovery/agro-planejamento-operacional.md, seção 6.2.
    """
    criado = await scenario.client.post(
        f"{BASE}/pilots",
        headers=scenario.first.auth,
        json={"nome": "Nathan Gomes", "canac": "123456", "crea": "GO-12345"},
    )

    assert criado.status_code == 201, criado.text
    # O CREA existe porque na AgroDrone a mesma pessoa é o agrônomo e o piloto.
    assert criado.json()["crea"] == "GO-12345"

    listados = await scenario.client.get(f"{BASE}/pilots", headers=scenario.first.auth)
    assert [p["nome"] for p in listados.json()] == ["Nathan Gomes"]


async def test_mesmo_canac_duas_vezes_e_recusado(scenario: Scenario) -> None:
    corpo = {"nome": "Nathan Gomes", "canac": "123456"}

    primeiro = await scenario.client.post(f"{BASE}/pilots", headers=scenario.first.auth, json=corpo)
    assert primeiro.status_code == 201, primeiro.text

    repetido = await scenario.client.post(f"{BASE}/pilots", headers=scenario.first.auth, json=corpo)
    assert repetido.status_code == 409


async def test_piloto_sem_canac_e_aceito(scenario: Scenario) -> None:
    """Empresa de um piloto só pode não ter o código à mão na hora do cadastro."""
    criado = await scenario.client.post(
        f"{BASE}/pilots", headers=scenario.first.auth, json={"nome": "Piloto sem registro"}
    )

    assert criado.status_code == 201, criado.text
    assert criado.json()["canac"] is None


async def test_piloto_de_uma_empresa_nao_aparece_na_outra(scenario: Scenario) -> None:
    await scenario.client.post(
        f"{BASE}/pilots",
        headers=scenario.first.auth,
        json={"nome": "Nathan Gomes", "canac": "123456"},
    )

    vizinha = await scenario.client.get(f"{BASE}/pilots", headers=scenario.second.auth)

    assert vizinha.json() == []


async def test_planejamento_guarda_quem_voou(scenario: Scenario) -> None:
    """O documento passa a apontar para o piloto cadastrado, em vez de só ao nome digitado."""
    piloto = await scenario.client.post(
        f"{BASE}/pilots",
        headers=scenario.first.auth,
        json={"nome": "Nathan Gomes", "canac": "123456"},
    )
    piloto_id = piloto.json()["id"]

    # O planejamento do cenário já existe; este é outro, criado com o piloto desde o começo.
    plano = await scenario.client.post(
        f"{BASE}/plans",
        headers=scenario.first.auth,
        json={
            "client_id": (
                await scenario.client.get(f"{BASE}/clients", headers=scenario.first.auth)
            ).json()[0]["id"],
            "property_id": (
                await scenario.client.get(f"{BASE}/properties", headers=scenario.first.auth)
            ).json()[0]["id"],
            "pilot_id": piloto_id,
            "cultura": "soja",
        },
    )

    assert plano.status_code == 201, plano.text
    assert plano.json()["pilot_id"] == piloto_id


# ------------------------------------------- o planejamento preenchido na lavoura, sem rede


async def _dados_do_plano(scenario: Scenario) -> dict[str, object]:
    """O corpo que o aparelho manda: os vínculos que ele já tinha guardados."""
    plano = await scenario.client.get(f"{BASE}/plans", headers=scenario.first.auth)
    primeiro = plano.json()[0]
    return {
        "client_id": primeiro["client_id"],
        "property_id": primeiro["property_id"],
        "cultura": "milho",
        "area_ha": 42.5,
        "param_velocidade_vento_max_kmh": 10,
    }


async def test_a_identidade_do_planejamento_pode_vir_do_aparelho(scenario: Scenario) -> None:
    """Fatia 6 da ADR 0022: o planejamento é preenchido na lavoura, onde não há sinal."""
    escolhida = str(uuid.uuid4())

    criado = await scenario.client.post(
        f"{BASE}/plans",
        headers=scenario.first.auth,
        json={**await _dados_do_plano(scenario), "id": escolhida},
    )

    assert criado.status_code == 201, criado.text
    assert criado.json()["id"] == escolhida
    # O número continua nascendo aqui: dois aparelhos sem rede não combinam um contador, e
    # é o número que o produtor recebe no documento.
    assert criado.json()["numero"] >= 1


async def test_reenviar_o_mesmo_planejamento_nao_gasta_outro_numero(
    scenario: Scenario,
) -> None:
    """O caso normal de quem opera sem sinal: a resposta se perde e o aparelho repete.

    Sem isto, o mesmo voo viraria dois planejamentos, cada um com o seu número — e o
    produtor receberia dois documentos do mesmo serviço.
    """
    escolhida = str(uuid.uuid4())
    corpo = {**await _dados_do_plano(scenario), "id": escolhida}

    primeiro = await scenario.client.post(f"{BASE}/plans", headers=scenario.first.auth, json=corpo)
    assert primeiro.status_code == 201, primeiro.text

    segundo = await scenario.client.post(f"{BASE}/plans", headers=scenario.first.auth, json=corpo)

    # 200, e não 201: quem esvazia a fila precisa saber o que de fato entrou.
    assert segundo.status_code == 200, segundo.text
    assert segundo.json()["numero"] == primeiro.json()["numero"]

    listados = await scenario.client.get(f"{BASE}/plans", headers=scenario.first.auth)
    iguais = [p for p in listados.json() if p["id"] == escolhida]
    assert len(iguais) == 1, "o reenvio criou um segundo planejamento"


async def test_quem_esta_online_continua_sem_mandar_identidade(scenario: Scenario) -> None:
    """Sem `id`, o servidor gera — é o caminho de hoje, e ele não mudou."""
    criado = await scenario.client.post(
        f"{BASE}/plans", headers=scenario.first.auth, json=await _dados_do_plano(scenario)
    )

    assert criado.status_code == 201, criado.text
    assert uuid.UUID(criado.json()["id"])


async def test_o_reenvio_nao_atravessa_a_fronteira_da_empresa(scenario: Scenario) -> None:
    """A identidade de outra empresa não pode virar "já existe" aqui.

    A chave primária é única no banco inteiro, e o isolamento não deixa enxergar a linha da
    vizinha. Se o reconhecimento do reenvio olhasse além do tenant, o aparelho de uma
    empresa receberia de volta o planejamento de outra.
    """
    da_vizinha = str(uuid.uuid4())
    na_vizinha = await scenario.client.post(
        f"{BASE}/clients",
        headers=scenario.second.auth,
        json={"nome": "Fazenda da Vizinha", "cpf_cnpj": "98765432000198"},
    )
    propriedade = await scenario.client.post(
        f"{BASE}/properties",
        headers=scenario.second.auth,
        json={
            "client_id": na_vizinha.json()["id"],
            "nome": "Talhao Sul",
            "municipio": "Rio Verde",
            "uf": "GO",
        },
    )
    dela = await scenario.client.post(
        f"{BASE}/plans",
        headers=scenario.second.auth,
        json={
            "id": da_vizinha,
            "client_id": na_vizinha.json()["id"],
            "property_id": propriedade.json()["id"],
        },
    )
    assert dela.status_code == 201, dela.text

    recusado = await scenario.client.post(
        f"{BASE}/plans",
        headers=scenario.first.auth,
        json={**await _dados_do_plano(scenario), "id": da_vizinha},
    )

    # Recusa, e não "já existe": nada da empresa vizinha volta para este aparelho.
    assert recusado.status_code == 409, recusado.text
    assert "Vizinha" not in recusado.text


# ------------------------------------------- o registro de voo do drone, pela API

CABECALHO_DE_VOO = [
    "Flight time",
    "Sprayed area",
    "Total Amount(L/Kg)",
    "Usage Per Mu(L/Kg/Mu)",
    "Flight duration(min:sec)",
    "Aircraft name",
    "Pliot Name",
    "Field Name",
    "Body Code",
    "Plot ID",
]

SERIE = "B26WN5P0025A3T"


def _linha_de_voo(
    *,
    quando: str,
    area: str,
    volume: str,
    duracao: str,
    talhao: str = "",
    plot: str = "",
    serie: str = SERIE,
) -> list[str]:
    return [quando, area, volume, "", duracao, "Valkyria", "Piloto de Teste", talhao, serie, plot]


def _planilha_de_voo(linhas: list[list[str]]) -> str:
    """Um .xlsx mínimo, em base64, com texto embutido. Só o que o leitor precisa ver."""
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"

    def coluna(indice: int) -> str:
        nome = ""
        indice += 1
        while indice:
            indice, resto = divmod(indice - 1, 26)
            nome = chr(65 + resto) + nome
        return nome

    corpo = []
    for numero, linha in enumerate(linhas, start=1):
        celulas = "".join(
            f'<c r="{coluna(i)}{numero}" t="inlineStr"><is><t>{valor}</t></is></c>'
            for i, valor in enumerate(linha)
            if valor
        )
        corpo.append(f'<row r="{numero}">{celulas}</row>')

    pacote = BytesIO()
    with zipfile.ZipFile(pacote, "w") as zf:
        zf.writestr(
            "xl/workbook.xml",
            f'<workbook xmlns="{ns}"><sheets><sheet name="voos" sheetId="1"/></sheets></workbook>',
        )
        zf.writestr(
            "xl/worksheets/sheet1.xml",
            f'<worksheet xmlns="{ns}"><sheetData>{"".join(corpo)}</sheetData></worksheet>',
        )
    return b64encode(pacote.getvalue()).decode()


#: Uma aplicação de dois voos, mais um translado que não pulverizou nada.
UM_DIA_DE_VOO = [
    CABECALHO_DE_VOO,
    _linha_de_voo(
        quando="2026-08-15 18:51:36-18:58:23",
        area="150",
        volume="60",
        duracao="06:47",
        talhao="Milho 1",
        plot="plot-a",
    ),
    _linha_de_voo(
        quando="2026-08-15 19:03:16-19:10:57",
        area="333",
        volume="130",
        duracao="07:41",
        talhao="Milho 1",
        plot="plot-a",
    ),
    _linha_de_voo(quando="2026-08-15 19:25:14-19:33:35", area="0.0", volume="0.0", duracao="08:21"),
]


async def _preview(
    scenario: Scenario, linhas: list[list[str]], **extra: object
) -> dict[str, object]:
    resposta = await scenario.client.post(
        f"{BASE}/flight-log/preview",
        headers=scenario.first.auth,
        json={"arquivo": _planilha_de_voo(linhas), **extra},
    )
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


async def test_o_registro_de_voo_e_lido_e_nada_e_gravado(scenario: Scenario) -> None:
    """O pedido do Nathan: não redigitar início, fim e área aplicada.

    A rota lê e propõe; gravar é outro passo, com confirmação. Em documento que vai ao
    MAPA, gravar sozinho o que um arquivo de terceiro disse é o caminho mais curto para um
    relatório divergente.
    """
    antes = await scenario.client.get(f"{BASE}/plans", headers=scenario.first.auth)

    corpo = await _preview(scenario, UM_DIA_DE_VOO)

    assert corpo["unidade_de_area"] == "mu"
    assert len(corpo["aplicacoes"]) == 1
    aplicacao = corpo["aplicacoes"][0]
    # 483 mu são 32,2 ha. Lidos como hectare, o relatório diria quinze vezes a área.
    assert aplicacao["area_ha"] == "32.2000"
    assert aplicacao["voos"] == 2
    assert aplicacao["duracao_segundos"] == 868
    assert aplicacao["equipamento_serie"] == SERIE

    # Nada entrou: a lista de planejamentos é a mesma de antes.
    depois = await scenario.client.get(f"{BASE}/plans", headers=scenario.first.auth)
    assert len(depois.json()) == len(antes.json())


async def test_o_voo_que_nao_pulverizou_vai_para_o_horimetro(scenario: Scenario) -> None:
    """Translado e calibração não entram no relatório do MAPA e não são descartados.

    Eles desgastam motor, hélice e bateria igual, e é por isso que a revisão vence. O
    relatório leva só a aplicação; a manutenção leva tudo.
    """
    corpo = await _preview(scenario, UM_DIA_DE_VOO)

    assert len(corpo["voos_auxiliares"]) == 1
    assert corpo["voos_auxiliares"][0]["duracao_segundos"] == 501

    horimetro = corpo["horimetro"][0]
    assert horimetro["voos"] == 3
    assert horimetro["duracao_aplicando_segundos"] == 868
    assert horimetro["duracao_auxiliar_segundos"] == 501
    assert horimetro["duracao_total_segundos"] == 1369


async def test_a_aeronave_e_encontrada_pelo_numero_de_serie(scenario: Scenario) -> None:
    """O arquivo traz apelido e série; quem identifica a ARP para o MAPA é o prefixo.

    Sem este casamento, o relatório mensal ficaria sem o campo de identificação da
    aeronave (Portaria 298/2021, art. 11, II) — e alguém o preencheria à mão.
    """
    cadastrada = await scenario.client.post(
        f"{BASE}/aircraft",
        headers=scenario.first.auth,
        json={
            "prefixo": "PP-ABC",
            "modelo": "T50",
            "fabricante": "DJI",
            "numero_serie": SERIE,
        },
    )
    assert cadastrada.status_code == 201, cadastrada.text

    corpo = await _preview(scenario, UM_DIA_DE_VOO)

    assert corpo["aplicacoes"][0]["prefixo"] == "PP-ABC"
    assert corpo["aplicacoes"][0]["aircraft_id"] == cadastrada.json()["id"]
    assert corpo["horimetro"][0]["prefixo"] == "PP-ABC"
    assert corpo["series_sem_aeronave"] == []


async def test_serie_sem_aeronave_volta_para_o_cadastro_rapido(scenario: Scenario) -> None:
    """Equipamento novo aparece no arquivo antes de alguém cadastrá-lo. É o caso comum."""
    corpo = await _preview(scenario, UM_DIA_DE_VOO)

    assert corpo["series_sem_aeronave"] == [SERIE]
    assert corpo["aplicacoes"][0]["aircraft_id"] is None
    assert corpo["aplicacoes"][0]["prefixo"] is None


async def test_a_aeronave_de_outra_empresa_nao_casa(scenario: Scenario) -> None:
    """O mesmo equipamento pode estar cadastrado na empresa vizinha, e isso não vaza.

    O isolamento é do PostgreSQL, e esta consulta corre sob ele como todas as outras.
    """
    cadastrada = await scenario.client.post(
        f"{BASE}/aircraft",
        headers=scenario.second.auth,
        json={"prefixo": "PP-XYZ", "numero_serie": SERIE},
    )
    assert cadastrada.status_code == 201, cadastrada.text

    corpo = await _preview(scenario, UM_DIA_DE_VOO)

    assert corpo["series_sem_aeronave"] == [SERIE]
    assert corpo["aplicacoes"][0]["prefixo"] is None


async def test_o_horario_vem_dos_dois_jeitos_para_a_tela_escolher(scenario: Scenario) -> None:
    """O arquivo não declara fuso, e a dedução é que ele está em UTC.

    Converter calado erraria o horário declarado **e** a leitura de clima que confronta
    aquele horário. Então os dois vêm, e quem confirma decide — é a seção 7.5 do
    discovery.
    """
    corpo = await _preview(scenario, UM_DIA_DE_VOO)

    aplicacao = corpo["aplicacoes"][0]
    assert aplicacao["comecou_em"] == "2026-08-15T18:51:36"
    assert aplicacao["comecou_em_ajustado"] == "2026-08-15T15:51:36"
    assert corpo["fuso_minutos"] == -180


async def test_o_deslocamento_do_fuso_e_escolha_de_quem_confirma(scenario: Scenario) -> None:
    corpo = await _preview(scenario, UM_DIA_DE_VOO, fuso_minutos=0)

    aplicacao = corpo["aplicacoes"][0]
    assert aplicacao["comecou_em_ajustado"] == aplicacao["comecou_em"]
    assert (
        corpo["voos_auxiliares"][0]["comecou_em_ajustado"]
        == (corpo["voos_auxiliares"][0]["comecou_em"])
    )


async def test_arquivo_que_nao_e_registro_de_voo_e_recusado_com_motivo(
    scenario: Scenario,
) -> None:
    resposta = await scenario.client.post(
        f"{BASE}/flight-log/preview",
        headers=scenario.first.auth,
        json={"arquivo": b64encode(b"isto nao e um zip").decode()},
    )

    assert resposta.status_code == 422, resposta.text
    assert "planilha nem um CSV" in resposta.json()["detail"]


async def test_arquivo_sem_a_unidade_da_area_e_recusado_pela_api(scenario: Scenario) -> None:
    """A recusa chega à tela com o motivo, em vez de uma área convertida por palpite."""
    cabecalho = [c for c in CABECALHO_DE_VOO if not c.startswith("Usage Per")]
    linha = _linha_de_voo(
        quando="2026-08-15 18:51:36-18:58:23",
        area="150",
        volume="60",
        duracao="06:47",
        talhao="Milho 1",
        plot="plot-a",
    )
    del linha[3]  # a coluna de consumo sai da linha também

    resposta = await scenario.client.post(
        f"{BASE}/flight-log/preview",
        headers=scenario.first.auth,
        json={"arquivo": _planilha_de_voo([cabecalho, linha])},
    )

    assert resposta.status_code == 422, resposta.text
    assert "unidade" in resposta.json()["detail"]


async def test_o_operador_confirma_e_o_voo_entra_pela_api(scenario: Scenario) -> None:
    """O caminho inteiro pela borda: preview, aeronave cadastrada, confirmação.

    O que a regra do serviço garante tem teste próprio em `test_flight_log_confirm.py`;
    aqui o que está sob prova é o contrato — o que a tela manda e o que ela recebe.
    """
    aeronave = await scenario.client.post(
        f"{BASE}/aircraft",
        headers=scenario.first.auth,
        json={"prefixo": "PP-CON", "numero_serie": SERIE},
    )
    assert aeronave.status_code == 201, aeronave.text

    revisado = await _preview(scenario, UM_DIA_DE_VOO)
    aplicacao = revisado["aplicacoes"][0]
    auxiliar = revisado["voos_auxiliares"][0]

    def voo(linha: dict[str, object], indice: int) -> dict[str, object]:
        """O que a tela manda por voo: o horário escolhido e o do arquivo."""
        return {
            "comecou_em": f"{linha['comecou_em_ajustado']}-03:00",
            "terminou_em": f"{linha['terminou_em_ajustado']}-03:00",
            "comecou_em_arquivo": linha["comecou_em"],
            "duracao_segundos": indice,
            "equipamento_serie": SERIE,
        }

    resposta = await scenario.client.post(
        f"{BASE}/flight-log/confirm",
        headers=scenario.first.auth,
        json={
            "aplicacoes": [
                {
                    "plot_id": aplicacao["plot_id"],
                    "talhao": aplicacao["talhao"],
                    "aircraft_id": aeronave.json()["id"],
                    "area_ha": aplicacao["area_ha"],
                    "volume_l": aplicacao["volume_l"],
                    "voos": [voo(aplicacao, aplicacao["duracao_segundos"])],
                }
            ],
            "voos_auxiliares": [
                {
                    **voo(auxiliar, auxiliar["duracao_segundos"]),
                    "aircraft_id": aeronave.json()["id"],
                }
            ],
        },
    )

    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["voos_gravados"] == 2

    horimetro = await scenario.client.get(
        f"{BASE}/aircraft/{aeronave.json()['id']}/horimetro", headers=scenario.first.auth
    )
    assert horimetro.status_code == 200, horimetro.text
    corpo = horimetro.json()
    assert corpo["voos"] == 2
    assert corpo["segundos_aplicando"] == aplicacao["duracao_segundos"]
    assert corpo["segundos_auxiliar"] == auxiliar["duracao_segundos"]


async def test_horario_sem_fuso_na_confirmacao_e_recusado(scenario: Scenario) -> None:
    """Fuso implícito é o erro que esta fatia inteira existe para não repetir.

    Aceitar o horário sem deslocamento deixaria o servidor adivinhar — e três horas de
    erro deslocam o documento e a conferência do clima.
    """
    resposta = await scenario.client.post(
        f"{BASE}/flight-log/confirm",
        headers=scenario.first.auth,
        json={
            "aplicacoes": [
                {
                    "plot_id": "plot-a",
                    "area_ha": "32.2",
                    "volume_l": "290.34",
                    "voos": [
                        {
                            "comecou_em": "2026-08-15T15:51:36",
                            "terminou_em": "2026-08-15T15:58:23",
                            "comecou_em_arquivo": "2026-08-15T18:51:36",
                            "duracao_segundos": 407,
                        }
                    ],
                }
            ]
        },
    )

    assert resposta.status_code == 422, resposta.text


async def test_horimetro_de_aeronave_que_nao_existe_e_404(scenario: Scenario) -> None:
    resposta = await scenario.client.get(
        f"{BASE}/aircraft/{uuid.uuid4()}/horimetro", headers=scenario.first.auth
    )

    assert resposta.status_code == 404, resposta.text


async def test_o_preview_devolve_cada_voo_da_bateria(scenario: Scenario) -> None:
    """Cinco baterias são cinco pousos e cinco decolagens.

    A aplicação vem somada — é assim que ela entra no relatório —, mas os voos vêm também:
    registrar uma linha só faria a contagem do horímetro mentir sobre o uso da aeronave,
    mesmo com o total de horas certo. É o que faz a revisão vencer na hora errada.
    """
    corpo = await _preview(scenario, UM_DIA_DE_VOO)

    aplicacao = corpo["aplicacoes"][0]
    assert aplicacao["voos"] == 2
    assert len(aplicacao["voos_detalhados"]) == 2

    primeiro, segundo = aplicacao["voos_detalhados"]
    # Na ordem em que aconteceram, cada um com a sua duração e os dois horários.
    assert primeiro["comecou_em"] == "2026-08-15T18:51:36"
    assert primeiro["comecou_em_ajustado"] == "2026-08-15T15:51:36"
    assert primeiro["duracao_segundos"] == 407
    assert segundo["comecou_em"] == "2026-08-15T19:03:16"
    assert segundo["duracao_segundos"] == 461
    # E a soma deles é a duração da aplicação, que é o que o relatório leva.
    assert (
        primeiro["duracao_segundos"] + segundo["duracao_segundos"]
        == aplicacao["duracao_segundos"]
    )
