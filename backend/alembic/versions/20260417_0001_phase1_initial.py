"""phase1_initial

Revision ID: 20260417_0001
Revises:
Create Date: 2026-04-17 20:00:00
"""

from __future__ import annotations

import hashlib
import os
import secrets

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260417_0001"
down_revision = None
branch_labels = None
depends_on = None


def _hash_password(password: str) -> str:
    iterations = 390000
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    ).hex()
    return f"pbkdf2_sha256${iterations}${salt}${digest}"


def upgrade() -> None:
    user_role_enum = sa.Enum(
        "admin",
        "manager",
        name="user_role",
        native_enum=False,
        create_constraint=True,
    )
    incident_type_enum = sa.Enum(
        "sleep",
        "absence",
        "phone",
        "smoking",
        name="incident_type",
        native_enum=False,
        create_constraint=True,
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("role", user_role_enum, nullable=False),
        sa.UniqueConstraint("username", name="uq_users_username"),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=False)

    op.create_table(
        "cameras",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("rtsp_url", sa.String(length=1024), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    op.create_table(
        "zones",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("camera_id", sa.Integer(), nullable=False),
        sa.Column("coordinates", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_zones_camera_id", "zones", ["camera_id"], unique=False)

    op.create_table(
        "incidents",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("camera_id", sa.Integer(), nullable=False),
        sa.Column("type", incident_type_enum, nullable=False),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("image_path", sa.String(length=1024), nullable=False),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_incidents_camera_id", "incidents", ["camera_id"], unique=False)

    admin_username = os.getenv("ADMIN_USERNAME")
    admin_password = os.getenv("ADMIN_PASSWORD")
    if not admin_username or not admin_password:
        raise RuntimeError("ADMIN_USERNAME and ADMIN_PASSWORD must be set before running migrations.")

    users_table = sa.table(
        "users",
        sa.column("username", sa.String),
        sa.column("password_hash", sa.String),
        sa.column("role", sa.String),
    )
    op.bulk_insert(
        users_table,
        [
            {
                "username": admin_username,
                "password_hash": _hash_password(admin_password),
                "role": "admin",
            }
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_incidents_camera_id", table_name="incidents")
    op.drop_table("incidents")

    op.drop_index("ix_zones_camera_id", table_name="zones")
    op.drop_table("zones")

    op.drop_table("cameras")

    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")

