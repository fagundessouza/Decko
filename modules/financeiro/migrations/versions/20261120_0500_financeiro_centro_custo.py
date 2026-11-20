"""financeiro centro de custo

Contra o quê o dinheiro saiu. Lista plana, não árvore.
Decisão: docs/adr/0025-centro-de-custo.md

Revision ID: c3a51d8e7b24
Revises: b94c7e1f20ad
Create Date: 2026-11-20 05:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3a51d8e7b24"
down_revision: str | None = "b94c7e1f20ad"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_GUC = "decko.tenant_id"
_PREDICATE = f"tenant_id = NULLIF(current_setting('{TENANT_GUC}', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "financeiro_centro_custo",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("nome", sa.String(length=120), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_financeiro_centro_custo_tenant_id_tenant"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_financeiro_centro_custo")),
        sa.UniqueConstraint("tenant_id", "nome", name="uq_financeiro_centro_custo_tenant_id_nome"),
    )
    op.create_index(
        op.f("ix_financeiro_centro_custo_tenant_id"),
        "financeiro_centro_custo",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_financeiro_centro_custo_tenant_id_ativo",
        "financeiro_centro_custo",
        ["tenant_id", "ativo"],
        unique=False,
    )

    # Como a empresa divide o próprio custo diz o que ela faz e onde ela gasta.
    op.execute("ALTER TABLE financeiro_centro_custo ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE financeiro_centro_custo FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation ON financeiro_centro_custo
        FOR ALL
        USING ({_PREDICATE})
        WITH CHECK ({_PREDICATE})
        """
    )

    op.add_column("financeiro_despesa", sa.Column("centro_custo_id", sa.UUID(), nullable=True))
    # RESTRICT: centro que já tem despesa não se apaga, desativa. Senão o custo do ano
    # passado perde o nome.
    op.create_foreign_key(
        op.f("fk_financeiro_despesa_centro_custo_id_financeiro_centro_custo"),
        "financeiro_despesa",
        "financeiro_centro_custo",
        ["centro_custo_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_financeiro_despesa_tenant_id_centro",
        "financeiro_despesa",
        ["tenant_id", "centro_custo_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_financeiro_despesa_tenant_id_centro", table_name="financeiro_despesa")
    op.drop_constraint(
        op.f("fk_financeiro_despesa_centro_custo_id_financeiro_centro_custo"),
        "financeiro_despesa",
        type_="foreignkey",
    )
    op.drop_column("financeiro_despesa", "centro_custo_id")

    op.drop_index(
        "ix_financeiro_centro_custo_tenant_id_ativo", table_name="financeiro_centro_custo"
    )
    op.drop_index(
        op.f("ix_financeiro_centro_custo_tenant_id"), table_name="financeiro_centro_custo"
    )
    op.drop_table("financeiro_centro_custo")
