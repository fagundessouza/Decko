"""abrir o pdv pede o pin de quem vai operar

Estacao de balcao aberta na conta de quem passou antes e como "quem fez" deixa de
significar alguma coisa. Nasce ligada; loja que nao quiser desliga nos ajustes.

Decisao: docs/adr/0020-operador-supervisor-e-papeis.md, decisao 1.

Revision ID: a1e6f39d4b27
Revises: e4c17b05a9d3
Create Date: 2026-11-13 13:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1e6f39d4b27"
down_revision: str | None = "e4c17b05a9d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "pdv_configuracao",
        sa.Column("exige_pin_no_pdv", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("pdv_configuracao", "exige_pin_no_pdv")
