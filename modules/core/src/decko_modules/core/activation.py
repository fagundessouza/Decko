"""Quais módulos estão ativos em cada empresa.

É a implementação da porta que o host declara em ``decko/activation.py``. O host monta as
rotas e aplica a verificação; quem sabe responder é este módulo, porque é ele que conhece
a empresa autenticada e a tabela que guarda a resposta.

Decisão: ``docs/adr/0004-ativacao-de-modulo-por-empresa.md``.
"""

import uuid
from collections.abc import Callable, Coroutine, Mapping, Sequence
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from decko.activation import register_activation_guard, register_permission_reconciler
from decko.config import get_settings
from decko.db import SessionFactory, bind_tenant, get_session
from decko.modules import discover
from decko.seed import apply_seed
from decko_modules.core.deps import CurrentPrincipal
from decko_modules.core.models import Role, RolePermission, Tenant, TenantModule


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


# O papel criado no bootstrap, que recebe as permissões dos módulos instalados. Fica aqui,
# e não no comando de bootstrap, porque quem precisa dele também é a ativação — e o
# comando já importa deste arquivo.
ADMIN_ROLE_NAME = "Administrador"


async def grant_module_permissions(
    session: AsyncSession, *, tenant_id: uuid.UUID, permissions: Sequence[str]
) -> list[str]:
    """Concede ao administrador da empresa as permissões de um módulo recém-instalado.

    Sem isto, instalar um módulo depois do cadastro da empresa deixava as telas dele
    inalcançáveis: o papel de administrador é montado no bootstrap a partir dos módulos
    que existiam naquele momento, e um módulo instalado depois não entrava em papel nenhum.

    Concede só o que falta, então reinstalar não duplica. Papéis que o cliente tenha
    criado não são tocados: o que o operador de caixa pode fazer é decisão da empresa.
    """
    if not permissions:
        return []

    role = await session.scalar(
        select(Role).where(Role.tenant_id == tenant_id, Role.name == ADMIN_ROLE_NAME)
    )
    if role is None:
        # Empresa sem o papel padrão (renomeado ou removido). Não há o que supor aqui.
        return []

    ja_tem = set(
        (
            await session.execute(
                select(RolePermission.permission).where(RolePermission.role_id == role.id)
            )
        )
        .scalars()
        .all()
    )

    concedidas = sorted(set(permissions) - ja_tem)
    for permission in concedidas:
        session.add(RolePermission(tenant_id=tenant_id, role_id=role.id, permission=permission))
    if concedidas:
        await session.flush()
    return concedidas


async def garantir_papeis_sugeridos(
    session: AsyncSession, *, tenant_id: uuid.UUID, ativos: Sequence[str]
) -> list[str]:
    """Cria os papéis que os módulos ativos sugerem e que a empresa ainda não tem.

    **Cria o que falta e não toca no que existe.** Um papel que a loja já ajustou não pode
    ser desfeito pela subida seguinte da aplicação — semente é ponto de partida, não
    configuração imposta para sempre (ADR 0010, e decisão 3 da ADR 0020). É a mesma regra
    que ``grant_module_permissions`` já segue para papéis do cliente.

    Só concede permissão declarada por módulo que a empresa tem ativo: um papel que cita
    ``clientes.cliente.read`` numa empresa sem o módulo `clientes` entraria com uma
    permissão que não leva a lugar nenhum.
    """
    manifests = discover(get_settings().modules_dir)
    # O núcleo entra sempre: ele não aparece em `tenant_module` porque é obrigatório.
    presentes = {nome for nome in manifests if nome in ativos or nome == "core"}

    declaradas = {permissao for nome in presentes for permissao in manifests[nome].permissions}

    existentes = set(
        (await session.execute(select(Role.name).where(Role.tenant_id == tenant_id)))
        .scalars()
        .all()
    )

    criados: list[str] = []
    for nome in sorted(presentes):
        for papel in manifests[nome].roles:
            if papel.name in existentes:
                continue

            role = Role(tenant_id=tenant_id, name=papel.name, description=papel.description or None)
            session.add(role)
            await session.flush()

            for permissao in sorted(set(papel.grants) & declaradas):
                session.add(
                    RolePermission(tenant_id=tenant_id, role_id=role.id, permission=permissao)
                )

            existentes.add(papel.name)
            criados.append(papel.name)

    if criados:
        await session.flush()
    return criados


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

    É aqui que a semente do módulo entra, e não em cada chamador: contratar por perfil,
    contratar módulo avulso e cadastrar empresa pelo comando passam todos por esta
    função, e repetir a carga em três lugares é como um deles fica para trás.
    """
    if await is_active(session, tenant_id, module_name):
        return False

    session.add(
        TenantModule(tenant_id=tenant_id, module_name=module_name, activated_by=activated_by)
    )
    await session.flush()

    # A semente é do módulo, escrita pelo serviço dele. O núcleo só dispara — ver
    # docs/adr/0010-dado-semente-com-identidade-estavel.md.
    await apply_seed(session, module_name=module_name, tenant_id=tenant_id)

    # Os papéis que o módulo sugere entram junto, para a empresa não precisar esperar a
    # próxima subida da aplicação só para ter um papel de operador.
    await garantir_papeis_sugeridos(
        session, tenant_id=tenant_id, ativos=await active_modules(session, tenant_id)
    )
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


async def reconciliar_permissoes(declaradas: Mapping[str, Sequence[str]]) -> int:
    """Acerta o papel de administrador de cada empresa com os módulos que ela tem ativos.

    Roda na subida da aplicação. Concede só o que falta, e só de módulo que a empresa já
    tem ativo — não é aqui que se instala nada. Papéis que o cliente tenha criado não são
    tocados.

    O caso que isto resolve: o módulo ganha uma permissão numa versão nova, e quem já o
    usava não a recebe por caminho nenhum, porque conceder na instalação só alcança quem
    instalar depois.
    """
    concedidas = 0
    async with SessionFactory() as session, session.begin():
        empresas = list((await session.execute(select(Tenant.id))).scalars().all())

        for tenant_id in empresas:
            await bind_tenant(session, tenant_id)
            ativos = await active_modules(session, tenant_id)

            permissoes = [
                permissao
                for nome, lista in declaradas.items()
                # O núcleo entra sempre: ele não aparece em tenant_module porque é
                # obrigatório, e a ausência de linha ali significa "inativo".
                if nome in ativos or nome == "core"
                for permissao in lista
            ]
            concedidas += len(
                await grant_module_permissions(session, tenant_id=tenant_id, permissions=permissoes)
            )
            # Alcança quem já usava o módulo antes de ele passar a sugerir papéis. Pelo
            # mesmo motivo do reconciliador: conceder só na instalação não alcança
            # ninguém que já tinha instalado.
            await garantir_papeis_sugeridos(session, tenant_id=tenant_id, ativos=ativos)

    return concedidas


# Registrado na importação do módulo. O núcleo é carregado antes de qualquer outro módulo
# (é dependência obrigatória de todos), então a verificação existe quando o host monta os
# demais routers.
register_activation_guard(require_active_module)
register_permission_reconciler(reconciliar_permissoes)
