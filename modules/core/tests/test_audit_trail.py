"""A trilha de auditoria nos fluxos de autenticação e de contratação.

Dois testes aqui são o motivo de o arquivo existir, e nenhum dos dois é "a linha foi
gravada":

- **A falha sobrevive.** Login recusado termina em 401, e a sessão da requisição desfaz
  tudo ao levantar. Registro de falha vai em transação própria justamente porque é nele
  que a trilha não pode ir embora junto.
- **O e-mail digitado não entra.** Quando a conta existe, `user_id` diz qual foi o alvo
  com mais precisão que um texto; quando não existe, o que foi digitado é palpite de quem
  sonda. Guardar encheria a trilha de dado pessoal de terceiro sem responder nada —
  regra 2 do `CLAUDE.md`.

Decisões e o que não dá para registrar: `decko_modules/core/audit.py`.
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

CORE = "/api/v1/core"
PASSWORD = "senha-local-de-teste-123"


@dataclass
class Conta:
    client: AsyncClient
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    slug: str
    email: str
    token: str
    refresh: str

    @property
    def auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


async def _trilha(tenant_id: uuid.UUID, action: str | None = None) -> list[AuditLog]:
    async with SessionFactory() as session, session.begin():
        await bind_tenant(session, tenant_id)
        consulta = select(AuditLog).order_by(AuditLog.created_at)
        if action is not None:
            consulta = consulta.where(AuditLog.action == action)
        resultado = await session.execute(consulta)
        return list(resultado.scalars().all())


@pytest_asyncio.fixture
async def conta() -> AsyncIterator[Conta]:
    sufixo = uuid.uuid4().hex[:8]
    slug = f"trilha-{sufixo}"
    email = f"admin-{sufixo}@teste-decko.com.br"

    async with SessionFactory() as session, session.begin():
        tenant, user, _granted = await _bootstrap(
            session,
            tenant_name="Empresa da Trilha",
            tenant_slug=slug,
            admin_email=email,
            admin_name="Administrador",
            password=PASSWORD,
            modules=[],
        )
        tenant_id, user_id = tenant.id, user.id

    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as http:
        login = await http.post(
            f"{CORE}/auth/login",
            json={"tenant_slug": slug, "email": email, "password": PASSWORD},
        )
        assert login.status_code == 200, login.text
        try:
            yield Conta(
                client=http,
                tenant_id=tenant_id,
                user_id=user_id,
                slug=slug,
                email=email,
                token=login.json()["access_token"],
                refresh=login.json()["refresh_token"],
            )
        finally:
            async with SessionFactory() as session, session.begin():
                await session.execute(delete(Tenant).where(Tenant.id == tenant_id))


async def test_entrar_deixa_rastro(conta: Conta) -> None:
    entradas = await _trilha(conta.tenant_id, "auth.login")

    assert len(entradas) == 1
    assert entradas[0].user_id == conta.user_id
    assert entradas[0].entity == "user_account"


async def test_senha_errada_fica_registrada_e_sobrevive_ao_401(conta: Conta) -> None:
    """O teste central: a requisição é desfeita, e a trilha não pode ir com ela."""
    recusado = await conta.client.post(
        f"{CORE}/auth/login",
        json={"tenant_slug": conta.slug, "email": conta.email, "password": "senha-errada-123"},
    )
    assert recusado.status_code == 401

    falhas = await _trilha(conta.tenant_id, "auth.login.failed")

    assert len(falhas) == 1
    # A conta alvo é identificada pela chave estrangeira, que é mais preciso que texto.
    assert falhas[0].user_id == conta.user_id
    assert falhas[0].data == {"motivo": "senha"}


async def test_email_desconhecido_nao_entra_na_trilha(conta: Conta) -> None:
    sondado = "quem-nao-existe@exemplo.com.br"
    recusado = await conta.client.post(
        f"{CORE}/auth/login",
        json={"tenant_slug": conta.slug, "email": sondado, "password": "qualquer-coisa-123"},
    )
    assert recusado.status_code == 401

    falhas = await _trilha(conta.tenant_id, "auth.login.failed")

    assert len(falhas) == 1
    # Não há conta, então não há a quem prender a tentativa — e o que foi digitado não vira
    # dado pessoal de terceiro guardado por nós.
    assert falhas[0].user_id is None
    assert falhas[0].data == {"motivo": "usuario_desconhecido"}
    assert sondado not in str([entrada.data for entrada in await _trilha(conta.tenant_id)])


async def test_empresa_inexistente_nao_tem_onde_registrar(conta: Conta) -> None:
    """Consequência do isolamento, não esquecimento: a linha exigiria uma empresa."""
    antes = len(await _trilha(conta.tenant_id))

    recusado = await conta.client.post(
        f"{CORE}/auth/login",
        json={
            "tenant_slug": "empresa-que-nunca-existiu",
            "email": conta.email,
            "password": PASSWORD,
        },
    )

    assert recusado.status_code == 401
    assert len(await _trilha(conta.tenant_id)) == antes


async def test_sair_deixa_rastro(conta: Conta) -> None:
    saida = await conta.client.post(f"{CORE}/auth/logout", json={"refresh_token": conta.refresh})
    assert saida.status_code == 204

    saidas = await _trilha(conta.tenant_id, "auth.logout")

    assert len(saidas) == 1
    assert saidas[0].user_id == conta.user_id


async def test_sair_duas_vezes_registra_uma(conta: Conta) -> None:
    """Token já revogado não encerrou nada, e a trilha não inventa um evento."""
    await conta.client.post(f"{CORE}/auth/logout", json={"refresh_token": conta.refresh})
    repetido = await conta.client.post(f"{CORE}/auth/logout", json={"refresh_token": conta.refresh})

    assert repetido.status_code == 204
    assert len(await _trilha(conta.tenant_id, "auth.logout")) == 1


async def test_token_reapresentado_fica_registrado(conta: Conta) -> None:
    """A rotação mata o token ao usá-lo. Reapresentar é cópia em circulação."""
    primeira = await conta.client.post(
        f"{CORE}/auth/refresh", json={"refresh_token": conta.refresh}
    )
    assert primeira.status_code == 200

    reusado = await conta.client.post(f"{CORE}/auth/refresh", json={"refresh_token": conta.refresh})

    assert reusado.status_code == 401
    reusos = await _trilha(conta.tenant_id, "auth.refresh.reused")
    assert len(reusos) == 1
    assert reusos[0].user_id == conta.user_id
    # Renovação que dá certo não entra: acontece a cada poucos minutos por sessão.
    assert await _trilha(conta.tenant_id, "auth.refresh") == []


async def test_contratar_modulo_registra_o_que_veio_junto(conta: Conta) -> None:
    instalado = await conta.client.post(f"{CORE}/modules/pdv/activate", headers=conta.auth)
    assert instalado.status_code == 200, instalado.text

    entradas = await _trilha(conta.tenant_id, "module.activate")

    assert len(entradas) == 1
    assert entradas[0].entity_id == "pdv"
    assert entradas[0].user_id == conta.user_id
    # O PDV traz a base comercial. Quem contrata escolhe um nome e recebe a árvore.
    assert entradas[0].data == {"instalados": ["comercial", "pdv"]}


async def test_desinstalar_deixa_rastro(conta: Conta) -> None:
    await conta.client.post(f"{CORE}/modules/comercial/activate", headers=conta.auth)

    await conta.client.delete(f"{CORE}/modules/comercial/activate", headers=conta.auth)

    entradas = await _trilha(conta.tenant_id, "module.deactivate")
    assert len(entradas) == 1
    assert entradas[0].entity_id == "comercial"


async def test_semear_registra_o_que_entrou(conta: Conta) -> None:
    await conta.client.post(f"{CORE}/modules/comercial/activate", headers=conta.auth)

    await conta.client.post(f"{CORE}/modules/comercial/seed", headers=conta.auth)

    entradas = await _trilha(conta.tenant_id, "module.seed")
    assert len(entradas) == 1
    # Já veio semeado na instalação, então o pedido pela vitrine não acrescentou nada — e a
    # trilha diz isso, em vez de sugerir que entrou algo.
    assert entradas[0].data == {"criados": []}


async def test_contratar_perfil_deixa_rastro(conta: Conta) -> None:
    contratado = await conta.client.post(f"{CORE}/profiles/comercio/activate", headers=conta.auth)
    assert contratado.status_code == 200, contratado.text

    entradas = await _trilha(conta.tenant_id, "profile.activate")

    assert len(entradas) == 1
    assert entradas[0].entity_id == "comercio"
    assert entradas[0].data == {"modulos": ["comercial", "pdv"]}


async def test_a_trilha_nunca_guarda_a_senha(conta: Conta) -> None:
    """Rede de segurança: senha em trilha de auditoria é vazamento permanente."""
    await conta.client.post(
        f"{CORE}/auth/login",
        json={"tenant_slug": conta.slug, "email": conta.email, "password": PASSWORD},
    )
    await conta.client.post(
        f"{CORE}/auth/login",
        json={"tenant_slug": conta.slug, "email": conta.email, "password": "outra-senha-999"},
    )
    await conta.client.post(f"{CORE}/modules/comercial/activate", headers=conta.auth)

    tudo = str([(entrada.action, entrada.data) for entrada in await _trilha(conta.tenant_id)])

    assert PASSWORD not in tudo
    assert "outra-senha-999" not in tudo
    assert conta.refresh not in tudo


# ---------------------------------------------------------------- consulta


async def _consultar(conta: Conta, **params: object) -> dict[str, object]:
    resposta = await conta.client.get(f"{CORE}/audit", headers=conta.auth, params=params)
    assert resposta.status_code == 200, resposta.text
    return dict(resposta.json())


async def test_consultar_traz_a_trilha_com_o_nome_de_quem_agiu(conta: Conta) -> None:
    pagina = await _consultar(conta)

    acoes = [entrada["action"] for entrada in pagina["entries"]]
    assert "auth.login" in acoes
    entrada = next(item for item in pagina["entries"] if item["action"] == "auth.login")
    assert entrada["author"] == "Administrador"


async def test_a_mais_recente_vem_primeiro(conta: Conta) -> None:
    """Quem abre a tela quer saber o que acabou de acontecer, não o cadastro da empresa."""
    await conta.client.post(f"{CORE}/modules/comercial/activate", headers=conta.auth)

    pagina = await _consultar(conta)

    assert pagina["entries"][0]["action"] == "module.activate"
    assert pagina["entries"][-1]["action"] == "tenant.bootstrap"


async def test_filtrar_por_grupo(conta: Conta) -> None:
    await conta.client.post(f"{CORE}/modules/comercial/activate", headers=conta.auth)

    autenticacao = await _consultar(conta, action_prefix="auth.")
    aplicativos = await _consultar(conta, action_prefix="module.")

    assert {entrada["action"] for entrada in autenticacao["entries"]} == {"auth.login"}
    assert {entrada["action"] for entrada in aplicativos["entries"]} == {"module.activate"}


async def test_curinga_no_filtro_nao_vira_varredura(conta: Conta) -> None:
    """``%`` é curinga no LIKE. Sem escapar, este filtro devolveria tudo."""
    pagina = await _consultar(conta, action_prefix="%")

    assert pagina["entries"] == []
    assert pagina["total"] == 0


async def test_total_acompanha_a_pagina(conta: Conta) -> None:
    """A tela diz "1 a 50 de 3.412", e o total não pode ser o tamanho da página."""
    await conta.client.post(f"{CORE}/modules/comercial/activate", headers=conta.auth)

    pagina = await _consultar(conta, limit=1)

    assert len(pagina["entries"]) == 1
    assert pagina["total"] >= 3


async def test_pagina_seguinte_nao_repete(conta: Conta) -> None:
    await conta.client.post(f"{CORE}/modules/comercial/activate", headers=conta.auth)

    primeira = await _consultar(conta, limit=1, offset=0)
    segunda = await _consultar(conta, limit=1, offset=1)

    assert primeira["entries"][0]["id"] != segunda["entries"][0]["id"]


async def test_autor_fica_nulo_quando_nao_houve_conta(conta: Conta) -> None:
    await conta.client.post(
        f"{CORE}/auth/login",
        json={
            "tenant_slug": conta.slug,
            "email": "nao-existe@exemplo.com.br",
            "password": "qualquer-coisa-123",
        },
    )

    pagina = await _consultar(conta, action_prefix="auth.login.failed")

    assert pagina["entries"][0]["author"] is None


async def test_consultar_exige_autenticacao(conta: Conta) -> None:
    sem_token = await conta.client.get(f"{CORE}/audit")

    assert sem_token.status_code == 401


async def test_uma_empresa_nao_le_a_trilha_da_outra(conta: Conta) -> None:
    """A trilha tem RLS, e a consulta não filtra por empresa no código — o banco filtra."""
    async with SessionFactory() as session, session.begin():
        outra, _user, _granted = await _bootstrap(
            session,
            tenant_name="Empresa Alheia",
            tenant_slug=f"alheia-{uuid.uuid4().hex[:8]}",
            admin_email=f"outro-{uuid.uuid4().hex[:8]}@teste-decko.com.br",
            admin_name="Outro",
            password=PASSWORD,
            modules=[],
        )
        outra_id = outra.id

    try:
        pagina = await _consultar(conta)
        assert all(entrada["author"] != "Outro" for entrada in pagina["entries"])
        # A empresa alheia tem a própria linha de cadastro, e ela não entra nesta contagem.
        assert pagina["total"] == len(await _trilha(conta.tenant_id))
    finally:
        async with SessionFactory() as session, session.begin():
            await session.execute(delete(Tenant).where(Tenant.id == outra_id))
