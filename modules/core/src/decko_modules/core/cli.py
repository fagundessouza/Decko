"""Comando administrativo do núcleo.

Cria a primeira empresa e seu usuário administrador. É o único caminho para o sistema sair
do zero: sem empresa cadastrada não há como autenticar, e a API não expõe criação de
empresa sem autenticação justamente para não deixar um cadastro aberto na internet.

Uso:

    uv run decko-admin bootstrap --tenant-name "AgroDrone" --tenant-slug agrodrone \\
        --admin-email nathan@exemplo.com.br --admin-name "Nathan Gomes"

A senha é pedida no terminal. Em execução automatizada, sem terminal para responder, ela
precisa vir em ``DECKO_ADMIN_PASSWORD`` — do contrário o comando fica esperando alguém
digitar e nunca termina.
"""

import argparse
import asyncio
import getpass
import os
import re
import sys
import unicodedata
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from decko.config import get_settings
from decko.db import SessionFactory, bind_tenant, engine
from decko.modules import discover
from decko_modules.core.activation import activate as activate_module
from decko_modules.core.models import (
    AuditLog,
    Role,
    RolePermission,
    Tenant,
    User,
    UserRole,
)
from decko_modules.core.security import hash_password

SLUG_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MIN_PASSWORD_LENGTH = 12
ADMIN_ROLE_NAME = "Administrador"
PASSWORD_ENV_VAR = "DECKO_ADMIN_PASSWORD"  # noqa: S105


class BootstrapError(Exception):
    pass


def normalize_slug(raw: str) -> str:
    """Converte o que foi digitado em um identificador válido.

    Recusar "AgroDrone" ou "Agro Drone" obrigaria a pessoa a adivinhar um formato que ela
    não tem motivo para conhecer. Normalizar e informar o resultado resolve o caso comum
    sem esconder o que foi gravado.
    """
    without_accents = (
        unicodedata.normalize("NFKD", raw.strip()).encode("ascii", "ignore").decode("ascii")
    )
    hyphenated = re.sub(r"[\s_]+", "-", without_accents.lower())
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9-]", "", hyphenated)).strip("-")


def _read_password() -> str:
    """Lê a senha do ambiente ou pergunta.

    A senha não é aceita como argumento de linha de comando de propósito: argumentos ficam
    no histórico do shell e na lista de processos da máquina.
    """
    from_env = os.environ.get(PASSWORD_ENV_VAR)
    if from_env:
        password = from_env
    else:
        if not sys.stdin.isatty():
            raise BootstrapError(
                f"Sem terminal interativo. Defina {PASSWORD_ENV_VAR} com a senha desejada."
            )
        password = getpass.getpass("Senha do administrador: ")
        if password != getpass.getpass("Repita a senha: "):
            raise BootstrapError("As senhas não conferem.")

    if len(password) < MIN_PASSWORD_LENGTH:
        raise BootstrapError(
            f"A senha precisa ter ao menos {MIN_PASSWORD_LENGTH} caracteres. "
            "Esta conta enxerga todos os dados da empresa."
        )
    return password


def _all_declared_permissions() -> list[str]:
    """Reúne as permissões declaradas nos manifestos dos módulos instalados.

    A fonte é o manifesto, e não uma lista escrita aqui: módulo novo instalado passa a ter
    suas permissões no papel de administrador sem alteração neste arquivo.
    """
    manifests = discover(get_settings().modules_dir)
    return sorted({permission for m in manifests.values() for permission in m.permissions})


async def _bootstrap(
    session: AsyncSession,
    *,
    tenant_name: str,
    tenant_slug: str,
    admin_email: str,
    admin_name: str,
    password: str,
    modules: Sequence[str] = (),
) -> tuple[Tenant, User, int]:
    if not SLUG_PATTERN.match(tenant_slug):
        raise BootstrapError(
            "O identificador da empresa deve conter apenas letras minúsculas, números e "
            "hífens (exemplo: agrodrone-jatai)."
        )

    existing = await session.scalar(select(Tenant).where(Tenant.slug == tenant_slug))
    if existing is not None:
        raise BootstrapError(f"Já existe uma empresa com o identificador '{tenant_slug}'.")

    tenant = Tenant(name=tenant_name, slug=tenant_slug)
    session.add(tenant)
    await session.flush()

    # A partir daqui as gravações são validadas contra esta empresa pelas políticas de RLS.
    await bind_tenant(session, tenant.id)

    permissions = _all_declared_permissions()
    role = Role(
        tenant_id=tenant.id,
        name=ADMIN_ROLE_NAME,
        description="Acesso total aos módulos instalados.",
    )
    session.add(role)
    await session.flush()

    for permission in permissions:
        session.add(RolePermission(tenant_id=tenant.id, role_id=role.id, permission=permission))

    user = User(
        tenant_id=tenant.id,
        email=admin_email.strip().lower(),
        full_name=admin_name,
        password_hash=hash_password(password),
    )
    session.add(user)
    await session.flush()

    session.add(UserRole(tenant_id=tenant.id, user_id=user.id, role_id=role.id))

    # A empresa nasce só com o núcleo. Módulo de segmento é contratado, não presumido —
    # ver docs/adr/0004-ativacao-de-modulo-por-empresa.md.
    for module_name in _validated_modules(modules):
        await activate_module(
            session, tenant_id=tenant.id, module_name=module_name, activated_by=user.id
        )

    session.add(
        AuditLog(
            tenant_id=tenant.id,
            user_id=user.id,
            action="tenant.bootstrap",
            entity="tenant",
            entity_id=str(tenant.id),
            data={
                "slug": tenant.slug,
                "granted_permissions": len(permissions),
                "activated_modules": list(modules),
            },
        )
    )

    return tenant, user, len(permissions)


def _validated_modules(modules: Sequence[str]) -> list[str]:
    """Confere os nomes contra os manifestos em disco.

    Ativar um módulo inexistente gravaria uma linha que nunca casaria com nada e a empresa
    ficaria sem o módulo sem nenhum aviso.
    """
    available = discover(get_settings().modules_dir)
    desconhecidos = [name for name in modules if name not in available]
    if desconhecidos:
        raise BootstrapError(
            f"Módulo não encontrado: {', '.join(desconhecidos)}. "
            f"Disponíveis: {', '.join(sorted(available))}."
        )
    # Obrigatório já vale como ativo; gravar linha para ele seria redundante.
    return [name for name in modules if not available[name].required]


async def _check_slug_available(slug: str) -> None:
    async with SessionFactory() as session, session.begin():
        taken = await session.scalar(select(Tenant).where(Tenant.slug == slug))
    if taken is not None:
        raise BootstrapError(f"Já existe uma empresa com o identificador '{slug}'.")


async def _run_bootstrap(args: argparse.Namespace) -> int:
    # Tudo o que pode ser verificado sem a senha é verificado antes de pedi-la. Pedir
    # primeiro faria a pessoa digitar a senha duas vezes para só então saber que o
    # identificador era inválido.
    try:
        slug = normalize_slug(args.tenant_slug)
        if not slug:
            raise BootstrapError(
                f"'{args.tenant_slug}' não produz um identificador válido. "
                "Use letras, números e hífens — por exemplo: agrodrone-jatai."
            )
        if slug != args.tenant_slug:
            print(f"Identificador ajustado de '{args.tenant_slug}' para '{slug}'.")

        await _check_slug_available(slug)
        password = _read_password()
    except BootstrapError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        await engine.dispose()
        return 1

    try:
        async with SessionFactory() as session, session.begin():
            tenant, user, granted = await _bootstrap(
                session,
                tenant_name=args.tenant_name,
                tenant_slug=slug,
                admin_email=args.admin_email,
                admin_name=args.admin_name,
                password=password,
                modules=args.modules,
            )
            summary = (tenant.name, tenant.slug, user.email, granted)
    except BootstrapError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1
    finally:
        await engine.dispose()

    name, slug, email, granted = summary
    print(f"Empresa criada:  {name}")
    print(f"Identificador:   {slug}   (use este valor no campo tenant_slug do login)")
    print(f"Administrador:   {email}")
    print(f"Permissões:      {granted} concedidas ao papel '{ADMIN_ROLE_NAME}'")
    return 0


async def _run_status(_: argparse.Namespace) -> int:
    try:
        async with SessionFactory() as session, session.begin():
            total = await session.scalar(select(func.count()).select_from(Tenant))
            rows = (
                await session.execute(
                    select(Tenant.name, Tenant.slug, Tenant.is_active).order_by(Tenant.created_at)
                )
            ).all()
    finally:
        await engine.dispose()

    print(f"Empresas cadastradas: {total}")
    for name, slug, is_active in rows:
        print(f"  {slug:<24} {name:<32} {'ativa' if is_active else 'inativa'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="decko-admin", description="Comandos administrativos do Decko."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    bootstrap = sub.add_parser("bootstrap", help="Cria uma empresa e seu usuário administrador.")
    bootstrap.add_argument("--tenant-name", required=True, help="Razão social ou nome fantasia.")
    bootstrap.add_argument(
        "--tenant-slug", required=True, help="Identificador curto usado no login."
    )
    bootstrap.add_argument("--admin-email", required=True)
    bootstrap.add_argument("--admin-name", required=True)
    bootstrap.add_argument(
        "--module",
        action="append",
        default=[],
        dest="modules",
        metavar="NOME",
        help="Módulo a ativar na empresa (repetível). Sem isto, só o núcleo fica ativo.",
    )
    bootstrap.set_defaults(handler=_run_bootstrap)

    status = sub.add_parser("status", help="Lista as empresas cadastradas.")
    status.set_defaults(handler=_run_status)

    args = parser.parse_args()
    started = datetime.now(UTC)
    exit_code = asyncio.run(args.handler(args))
    if exit_code == 0 and args.command == "bootstrap":
        print(f"Concluído em {(datetime.now(UTC) - started).total_seconds():.1f}s")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
