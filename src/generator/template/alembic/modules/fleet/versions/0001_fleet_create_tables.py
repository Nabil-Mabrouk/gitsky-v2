"""fleet: create fleet_projects and fleet_lifecycle_events

Revision ID: 0001_fleet_tables
Revises:
Create Date: 2026-07-10

Chaîne du module fleet (Chap 19/20) : registre des projets + journal de vie.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_fleet_tables"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fleet_projects",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("tier", sa.String(), nullable=False),
        sa.Column("domain", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("template_version", sa.String(), nullable=True),
        sa.Column("first_deployed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_fleet_projects_id", "fleet_projects", ["id"], unique=False)
    op.create_index("ix_fleet_projects_name", "fleet_projects", ["name"], unique=True)

    op.create_table(
        "fleet_lifecycle_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_name", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("tier", sa.String(), nullable=True),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_fleet_lifecycle_events_id", "fleet_lifecycle_events", ["id"], unique=False
    )
    op.create_index(
        "ix_fleet_lifecycle_events_project_name",
        "fleet_lifecycle_events",
        ["project_name"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_fleet_lifecycle_events_project_name", table_name="fleet_lifecycle_events")
    op.drop_index("ix_fleet_lifecycle_events_id", table_name="fleet_lifecycle_events")
    op.drop_table("fleet_lifecycle_events")
    op.drop_index("ix_fleet_projects_name", table_name="fleet_projects")
    op.drop_index("ix_fleet_projects_id", table_name="fleet_projects")
    op.drop_table("fleet_projects")
