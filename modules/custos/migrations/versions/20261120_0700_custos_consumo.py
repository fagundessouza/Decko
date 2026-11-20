"""custos consumo

Consumo interno: liga uma saída de estoque a um centro de custo.
Decisão: docs/adr/0026-consumo-interno-e-custo-por-centro.md

Revision ID: e52b71f93c0d
Revises:
Create Date: 2026-11-20 07:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e52b71f93c0d"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = ("custos",)
# Aponta para duas tabelas de outros módulos: ambas precisam existir antes. Declarar aqui
# é o que torna a ordem independente de quem roda primeiro.
#   28f12c9b0559 — comercial_movimento
#   c3a51d8e7b24 — financeiro_centro_custo
depends_on: str | Sequence[str] | None = ("28f12c9b0559", "c3a51d8e7b24")

TENANT_GUC = "decko.tenant_id"
_PREDICATE = f"tenant_id = NULLIF(current_setting('{TENANT_GUC}', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "custos_consumo",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("movimento_id", sa.UUID(), nullable=False),
        sa.Column("centro_custo_id", sa.UUID(), nullable=False),
        sa.Column("valor", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("custo_unitario", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("observacao", sa.Text(), nullable=True),
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
            name=op.f("fk_custos_consumo_tenant_id_tenant"),
            ondelete="CASCADE",
        ),
        # RESTRICT nos dois: nem a razão de estoque nem o centro somem por baixo de um
        # custo já lançado.
        sa.ForeignKeyConstraint(
            ["movimento_id"],
            ["comercial_movimento.id"],
            name=op.f("fk_custos_consumo_movimento_id_comercial_movimento"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["centro_custo_id"],
            ["financeiro_centro_custo.id"],
            name=op.f("fk_custos_consumo_centro_custo_id_financeiro_centro_custo"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_custos_consumo")),
        # Lançar o mesmo movimento contra dois centros faria o mesmo adubo custar duas vezes.
        sa.UniqueConstraint("tenant_id", "movimento_id", name="uq_custos_consumo_movimento"),
        sa.CheckConstraint("valor >= 0", name=op.f("ck_custos_consumo_valor_nao_negativo")),
    )
    op.create_index(
        op.f("ix_custos_consumo_tenant_id"), "custos_consumo", ["tenant_id"], unique=False
    )
    op.create_index(
        "ix_custos_consumo_tenant_id_centro",
        "custos_consumo",
        ["tenant_id", "centro_custo_id"],
        unique=False,
    )

    # Quanto a empresa gasta, e em quê, é informação comercial.
    op.execute("ALTER TABLE custos_consumo ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE custos_consumo FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation ON custos_consumo
        FOR ALL
        USING ({_PREDICATE})
        WITH CHECK ({_PREDICATE})
        """
    )


def downgrade() -> None:
    op.drop_index("ix_custos_consumo_tenant_id_centro", table_name="custos_consumo")
    op.drop_index(op.f("ix_custos_consumo_tenant_id"), table_name="custos_consumo")
    op.drop_table("custos_consumo")
