from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from decko.db import get_session
from decko.modules import ModuleManifest, dependents, with_dependencies
from decko.profiles import Profile, modules_to_activate
from decko.seed import apply_seed, has_seed
from decko_modules.core import activation, service
from decko_modules.core.deps import CurrentPrincipal, require
from decko_modules.core.models import Tenant, User
from decko_modules.core.schemas import (
    LoginRequest,
    ModuleOut,
    ProfileOut,
    RefreshRequest,
    SeedResultOut,
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


def _module_out(manifest: ModuleManifest, *, active: bool) -> ModuleOut:
    """O módulo como a vitrine o mostra.

    Tudo o que descreve o módulo vem do manifesto; só o active vem do banco. Assim
    acrescentar um módulo é escrever um module.toml, e não editar também a interface.
    """
    return ModuleOut(
        name=manifest.name,
        label=manifest.label,
        version=manifest.version,
        required=manifest.required,
        active=active,
        category=manifest.category,
        summary=manifest.summary,
        icon=manifest.icon,
        accent=manifest.accent,
        depends=list(manifest.depends),
        has_seed=has_seed(manifest.name),
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
        _module_out(manifest, active=manifest.required or manifest.name in active)
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
        await activation.grant_module_permissions(
            session,
            tenant_id=principal.tenant_id,
            permissions=manifests[module_name].permissions,
        )

    return [_module_out(manifests[name], active=True) for name in profile.modules]


def _manifests(request: Request) -> dict[str, ModuleManifest]:
    return {manifest.name: manifest for manifest in request.app.state.modules}


def _manifest_or_404(request: Request, module_name: str) -> ModuleManifest:
    manifest = _manifests(request).get(module_name)
    if manifest is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Não existe módulo '{module_name}' nesta instalação.",
        )
    return manifest


@router.post("/modules/{module_name}/activate", response_model=list[ModuleOut])
async def activate_module(
    module_name: str,
    request: Request,
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("core.module.activate"))],
) -> list[ModuleOut]:
    """Instala o módulo na empresa, junto com o que ele precisa para funcionar.

    Devolve a lista, e não só o módulo pedido, porque quem chamou precisa saber que
    outras coisas passaram a existir no menu.
    """
    manifest = _manifest_or_404(request, module_name)
    manifests = _manifests(request)

    ativados: list[ModuleOut] = []
    for name in with_dependencies(manifest.name, manifests):
        dependencia = manifests[name]
        if dependencia.required:
            continue
        await activation.activate(
            session,
            tenant_id=principal.tenant_id,
            module_name=name,
            activated_by=principal.user_id,
        )
        # As permissões do módulo entram no papel de administrador agora. O papel é
        # montado no cadastro da empresa, a partir dos módulos que existiam naquele
        # momento; sem isto, módulo instalado depois ficaria com as telas inalcançáveis.
        await activation.grant_module_permissions(
            session, tenant_id=principal.tenant_id, permissions=dependencia.permissions
        )
        ativados.append(_module_out(dependencia, active=True))
    return ativados


@router.delete("/modules/{module_name}/activate", response_model=ModuleOut)
async def deactivate_module(
    module_name: str,
    request: Request,
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("core.module.activate"))],
) -> ModuleOut:
    """Desinstala o módulo. Os dados dele permanecem no banco — ver ADR 0004."""
    manifest = _manifest_or_404(request, module_name)
    if manifest.required:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"O módulo '{manifest.name}' é obrigatório e não pode ser desativado.",
        )

    # Desligar um módulo de que outro depende deixaria o segundo com telas que não abrem.
    # Recusar e dizer quais são é mais honesto do que desinstalar em cascata sem avisar.
    ativos = set(await activation.active_modules(session, principal.tenant_id))
    presos = [name for name in dependents(manifest.name, _manifests(request)) if name in ativos]
    if presos:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"O módulo '{manifest.name}' é usado por: {', '.join(presos)}. "
                "Desinstale esses antes."
            ),
        )

    await activation.deactivate(session, tenant_id=principal.tenant_id, module_name=manifest.name)
    return _module_out(manifest, active=False)


@router.post("/modules/{module_name}/seed", response_model=SeedResultOut)
async def seed_module(
    module_name: str,
    request: Request,
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("core.module.activate"))],
) -> SeedResultOut:
    """Traz os itens iniciais do módulo para esta empresa.

    Existe por causa da decisão 3 do ADR 0010: a semente entra na contratação, e não numa
    subida de aplicação. Isso protege quem já opera de receber linhas no catálogo sem
    pedir, e deixa de fora a empresa que instalou o módulo antes de a semente existir.
    Este é o pedido dela — explícito, de quem tem permissão para contratar módulo.

    Repetir não duplica e não ressuscita o que a empresa apagou: o registro de semente
    responde isso, e ele é o mesmo que a ativação usa.
    """
    manifest = _manifest_or_404(request, module_name)

    # Semear módulo não contratado criaria catálogo para tela que nem abre.
    if not manifest.required and not await activation.is_active(
        session, principal.tenant_id, manifest.name
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"O módulo '{manifest.name}' não está ativo nesta empresa.",
        )

    criados = await apply_seed(session, module_name=manifest.name, tenant_id=principal.tenant_id)
    return SeedResultOut(module=manifest.name, created=criados)


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
