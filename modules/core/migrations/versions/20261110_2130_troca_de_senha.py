"""troca de senha obrigatoria na primeira entrada

O dono cria o operador com uma senha inicial, e o operador e obrigado a troca-la ao entrar.
Sem isso a trilha nao vale nada: se o dono conhece a senha do operador, "quem fez" e sempre
contestavel.

Decisao: docs/adr/0020-operador-supervisor-e-papeis.md, decisao 6.

Revision ID: d5a93f21c6b8
Revises: 7c4e1b9a2f03
Create Date: 2026-11-10 21:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d5a93f21c6b8"
down_revision: str | None = "7c4e1b9a2f03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # `false` para quem ja existe: ninguem que ja usa o sistema pode ser trancado numa
    # troca de senha que nunca pediu. A exigencia nasce com quem for criado daqui para a
    # frente.
    op.add_column(
        "user_account",
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("user_account", "must_change_password")
