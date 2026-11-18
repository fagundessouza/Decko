"""numero de serie da aeronave, para casar o registro de voo importado

Revision ID: a3f29c71d845
Revises: 64a9720e8095
Create Date: 2026-11-17 23:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a3f29c71d845"
down_revision: str | None = "64a9720e8095"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agro_aircraft", sa.Column("numero_serie", sa.String(length=60), nullable=True))
    # Único por empresa, e não no banco inteiro: duas empresas podem ter equipamentos
    # diferentes, e o série é do fabricante, não nosso. Nulo não conflita com nulo em
    # PostgreSQL, então aeronave sem série cadastrada continua convivendo com as outras.
    op.create_unique_constraint(
        "uq_agro_aircraft_tenant_id_numero_serie",
        "agro_aircraft",
        ["tenant_id", "numero_serie"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_agro_aircraft_tenant_id_numero_serie", "agro_aircraft", type_="unique")
    op.drop_column("agro_aircraft", "numero_serie")
