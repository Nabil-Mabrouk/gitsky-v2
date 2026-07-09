"""security: create security_events table

Revision ID: 0001_security_events
Revises:
Create Date: 2026-07-09

Chaîne du module security. Crée `security_events` (journal d'intrusion, Chap 14).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_security_events"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "security_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("ip_address", sa.String(), nullable=True),
        sa.Column("path", sa.String(), nullable=True),
        sa.Column("user_agent", sa.String(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_security_events_id", "security_events", ["id"], unique=False)
    op.create_index(
        "ix_security_events_event_type", "security_events", ["event_type"], unique=False
    )
    op.create_index(
        "ix_security_events_severity", "security_events", ["severity"], unique=False
    )
    op.create_index(
        "ix_security_events_ip_address", "security_events", ["ip_address"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_security_events_ip_address", table_name="security_events")
    op.drop_index("ix_security_events_severity", table_name="security_events")
    op.drop_index("ix_security_events_event_type", table_name="security_events")
    op.drop_index("ix_security_events_id", table_name="security_events")
    op.drop_table("security_events")
