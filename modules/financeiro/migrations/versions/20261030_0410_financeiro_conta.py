"""financeiro conta

Conta de recebimento: para onde o dinheiro foi.
Decisão: docs/adr/0014-conta-de-recebimento.md

Revision ID: d82f4b61c073
Revises:
Create Date: 2026-10-30 04:10:22.771045
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d82f4b61c073"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = ("financeiro",)
# A conta pertence a uma empresa: a migração do núcleo precisa ter rodado antes.
depends_on: str | Sequence[str] | None = ("31a827ed5da2",)

TENANT_GUC = "decko.tenant_id"
_PREDICATE = f"tenant_id = NULLIF(current_setting('{TENANT_GUC}', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "financeiro_conta",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("nome", sa.String(length=120), nullable=False),
        sa.Column("instituicao", sa.String(length=120), nullable=True),
        sa.Column("chave_pix", sa.String(length=200), nullable=True),
        sa.Column("ativa", sa.Boolean(), nullable=False, server_default=sa.text("true")),
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
            name=op.f("fk_financeiro_conta_tenant_id_tenant"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_financeiro_conta")),
        sa.UniqueConstraint("tenant_id", "nome", name="uq_financeiro_conta_tenant_id_nome"),
    )
    op.create_index(
        op.f("ix_financeiro_conta_tenant_id"), "financeiro_conta", ["tenant_id"], unique=False
    )
    op.create_index(
        "ix_financeiro_conta_tenant_id_ativa",
        "financeiro_conta",
        ["tenant_id", "ativa"],
        unique=False,
    )

    # Onde a loja recebe dinheiro, e com qual chave Pix, é informação comercial e pessoal.
    op.execute("ALTER TABLE financeiro_conta ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE financeiro_conta FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation ON financeiro_conta
        FOR ALL
        USING ({_PREDICATE})
        WITH CHECK ({_PREDICATE})
        """
    )


def downgrade() -> None:
    op.drop_index("ix_financeiro_conta_tenant_id_ativa", table_name="financeiro_conta")
    op.drop_index(op.f("ix_financeiro_conta_tenant_id"), table_name="financeiro_conta")
    op.drop_table("financeiro_conta")
