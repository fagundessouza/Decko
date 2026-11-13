import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from decko.config import get_settings
from decko.db import get_session
from decko.modules import ModuleManifest, dependents, with_dependencies
from decko.profiles import Profile, modules_to_activate
from decko.seed import apply_seed, has_seed
from decko_modules.core import activation, audit, service
from decko_modules.core.breach import SenhaVazadaError
from decko_modules.core.deps import CurrentPrincipal, require
from decko_modules.core.models import Tenant, User
from decko_modules.core.schemas import (
    AuditEntryOut,
    AuditPageOut,
    CrachaIn,
    DefinirPinIn,
    EntrarPorPinIn,
    LoginRequest,
    MembroIn,
    MembroOut,
    MembroPatchIn,
    ModuleOut,
    OperadorOut,
    PapeisIn,
    PapelOut,
    PapelResumoOut,
    ProfileOut,
    RefreshRequest,
    SeedResultOut,
    SessionOut,
    TenantProfileIn,
    TenantProfileOut,
    TokenResponse,
    TrocaDeSenhaIn,
)

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]

_INVALID_CREDENTIALS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Credenciais inválidas",
    headers={"WWW-Authenticate": "Bearer"},
)


@router.post("/auth/login", response_model=TokenResponse)
async def login(payload: LoginRequest, request: Request, session: SessionDep) -> TokenResponse:
    ip = audit.ip_de(request)
    try:
        user, tenant, permissions = await service.authenticate(
            session,
            tenant_slug=payload.tenant_slug,
            email=payload.email,
            password=payload.password,
        )
    except service.AuthError as falha:
        # Em transação própria: esta requisição vai levantar, e a linha iria embora com ela.
        # Tentativa contra empresa inexistente não tem empresa a que se prender — ver
        # decko_modules.core.audit.
        if falha.tenant_id is not None:
            await audit.registrar_a_parte(
                tenant_id=falha.tenant_id,
                user_id=falha.user_id,
                action="auth.login.failed",
                entity="user_account",
                entity_id=str(falha.user_id) if falha.user_id else None,
                data={"motivo": falha.motivo},
                ip=ip,
            )
        raise _INVALID_CREDENTIALS from None

    access_token, refresh_token, expires_in = await service.issue_tokens(
        session, user=user, tenant=tenant, permissions=permissions
    )
    audit.registrar(
        session,
        tenant_id=tenant.id,
        user_id=user.id,
        action="auth.login",
        entity="user_account",
        entity_id=str(user.id),
        ip=ip,
    )
    return TokenResponse(
        access_token=access_token, refresh_token=refresh_token, expires_in=expires_in
    )


@router.post("/auth/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, request: Request, session: SessionDep) -> TokenResponse:
    try:
        *_, access_token, refresh_token, expires_in = await service.rotate_refresh_token(
            session, raw_token=payload.refresh_token
        )
    except service.AuthError as falha:
        # Só a reapresentação de token já revogado é registrada: é cópia em circulação.
        if falha.tenant_id is not None:
            await audit.registrar_a_parte(
                tenant_id=falha.tenant_id,
                user_id=falha.user_id,
                action="auth.refresh.reused",
                entity="refresh_token",
                data={"motivo": falha.motivo},
                ip=audit.ip_de(request),
            )
        raise _INVALID_CREDENTIALS from None

    return TokenResponse(
        access_token=access_token, refresh_token=refresh_token, expires_in=expires_in
    )


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(payload: RefreshRequest, request: Request, session: SessionDep) -> None:
    encerrada = await service.revoke_refresh_token(session, raw_token=payload.refresh_token)
    if encerrada is None:
        # Token inválido ou já revogado: nada aconteceu, e a resposta continua 204 para
        # não dizer a quem chamou se o token valia.
        return

    tenant_id, user_id = encerrada
    audit.registrar(
        session,
        tenant_id=tenant_id,
        user_id=user_id,
        action="auth.logout",
        entity="user_account",
        entity_id=str(user_id),
        ip=audit.ip_de(request),
    )


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


@router.get("/audit", response_model=AuditPageOut)
async def read_audit(
    session: SessionDep,
    _: Annotated[object, Depends(require("core.audit.read"))],
    action_prefix: Annotated[str | None, Query(max_length=80)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditPageOut:
    """A trilha desta empresa, do mais recente para o mais antigo.

    Escrever a trilha sem poder consultá-la atende a LGPD pela metade: o titular tem
    direito de saber o que foi feito com o dado dele, e isso exige alguém conseguindo
    olhar. A permissão ``core.audit.read`` existe desde a primeira versão e era esta rota
    que faltava.

    Somente leitura, como a tabela: a trilha não tem rota de escrita nem de exclusão, e
    quem registra é o fluxo que agiu.
    """
    pagina = await audit.consultar(session, action_prefix=action_prefix, limit=limit, offset=offset)
    return AuditPageOut(
        total=pagina.total,
        entries=[
            AuditEntryOut(
                id=entrada.log.id,
                action=entrada.log.action,
                entity=entrada.log.entity,
                entity_id=entrada.log.entity_id,
                data=entrada.log.data,
                ip_address=str(entrada.log.ip_address) if entrada.log.ip_address else None,
                created_at=entrada.log.created_at,
                user_id=entrada.log.user_id,
                author=entrada.autor,
            )
            for entrada in pagina.entradas
        ],
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
        # Módulo da plataforma não entra na vitrine de ninguém. Quem já o tem ativo
        # continua vendo o menu dele; o que não aparece é a oferta de contratá-lo.
        if not manifest.interno or manifest.name in active
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

    audit.registrar(
        session,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        action="profile.activate",
        entity="profile",
        entity_id=profile.name,
        data={"modulos": list(profile.modules)},
        ip=audit.ip_de(request),
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

    audit.registrar(
        session,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        action="module.activate",
        entity="tenant_module",
        entity_id=manifest.name,
        # Registra também o que veio junto: quem contrata escolhe um nome e recebe a
        # árvore, e a trilha precisa dizer o que de fato passou a existir.
        data={"instalados": [item.name for item in ativados]},
        ip=audit.ip_de(request),
    )
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
    audit.registrar(
        session,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        action="module.deactivate",
        entity="tenant_module",
        entity_id=manifest.name,
        ip=audit.ip_de(request),
    )
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
    audit.registrar(
        session,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        action="module.seed",
        entity="tenant_module",
        entity_id=manifest.name,
        # Os identificadores, e não a contagem: a conferência precisa saber **o que** entrou.
        data={"criados": criados},
        ip=audit.ip_de(request),
    )
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


# ----------------------------------------------------------------------- equipe da loja
#
# O dono da loja administra a própria equipe. As permissões `core.user.*` e `core.role.*`
# existiam no manifesto desde a primeira versão e não tinham rota nenhuma por trás: só o
# comando `decko-admin bootstrap` criava gente, na linha de comando do servidor.
#
# Decisão: docs/adr/0020-operador-supervisor-e-papeis.md.


def _invalido(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))


def _membro_visto(membro: service.Membro) -> MembroOut:
    return MembroOut(
        id=membro.user.id,
        email=membro.user.email,
        full_name=membro.user.full_name,
        is_active=membro.user.is_active,
        last_login_at=membro.user.last_login_at,
        must_change_password=membro.user.must_change_password,
        # Se tem PIN, nunca qual é.
        tem_pin=membro.user.tem_pin,
        cracha=membro.user.cracha,
        papeis=[PapelResumoOut.model_validate(p) for p in membro.papeis],
    )


async def _um_membro(session: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID) -> MembroOut:
    """Relê a pessoa com os papéis, depois de mexer.

    Relê em vez de montar do objeto em memória pelo mesmo motivo do caixa: campo com valor
    gerado pelo banco fica expirado depois do flush, e lê-lo dispara busca síncrona dentro
    de função assíncrona.
    """
    for membro in await service.listar_membros(session, tenant_id):
        if membro.user.id == user_id:
            return _membro_visto(membro)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pessoa não encontrada.")


async def _carregar_membro(session: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID) -> User:
    user = await session.get(User, user_id)
    if user is None or user.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pessoa não encontrada.")
    return user


@router.get("/papeis", response_model=list[PapelOut])
async def listar_papeis(
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("core.role.read"))],
) -> list[PapelOut]:
    """Os papéis da empresa e o que cada um concede."""
    return [
        PapelOut(
            id=linha.papel.id,
            name=linha.papel.name,
            description=linha.papel.description,
            permissoes=linha.permissoes,
        )
        for linha in await service.listar_papeis(session, principal.tenant_id)
    ]


@router.get("/users", response_model=list[MembroOut])
async def listar_usuarios(
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("core.user.read"))],
) -> list[MembroOut]:
    return [
        _membro_visto(membro)
        for membro in await service.listar_membros(session, principal.tenant_id)
    ]


@router.post("/users", response_model=MembroOut, status_code=status.HTTP_201_CREATED)
async def criar_usuario(
    payload: MembroIn,
    request: Request,
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("core.user.create"))],
) -> MembroOut:
    """Cria alguém da equipe, com senha inicial que ela será obrigada a trocar."""
    try:
        user = await service.criar_membro(
            session,
            tenant_id=principal.tenant_id,
            email=payload.email,
            full_name=payload.full_name,
            senha_inicial=payload.senha_inicial,
            role_ids=payload.papeis,
            breach_check=get_settings().breach_check_enabled,
        )
    except SenhaVazadaError as exc:
        raise _invalido(exc) from exc
    except service.EquipeError as exc:
        raise _invalido(exc) from exc

    # A senha **não** entra na trilha, em forma nenhuma — ver o cabeçalho de `audit.py`.
    audit.registrar(
        session,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        action="user.create",
        entity="user_account",
        entity_id=str(user.id),
        data={"email": user.email, "papeis": len(payload.papeis)},
        ip=audit.ip_de(request),
    )
    return await _um_membro(session, principal.tenant_id, user.id)


@router.patch("/users/{user_id}", response_model=MembroOut)
async def atualizar_usuario(
    user_id: uuid.UUID,
    payload: MembroPatchIn,
    request: Request,
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("core.user.update"))],
) -> MembroOut:
    user = await _carregar_membro(session, principal.tenant_id, user_id)
    if payload.full_name is not None:
        try:
            await service.renomear_membro(session, user=user, full_name=payload.full_name)
        except service.EquipeError as exc:
            raise _invalido(exc) from exc

        audit.registrar(
            session,
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            action="user.update",
            entity="user_account",
            entity_id=str(user.id),
            data={"full_name": user.full_name},
            ip=audit.ip_de(request),
        )
    return await _um_membro(session, principal.tenant_id, user_id)


@router.put("/users/{user_id}/papeis", response_model=MembroOut)
async def definir_papeis(
    user_id: uuid.UUID,
    payload: PapeisIn,
    request: Request,
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("core.role.assign"))],
) -> MembroOut:
    """Troca os papéis da pessoa pelos informados.

    **Ninguém troca os próprios papéis.** Quem tirasse de si a permissão de administrar
    ficaria trancado do lado de fora da própria empresa, sem caminho de volta pela
    interface — e o único jeito de voltar seria a linha de comando do servidor.
    """
    if user_id == principal.user_id:
        raise _invalido(
            ValueError("Você não pode trocar os próprios papéis; peça a outro administrador.")
        )

    user = await _carregar_membro(session, principal.tenant_id, user_id)
    try:
        papeis = await service.definir_papeis(session, user=user, role_ids=payload.papeis)
    except service.EquipeError as exc:
        raise _invalido(exc) from exc

    audit.registrar(
        session,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        action="user.roles",
        entity="user_account",
        entity_id=str(user.id),
        data={"papeis": [p.name for p in papeis]},
        ip=audit.ip_de(request),
    )
    return await _um_membro(session, principal.tenant_id, user_id)


@router.post("/users/{user_id}/situacao", response_model=MembroOut)
async def definir_situacao(
    user_id: uuid.UUID,
    ativo: Annotated[bool, Query(description="Liga ou desliga o acesso da pessoa.")],
    request: Request,
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("core.user.deactivate"))],
) -> MembroOut:
    """Liga ou desliga o acesso. O que a pessoa fez continua no histórico — não se apaga.

    Desligar a si mesmo é recusado pelo mesmo motivo que trocar os próprios papéis.
    """
    if user_id == principal.user_id:
        raise _invalido(ValueError("Você não pode desligar o próprio acesso."))

    user = await _carregar_membro(session, principal.tenant_id, user_id)
    await service.definir_situacao(session, user=user, ativo=ativo)

    audit.registrar(
        session,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        action="user.activate" if ativo else "user.deactivate",
        entity="user_account",
        entity_id=str(user.id),
        ip=audit.ip_de(request),
    )
    return await _um_membro(session, principal.tenant_id, user_id)


@router.post("/auth/senha", status_code=status.HTTP_204_NO_CONTENT)
async def trocar_senha(
    payload: TrocaDeSenhaIn,
    request: Request,
    session: SessionDep,
    principal: CurrentPrincipal,
) -> None:
    """Troca a própria senha. Não exige permissão: é da própria conta.

    É por aqui que quem foi criado pelo dono deixa de usar a senha que o dono escolheu —
    e é isso que torna a trilha capaz de dizer quem fez o quê.
    """
    user = await _carregar_membro(session, principal.tenant_id, principal.user_id)
    try:
        await service.trocar_senha(
            session,
            user=user,
            senha_atual=payload.senha_atual,
            nova_senha=payload.nova_senha,
            breach_check=get_settings().breach_check_enabled,
        )
    except SenhaVazadaError as exc:
        raise _invalido(exc) from exc
    except service.EquipeError as exc:
        raise _invalido(exc) from exc

    audit.registrar(
        session,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        action="user.password",
        entity="user_account",
        entity_id=str(user.id),
        ip=audit.ip_de(request),
    )


# ------------------------------------------------------------------- entrada rápida


@router.get("/operadores", response_model=list[OperadorOut])
async def listar_operadores(session: SessionDep, principal: CurrentPrincipal) -> list[OperadorOut]:
    """Quem dá para escolher na troca de operador: só quem já tem PIN.

    Pede apenas estar autenticado, e não uma permissão de administração: quem precisa
    desta lista é quem está no balcão querendo passar o turno. Dentro de uma loja, saber
    o nome de quem trabalha ali não é segredo — e o que entra é o PIN.
    """
    linhas = (
        await session.execute(
            select(User.id, User.full_name)
            .where(
                User.tenant_id == principal.tenant_id,
                User.is_active.is_(True),
                User.pin_hash.is_not(None),
            )
            .order_by(User.full_name)
        )
    ).all()
    return [OperadorOut(id=user_id, nome=nome) for user_id, nome in linhas]


@router.post("/auth/pin", response_model=TokenResponse)
async def entrar_por_pin(
    payload: EntrarPorPinIn,
    request: Request,
    session: SessionDep,
    principal: CurrentPrincipal,
) -> TokenResponse:
    """Troca de operador na estação, sem digitar empresa, e-mail e senha.

    **Exige uma estação já autenticada nesta empresa**, e é isso que sustenta um PIN de
    quatro dígitos: o login completo diz "este aparelho é da loja", e o PIN diz apenas
    qual pessoa está nele agora. Sem essa âncora, o PIN seria a porta da frente.

    A sessão anterior não é revogada aqui: ela expira sozinha, e o token novo é o que a
    estação passa a usar. Ver docs/adr/0020-operador-supervisor-e-papeis.md, decisão 1.
    """
    ip = audit.ip_de(request)
    try:
        user, tenant, permissions = await service.entrar_por_pin(
            session,
            tenant_id=principal.tenant_id,
            pin=payload.pin,
            user_id=payload.user_id,
            cracha=payload.cracha,
        )
    except service.EquipeError as exc:
        raise _invalido(exc) from exc
    except service.AuthError as exc:
        # Em transação própria: a requisição vai levantar, e com ela a trilha iria embora
        # — e o que se investiga depois é justamente a sequência de tentativas.
        await audit.registrar_a_parte(
            tenant_id=exc.tenant_id or principal.tenant_id,
            user_id=exc.user_id,
            action="auth.pin.failed",
            entity="user_account",
            entity_id=str(exc.user_id) if exc.user_id else None,
            data={"motivo": exc.motivo},
            ip=ip,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    access_token, refresh_token, expires_in = await service.issue_tokens(
        session, user=user, tenant=tenant, permissions=permissions
    )
    audit.registrar(
        session,
        tenant_id=tenant.id,
        user_id=user.id,
        action="auth.pin",
        entity="user_account",
        entity_id=str(user.id),
        # Quem estava na estação antes: é o que liga uma troca de operador à anterior.
        data={"estacao_de": str(principal.user_id)},
        ip=ip,
    )
    return TokenResponse(
        access_token=access_token, refresh_token=refresh_token, expires_in=expires_in
    )


@router.put("/auth/pin", status_code=status.HTTP_204_NO_CONTENT)
async def definir_pin(
    payload: DefinirPinIn,
    request: Request,
    session: SessionDep,
    principal: CurrentPrincipal,
) -> None:
    """Define o próprio PIN. Não exige permissão: é da própria conta."""
    user = await _carregar_membro(session, principal.tenant_id, principal.user_id)
    try:
        await service.definir_pin(session, user=user, senha=payload.senha, pin=payload.pin)
    except service.EquipeError as exc:
        raise _invalido(exc) from exc

    audit.registrar(
        session,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        action="user.pin",
        entity="user_account",
        entity_id=str(user.id),
        ip=audit.ip_de(request),
    )


@router.delete("/users/{user_id}/pin", response_model=MembroOut)
async def remover_pin(
    user_id: uuid.UUID,
    request: Request,
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("core.user.update"))],
) -> MembroOut:
    """Tira o PIN de quem esqueceu. A senha continua valendo, e um PIN novo é só definir."""
    user = await _carregar_membro(session, principal.tenant_id, user_id)
    await service.remover_pin(session, user=user)

    audit.registrar(
        session,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        action="user.pin.remove",
        entity="user_account",
        entity_id=str(user.id),
        ip=audit.ip_de(request),
    )
    return await _um_membro(session, principal.tenant_id, user_id)


@router.put("/users/{user_id}/cracha", response_model=MembroOut)
async def definir_cracha(
    user_id: uuid.UUID,
    payload: CrachaIn,
    request: Request,
    session: SessionDep,
    principal: CurrentPrincipal,
    _: Annotated[object, Depends(require("core.user.update"))],
) -> MembroOut:
    """O dono emite o crachá: é cartão da loja, não escolha de quem o usa."""
    user = await _carregar_membro(session, principal.tenant_id, user_id)
    try:
        await service.definir_cracha(session, user=user, cracha=payload.cracha)
        await session.flush()
    except service.EquipeError as exc:
        raise _invalido(exc) from exc
    except IntegrityError as exc:
        # Quem recusa dois crachás iguais é o banco: validar só aqui deixaria passar duas
        # emissões simultâneas.
        raise _invalido(ValueError("Já existe alguém com este crachá nesta empresa.")) from exc

    audit.registrar(
        session,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        action="user.cracha",
        entity="user_account",
        entity_id=str(user.id),
        data={"emitido": user.cracha is not None},
        ip=audit.ip_de(request),
    )
    return await _um_membro(session, principal.tenant_id, user_id)
