"""administrador da plataforma

Quem administra a plataforma enxerga quem usa o Decko. E marca de **pessoa**, nao
permissao de papel: permissao e declarada por manifesto, e o reconciliador a concederia ao
papel Administrador de toda empresa — a conta do cliente ganharia a lista de clientes.

Decisao: docs/adr/0021-nivel-de-plataforma.md, decisao 1.

Revision ID: c93b7e14f25d
Revises: f82b4e17c0a9
Create Date: 2026-11-13 19:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c93b7e14f25d"
down_revision: str | None = "f82b4e17c0a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_account",
        sa.Column("is_platform_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("user_account", "is_platform_admin")
