from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from decko.db import get_session
from decko.modules import ModuleManifest
from decko.profiles import Profile, modules_to_activate
from decko_modules.core import activation, service
from decko_modules.core.deps import CurrentPrincipal, require
from decko_modules.core.models import Tenant, User
from decko_modules.core.schemas import (
    LoginRequest,
    ModuleOut,
    ProfileOut,
    RefreshRequest,
    SessionOut,
    TenantProfileIn,
    TenantProfileOut,
    TokenResponse,
)

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]

_INVALID_CREDENTIALS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Credenciais inválidas",
    headers={"WWW-Authenticate": "Bearer"},
)


@router.post("/auth/login", response_model=TokenResponse)
async def login(payload: LoginRequest, session: SessionDep) -> TokenResponse:
    try:
        user, tenant, permissions = await service.authenticate(
            session,
            tenant_slug=payload.tenant_slug,
            email=payload.email,
            password=payload.password,
        )
    except service.AuthError:
        raise _INVALID_CREDENTIALS from None

    access_token, refresh_token, expires_in = await service.issue_tokens(
        session, user=user, tenant=tenant, permissions=permissions
    )
    return TokenResponse(
        access_token=access_token, refresh_token=refresh_token, expires_in=expires_in
    )


@router.post("/auth/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, session: SessionDep) -> TokenResponse:
    try:
        *_, access_token, refresh_token, expires_in = await service.rotate_refresh_token(
            session, raw_token=payload.refresh_token
        )
    except service.AuthError:
        raise _INVALID_CREDENTIALS from None

    return TokenResponse(
        access_token=access_token, refresh_token=refresh_token, expires_in=expires_in
    )


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(payload: RefreshRequest, session: SessionDep) -> None:
    await service.revoke_refresh_token(session, raw_token=payload.refresh_token)


@router.get("/auth/me", response_model=SessionOut)
async def me(principal: CurrentPrincipal, session: SessionDep) -> SessionOut:
    user = await session.get(User, principal.user_id)
    tenant = await session.get(Tenant, principal.tenant_id)
    if user is None or tenant is None:
        raise _INVALID_CREDENTIALS

    return SessionOut(
        user=user,  # type: ignore[arg-type]
        tenant=tenant,  # type: ignore[arg-type]
        permissions=sorted(principal.permissions),
        # Permissão e ativação são coisas distintas: o administrador recebe as permissões
        # de todos os módulos instalados na plataforma, mas só alcança os que a empresa
        # ativou. A interface monta o menu a partir desta lista, não do prefixo das
        # permissões — ver docs/adr/0004-ativacao-de-modulo-por-empresa.md.
        active_modules=await activation.active_modules(session, principal.tenant_id),
    )


@router.get("/modules", response_model=list[ModuleOut])
async def list_modules(
    request: Request,
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("core.module.read"))],
) -> list[ModuleOut]:
    """Os módulos instalados na plataforma e quais estão ativos nesta empresa.

    O catálogo vem dos manifestos em disco, carregados na inicialização; o estado vem do
    banco. São as duas únicas fontes, e nenhuma delas é uma lista escrita à mão.
    """
    active = set(await activation.active_modules(session, principal.tenant_id))
    manifests: list[ModuleManifest] = request.app.state.modules

    return [
        ModuleOut(
            name=manifest.name,
            label=manifest.label,
            version=manifest.version,
            required=manifest.required,
            active=manifest.required or manifest.name in active,
        )
        for manifest in manifests
    ]


@router.get("/profiles", response_model=list[ProfileOut])
async def list_profiles(
    request: Request,
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("core.module.read"))],
) -> list[ProfileOut]:
    """Os segmentos que a plataforma sabe configurar.

    Quem está contratando conhece o ramo do negócio, não a lista de módulos — o perfil é o
    atalho entre as duas coisas.
    """
    active = set(await activation.active_modules(session, principal.tenant_id))
    manifests: dict[str, ModuleManifest] = {
        manifest.name: manifest for manifest in request.app.state.modules
    }
    profiles: dict[str, Profile] = request.app.state.profiles

    return [
        ProfileOut(
            name=profile.name,
            label=profile.label,
            description=profile.description.strip(),
            modules=list(profile.modules),
            # Já contratado quando todo módulo não obrigatório do perfil está ativo.
            active=all(manifests[name].required or name in active for name in profile.modules),
        )
        for profile in profiles.values()
    ]


@router.post("/profiles/{profile_name}/activate", response_model=list[ModuleOut])
async def activate_profile(
    profile_name: str,
    request: Request,
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("core.module.activate"))],
) -> list[ModuleOut]:
    """Contrata um segmento inteiro: ativa de uma vez os módulos que ele reúne.

    Devolve o estado de cada módulo do perfil, e não só "ok", para quem chamou saber
    exatamente o que passou a existir.
    """
    profiles: dict[str, Profile] = request.app.state.profiles
    profile = profiles.get(profile_name)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Não existe perfil '{profile_name}' nesta instalação.",
        )

    manifests: dict[str, ModuleManifest] = {
        manifest.name: manifest for manifest in request.app.state.modules
    }

    for module_name in modules_to_activate(profile, manifests):
        await activation.activate(
            session,
            tenant_id=principal.tenant_id,
            module_name=module_name,
            activated_by=principal.user_id,
        )

    return [
        ModuleOut(
            name=manifests[name].name,
            label=manifests[name].label,
            version=manifests[name].version,
            required=manifests[name].required,
            active=True,
        )
        for name in profile.modules
    ]


def _manifest_or_404(request: Request, module_name: str) -> ModuleManifest:
    for manifest in request.app.state.modules:
        if manifest.name == module_name:
            return manifest
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Não existe módulo '{module_name}' nesta instalação.",
    )


@router.post("/modules/{module_name}/activate", response_model=ModuleOut)
async def activate_module(
    module_name: str,
    request: Request,
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("core.module.activate"))],
) -> ModuleOut:
    manifest = _manifest_or_404(request, module_name)
    await activation.activate(
        session,
        tenant_id=principal.tenant_id,
        module_name=manifest.name,
        activated_by=principal.user_id,
    )
    return ModuleOut(
        name=manifest.name,
        label=manifest.label,
        version=manifest.version,
        required=manifest.required,
        active=True,
    )


@router.delete("/modules/{module_name}/activate", response_model=ModuleOut)
async def deactivate_module(
    module_name: str,
    request: Request,
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("core.module.activate"))],
) -> ModuleOut:
    manifest = _manifest_or_404(request, module_name)
    if manifest.required:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"O módulo '{manifest.name}' é obrigatório e não pode ser desativado.",
        )

    await activation.deactivate(session, tenant_id=principal.tenant_id, module_name=manifest.name)
    return ModuleOut(
        name=manifest.name,
        label=manifest.label,
        version=manifest.version,
        required=manifest.required,
        active=False,
    )


async def _current_tenant(session: AsyncSession, principal: CurrentPrincipal) -> Tenant:
    tenant = await session.get(Tenant, principal.tenant_id)
    if tenant is None:
        raise _INVALID_CREDENTIALS
    return tenant


@router.get("/tenant", response_model=TenantProfileOut)
async def read_tenant(
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("core.tenant.read"))],
) -> Tenant:
    """A empresa de quem está autenticado. Não existe rota para ler outra."""
    return await _current_tenant(session, principal)


@router.put("/tenant", response_model=TenantProfileOut)
async def update_tenant(
    payload: TenantProfileIn,
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("core.tenant.update"))],
) -> Tenant:
    """Edita a identificação da empresa.

    São os dados que o Planejamento Operacional imprime no cabeçalho — registro no MAPA,
    CREA, CDA e inscrições. Sem eles o documento sai com o bloco em branco, e era o que
    acontecia: os campos não existiam e a permissão declarada no manifesto não tinha rota.

    O tenant alterado é sempre o de quem chamou, tirado do token. Aceitá-lo no corpo
    deixaria uma empresa editar outra com um identificador adivinhado.
    """
    tenant = await _current_tenant(session, principal)
    for field, value in payload.model_dump().items():
        setattr(tenant, field, value)
    await session.flush()
    return tenant
