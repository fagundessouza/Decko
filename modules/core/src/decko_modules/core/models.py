"""Modelo de dados do núcleo: empresa, usuário, papéis e auditoria.

Toda tabela que pertence a uma empresa carrega ``tenant_id`` e tem política de Row Level
Security. A coluna existe para o banco poder filtrar — não para a aplicação lembrar de
filtrar.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from decko.db import Base, TenantMixin, TimestampMixin


class Tenant(TimestampMixin, Base):
    """Empresa cliente. Não herda TenantMixin: esta é a própria fronteira do isolamento."""

    __tablename__ = "tenant"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    cnpj: Mapped[str | None] = mapped_column(String(14), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    users: Mapped[list["User"]] = relationship(back_populates="tenant")


class User(TenantMixin, TimestampMixin, Base):
    __tablename__ = "user_account"
    __table_args__ = (
        # E-mail é único dentro da empresa, não globalmente: a mesma pessoa pode operar
        # em duas empresas diferentes com o mesmo endereço.
        UniqueConstraint("tenant_id", "email", name="uq_user_account_tenant_id_email"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tenant: Mapped["Tenant"] = relationship(back_populates="users")
    roles: Mapped[list["Role"]] = relationship(secondary="user_role", back_populates="users")


class Role(TenantMixin, TimestampMixin, Base):
    __tablename__ = "role"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_role_tenant_id_name"),)

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(String(300), nullable=True)

    users: Mapped[list["User"]] = relationship(secondary="user_role", back_populates="roles")
    permissions: Mapped[list["RolePermission"]] = relationship(
        back_populates="role", cascade="all, delete-orphan"
    )


class RolePermission(TenantMixin, Base):
    """Permissão concedida a um papel.

    A permissão é guardada como texto (ex.: ``agro.plan.create``) e não como chave
    estrangeira: quem declara as permissões existentes é o manifesto do módulo, então uma
    tabela de permissões no banco sairia de sincronia com os módulos instalados.
    """

    __tablename__ = "role_permission"
    __table_args__ = (
        UniqueConstraint("role_id", "permission", name="uq_role_permission_role_id_permission"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("role.id", ondelete="CASCADE"), nullable=False
    )
    permission: Mapped[str] = mapped_column(String(120), nullable=False)

    role: Mapped["Role"] = relationship(back_populates="permissions")


class UserRole(TenantMixin, Base):
    __tablename__ = "user_role"
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_role_user_id_role_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("role.id", ondelete="CASCADE"), nullable=False
    )


class RefreshToken(TenantMixin, Base):
    """Refresh token revogável.

    Guardado no PostgreSQL e não em cache: a revogação precisa sobreviver a reinício e a
    perda de cache, senão um token revogado volta a valer. Só o hash é persistido, para
    que o vazamento da tabela não entregue tokens utilizáveis.
    """

    __tablename__ = "refresh_token"
    __table_args__ = (Index("ix_refresh_token_user_id_expires_at", "user_id", "expires_at"),)

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditLog(TenantMixin, Base):
    """Trilha de auditoria. Só recebe inserção: não há atualização nem exclusão.

    Exigida pela LGPD e pela natureza regulada do domínio — um relatório com efeito legal
    precisa de histórico de quem alterou o quê.
    """

    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_tenant_id_created_at", "tenant_id", "created_at"),
        Index("ix_audit_log_entity_entity_id", "entity", "entity_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("user_account.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    data: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# Tabelas sujeitas a Row Level Security. A migração lê esta lista, de modo que uma tabela
# nova com tenant_id não pode ser esquecida sem que o teste de isolamento acuse.
TENANT_SCOPED_TABLES = (
    User.__tablename__,
    Role.__tablename__,
    RolePermission.__tablename__,
    UserRole.__tablename__,
    RefreshToken.__tablename__,
    AuditLog.__tablename__,
)
