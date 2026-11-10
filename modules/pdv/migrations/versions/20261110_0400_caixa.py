"""caixa

A sessão de caixa: o que passou pelas mãos de um operador, entre abrir e fechar.
Decisão: docs/adr/0008-ponto-de-venda.md, atualização de 10/11/2026.

Revision ID: a7f41c9e2d58
Revises: 5e7a09d3fb18
Create Date: 2026-11-10 04:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7f41c9e2d58"
down_revision: str | None = "5e7a09d3fb18"
branch_labels: str | Sequence[str] | None = None
# A chave estrangeira do operador aponta para `user_account`, do módulo `core`.
depends_on: str | Sequence[str] | None = ("7c4e1b9a2f03",)

# Precisa coincidir com decko.tenancy.TENANT_GUC.
TENANT_GUC = "decko.tenant_id"
_PREDICATE = f"tenant_id = NULLIF(current_setting('{TENANT_GUC}', true), '')::uuid"

_TABELAS = ("pdv_caixa", "pdv_caixa_movimento")


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
        "pdv_caixa",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("operador_id", sa.UUID(), nullable=False),
        sa.Column(
            "aberto_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("fechado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("abertura", sa.Numeric(18, 2), nullable=False),
        # Só no fechamento. São fato histórico — o que foi contado, o que se esperava
        # naquele instante, e a diferença. O esperado de um caixa aberto é conta feita na
        # leitura e não se guarda.
        sa.Column("contado", sa.Numeric(18, 2), nullable=True),
        sa.Column("esperado", sa.Numeric(18, 2), nullable=True),
        sa.Column("diferenca", sa.Numeric(18, 2), nullable=True),
        sa.Column("observacao", sa.String(500), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("abertura >= 0", name=op.f("ck_pdv_caixa_abertura_nao_negativa")),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_pdv_caixa_tenant_id_tenant"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["operador_id"],
            ["user_account.id"],
            name=op.f("fk_pdv_caixa_operador_id_user_account"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pdv_caixa")),
    )

    # Um operador não tem dois caixas abertos ao mesmo tempo, e quem recusa é o banco.
    # Duas abas abertas tentariam as duas; validar só na aplicação deixaria passar.
    op.create_index(
        "uq_pdv_caixa_aberto_por_operador",
        "pdv_caixa",
        ["tenant_id", "operador_id"],
        unique=True,
        postgresql_where=sa.text("fechado_em IS NULL"),
    )

    op.create_table(
        "pdv_caixa_movimento",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("caixa_id", sa.UUID(), nullable=False),
        sa.Column(
            "tipo",
            sa.Enum("sangria", "suprimento", name="pdv_tipo_movimento_caixa"),
            nullable=False,
        ),
        sa.Column("valor", sa.Numeric(18, 2), nullable=False),
        sa.Column("motivo", sa.String(200), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("valor > 0", name=op.f("ck_pdv_caixa_movimento_valor_positivo")),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_pdv_caixa_movimento_tenant_id_tenant"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["caixa_id"],
            ["pdv_caixa.id"],
            name=op.f("fk_pdv_caixa_movimento_caixa_id_pdv_caixa"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pdv_caixa_movimento")),
    )

    # Nulo quando a venda foi feita sem caixa aberto, e continua nulo: abrir o caixa
    # depois não puxa para dentro dele o que foi vendido antes.
    op.add_column("pdv_venda", sa.Column("caixa_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("fk_pdv_venda_caixa_id_pdv_caixa"),
        "pdv_venda",
        "pdv_caixa",
        ["caixa_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    _enable_row_level_security()


def downgrade() -> None:
    op.drop_constraint(op.f("fk_pdv_venda_caixa_id_pdv_caixa"), "pdv_venda", type_="foreignkey")
    op.drop_column("pdv_venda", "caixa_id")
    op.drop_table("pdv_caixa_movimento")
    op.drop_index("uq_pdv_caixa_aberto_por_operador", table_name="pdv_caixa")
    op.drop_table("pdv_caixa")
    sa.Enum(name="pdv_tipo_movimento_caixa").drop(op.get_bind(), checkfirst=True)
