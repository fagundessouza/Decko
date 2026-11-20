"""financeiro despesa

Contas a pagar: o que se deve, para quem, e quando vence.
Decisão: docs/adr/0024-contas-a-pagar.md

Revision ID: b94c7e1f20ad
Revises: d82f4b61c073
Create Date: 2026-11-20 03:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b94c7e1f20ad"
down_revision: str | None = "d82f4b61c073"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_GUC = "decko.tenant_id"
_PREDICATE = f"tenant_id = NULLIF(current_setting('{TENANT_GUC}', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "financeiro_despesa",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("descricao", sa.String(length=200), nullable=False),
        sa.Column("fornecedor_nome", sa.String(length=200), nullable=True),
        sa.Column("fornecedor_cpf_cnpj", sa.String(length=14), nullable=True),
        sa.Column("valor", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("vencimento", sa.Date(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("aberta", "paga", "cancelada", name="financeiro_status_despesa"),
            nullable=False,
            server_default="aberta",
        ),
        sa.Column("pago_em", sa.Date(), nullable=True),
        sa.Column("valor_pago", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("conta_id", sa.UUID(), nullable=True),
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
            name=op.f("fk_financeiro_despesa_tenant_id_tenant"),
            ondelete="CASCADE",
        ),
        # RESTRICT, e não CASCADE: conta que já pagou alguma coisa não se apaga — ADR 0014,
        # decisão 4. Quem sai de cena desativa.
        sa.ForeignKeyConstraint(
            ["conta_id"],
            ["financeiro_conta.id"],
            name=op.f("fk_financeiro_despesa_conta_id_financeiro_conta"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_financeiro_despesa")),
        sa.CheckConstraint("valor >= 0", name=op.f("ck_financeiro_despesa_valor_nao_negativo")),
        sa.CheckConstraint(
            "valor_pago IS NULL OR valor_pago >= 0",
            name=op.f("ck_financeiro_despesa_valor_pago_nao_negativo"),
        ),
        # Estado impossível não deve caber no banco: paga tem data e valor, o resto não tem
        # nenhum dos dois.
        sa.CheckConstraint(
            "(status = 'paga' AND pago_em IS NOT NULL AND valor_pago IS NOT NULL)"
            " OR (status <> 'paga' AND pago_em IS NULL AND valor_pago IS NULL)",
            name=op.f("ck_financeiro_despesa_paga_tem_data_e_valor"),
        ),
    )
    op.create_index(
        op.f("ix_financeiro_despesa_tenant_id"), "financeiro_despesa", ["tenant_id"], unique=False
    )
    op.create_index(
        "ix_financeiro_despesa_tenant_id_vencimento",
        "financeiro_despesa",
        ["tenant_id", "vencimento"],
        unique=False,
    )
    op.create_index(
        "ix_financeiro_despesa_tenant_id_status",
        "financeiro_despesa",
        ["tenant_id", "status"],
        unique=False,
    )

    # Quanto a empresa deve, a quem, e com qual CNPJ é informação comercial e pessoal.
    op.execute("ALTER TABLE financeiro_despesa ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE financeiro_despesa FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation ON financeiro_despesa
        FOR ALL
        USING ({_PREDICATE})
        WITH CHECK ({_PREDICATE})
        """
    )


def downgrade() -> None:
    op.drop_index("ix_financeiro_despesa_tenant_id_status", table_name="financeiro_despesa")
    op.drop_index("ix_financeiro_despesa_tenant_id_vencimento", table_name="financeiro_despesa")
    op.drop_index(op.f("ix_financeiro_despesa_tenant_id"), table_name="financeiro_despesa")
    op.drop_table("financeiro_despesa")
    sa.Enum(name="financeiro_status_despesa").drop(op.get_bind(), checkfirst=True)
