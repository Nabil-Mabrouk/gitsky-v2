"""onboarding: create user_profiles table

Revision ID: 0001_onboarding_profiles
Revises:
Create Date: 2026-07-09

Chaîne du module onboarding. Crée `user_profiles` (1:1 avec users, Chap 4). La
table `users` est créée par la chaîne core (appliquée avant).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_onboarding_profiles"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("flow_id", sa.String(), nullable=False),
        sa.Column("answers", sa.JSON(), nullable=True),
        sa.Column("profile", sa.String(), nullable=True),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_user_profiles_id", "user_profiles", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_user_profiles_id", table_name="user_profiles")
    op.drop_table("user_profiles")
