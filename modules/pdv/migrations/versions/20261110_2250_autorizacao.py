"""autorizacao do supervisor

O que o operador nao faz sozinho, quem liberou, e a partir de quanto cada loja exige.

Decisao: docs/adr/0020-operador-supervisor-e-papeis.md, decisao 4.
Requisito: docs/discovery/pdv-operador-supervisor-e-papeis.md.

Revision ID: e4c17b05a9d3
Revises: b3d82c1f47ea
Create Date: 2026-11-10 22:50:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e4c17b05a9d3"
down_revision: str | None = "b3d82c1f47ea"
branch_labels: str | Sequence[str] | None = None
# `pdv_autorizacao` aponta para `user_account`, do modulo `core`.
depends_on: str | Sequence[str] | None = ("7c4e1b9a2f03",)

TENANT_GUC = "decko.tenant_id"
_PREDICATE = f"tenant_id = NULLIF(current_setting('{TENANT_GUC}', true), '')::uuid"

_TABELAS = ("pdv_configuracao", "pdv_autorizacao")


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
        "pdv_configuracao",
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        # As quatro que o dono do projeto escolheu nascem ligadas.
        sa.Column("exige_cancelar_item", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("exige_cancelar_venda", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("exige_sangria", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("exige_devolucao", sa.Boolean(), nullable=False, server_default=sa.true()),
        # As duas que dependem de um numero nascem desligadas: liga-las exige escolher o
        # limite, e inventar esse limite seria inventar regra de negocio.
        sa.Column("exige_desconto", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("desconto_livre", sa.Numeric(18, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("exige_diferenca", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "diferenca_livre", sa.Numeric(18, 2), nullable=False, server_default=sa.text("0")
        ),
        sa.CheckConstraint("desconto_livre >= 0", name=op.f("ck_pdv_configuracao_desconto_livre")),
        sa.CheckConstraint(
            "diferenca_livre >= 0", name=op.f("ck_pdv_configuracao_diferenca_livre")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_pdv_configuracao_tenant_id_tenant"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", name=op.f("pk_pdv_configuracao")),
    )

    op.create_table(
        "pdv_autorizacao",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column(
            "acao",
            sa.Enum(
                "cancelar_item",
                "cancelar_venda",
                "sangria",
                "devolucao",
                "desconto",
                "fechar_caixa",
                name="pdv_acao_autorizada",
            ),
            nullable=False,
        ),
        sa.Column("solicitante_id", sa.UUID(), nullable=True),
        sa.Column("autorizador_id", sa.UUID(), nullable=True),
        sa.Column("referencia", sa.String(80), nullable=True),
        sa.Column("valor", sa.Numeric(18, 2), nullable=True),
        sa.Column("motivo", sa.String(200), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_pdv_autorizacao_tenant_id_tenant"),
            ondelete="CASCADE",
        ),
        # `SET NULL` nas duas pessoas: a linha e historico e nao pode sumir com quem saiu
        # da empresa.
        sa.ForeignKeyConstraint(
            ["solicitante_id"],
            ["user_account.id"],
            name=op.f("fk_pdv_autorizacao_solicitante_id_user_account"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["autorizador_id"],
            ["user_account.id"],
            name=op.f("fk_pdv_autorizacao_autorizador_id_user_account"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pdv_autorizacao")),
    )
    op.create_index(
        "ix_pdv_autorizacao_tenant_id_created_at", "pdv_autorizacao", ["tenant_id", "created_at"]
    )
    op.create_index("ix_pdv_autorizacao_autorizador_id", "pdv_autorizacao", ["autorizador_id"])

    _enable_row_level_security()


def downgrade() -> None:
    op.drop_index("ix_pdv_autorizacao_autorizador_id", table_name="pdv_autorizacao")
    op.drop_index("ix_pdv_autorizacao_tenant_id_created_at", table_name="pdv_autorizacao")
    op.drop_table("pdv_autorizacao")
    op.drop_table("pdv_configuracao")
    sa.Enum(name="pdv_acao_autorizada").drop(op.get_bind(), checkfirst=True)
