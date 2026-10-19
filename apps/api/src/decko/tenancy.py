"""Tenant em escopo de requisição.

O identificador do tenant vive em um ContextVar e é aplicado na sessão de banco como um
parâmetro de configuração do PostgreSQL. As políticas de Row Level Security leem esse
parâmetro, de modo que o isolamento é imposto pelo banco e não pela disciplina de quem
escreve a consulta.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from uuid import UUID

# Nome do parâmetro lido pelas políticas de RLS. Alterar aqui exige alterar as migrações.
TENANT_GUC = "decko.tenant_id"

_current_tenant: ContextVar[UUID | None] = ContextVar("decko_current_tenant", default=None)


def get_current_tenant() -> UUID | None:
    return _current_tenant.get()


def set_current_tenant(tenant_id: UUID | None) -> Token[UUID | None]:
    return _current_tenant.set(tenant_id)


def reset_current_tenant(token: Token[UUID | None]) -> None:
    _current_tenant.reset(token)


@contextmanager
def tenant_scope(tenant_id: UUID | None) -> Iterator[None]:
    token = set_current_tenant(tenant_id)
    try:
        yield
    finally:
        reset_current_tenant(token)
