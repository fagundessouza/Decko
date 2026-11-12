"""entrada rapida por PIN e cracha

No balcao a troca de operador acontece varias vezes por turno. Digitar empresa, e-mail e
senha a cada troca e o que faz a loja deixar uma conta so aberta o dia inteiro — e ai
"quem fez" deixa de significar alguma coisa.

O cracha identifica; o PIN autentica. Decisao: docs/adr/0020-operador-supervisor-e-papeis.md.

Revision ID: f82b4e17c0a9
Revises: d5a93f21c6b8
Create Date: 2026-11-12 09:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f82b4e17c0a9"
down_revision: str | None = "d5a93f21c6b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("user_account", sa.Column("pin_hash", sa.Text(), nullable=True))
    op.add_column("user_account", sa.Column("cracha", sa.String(60), nullable=True))
    op.add_column(
        "user_account",
        sa.Column("pin_tentativas", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "user_account",
        sa.Column("pin_bloqueado_ate", sa.DateTime(timezone=True), nullable=True),
    )

    # Dois crachas iguais na mesma empresa tornariam a leitura ambigua. Nulo nao conflita
    # com nulo no PostgreSQL, entao quem nao tem cracha continua sem.
    op.create_unique_constraint(
        "uq_user_account_tenant_id_cracha", "user_account", ["tenant_id", "cracha"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_user_account_tenant_id_cracha", "user_account", type_="unique")
    op.drop_column("user_account", "pin_bloqueado_ate")
    op.drop_column("user_account", "pin_tentativas")
    op.drop_column("user_account", "cracha")
    op.drop_column("user_account", "pin_hash")
