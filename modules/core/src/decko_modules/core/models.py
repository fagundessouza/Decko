"""Modelo de dados do núcleo: empresa, usuário, papéis e auditoria.

Toda tabela que pertence a uma empresa carrega ``tenant_id`` e tem política de Row Level
Security. A coluna existe para o banco poder filtrar — não para a aplicação lembrar de
filtrar.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
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
    # Guardado sem máscara e conferido pelo dígito verificador na entrada — ver
    # decko.documents. Catorze posições servem tanto ao CNPJ numérico quanto ao
    # alfanumérico, que manteve o tamanho.
    cnpj: Mapped[str | None] = mapped_column(String(14), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Identificação da empresa aplicadora no cabeçalho do Planejamento Operacional.
    # São registros profissionais e fiscais que o formulário exige impressos; sem eles o
    # documento sai com o bloco em branco. Ficam no núcleo, e não no módulo agro, porque
    # identificam a empresa — o agro apenas os imprime.
    registro_mapa: Mapped[str | None] = mapped_column(String(60), nullable=True)
    crea: Mapped[str | None] = mapped_column(String(40), nullable=True)
    cda: Mapped[str | None] = mapped_column(String(40), nullable=True)
    inscricao_estadual: Mapped[str | None] = mapped_column(String(40), nullable=True)
    inscricao_municipal: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # Endereço, telefone e e-mail como saem no rodapé do talão. Texto livre porque é
    # exatamente isso no papel, numa única linha — ver questão Q2 do discovery.
    rodape: Mapped[str | None] = mapped_column(String(300), nullable=True)

    users: Mapped[list["User"]] = relationship(back_populates="tenant")


class User(TenantMixin, TimestampMixin, Base):
    __tablename__ = "user_account"
    __table_args__ = (
        # E-mail é único dentro da empresa, não globalmente: a mesma pessoa pode operar
        # em duas empresas diferentes com o mesmo endereço.
        UniqueConstraint("tenant_id", "email", name="uq_user_account_tenant_id_email"),
        # O crachá identifica alguém: dois iguais na mesma empresa tornariam a leitura
        # ambígua, e quem recusa isso é o banco.
        UniqueConstraint("tenant_id", "cracha", name="uq_user_account_tenant_id_cracha"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Quem foi criado pelo dono entra com senha inicial e **tem** de trocá-la. Sem isso a
    # trilha não vale nada: se o dono conhece a senha do operador, "quem fez" é sempre
    # contestável — ver docs/adr/0020-operador-supervisor-e-papeis.md, decisão 6.
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )

    # ------------------------------------------------------------------ entrada rápida
    #
    # No balcão a troca de operador acontece várias vezes por turno, e digitar empresa,
    # e-mail e senha a cada troca é o que faz a loja deixar uma conta só aberta o dia
    # inteiro — e aí "quem fez" deixa de significar alguma coisa.
    #
    # **O crachá identifica; o PIN autentica.** O crachá é um código impresso, lido pelo
    # mesmo leitor de código de barras que já funciona como teclado: não é segredo, e
    # sozinho não entra. O PIN é o segredo, guardado com o mesmo algoritmo da senha.
    #
    # Essa separação não é preciosismo: com hash forte não há como descobrir de quem é um
    # PIN sem testar o de todo mundo, e testar dez Argon2 por tentativa seria um segundo
    # de espera por troca de operador. Ver docs/adr/0020-operador-supervisor-e-papeis.md.
    pin_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    cracha: Mapped[str | None] = mapped_column(String(60), nullable=True)

    # PIN curto só se sustenta com bloqueio: sem isto, quem ficar sozinho com a estação
    # tenta dez mil combinações. O contador zera a cada acerto.
    pin_tentativas: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    pin_bloqueado_ate: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Administra a **plataforma**, não uma empresa: enxerga quem usa o Decko.
    #
    # É marca de pessoa, e não permissão de papel, de propósito. Permissão é declarada por
    # manifesto, e o reconciliador a concederia ao papel `Administrador` de **toda**
    # empresa — a conta do cliente ganharia a lista de clientes. Ligada só pela linha de
    # comando do servidor. Ver docs/adr/0021-nivel-de-plataforma.md.
    is_platform_admin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )

    tenant: Mapped["Tenant"] = relationship(back_populates="users")
    roles: Mapped[list["Role"]] = relationship(secondary="user_role", back_populates="users")

    @property
    def tem_pin(self) -> bool:
        """Se tem PIN, nunca qual é. É o que a tela precisa saber, e só isso."""
        return self.pin_hash is not None


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


class TenantModule(TenantMixin, Base):
    """Módulo ativo em uma empresa.

    A ausência de linha é a resposta "inativo": o padrão é negar, do mesmo jeito que a
    política de RLS trata o tenant não definido.

    ``module_name`` é texto e não chave estrangeira porque a lista de módulos existentes
    vem dos manifestos em disco, não do banco. Uma tabela de módulos aqui sairia de
    sincronia com o que está instalado na plataforma.

    Decisão: ``docs/adr/0004-ativacao-de-modulo-por-empresa.md``.
    """

    __tablename__ = "tenant_module"
    __table_args__ = (
        UniqueConstraint("tenant_id", "module_name", name="uq_tenant_module_tenant_id_module_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    module_name: Mapped[str] = mapped_column(String(60), nullable=False)
    activated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    activated_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("user_account.id", ondelete="SET NULL"), nullable=True
    )


class SeedStatus(StrEnum):
    ATIVO = "ativo"
    # O cliente apagou a linha semeada. Fica anotado para a reativação **não** recriá-la:
    # ressuscitar o que alguém apagou de propósito é a falha pior, porque reaparece sem
    # explicação e sem como impedir.
    REMOVIDO = "removido"


class SeedRecord(TenantMixin, Base):
    """De onde veio cada linha que o sistema criou sozinho.

    É a identidade estável que torna a carga de semente repetível: ``ref`` é um nome que o
    módulo escreve e nunca muda (``comercial.unidade.un``), e ele resolve para uma linha
    concreta. Sem isso, "ativar o perfil comércio" não teria como ser idempotente —
    reconhecer a semente pelo nome criaria duplicata no instante em que o cliente
    renomeasse "Unidade" para "Un".

    É **por empresa**: cada uma recebe a sua cópia da semente, e o registro acompanha.

    ``table_name`` e ``row_id`` não formam chave estrangeira, porque o destino é escolhido
    em tempo de execução e não há como apontar para uma tabela dinâmica. A consequência é
    assumida: a linha de registro pode sobreviver ao desaparecimento do destino, e por
    isso ausência é caso normal para quem lê, não erro.

    Decisão: ``docs/adr/0010-dado-semente-com-identidade-estavel.md``.
    """

    __tablename__ = "seed_record"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "module_name", "ref", name="uq_seed_record_tenant_id_module_name_ref"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    module_name: Mapped[str] = mapped_column(String(60), nullable=False)
    ref: Mapped[str] = mapped_column(String(120), nullable=False)
    table_name: Mapped[str] = mapped_column(String(63), nullable=False)
    row_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)

    # SHA-256 dos campos que a semente escreveu. Guarda o hash e não os valores: a regra 2
    # do CLAUDE.md manda não espalhar dado do cliente por tabela de infraestrutura, e o
    # hash já responde a única pergunta que importa — "o cliente mexeu nisto?".
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)

    status: Mapped[SeedStatus] = mapped_column(
        Enum(
            SeedStatus,
            name="seed_status",
            values_callable=lambda enum_class: [member.value for member in enum_class],
        ),
        nullable=False,
        default=SeedStatus.ATIVO,
    )
    seeded_at: Mapped[datetime] = mapped_column(
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
    TenantModule.__tablename__,
    SeedRecord.__tablename__,
)
