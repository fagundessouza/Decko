"""voo importado do registro do equipamento

Revision ID: e81c4b50f2a7
Revises: a3f29c71d845
Create Date: 2026-11-18 00:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e81c4b50f2a7"
down_revision: str | None = "a3f29c71d845"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agro_flight",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("aircraft_id", sa.UUID(), nullable=True),
        sa.Column("plan_id", sa.UUID(), nullable=True),
        sa.Column("is_spraying", sa.Boolean(), nullable=False),
        sa.Column("plot_id", sa.String(length=80), nullable=True),
        sa.Column("talhao", sa.String(length=200), nullable=True),
        sa.Column("comecou_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("terminou_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("comecou_em_arquivo", sa.DateTime(), nullable=False),
        sa.Column("duracao_segundos", sa.Integer(), nullable=False),
        sa.Column("area_ha", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("volume_l", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("largura_faixa_m", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("altura_voo_m", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("equipamento_serie", sa.String(length=60), nullable=True),
        sa.Column("equipamento_apelido", sa.String(length=120), nullable=True),
        sa.Column("piloto", sa.String(length=200), nullable=True),
        sa.Column("lugar", sa.String(length=400), nullable=True),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["aircraft_id"],
            ["agro_aircraft.id"],
            name=op.f("fk_agro_flight_aircraft_id_agro_aircraft"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["agro_operational_plan.id"],
            name=op.f("fk_agro_flight_plan_id_agro_operational_plan"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_agro_flight_tenant_id_tenant"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agro_flight")),
        # Reimportar o mesmo arquivo não duplica hora de voo. A chave é o instante que está
        # no arquivo, e não o convertido: a conversão de fuso é escolha de quem confirma.
        sa.UniqueConstraint(
            "tenant_id",
            "equipamento_serie",
            "comecou_em_arquivo",
            name="uq_agro_flight_tenant_id_equipamento_serie_comecou_em_arquivo",
        ),
    )
    op.create_index(op.f("ix_agro_flight_tenant_id"), "agro_flight", ["tenant_id"], unique=False)
    # O horímetro é uma soma por aeronave, e é a consulta mais frequente desta tabela.
    op.create_index(
        "ix_agro_flight_tenant_id_aircraft_id",
        "agro_flight",
        ["tenant_id", "aircraft_id"],
        unique=False,
    )

    # A tabela nova entra com o mesmo isolamento das outras do módulo. Sem política, uma
    # empresa enxergaria o voo da outra — e o teste de isolamento do agro acusa.
    op.execute("ALTER TABLE agro_flight ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE agro_flight FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON agro_flight
        FOR ALL
        USING (tenant_id = NULLIF(current_setting('decko.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('decko.tenant_id', true), '')::uuid)
        """
    )


def downgrade() -> None:
    op.drop_index("ix_agro_flight_tenant_id_aircraft_id", table_name="agro_flight")
    op.drop_index(op.f("ix_agro_flight_tenant_id"), table_name="agro_flight")
    op.drop_table("agro_flight")
