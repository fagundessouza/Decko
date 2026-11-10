"""Regra de negócio de autenticação e sessão. Não conhece HTTP."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from decko.config import get_settings
from decko.db import bind_tenant
from decko_modules.core import security
from decko_modules.core.breach import recusar_se_vazada
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

    O contexto carregado aqui **não** vai para a resposta: serve para a trilha de auditoria
    saber a qual empresa e a qual conta prender a tentativa. Sem isso, quem registra
    precisaria repetir a consulta que acabou de falhar, ou a trilha diria apenas "alguém
    errou", que não serve para investigar nada. O ``motivo`` é vocabulário interno, nunca
    texto para quem chamou.
    """

    def __init__(
        self,
        message: str = "Credenciais inválidas",
        *,
        tenant_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        motivo: str | None = None,
    ) -> None:
        super().__init__(message)
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.motivo = motivo


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
        # Sem ``user_id``: não há conta, e o e-mail digitado não entra na trilha.
        raise AuthError(tenant_id=tenant.id, motivo="usuario_desconhecido")

    if not security.verify_password(password, user.password_hash):
        raise AuthError(tenant_id=tenant.id, user_id=user.id, motivo="senha")

    if not user.is_active:
        raise AuthError(
            "Usuário desativado",
            tenant_id=tenant.id,
            user_id=user.id,
            motivo="usuario_inativo",
        )

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

    if stored is None:
        raise AuthError("Sessão inválida")
    if stored.revoked_at is not None:
        # Token que já morreu sendo apresentado de novo. A rotação garante que o legítimo
        # só é usado uma vez, então reapresentar é cópia em circulação — e é o único
        # evento desta rota que vale registrar. Renovação que dá certo acontece a cada
        # poucos minutos por sessão e afogaria a trilha sem dizer nada que o login já não
        # disse.
        raise AuthError(
            "Sessão inválida",
            tenant_id=stored.tenant_id,
            user_id=stored.user_id,
            motivo="token_reutilizado",
        )
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


async def revoke_refresh_token(
    session: AsyncSession, *, raw_token: str
) -> tuple[uuid.UUID, uuid.UUID] | None:
    """Encerra a sessão. Devolve a empresa e o usuário quando havia o que encerrar.

    Devolve em vez de ficar calada porque a trilha precisa saber quem saiu, e só aqui se
    descobre: o token vem cru, e quem o resolve é esta função. Sair com token já revogado
    ou inválido continua devolvendo ``None`` — não aconteceu nada para registrar.
    """
    stored = await _find_refresh_token(session, raw_token)
    if stored is None or stored.revoked_at is not None:
        return None

    stored.revoked_at = datetime.now(UTC)
    return stored.tenant_id, stored.user_id


# ----------------------------------------------------------------------- equipe da loja
#
# O dono da loja administra a própria equipe. Até 10/11/2026 as permissões `core.user.*` e
# `core.role.*` existiam no manifesto e não tinham rota nenhuma por trás: só o comando
# `decko-admin bootstrap` criava gente. Ver docs/adr/0020-operador-supervisor-e-papeis.md.


class EquipeError(Exception):
    """Erro de regra ao administrar usuário ou papel. Vira 422 na borda."""


@dataclass(frozen=True)
class Membro:
    """Um usuário da empresa com os papéis dele, para listagem."""

    user: User
    papeis: list[Role]


async def listar_membros(session: AsyncSession, tenant_id: uuid.UUID) -> list[Membro]:
    """Todos os usuários da empresa, com os papéis de cada um.

    Duas consultas, e não uma por usuário: a lista da equipe é das poucas telas que uma
    loja abre com dez linhas e um PC antigo, e N+1 aqui aparece.
    """
    usuarios = list(
        (
            await session.execute(
                select(User).where(User.tenant_id == tenant_id).order_by(User.full_name)
            )
        )
        .scalars()
        .all()
    )
    if not usuarios:
        return []

    vinculos = (
        await session.execute(
            select(UserRole.user_id, Role)
            .join(Role, Role.id == UserRole.role_id)
            .where(UserRole.user_id.in_([u.id for u in usuarios]))
            .order_by(Role.name)
        )
    ).all()

    por_usuario: dict[uuid.UUID, list[Role]] = {}
    for user_id, role in vinculos:
        por_usuario.setdefault(user_id, []).append(role)

    return [Membro(user=u, papeis=por_usuario.get(u.id, [])) for u in usuarios]


@dataclass(frozen=True)
class PapelComPermissoes:
    papel: Role
    permissoes: list[str]


async def listar_papeis(session: AsyncSession, tenant_id: uuid.UUID) -> list[PapelComPermissoes]:
    """Os papéis da empresa e o que cada um concede.

    O dono precisa ver o que está dando antes de dar. Nesta versão ele **escolhe** entre os
    papéis existentes; montar um do zero é o passo seguinte — ADR 0020.
    """
    papeis = list(
        (await session.execute(select(Role).where(Role.tenant_id == tenant_id).order_by(Role.name)))
        .scalars()
        .all()
    )
    if not papeis:
        return []

    linhas = (
        await session.execute(
            select(RolePermission.role_id, RolePermission.permission)
            .where(RolePermission.role_id.in_([p.id for p in papeis]))
            .order_by(RolePermission.permission)
        )
    ).all()

    por_papel: dict[uuid.UUID, list[str]] = {}
    for role_id, permissao in linhas:
        por_papel.setdefault(role_id, []).append(permissao)

    return [PapelComPermissoes(papel=p, permissoes=por_papel.get(p.id, [])) for p in papeis]


async def _papeis_da_empresa(
    session: AsyncSession, *, tenant_id: uuid.UUID, role_ids: Sequence[uuid.UUID]
) -> list[Role]:
    if not role_ids:
        return []

    achados = list(
        (
            await session.execute(
                select(Role).where(Role.tenant_id == tenant_id, Role.id.in_(set(role_ids)))
            )
        )
        .scalars()
        .all()
    )
    if len(achados) != len(set(role_ids)):
        # Papel de outra empresa nunca chega aqui — a RLS já o esconde —, então isto é
        # id inexistente ou digitado errado, e dizer "não encontrado" é a verdade.
        raise EquipeError("Papel não encontrado nesta empresa.")
    return achados


async def criar_membro(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    email: str,
    full_name: str,
    senha_inicial: str,
    role_ids: Sequence[uuid.UUID],
    breach_check: bool,
) -> User:
    """Cria o usuário com senha inicial, que ele será obrigado a trocar ao entrar.

    A conferência de senha vazada vale aqui pelo mesmo motivo que vale no cadastro da
    empresa: senha que já vazou é adivinhada em segundos, e a do operador abre o caixa.
    """
    endereco = email.strip().lower()
    nome = full_name.strip()
    if not nome:
        raise EquipeError("Diga o nome de quem vai usar.")

    ja_existe = await session.scalar(
        select(User.id).where(User.tenant_id == tenant_id, User.email == endereco)
    )
    if ja_existe is not None:
        raise EquipeError(f"Já existe alguém com o e-mail {endereco} nesta empresa.")

    papeis = await _papeis_da_empresa(session, tenant_id=tenant_id, role_ids=role_ids)
    await recusar_se_vazada(senha_inicial, habilitada=breach_check)

    user = User(
        tenant_id=tenant_id,
        email=endereco,
        full_name=nome,
        password_hash=security.hash_password(senha_inicial),
        must_change_password=True,
    )
    session.add(user)
    await session.flush()

    for papel in papeis:
        session.add(UserRole(tenant_id=tenant_id, user_id=user.id, role_id=papel.id))
    await session.flush()
    return user


async def definir_papeis(
    session: AsyncSession, *, user: User, role_ids: Sequence[uuid.UUID]
) -> list[Role]:
    """Troca os papéis da pessoa pelos informados.

    Substitui em vez de acrescentar: a tela mostra o conjunto inteiro, e quem tira uma
    marcação espera que ela saia.
    """
    papeis = await _papeis_da_empresa(session, tenant_id=user.tenant_id, role_ids=role_ids)

    await session.execute(delete(UserRole).where(UserRole.user_id == user.id))
    for papel in papeis:
        session.add(UserRole(tenant_id=user.tenant_id, user_id=user.id, role_id=papel.id))
    await session.flush()
    return papeis


async def definir_situacao(session: AsyncSession, *, user: User, ativo: bool) -> User:
    """Liga ou desliga o acesso da pessoa. O que ela fez continua no histórico."""
    user.is_active = ativo
    await session.flush()
    return user


async def renomear_membro(session: AsyncSession, *, user: User, full_name: str) -> User:
    nome = full_name.strip()
    if not nome:
        raise EquipeError("Diga o nome de quem vai usar.")
    user.full_name = nome
    await session.flush()
    return user


async def trocar_senha(
    session: AsyncSession, *, user: User, senha_atual: str, nova_senha: str, breach_check: bool
) -> User:
    """Troca a senha de quem está pedindo, conferindo a atual.

    Conferir a atual mesmo quando a troca é obrigatória: sem isso, um terminal deixado
    aberto no balcão permitiria a qualquer um tomar a conta do operador.
    """
    if not security.verify_password(senha_atual, user.password_hash):
        raise EquipeError("A senha atual não confere.")
    if nova_senha == senha_atual:
        raise EquipeError("A senha nova precisa ser diferente da atual.")

    await recusar_se_vazada(nova_senha, habilitada=breach_check)

    user.password_hash = security.hash_password(nova_senha)
    user.must_change_password = False
    await session.flush()
    return user
