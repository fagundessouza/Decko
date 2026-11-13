"""qual empresa da plataforma este contato e

Liga "quem o Decko cobra" a "quem usa o Decko". Sem isto, bloquear uma assinatura nao tem o
que bloquear. Nulo e o caso normal: cliente de balcao nao e empresa nenhuma.

Decisao: docs/adr/0021-nivel-de-plataforma.md, decisao 4.

Revision ID: b47c2f0a9e18
Revises: 62a2f7722e81
Create Date: 2026-11-13 19:05:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b47c2f0a9e18"
down_revision: str | None = "62a2f7722e81"
branch_labels: str | Sequence[str] | None = None
# A chave estrangeira aponta para `tenant`, do modulo `core`.
depends_on: str | Sequence[str] | None = ("7c4e1b9a2f03",)


def upgrade() -> None:
    op.add_column("clientes_cliente", sa.Column("tenant_assinante_id", sa.UUID(), nullable=True))
    # `RESTRICT`: apagar a empresa por baixo de uma assinatura que a cobra nao pode ser
    # silencioso.
    op.create_foreign_key(
        op.f("fk_clientes_cliente_tenant_assinante_id_tenant"),
        "clientes_cliente",
        "tenant",
        ["tenant_assinante_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    # Uma empresa e apontada por no maximo um contato: duas assinaturas pagando o mesmo
    # acesso tornaria "esta bloqueada?" uma pergunta sem resposta.
    op.create_unique_constraint(
        "uq_clientes_cliente_tenant_assinante_id", "clientes_cliente", ["tenant_assinante_id"]
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_clientes_cliente_tenant_assinante_id", "clientes_cliente", type_="unique"
    )
    op.drop_constraint(
        op.f("fk_clientes_cliente_tenant_assinante_id_tenant"),
        "clientes_cliente",
        type_="foreignkey",
    )
    op.drop_column("clientes_cliente", "tenant_assinante_id")
