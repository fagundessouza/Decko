"""venda identificada

A venda passa a poder apontar para quem comprou.
Decisão: docs/adr/0008-ponto-de-venda.md, atualização de 29/10/2026.

Revision ID: 9d3b70c15ae4
Revises: f836e10043a7
Create Date: 2026-10-29 03:10:44.902117
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9d3b70c15ae4"
down_revision: str | None = "f836e10043a7"
branch_labels: str | Sequence[str] | None = None
# A chave estrangeira aponta para uma tabela do módulo `clientes`: a migração dele precisa
# ter rodado antes. É o mesmo mecanismo que amarra o PDV ao `comercial`.
depends_on: str | Sequence[str] | None = ("62a2f7722e81",)


def upgrade() -> None:
    op.add_column("pdv_venda", sa.Column("cliente_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("fk_pdv_venda_cliente_id_clientes_cliente"),
        "pdv_venda",
        "clientes_cliente",
        ["cliente_id"],
        ["id"],
        # RESTRICT, e não SET NULL: o cadastro de clientes nunca apaga, só desativa,
        # justamente para a venda continuar apontando para alguém.
        ondelete="RESTRICT",
    )
    # As vendas de um cliente são a consulta que esta coluna existe para responder.
    op.create_index(
        "ix_pdv_venda_tenant_id_cliente_id", "pdv_venda", ["tenant_id", "cliente_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_pdv_venda_tenant_id_cliente_id", table_name="pdv_venda")
    op.drop_constraint(
        op.f("fk_pdv_venda_cliente_id_clientes_cliente"), "pdv_venda", type_="foreignkey"
    )
    op.drop_column("pdv_venda", "cliente_id")
