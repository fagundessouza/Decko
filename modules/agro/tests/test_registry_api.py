"""Cadastros de produto e receituário, e a tabela de produtos do planejamento.

O que está sob teste é o caminho completo pela API: antes disto as três tabelas existiam
com permissão declarada no manifesto, mas só podiam ser preenchidas escrevendo direto no
banco — o que deixava a tabela de produtos do documento legal sempre vazia na prática.

Todo o cenário é montado por HTTP, de propósito. Montá-lo pela sessão do banco provaria
que o modelo aceita os dados, não que o operador em campo consegue cadastrá-los.
"""

import uuid
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
