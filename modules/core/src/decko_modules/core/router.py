from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from decko.db import get_session
from decko_modules.core import service
from decko_modules.core.deps import CurrentPrincipal, require
from decko_modules.core.models import Tenant, User
from decko_modules.core.schemas import (
    LoginRequest,
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
