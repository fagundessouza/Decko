"""assinaturas schema

Plano, assinatura e a cobrança de cada mês.
Decisão: docs/adr/0013-assinatura-recorrente.md

Revision ID: c41d8a97b2e5
Revises:
Create Date: 2026-10-30 01:20:33.512094
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c41d8a97b2e5"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = ("assinaturas",)
# A assinatura aponta para o cliente, e a cobrança para o usuário que concedeu prazo: as
# migrações do núcleo e do módulo de clientes precisam ter rodado antes.
depends_on: str | Sequence[str] | None = ("62a2f7722e81",)

TENANT_GUC = "decko.tenant_id"
_PREDICATE = f"tenant_id = NULLIF(current_setting('{TENANT_GUC}', true), '')::uuid"

TABELAS = ("assinaturas_plano", "assinaturas_assinatura", "assinaturas_cobranca")


def _carimbo(nome: str) -> sa.Column:
    return sa.Column(
        nome, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "assinaturas_plano",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("nome", sa.String(length=120), nullable=False),
        sa.Column("descricao", sa.String(length=400), nullable=True),
        sa.Column("preco_mensal", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        _carimbo("created_at"),
        _carimbo("updated_at"),
        sa.CheckConstraint("preco_mensal >= 0", name="preco_mensal_nao_negativo"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_assinaturas_plano_tenant_id_tenant"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assinaturas_plano")),
        sa.UniqueConstraint("tenant_id", "nome", name="uq_assinaturas_plano_tenant_id_nome"),
    )
    op.create_index(
        op.f("ix_assinaturas_plano_tenant_id"), "assinaturas_plano", ["tenant_id"], unique=False
    )

    op.create_table(
        "assinaturas_assinatura",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("cliente_id", sa.UUID(), nullable=False),
        sa.Column("plano_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("ativa", "cancelada", name="assinaturas_status_assinatura"),
            nullable=False,
        ),
        sa.Column("inicio", sa.Date(), nullable=False),
        sa.Column("dia_vencimento", sa.Integer(), nullable=False),
        sa.Column("cancelada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        _carimbo("created_at"),
        _carimbo("updated_at"),
        sa.CheckConstraint(
            "dia_vencimento BETWEEN 1 AND 28", name="dia_vencimento_existe_em_todo_mes"
        ),
        # RESTRICT: o cadastro de clientes nunca apaga, só desativa, justamente para a
        # cobrança continuar apontando para alguém.
        sa.ForeignKeyConstraint(
            ["cliente_id"],
            ["clientes_cliente.id"],
            name=op.f("fk_assinaturas_assinatura_cliente_id_clientes_cliente"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["plano_id"],
            ["assinaturas_plano.id"],
            name=op.f("fk_assinaturas_assinatura_plano_id_assinaturas_plano"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_assinaturas_assinatura_tenant_id_tenant"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assinaturas_assinatura")),
    )
    op.create_index(
        op.f("ix_assinaturas_assinatura_tenant_id"),
        "assinaturas_assinatura",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_assinaturas_assinatura_tenant_id_status",
        "assinaturas_assinatura",
        ["tenant_id", "status"],
        unique=False,
    )

    op.create_table(
        "assinaturas_cobranca",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("assinatura_id", sa.UUID(), nullable=False),
        sa.Column("competencia", sa.Date(), nullable=False),
        sa.Column("valor", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("vencimento", sa.Date(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("aberta", "paga", "cancelada", name="assinaturas_status_cobranca"),
            nullable=False,
        ),
        sa.Column("pago_em", sa.Date(), nullable=True),
        sa.Column("forma_pagamento", sa.String(length=40), nullable=True),
        sa.Column("observacao", sa.String(length=300), nullable=True),
        sa.Column("prazo_ate", sa.Date(), nullable=True),
        sa.Column("prazo_motivo", sa.String(length=300), nullable=True),
        sa.Column("prazo_por", sa.UUID(), nullable=True),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        _carimbo("created_at"),
        _carimbo("updated_at"),
        sa.CheckConstraint("valor >= 0", name="valor_nao_negativo"),
        sa.ForeignKeyConstraint(
            ["assinatura_id"],
            ["assinaturas_assinatura.id"],
            name=op.f("fk_assinaturas_cobranca_assinatura_id_assinaturas_assinatura"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["prazo_por"],
            ["user_account.id"],
            name=op.f("fk_assinaturas_cobranca_prazo_por_user_account"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_assinaturas_cobranca_tenant_id_tenant"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assinaturas_cobranca")),
        # Uma por competência: é o que torna gerar o mês repetível.
        sa.UniqueConstraint(
            "tenant_id",
            "assinatura_id",
            "competencia",
            name="uq_assinaturas_cobranca_assinatura_competencia",
        ),
    )
    op.create_index(
        op.f("ix_assinaturas_cobranca_tenant_id"),
        "assinaturas_cobranca",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_assinaturas_cobranca_tenant_id_status",
        "assinaturas_cobranca",
        ["tenant_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_assinaturas_cobranca_tenant_id_vencimento",
        "assinaturas_cobranca",
        ["tenant_id", "vencimento"],
        unique=False,
    )

    # Mesma proteção das demais tabelas de empresa. Aqui ela guarda informação comercial:
    # quem assina o quê, por quanto, e quem está devendo.
    for tabela in TABELAS:
        op.execute(f"ALTER TABLE {tabela} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tabela} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {tabela}
            FOR ALL
            USING ({_PREDICATE})
            WITH CHECK ({_PREDICATE})
            """
        )


def downgrade() -> None:
    op.drop_table("assinaturas_cobranca")
    op.drop_table("assinaturas_assinatura")
    op.drop_table("assinaturas_plano")
    op.execute("DROP TYPE assinaturas_status_cobranca")
    op.execute("DROP TYPE assinaturas_status_assinatura")
