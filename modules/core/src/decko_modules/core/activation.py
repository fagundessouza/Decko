"""Quais módulos estão ativos em cada empresa.

É a implementação da porta que o host declara em ``decko/activation.py``. O host monta as
rotas e aplica a verificação; quem sabe responder é este módulo, porque é ele que conhece
a empresa autenticada e a tabela que guarda a resposta.

Decisão: ``docs/adr/0004-ativacao-de-modulo-por-empresa.md``.
"""

import uuid
from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from decko.activation import register_activation_guard
from decko.db import get_session
from decko_modules.core.deps import CurrentPrincipal
from decko_modules.core.models import TenantModule


async def is_active(session: AsyncSession, tenant_id: uuid.UUID, module_name: str) -> bool:
    found = await session.scalar(
        select(TenantModule.id).where(
            TenantModule.tenant_id == tenant_id,
            TenantModule.module_name == module_name,
        )
    )
    return found is not None


async def active_modules(session: AsyncSession, tenant_id: uuid.UUID) -> list[str]:
    result = await session.execute(
        select(TenantModule.module_name)
        .where(TenantModule.tenant_id == tenant_id)
        .order_by(TenantModule.module_name)
    )
    return list(result.scalars().all())


async def activate(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    module_name: str,
    activated_by: uuid.UUID | None = None,
) -> bool:
    """Ativa o módulo. Devolve False quando já estava ativo.

    Repetir a ativação não é erro: quem contrata duas vezes o mesmo módulo espera que
    continue funcionando, não uma falha.
    """
    if await is_active(session, tenant_id, module_name):
        return False

    session.add(
        TenantModule(tenant_id=tenant_id, module_name=module_name, activated_by=activated_by)
    )
    await session.flush()
    return True


async def deactivate(session: AsyncSession, *, tenant_id: uuid.UUID, module_name: str) -> bool:
    """Desativa o módulo. Os dados dele permanecem no banco — ver ADR 0004."""
    result = await session.execute(
        delete(TenantModule).where(
            TenantModule.tenant_id == tenant_id,
            TenantModule.module_name == module_name,
        )
    )
    return bool(result.rowcount)


def require_active_module(
    module_name: str,
) -> Callable[..., Coroutine[Any, Any, None]]:
    """Dependência que recusa a requisição quando o módulo não está ativo na empresa.

    Aplicada pelo host na montagem do router, não escrita dentro do módulo protegido.
    """

    async def dependency(
        principal: CurrentPrincipal,
        session: Annotated[AsyncSession, Depends(get_session)],
    ) -> None:
        if not await is_active(session, principal.tenant_id, module_name):
            # 404 e não 403: para quem não contratou, o módulo não faz parte do sistema.
            # 403 confirmaria a existência e revelaria a composição comercial alheia.
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"O módulo '{module_name}' não está ativo nesta empresa.",
            )

    return dependency


# Registrado na importação do módulo. O núcleo é carregado antes de qualquer outro módulo
# (é dependência obrigatória de todos), então a verificação existe quando o host monta os
# demais routers.
register_activation_guard(require_active_module)
