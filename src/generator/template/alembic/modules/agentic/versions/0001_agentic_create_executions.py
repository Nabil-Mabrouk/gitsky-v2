"""agentic: create service_executions table

Revision ID: 0001_agentic_executions
Revises:
Create Date: 2026-07-09

Chaîne du module agentic. Crée `service_executions` (traçabilité des exécutions,
Chap 15). La table `users` est créée par la chaîne core (appliquée avant).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_agentic_executions"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "service_executions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("service_slug", sa.String(), nullable=False),
        sa.Column("workflow_name", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("input_params", sa.JSON(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_service_executions_id", "service_executions", ["id"], unique=False
    )
    op.create_index(
        "ix_service_executions_user_id", "service_executions", ["user_id"], unique=False
    )
    op.create_index(
        "ix_service_executions_service_slug",
        "service_executions",
        ["service_slug"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_service_executions_service_slug", table_name="service_executions")
    op.drop_index("ix_service_executions_user_id", table_name="service_executions")
    op.drop_index("ix_service_executions_id", table_name="service_executions")
    op.drop_table("service_executions")
