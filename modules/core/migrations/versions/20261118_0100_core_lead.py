"""lead da pagina publica

Revision ID: f7b21c604ae9
Revises: c93b7e14f25d
Create Date: 2026-11-18 01:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f7b21c604ae9"
down_revision: str | None = "c93b7e14f25d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "core_lead",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("nome", sa.String(length=200), nullable=False),
        sa.Column("empresa", sa.String(length=200), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("telefone", sa.String(length=30), nullable=True),
        sa.Column("segmento", sa.String(length=80), nullable=True),
        sa.Column("mensagem", sa.Text(), nullable=True),
        sa.Column("origem", sa.String(length=200), nullable=True),
        sa.Column("consentimento_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.Column("atendido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("observacao", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_core_lead")),
    )
    # A conferência de enxurrada consulta por IP e hora; sem índice ela varre a tabela a
    # cada envio do formulário, que é justamente o caminho que um robô repete.
    op.create_index(
        "ix_core_lead_ip_created_at", "core_lead", ["ip", "created_at"], unique=False
    )
    # Nenhuma política de isolamento aqui, e isso é deliberado: `core_lead` vive fora da
    # fronteira de empresa, como `tenant` — um lead ainda não é empresa nenhuma. Quem o lê
    # é o nível de plataforma, conferido na borda (`require_platform_admin`).


def downgrade() -> None:
    op.drop_index("ix_core_lead_ip_created_at", table_name="core_lead")
    op.drop_table("core_lead")
