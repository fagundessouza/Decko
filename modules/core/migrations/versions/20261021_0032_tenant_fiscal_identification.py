"""tenant fiscal identification

Identificação da empresa aplicadora no cabeçalho do Planejamento Operacional: os campos
que o formulário do MAPA exige impressos e que até aqui saíam em branco, porque não
existiam no modelo. Ver docs/discovery/agro-planejamento-operacional.md, seção 4.1.

Todos nulos: empresa já cadastrada não deixa de funcionar por não os ter ainda, e o
formulário de quem não é do agro não os usa.

Revision ID: 3a486fcfab2d
Revises: 0b2349b8d57a
Create Date: 2026-10-21 00:32:11.311841
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3a486fcfab2d"
down_revision: str | None = "0b2349b8d57a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tenant", sa.Column("registro_mapa", sa.String(length=60), nullable=True))
    op.add_column("tenant", sa.Column("crea", sa.String(length=40), nullable=True))
    op.add_column("tenant", sa.Column("cda", sa.String(length=40), nullable=True))
    op.add_column("tenant", sa.Column("inscricao_estadual", sa.String(length=40), nullable=True))
    op.add_column("tenant", sa.Column("inscricao_municipal", sa.String(length=40), nullable=True))
    op.add_column("tenant", sa.Column("rodape", sa.String(length=300), nullable=True))


def downgrade() -> None:
    op.drop_column("tenant", "rodape")
    op.drop_column("tenant", "inscricao_municipal")
    op.drop_column("tenant", "inscricao_estadual")
    op.drop_column("tenant", "cda")
    op.drop_column("tenant", "crea")
    op.drop_column("tenant", "registro_mapa")
