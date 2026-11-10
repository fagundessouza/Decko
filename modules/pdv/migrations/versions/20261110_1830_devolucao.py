"""devolucao

O que o cliente trouxe de volta, e quanto recebeu por isso. Documento novo que aponta para
a venda: a venda não é alterada, e continua `finalizada`.

Decisão: atualização de 10/11/2026 da docs/adr/0008-ponto-de-venda.md.
Requisito: docs/discovery/pdv-devolucao-de-venda.md.

Revision ID: b3d82c1f47ea
Revises: a7f41c9e2d58
Create Date: 2026-11-10 18:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b3d82c1f47ea"
down_revision: str | None = "a7f41c9e2d58"
branch_labels: str | Sequence[str] | None = None
# `pdv_devolucao.operador_id` aponta para `user_account`, do módulo `core`.
depends_on: str | Sequence[str] | None = ("7c4e1b9a2f03",)

# Precisa coincidir com decko.tenancy.TENANT_GUC.
TENANT_GUC = "decko.tenant_id"
_PREDICATE = f"tenant_id = NULLIF(current_setting('{TENANT_GUC}', true), '')::uuid"

_TABELAS = ("pdv_devolucao", "pdv_devolucao_item")


def _enable_row_level_security() -> None:
    for table in _TABELAS:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
            FOR ALL
            USING ({_PREDICATE})
            WITH CHECK ({_PREDICATE})
            """
        )


def upgrade() -> None:
    op.create_table(
        "pdv_devolucao",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("venda_id", sa.UUID(), nullable=False),
        sa.Column("operador_id", sa.UUID(), nullable=True),
        sa.Column("caixa_id", sa.UUID(), nullable=True),
        # O enum da forma de pagamento já existe desde o schema do PDV: `create_type=False`
        # porque criar de novo abortaria a migração em vez de reusar o tipo.
        sa.Column(
            "forma",
            postgresql.ENUM(name="pdv_forma_pagamento", create_type=False),
            nullable=False,
        ),
        sa.Column("motivo", sa.String(300), nullable=False),
        sa.Column("total", sa.Numeric(18, 2), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("total >= 0", name=op.f("ck_pdv_devolucao_total_nao_negativo")),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_pdv_devolucao_tenant_id_tenant"),
            ondelete="CASCADE",
        ),
        # `RESTRICT`: a devolução é documento sobre a venda, não parte dela. Apagar a venda
        # por baixo de um reembolso já pago não pode ser silencioso.
        sa.ForeignKeyConstraint(
            ["venda_id"],
            ["pdv_venda.id"],
            name=op.f("fk_pdv_devolucao_venda_id_pdv_venda"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["operador_id"],
            ["user_account.id"],
            name=op.f("fk_pdv_devolucao_operador_id_user_account"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["caixa_id"],
            ["pdv_caixa.id"],
            name=op.f("fk_pdv_devolucao_caixa_id_pdv_caixa"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pdv_devolucao")),
    )
    op.create_index("ix_pdv_devolucao_venda_id", "pdv_devolucao", ["venda_id"])
    op.create_index(
        "ix_pdv_devolucao_tenant_id_created_at", "pdv_devolucao", ["tenant_id", "created_at"]
    )

    op.create_table(
        "pdv_devolucao_item",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("devolucao_id", sa.UUID(), nullable=False),
        sa.Column("venda_item_id", sa.UUID(), nullable=False),
        sa.Column("quantidade", sa.Numeric(18, 6), nullable=False),
        sa.Column("valor", sa.Numeric(18, 2), nullable=False),
        sa.Column(
            "destino",
            sa.Enum("estoque", "avaria", name="pdv_destino_devolucao"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "quantidade > 0", name=op.f("ck_pdv_devolucao_item_quantidade_positiva")
        ),
        sa.CheckConstraint("valor >= 0", name=op.f("ck_pdv_devolucao_item_valor_nao_negativo")),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_pdv_devolucao_item_tenant_id_tenant"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["devolucao_id"],
            ["pdv_devolucao.id"],
            name=op.f("fk_pdv_devolucao_item_devolucao_id_pdv_devolucao"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["venda_item_id"],
            ["pdv_venda_item.id"],
            name=op.f("fk_pdv_devolucao_item_venda_item_id_pdv_venda_item"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pdv_devolucao_item")),
    )
    op.create_index("ix_pdv_devolucao_item_devolucao_id", "pdv_devolucao_item", ["devolucao_id"])
    # Usado para somar o que cada linha da venda já devolveu, que é o limite da próxima.
    op.create_index("ix_pdv_devolucao_item_venda_item_id", "pdv_devolucao_item", ["venda_item_id"])

    _enable_row_level_security()


def downgrade() -> None:
    op.drop_index("ix_pdv_devolucao_item_venda_item_id", table_name="pdv_devolucao_item")
    op.drop_index("ix_pdv_devolucao_item_devolucao_id", table_name="pdv_devolucao_item")
    op.drop_table("pdv_devolucao_item")
    op.drop_index("ix_pdv_devolucao_tenant_id_created_at", table_name="pdv_devolucao")
    op.drop_index("ix_pdv_devolucao_venda_id", table_name="pdv_devolucao")
    op.drop_table("pdv_devolucao")
    sa.Enum(name="pdv_destino_devolucao").drop(op.get_bind(), checkfirst=True)
