"""pagamento conta

O pagamento passa a dizer em qual conta o dinheiro caiu.
Decisão: docs/adr/0014-conta-de-recebimento.md

Revision ID: 5e7a09d3fb18
Revises: 9d3b70c15ae4
Create Date: 2026-10-30 04:25:07.336911
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5e7a09d3fb18"
down_revision: str | None = "9d3b70c15ae4"
branch_labels: str | Sequence[str] | None = None
# A chave estrangeira aponta para uma tabela do módulo `financeiro`.
depends_on: str | Sequence[str] | None = ("d82f4b61c073",)


def upgrade() -> None:
    # Nulo por padrão: velocidade de balcão é requisito, e um campo obrigatório a mais por
    # pagamento é fila parada. Quem quer a conferência separada preenche.
    op.add_column("pdv_pagamento", sa.Column("conta_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("fk_pdv_pagamento_conta_id_financeiro_conta"),
        "pdv_pagamento",
        "financeiro_conta",
        ["conta_id"],
        ["id"],
        # RESTRICT: conta não se apaga, desativa — o recebimento de ontem continua
        # apontando para ela.
        ondelete="RESTRICT",
    )
    # A conferência de fim de dia é a consulta que esta coluna existe para responder.
    op.create_index(
        "ix_pdv_pagamento_tenant_id_conta_id",
        "pdv_pagamento",
        ["tenant_id", "conta_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_pdv_pagamento_tenant_id_conta_id", table_name="pdv_pagamento")
    op.drop_constraint(
        op.f("fk_pdv_pagamento_conta_id_financeiro_conta"), "pdv_pagamento", type_="foreignkey"
    )
    op.drop_column("pdv_pagamento", "conta_id")
