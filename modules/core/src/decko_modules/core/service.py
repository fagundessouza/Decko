"""Regra de negócio de autenticação e sessão. Não conhece HTTP."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from decko.config import get_settings
from decko.db import bind_tenant
from decko_modules.core import security
from decko_modules.core.models import (
    RefreshToken,
    Role,
    RolePermission,
    Tenant,
    User,
    UserRole,
)

# Hash descartável usado para igualar o tempo de resposta quando o usuário não existe.
# Sem isso, a diferença de latência revela quais e-mails estão cadastrados.
_DUMMY_HASH = security.hash_password("decko-timing-equalizer")


class AuthError(Exception):
    """Falha de autenticação.

    A mensagem é deliberadamente genérica: distinguir "empresa inexistente" de "senha
    errada" entrega informação a quem está sondando.
    """

    def __init__(self, message: str = "Credenciais inválidas") -> None:
        super().__init__(message)


async def _load_permissions(session: AsyncSession, user_id: uuid.UUID) -> list[str]:
    result = await session.execute(
        select(RolePermission.permission)
        .join(Role, Role.id == RolePermission.role_id)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id)
        .distinct()
    )
    return sorted(result.scalars().all())


async def authenticate(
    session: AsyncSession, *, tenant_slug: str, email: str, password: str
) -> tuple[User, Tenant, list[str]]:
    """Valida credenciais e devolve usuário, empresa e permissões efetivas."""
    tenant = await session.scalar(
        select(Tenant).where(Tenant.slug == tenant_slug, Tenant.is_active.is_(True))
    )
    if tenant is None:
        security.verify_password(password, _DUMMY_HASH)
        raise AuthError

    # A partir daqui as consultas enxergam apenas esta empresa.
    await bind_tenant(session, tenant.id)

    user = await session.scalar(select(User).where(User.email == email))
    if user is None:
        security.verify_password(password, _DUMMY_HASH)
        raise AuthError

    if not security.verify_password(password, user.password_hash):
        raise AuthError

    if not user.is_active:
        raise AuthError("Usuário desativado")

    if security.needs_rehash(user.password_hash):
        user.password_hash = security.hash_password(password)

    user.last_login_at = datetime.now(UTC)
    permissions = await _load_permissions(session, user.id)
    return user, tenant, permissions


async def issue_tokens(
    session: AsyncSession, *, user: User, tenant: Tenant, permissions: list[str]
) -> tuple[str, str, int]:
    """Emite um par de tokens e persiste o hash do refresh."""
    settings = get_settings()
    access_token, expires_in = security.create_access_token(
        user_id=user.id, tenant_id=tenant.id, permissions=permissions
    )
    raw_refresh, refresh_hash = security.new_refresh_token(tenant.id)

    session.add(
        RefreshToken(
            tenant_id=tenant.id,
            user_id=user.id,
            token_hash=refresh_hash,
            expires_at=datetime.now(UTC) + timedelta(seconds=settings.refresh_token_ttl_seconds),
        )
    )
    return access_token, raw_refresh, expires_in


async def _find_refresh_token(session: AsyncSession, raw_token: str) -> RefreshToken | None:
    """Localiza o token, amarrando antes a empresa indicada por ele.

    Sem esse passo a consulta roda sem empresa definida e o RLS não devolve linha alguma,
    fazendo qualquer renovação legítima parecer inválida.
    """
    try:
        tenant_id = security.tenant_from_refresh_token(raw_token)
    except ValueError:
        return None

    await bind_tenant(session, tenant_id)
    token_hash = security.hash_refresh_token(raw_token)
    return await session.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))


async def rotate_refresh_token(
    session: AsyncSession, *, raw_token: str
) -> tuple[User, Tenant, list[str], str, str, int]:
    """Troca um refresh token por um novo par, invalidando o anterior.

    A rotação é o que limita o dano de um token vazado: usado uma vez, ele morre.
    """
    stored = await _find_refresh_token(session, raw_token)

    if stored is None or stored.revoked_at is not None:
        raise AuthError("Sessão inválida")
    if stored.expires_at <= datetime.now(UTC):
        raise AuthError("Sessão expirada")

    user = await session.get(User, stored.user_id)
    tenant = await session.get(Tenant, stored.tenant_id)
    if user is None or tenant is None or not user.is_active or not tenant.is_active:
        raise AuthError("Sessão inválida")

    stored.revoked_at = datetime.now(UTC)
    permissions = await _load_permissions(session, user.id)
    access_token, raw_refresh, expires_in = await issue_tokens(
        session, user=user, tenant=tenant, permissions=permissions
    )
    return user, tenant, permissions, access_token, raw_refresh, expires_in


async def revoke_refresh_token(session: AsyncSession, *, raw_token: str) -> None:
    stored = await _find_refresh_token(session, raw_token)
    if stored is not None and stored.revoked_at is None:
        stored.revoked_at = datetime.now(UTC)
