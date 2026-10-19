"""Dependências de autenticação e autorização reutilizáveis por qualquer módulo."""

import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from decko.db import bind_tenant, get_session
from decko.tenancy import set_current_tenant
from decko_modules.core import security

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    permissions: frozenset[str]

    def can(self, permission: str) -> bool:
        return permission in self.permissions


async def get_principal(
    session: Annotated[AsyncSession, Depends(get_session)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> Principal:
    """Valida o token e amarra o tenant à sessão recebida.

    A ordem importa: esta dependência recebe a sessão e só então define o tenant nela, de
    modo que nenhuma consulta do endpoint roda fora do escopo da empresa.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticação requerida",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = security.decode_access_token(credentials.credentials)
        user_id = uuid.UUID(payload["sub"])
        tenant_id = uuid.UUID(payload["tid"])
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido ou expirado",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    set_current_tenant(tenant_id)
    await bind_tenant(session, tenant_id)

    return Principal(
        user_id=user_id,
        tenant_id=tenant_id,
        permissions=frozenset(payload.get("perms", [])),
    )


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


def require(
    permission: str,
) -> Callable[[Principal], Coroutine[Any, Any, Principal]]:
    """Exige uma permissão nomeada, como ``agro.plan.create``.

    As permissões válidas são declaradas no manifesto de cada módulo.
    """

    async def dependency(principal: CurrentPrincipal) -> Principal:
        if not principal.can(permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permissão necessária: {permission}",
            )
        return principal

    return dependency
