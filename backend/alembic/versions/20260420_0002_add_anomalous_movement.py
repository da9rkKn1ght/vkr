"""add_anomalous_movement

Revision ID: 20260420_0002
Revises: 20260417_0001
Create Date: 2026-04-20 12:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260420_0002"
down_revision = "20260417_0001"
branch_labels = None
depends_on = None


OLD_INCIDENT_ENUM = sa.Enum(
    "sleep",
    "absence",
    "phone",
    "smoking",
    name="incident_type",
    native_enum=False,
    create_constraint=True,
)

NEW_INCIDENT_ENUM = sa.Enum(
    "sleep",
    "absence",
    "phone",
    "smoking",
    "anomalous_movement",
    name="incident_type",
    native_enum=False,
    create_constraint=True,
)


def upgrade() -> None:
    with op.batch_alter_table("incidents", recreate="always") as batch_op:
        batch_op.alter_column(
            "type",
            existing_type=OLD_INCIDENT_ENUM,
            type_=NEW_INCIDENT_ENUM,
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("incidents", recreate="always") as batch_op:
        batch_op.alter_column(
            "type",
            existing_type=NEW_INCIDENT_ENUM,
            type_=OLD_INCIDENT_ENUM,
            existing_nullable=False,
        )

