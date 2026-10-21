"""Perfil de segmento: contratar um ramo inteiro de uma vez.

Quem contrata conhece o próprio ramo, não a lista de módulos. Estes testes provam que o
atalho funciona e que ele não contorna a barreira de ativação — ele a usa.

Decisão: ``docs/adr/0005-perfil-de-segmento.md``.
"""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from decko.db import SessionFactory
from decko.main import create_app
from decko.modules import ModuleManifest
from decko.profiles import Profile, ProfileError
from decko.profiles import discover as discover_profiles
from decko_modules.core.cli import _bootstrap
from decko_modules.core.models import Tenant

PASSWORD = "senha-local-de-teste-123"
CORE = "/api/v1/core"
AGRO = "/api/v1/agro"
PERFIL = "pulverizacao-agricola"


@dataclass
class Company:
    tenant_id: uuid.UUID
    token: str


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    created: list[uuid.UUID] = []
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as http:
        http.created = created  # type: ignore[attr-defined]
        try:
            yield http
        finally:
            async with SessionFactory() as session, session.begin():
                for tenant_id in created:
                    await session.execute(delete(Tenant).where(Tenant.id == tenant_id))


async def _company(client: AsyncClient) -> Company:
    suffix = uuid.uuid4().hex[:8]
    slug = f"teste-{suffix}"
    email = f"admin-{suffix}@teste-decko.com.br"

    async with SessionFactory() as session, session.begin():
        tenant, _user, _granted = await _bootstrap(
            session,
            tenant_name="Empresa de Teste",
            tenant_slug=slug,
            admin_email=email,
            admin_name="Administrador",
            password=PASSWORD,
            modules=[],
        )
        tenant_id = tenant.id

    login = await client.post(
        f"{CORE}/auth/login",
        json={"tenant_slug": slug, "email": email, "password": PASSWORD},
    )
    client.created.append(tenant_id)  # type: ignore[attr-defined]
    return Company(tenant_id=tenant_id, token=login.json()["access_token"])


def _auth(company: Company) -> dict[str, str]:
    return {"Authorization": f"Bearer {company.token}"}


async def test_profiles_are_listed_with_what_they_bring(client: AsyncClient) -> None:
    company = await _company(client)

    profiles = (await client.get(f"{CORE}/profiles", headers=_auth(company))).json()
    by_name = {profile["name"]: profile for profile in profiles}

    assert PERFIL in by_name
    assert by_name[PERFIL]["modules"] == ["agro"]
    assert by_name[PERFIL]["label"]
    assert by_name[PERFIL]["description"]


async def test_a_new_company_has_no_profile_contracted(client: AsyncClient) -> None:
    company = await _company(client)

    profiles = (await client.get(f"{CORE}/profiles", headers=_auth(company))).json()

    assert all(profile["active"] is False for profile in profiles)


async def test_contracting_a_profile_opens_its_modules(client: AsyncClient) -> None:
    """É o 'um clique': escolher o ramo e o sistema ficar alcançável."""
    company = await _company(client)
    assert (await client.get(f"{AGRO}/clients", headers=_auth(company))).status_code == 404

    response = await client.post(f"{CORE}/profiles/{PERFIL}/activate", headers=_auth(company))

    assert response.status_code == 200
    assert [module["name"] for module in response.json()] == ["agro"]
    assert (await client.get(f"{AGRO}/clients", headers=_auth(company))).status_code == 200


async def test_the_profile_shows_as_contracted_afterwards(client: AsyncClient) -> None:
    company = await _company(client)
    await client.post(f"{CORE}/profiles/{PERFIL}/activate", headers=_auth(company))

    profiles = (await client.get(f"{CORE}/profiles", headers=_auth(company))).json()
    by_name = {profile["name"]: profile for profile in profiles}

    assert by_name[PERFIL]["active"] is True


async def test_contracting_twice_is_not_an_error(client: AsyncClient) -> None:
    company = await _company(client)
    await client.post(f"{CORE}/profiles/{PERFIL}/activate", headers=_auth(company))

    again = await client.post(f"{CORE}/profiles/{PERFIL}/activate", headers=_auth(company))

    assert again.status_code == 200


async def test_the_session_reports_what_the_profile_turned_on(client: AsyncClient) -> None:
    company = await _company(client)
    await client.post(f"{CORE}/profiles/{PERFIL}/activate", headers=_auth(company))

    session = (await client.get(f"{CORE}/auth/me", headers=_auth(company))).json()

    assert session["active_modules"] == ["agro"]


async def test_an_unknown_profile_does_not_exist(client: AsyncClient) -> None:
    company = await _company(client)

    response = await client.post(f"{CORE}/profiles/supermercado/activate", headers=_auth(company))

    assert response.status_code == 404


async def test_contracting_a_profile_requires_authentication(client: AsyncClient) -> None:
    response = await client.post(f"{CORE}/profiles/{PERFIL}/activate")

    assert response.status_code == 401


def test_a_profile_listing_an_absent_module_is_refused(tmp_path: Path) -> None:
    """Erro de empacotamento aparece na inicialização, não na frente de quem contrata."""
    (tmp_path / "supermercado.toml").write_text(
        '[profile]\nname = "supermercado"\nlabel = "Supermercado"\nmodules = ["pdv", "estoque"]\n',
        encoding="utf-8",
    )

    with pytest.raises(ProfileError) as erro:
        discover_profiles(tmp_path, {})

    assert "pdv" in str(erro.value)


def test_required_modules_need_no_activation_row() -> None:
    """O núcleo já vale como ativo; gravar linha para ele seria redundante."""
    from decko.profiles import modules_to_activate

    manifests = {
        "core": ModuleManifest(
            name="core", label="Núcleo", version="0.1.0", package="x", required=True
        ),
        "agro": ModuleManifest(name="agro", label="Agro", version="0.1.0", package="y"),
    }
    profile = Profile(name="p", label="P", description="", modules=("core", "agro"))

    assert modules_to_activate(profile, manifests) == ["agro"]
