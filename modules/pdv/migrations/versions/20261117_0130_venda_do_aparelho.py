"""a hora em que a venda aconteceu no aparelho

Venda registrada sem rede tem duas horas verdadeiras: a do balcao, quando o cliente levou
a mercadoria, e a do servidor, quando a fila subiu. Guardar so uma delas faz a trilha
mentir — e qual delas responde "quando isso foi feito" e o tipo de coisa que so se
descobre errada numa fiscalizacao.

`created_at` continua sendo a hora do servidor. Esta coluna e a do aparelho, e e nula para
toda venda feita com rede, que e a maioria.

Decisao: docs/adr/0019-offline-first.md e docs/adr/0022-offline-first-as-respostas.md.

Revision ID: c7a4b812e5f0
Revises: a1e6f39d4b27
Create Date: 2026-11-17 01:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c7a4b812e5f0"
down_revision: str | None = "a1e6f39d4b27"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "pdv_venda",
        sa.Column("registrada_no_aparelho_em", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("pdv_venda", "registrada_no_aparelho_em")
