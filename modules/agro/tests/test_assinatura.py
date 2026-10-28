"""Assinatura desenhada na tela, no Planejamento Operacional.

É o que o Nathan descreve: *"Faço o relatório e pego assinatura do produtor"*, no celular,
em campo. Um rabisco solto não prova nada — o que torna a assinatura eletrônica simples
defensável é saber **o que** foi assinado, por quem, quando e de onde (Lei 14.063/2020).
Daí o teste central ser o do documento alterado depois da assinatura.

Decisões e limites: ``docs/discovery/assinaturas-dois-modulos.md``.
"""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from decimal import Decimal

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from decko.db import SessionFactory
from decko.main import create_app
from decko_modules.agro.models import Client, OperationalPlan, Property
from decko_modules.core.cli import _bootstrap
from decko_modules.core.models import Tenant

BASE = "/api/v1/agro"
PASSWORD = "senha-local-de-teste-123"

# Um traço qualquer, como sai de um dedo na tela: duas linhas numa caixa de 0 a 1.
TRACO = [
    [[0.1, 0.5], [0.3, 0.2], [0.5, 0.6], [0.7, 0.3]],
    [[0.2, 0.7], [0.6, 0.7]],
]


@dataclass
class Cenario:
    client: AsyncClient
    tenant_id: uuid.UUID
    token: str
    plan_id: uuid.UUID

    @property
    def auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


@pytest_asyncio.fixture
async def cenario() -> AsyncIterator[Cenario]:
    sufixo = uuid.uuid4().hex[:8]
    slug = f"assina-{sufixo}"
    email = f"agronomo-{sufixo}@teste-decko.com.br"

    async with SessionFactory() as session, session.begin():
        tenant, _user, _granted = await _bootstrap(
            session,
            tenant_name="AgroDrone Teste",
            tenant_slug=slug,
            admin_email=email,
            admin_name="Responsavel",
            password=PASSWORD,
            modules=["agro"],
        )
        tenant_id = tenant.id

        contratante = Client(
            tenant_id=tenant_id, nome="Fazenda Santa Clara", cpf_cnpj="12345678000195"
        )
        session.add(contratante)
        await session.flush()

        propriedade = Property(
            tenant_id=tenant_id,
            client_id=contratante.id,
            nome="Talhao Norte",
            municipio="Jatai",
            uf="GO",
        )
        session.add(propriedade)
        await session.flush()

        plano = OperationalPlan(
            tenant_id=tenant_id,
            numero=1,
            client_id=contratante.id,
            property_id=propriedade.id,
            area_ha=Decimal("120.50"),
        )
        session.add(plano)
        await session.flush()
        plan_id = plano.id

    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as http:
        login = await http.post(
            "/api/v1/core/auth/login",
            json={"tenant_slug": slug, "email": email, "password": PASSWORD},
        )
        assert login.status_code == 200, login.text
        try:
            yield Cenario(
                client=http,
                tenant_id=tenant_id,
                token=login.json()["access_token"],
                plan_id=plan_id,
            )
        finally:
            async with SessionFactory() as session, session.begin():
                await session.execute(delete(Tenant).where(Tenant.id == tenant_id))


async def _assinar(cenario: Cenario, papel: str = "proprietario_preposto", **extra: object):
    return await cenario.client.post(
        f"{BASE}/plans/{cenario.plan_id}/signatures",
        headers=cenario.auth,
        json={"papel": papel, "nome": "Jose da Silva", "traco": TRACO, **extra},
    )


async def test_assina_e_guarda_o_vinculo_com_o_documento(cenario: Cenario) -> None:
    resposta = await _assinar(cenario)

    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["nome"] == "Jose da Silva"
    assert resposta.json()["assinado_em"] is not None
    # Sem o hash, o traço é um desenho solto que não diz o que foi assinado.
    assert len(resposta.json()["documento_hash"]) == 64


async def test_assinatura_em_branco_e_recusada(cenario: Cenario) -> None:
    """Confirmar sem desenhar nada registraria uma assinatura que ninguém fez."""
    recusada = await _assinar(cenario, traco=[])

    assert recusada.status_code == 422
    assert "branco" in recusada.json()["detail"]


async def test_nao_assina_o_mesmo_papel_duas_vezes(cenario: Cenario) -> None:
    """Trocar assinatura em silêncio é o que ninguém descobre a tempo."""
    assert (await _assinar(cenario)).status_code == 200

    repetida = await _assinar(cenario)

    assert repetida.status_code == 422
    assert "já assinou" in repetida.json()["detail"]


async def test_papeis_diferentes_assinam_o_mesmo_planejamento(cenario: Cenario) -> None:
    """O formulário tem quatro assinaturas, e na AgroDrone a mesma pessoa cobre duas."""
    assert (await _assinar(cenario, papel="eng_agronomo")).status_code == 200
    assert (await _assinar(cenario, papel="piloto_agricola")).status_code == 200


async def test_documento_intacto_nao_acusa_divergencia(cenario: Cenario) -> None:
    await _assinar(cenario)

    conferencia = await cenario.client.get(
        f"{BASE}/plans/{cenario.plan_id}/signatures/check", headers=cenario.auth
    )

    assert conferencia.json()["divergentes"] == []


async def test_editar_o_planejamento_depois_de_assinado_e_acusado(cenario: Cenario) -> None:
    """O teste central: o hash existe para responder se é o mesmo documento.

    Se alguém mudar a área depois da assinatura, quem conferir precisa saber disso antes
    do fiscal.
    """
    await _assinar(cenario)

    async with SessionFactory() as session, session.begin():
        from decko.db import bind_tenant

        await bind_tenant(session, cenario.tenant_id)
        plano = await session.get(OperationalPlan, cenario.plan_id)
        assert plano is not None
        plano.area_ha = Decimal("999.00")

    conferencia = await cenario.client.get(
        f"{BASE}/plans/{cenario.plan_id}/signatures/check", headers=cenario.auth
    )

    assert conferencia.json()["divergentes"] == ["proprietario_preposto"]


async def test_a_assinatura_sai_no_pdf(cenario: Cenario) -> None:
    """O traço entra no documento como vetor, então ele cresce."""
    antes = await cenario.client.get(f"{BASE}/plans/{cenario.plan_id}/pdf", headers=cenario.auth)
    await _assinar(cenario)
    depois = await cenario.client.get(f"{BASE}/plans/{cenario.plan_id}/pdf", headers=cenario.auth)

    assert depois.status_code == 200
    assert len(depois.content) > len(antes.content)


async def test_assinar_exige_autenticacao(cenario: Cenario) -> None:
    sem_token = await cenario.client.post(
        f"{BASE}/plans/{cenario.plan_id}/signatures",
        json={"papel": "eng_agronomo", "nome": "Jose", "traco": TRACO},
    )

    assert sem_token.status_code == 401
