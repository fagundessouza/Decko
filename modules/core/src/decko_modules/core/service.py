"""Regra de negócio de autenticação e sessão. Não conhece HTTP."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from decko.config import get_settings
from decko.db import SessionFactory, bind_tenant
from decko.modules import discover
from decko_modules.core import security
from decko_modules.core.breach import recusar_se_vazada
from decko_modules.core.models import (
    Lead,
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


async def permissoes_de(session: AsyncSession, user_id: uuid.UUID) -> set[str]:
    """O que esta pessoa pode, somando os papéis dela.

    Público porque outro módulo precisa: o PDV confere, no ato, se quem está liberando uma
    ação realmente pode liberá-la — e não dá para confiar no token de quem **pediu** a
    liberação. Ver ``docs/adr/0020-operador-supervisor-e-papeis.md``, decisão 4.
    """
    return set(await _load_permissions(session, user_id))


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
        await security.verify_password_async(password, _DUMMY_HASH)
        raise AuthError

    # A partir daqui as consultas enxergam apenas esta empresa.
    await bind_tenant(session, tenant.id)

    user = await session.scalar(select(User).where(User.email == email))
    if user is None:
        await security.verify_password_async(password, _DUMMY_HASH)
        # Sem ``user_id``: não há conta, e o e-mail digitado não entra na trilha.
        raise AuthError(tenant_id=tenant.id, motivo="usuario_desconhecido")

    if not await security.verify_password_async(password, user.password_hash):
        raise AuthError(tenant_id=tenant.id, user_id=user.id, motivo="senha")

    if not user.is_active:
        raise AuthError(
            "Usuário desativado",
            tenant_id=tenant.id,
            user_id=user.id,
            motivo="usuario_inativo",
        )

    if security.needs_rehash(user.password_hash):
        user.password_hash = await security.hash_password_async(password)

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

    O dono precisa ver o que está dando antes de dar — e desde 13/11/2026 também monta e
    ajusta papel, não só escolhe entre os semeados.
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
        password_hash=await security.hash_password_async(senha_inicial),
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
    if not await security.verify_password_async(senha_atual, user.password_hash):
        raise EquipeError("A senha atual não confere.")
    if nova_senha == senha_atual:
        raise EquipeError("A senha nova precisa ser diferente da atual.")

    await recusar_se_vazada(nova_senha, habilitada=breach_check)

    user.password_hash = await security.hash_password_async(nova_senha)
    user.must_change_password = False
    await session.flush()
    return user


# ------------------------------------------------------------------- entrada rápida
#
# O crachá identifica; o PIN autentica. Decisão e motivos:
# docs/adr/0020-operador-supervisor-e-papeis.md, decisão 1.

PIN_MIN = 4
PIN_MAX = 8

# Cinco tentativas e cinco minutos de espera. PIN curto só se sustenta com bloqueio: sem
# ele, quem ficar sozinho com a estação percorre dez mil combinações sem pressa. Cinco é
# folgado para quem erra de dedo e inútil para quem está tentando adivinhar.
PIN_TENTATIVAS = 5
PIN_BLOQUEIO = timedelta(minutes=5)


def _pin_bem_formado(pin: str) -> str:
    """Só dígitos, de 4 a 8. É o formato do teclado numérico do balcão."""
    limpo = pin.strip()
    if not limpo.isdigit() or not (PIN_MIN <= len(limpo) <= PIN_MAX):
        raise EquipeError(f"O PIN é só de números, de {PIN_MIN} a {PIN_MAX} dígitos.")
    return limpo


async def definir_pin(session: AsyncSession, *, user: User, senha: str, pin: str) -> User:
    """A pessoa define o próprio PIN, confirmando com a senha dela.

    Confirmar com a senha é o que mantém o PIN **dela**: sem isso, um terminal deixado
    aberto no balcão permitiria a qualquer um gravar um PIN próprio na conta alheia e
    voltar nela quando quisesse.
    """
    if not await security.verify_password_async(senha, user.password_hash):
        raise EquipeError("A senha não confere.")

    user.pin_hash = await security.hash_password_async(_pin_bem_formado(pin))
    user.pin_tentativas = 0
    user.pin_bloqueado_ate = None
    await session.flush()
    return user


async def remover_pin(session: AsyncSession, *, user: User) -> User:
    """Tira o PIN de alguém. É o caminho de quem esqueceu — a senha continua valendo."""
    user.pin_hash = None
    user.pin_tentativas = 0
    user.pin_bloqueado_ate = None
    await session.flush()
    return user


async def definir_cracha(session: AsyncSession, *, user: User, cracha: str | None) -> User:
    """O dono emite o crachá: é um cartão da loja, não uma escolha de quem o usa.

    Vazio apaga. A unicidade por empresa é do banco — dois crachás iguais tornariam a
    leitura ambígua, e validar só aqui deixaria passar duas emissões simultâneas.
    """
    codigo = (cracha or "").strip() or None
    if codigo is not None and len(codigo) > 60:
        raise EquipeError("O código do crachá é longo demais.")

    user.cracha = codigo
    await session.flush()
    return user


async def _penalizar_pin(*, tenant_id: uuid.UUID, user_id: uuid.UUID) -> None:
    """Conta a tentativa errada **em transação própria**, e bloqueia ao chegar no limite.

    Em transação própria pelo mesmo motivo da trilha de falha: a requisição vai levantar,
    e a sessão dela desfaz tudo ao fazê-lo — inclusive o contador. Guardado junto, o
    bloqueio nunca chegaria a existir, e cinco tentativas virariam infinitas.
    """
    async with SessionFactory() as session, session.begin():
        await bind_tenant(session, tenant_id)
        user = await session.get(User, user_id)
        if user is None:  # pragma: no cover - acabou de ser lido
            return

        user.pin_tentativas += 1
        if user.pin_tentativas >= PIN_TENTATIVAS:
            user.pin_bloqueado_ate = datetime.now(UTC) + PIN_BLOQUEIO
            user.pin_tentativas = 0


async def conferir_pin(session: AsyncSession, *, user: User, pin: str) -> None:
    """Confere o PIN e cuida do bloqueio. Levanta ``AuthError`` quando não serve.

    Vive aqui, e não em cada chamador, porque o PDV também confere PIN — na liberação do
    supervisor. Dois caminhos para o mesmo segredo com contagens separadas dariam a quem
    adivinha o dobro de tentativas.
    """
    agora = datetime.now(UTC)

    if user.pin_hash is None:
        raise AuthError(
            "Esta pessoa ainda não tem PIN.",
            tenant_id=user.tenant_id,
            user_id=user.id,
            motivo="pin_ausente",
        )

    if user.pin_bloqueado_ate is not None and user.pin_bloqueado_ate > agora:
        faltam = max(1, int((user.pin_bloqueado_ate - agora).total_seconds() // 60) + 1)
        raise AuthError(
            f"PIN bloqueado por tentativas erradas. Tente em {faltam} min, ou use a senha.",
            tenant_id=user.tenant_id,
            user_id=user.id,
            motivo="pin_bloqueado",
        )

    if not await security.verify_password_async(pin, user.pin_hash):
        await _penalizar_pin(tenant_id=user.tenant_id, user_id=user.id)
        raise AuthError(
            "PIN incorreto.",
            tenant_id=user.tenant_id,
            user_id=user.id,
            motivo="pin_errado",
        )

    user.pin_tentativas = 0
    user.pin_bloqueado_ate = None


async def entrar_por_pin(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    pin: str,
    user_id: uuid.UUID | None = None,
    cracha: str | None = None,
) -> tuple[User, Tenant, list[str]]:
    """Troca de operador na estação: quem é vem do nome escolhido ou do crachá lido.

    **Só funciona a partir de uma estação já autenticada nesta empresa** — quem chama já
    passou por um login completo. É esse login que diz "este aparelho é da loja"; o PIN
    diz apenas qual pessoa está nele agora. Sem essa âncora, um PIN de quatro dígitos
    seria a porta da frente.
    """
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None or not tenant.is_active:  # pragma: no cover - a sessão já valida
        raise AuthError

    if user_id is not None:
        user = await session.get(User, user_id)
        if user is not None and user.tenant_id != tenant_id:
            user = None
    elif cracha is not None and cracha.strip():
        user = await session.scalar(select(User).where(User.cracha == cracha.strip()))
    else:
        raise EquipeError("Diga quem está entrando: escolha o nome ou passe o crachá.")

    if user is None:
        # Sem ``user_id``: crachá desconhecido é palpite de quem sonda, e guardá-lo
        # encheria a trilha sem responder nada.
        raise AuthError(
            "Crachá não reconhecido.", tenant_id=tenant_id, motivo="cracha_desconhecido"
        )

    if not user.is_active:
        raise AuthError(
            "Usuário desativado",
            tenant_id=tenant_id,
            user_id=user.id,
            motivo="usuario_inativo",
        )

    await conferir_pin(session, user=user, pin=pin)

    user.last_login_at = datetime.now(UTC)
    return user, tenant, await _load_permissions(session, user.id)


# ----------------------------------------------------------------- montar papel
#
# Até 13/11/2026 o dono **escolhia** entre os papéis semeados pelos manifestos. Escolher
# cobre o caso comum e é o que o Odoo tem nativamente, mas não é "controle do que o
# operador pode fazer" — loja que quer um operador que devolve, ou um supervisor que não
# fecha, precisa montar o papel dela. Ver docs/adr/0020-operador-supervisor-e-papeis.md.

# As permissões sem as quais a empresa fica sem dono: quem as tem administra gente e
# papel. Se a última pessoa que as tem perdê-las, não há caminho de volta pela interface.
PERMISSOES_DE_DONO = ("core.user.read", "core.role.write")


async def _quem_ainda_administra(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    """Quantas pessoas ativas ainda conseguem administrar gente e papel nesta empresa."""
    linhas = (
        await session.execute(
            select(User.id)
            .join(UserRole, UserRole.user_id == User.id)
            .join(RolePermission, RolePermission.role_id == UserRole.role_id)
            .where(
                User.tenant_id == tenant_id,
                User.is_active.is_(True),
                RolePermission.permission.in_(PERMISSOES_DE_DONO),
            )
            .group_by(User.id)
            .having(func.count(RolePermission.permission.distinct()) == len(PERMISSOES_DE_DONO))
        )
    ).all()
    return len(linhas)


async def _recusar_empresa_sem_dono(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Depois de mexer em papel, confere se ainda há quem administre.

    É a única trava desta área, e ela é sobre a empresa, não sobre quem está pedindo:
    proibir alguém de editar o próprio papel resolveria o caso mais óbvio e deixaria
    passar o de tirar a permissão do colega que era o outro administrador.

    A conferência roda **depois** da alteração, dentro da mesma transação: é o estado
    final que importa, e desfazer é o que a transação faz de graça.
    """
    if await _quem_ainda_administra(session, tenant_id) == 0:
        raise EquipeError(
            "Isto deixaria a empresa sem ninguém que administre gente e papel. "
            "Dê a permissão a outra pessoa antes."
        )


def _permissoes_declaradas(ativos: Sequence[str]) -> set[str]:
    """O que os módulos ativos declaram. É a lista que um papel pode conceder.

    A fonte é o manifesto, como em todo o resto: conceder permissão de módulo que a
    empresa não tem entraria no papel sem levar a lugar nenhum, e conceder permissão
    inventada entraria sem nunca casar com rota nenhuma.
    """
    manifests = discover(get_settings().modules_dir)
    return {
        permissao
        for nome, manifest in manifests.items()
        # O núcleo entra sempre: ele não aparece em `tenant_module` porque é obrigatório.
        if nome in ativos or nome == "core"
        for permissao in manifest.permissions
    }


async def criar_papel(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    nome: str,
    descricao: str | None,
    permissoes: Sequence[str],
    ativos: Sequence[str],
) -> Role:
    titulo = nome.strip()
    if not titulo:
        raise EquipeError("Dê um nome ao papel.")

    ja_existe = await session.scalar(
        select(Role.id).where(Role.tenant_id == tenant_id, Role.name == titulo)
    )
    if ja_existe is not None:
        raise EquipeError(f"Já existe um papel chamado '{titulo}'.")

    papel = Role(tenant_id=tenant_id, name=titulo, description=(descricao or "").strip() or None)
    session.add(papel)
    await session.flush()

    await _trocar_permissoes(session, papel=papel, permissoes=permissoes, ativos=ativos)
    return papel


async def editar_papel(
    session: AsyncSession,
    *,
    papel: Role,
    nome: str,
    descricao: str | None,
    permissoes: Sequence[str],
    ativos: Sequence[str],
) -> Role:
    titulo = nome.strip()
    if not titulo:
        raise EquipeError("Dê um nome ao papel.")

    conflito = await session.scalar(
        select(Role.id).where(
            Role.tenant_id == papel.tenant_id, Role.name == titulo, Role.id != papel.id
        )
    )
    if conflito is not None:
        raise EquipeError(f"Já existe um papel chamado '{titulo}'.")

    papel.name = titulo
    papel.description = (descricao or "").strip() or None
    await _trocar_permissoes(session, papel=papel, permissoes=permissoes, ativos=ativos)
    await _recusar_empresa_sem_dono(session, papel.tenant_id)
    return papel


async def _trocar_permissoes(
    session: AsyncSession, *, papel: Role, permissoes: Sequence[str], ativos: Sequence[str]
) -> None:
    """Substitui o conjunto: a tela mostra tudo, e quem desmarca espera que saia."""
    declaradas = _permissoes_declaradas(ativos)
    pedidas = set(permissoes)

    desconhecidas = sorted(pedidas - declaradas)
    if desconhecidas:
        raise EquipeError(f"Permissão que nenhum módulo ativo declara: {', '.join(desconhecidas)}.")

    await session.execute(delete(RolePermission).where(RolePermission.role_id == papel.id))
    for permissao in sorted(pedidas):
        session.add(
            RolePermission(tenant_id=papel.tenant_id, role_id=papel.id, permission=permissao)
        )
    await session.flush()


async def apagar_papel(session: AsyncSession, *, papel: Role) -> None:
    """Apaga um papel que ninguém tem.

    Com gente dentro, apagar tiraria o acesso de alguém por um caminho que não se parece
    com isso — tirar acesso é na tela da pessoa, dito com o nome dela.
    """
    em_uso = await session.scalar(
        select(func.count(UserRole.id)).where(UserRole.role_id == papel.id)
    )
    if em_uso:
        raise EquipeError(
            f"{em_uso} pessoa(s) ainda têm este papel. Troque o papel delas primeiro."
        )

    await session.delete(papel)
    await session.flush()
    await _recusar_empresa_sem_dono(session, papel.tenant_id)


# ------------------------------------------------------------- lead da página pública

#: Quantos pedidos de contato o mesmo IP pode mandar por hora.
#:
#: Dez é folgado para gente e apertado para robô. O formulário é a porta mais aberta do
#: sistema — sem login, por definição —, e sem um teto ele vira caixa de entrada de spam
#: na primeira varredura automática que encontrar a página.
LEADS_POR_HORA = 10

#: Por quanto tempo o IP de quem pediu contato fica guardado.
#:
#: Ele serve só para conter enxurrada. Guardar além disso seria guardar rastro de gente
#: sem motivo — e motivo é o que a LGPD cobra.
DIAS_DE_IP = 60


class LeadError(Exception):
    """Pedido de contato recusado. Vira 422 na borda."""


async def registrar_lead(
    session: AsyncSession,
    *,
    dados: dict[str, Any],
    ip: str | None,
) -> Lead:
    """Guarda um pedido de contato vindo da página pública.

    Duas defesas, e nenhuma delas é CAPTCHA — que empurra o custo do nosso spam para a
    paciência de quem quer falar com a gente:

    - **Teto por IP e por hora.** Gente não manda dez pedidos numa hora; robô manda mil.
    - **Campo-armadilha**, conferido na borda: o formulário tem um campo invisível que
      pessoa nenhuma preenche e preenchedor automático preenche sempre.

    O consentimento é gravado com a hora porque é ele que autoriza o contato depois.
    """
    if ip is not None:
        desde = datetime.now(UTC) - timedelta(hours=1)
        quantos = await session.scalar(
            select(func.count())
            .select_from(Lead)
            .where(Lead.ip == ip, Lead.created_at >= desde)
        )
        if (quantos or 0) >= LEADS_POR_HORA:
            raise LeadError(
                "Recebemos vários pedidos deste mesmo lugar na última hora. "
                "Se foi você, aguarde um pouco ou escreva direto para a gente."
            )

    lead = Lead(**dados, ip=ip, consentimento_em=datetime.now(UTC))
    session.add(lead)
    await session.flush()
    return lead


async def esquecer_ip_antigo(session: AsyncSession) -> int:
    """Apaga o IP dos pedidos velhos, mantendo o pedido.

    O IP serve para conter robô na hora; depois, é rastro de gente guardado sem motivo. O
    lead continua inteiro — quem pediu contato continua tendo pedido contato.
    """
    corte = datetime.now(UTC) - timedelta(days=DIAS_DE_IP)
    resultado = await session.execute(
        update(Lead)
        .where(Lead.ip.is_not(None), Lead.created_at < corte)
        .values(ip=None)
    )
    return resultado.rowcount or 0
