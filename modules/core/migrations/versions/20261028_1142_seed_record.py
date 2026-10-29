"""seed record

Identidade estável do dado-semente, por empresa.
Decisão: docs/adr/0010-dado-semente-com-identidade-estavel.md

Revision ID: 7c4e1b9a2f03
Revises: 31a827ed5da2
Create Date: 2026-10-28 11:42:10.118204
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7c4e1b9a2f03"
down_revision: str | None = "31a827ed5da2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Precisa coincidir com decko.tenancy.TENANT_GUC.
TENANT_GUC = "decko.tenant_id"
_PREDICATE = f"tenant_id = NULLIF(current_setting('{TENANT_GUC}', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "seed_record",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("module_name", sa.String(length=60), nullable=False),
        sa.Column("ref", sa.String(length=120), nullable=False),
        sa.Column("table_name", sa.String(length=63), nullable=False),
        sa.Column("row_id", sa.UUID(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.Enum("ativo", "removido", name="seed_status"),
            nullable=False,
        ),
        sa.Column(
            "seeded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_seed_record_tenant_id_tenant"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_seed_record")),
        sa.UniqueConstraint(
            "tenant_id",
            "module_name",
            "ref",
            name="uq_seed_record_tenant_id_module_name_ref",
        ),
    )
    op.create_index(op.f("ix_seed_record_tenant_id"), "seed_record", ["tenant_id"], unique=False)

    # Mesma proteção das demais tabelas de empresa. Aqui ela também evita um vazamento
    # discreto: saber que módulos semearam o quê é informação da composição comercial.
    op.execute("ALTER TABLE seed_record ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE seed_record FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation ON seed_record
        FOR ALL
        USING ({_PREDICATE})
        WITH CHECK ({_PREDICATE})
        """
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_seed_record_tenant_id"), table_name="seed_record")
    op.drop_table("seed_record")
    op.execute("DROP TYPE seed_status")
