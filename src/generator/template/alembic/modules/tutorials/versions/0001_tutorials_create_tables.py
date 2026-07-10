"""tutorials: create tutorials and lessons tables

Revision ID: 0001_tutorials_tables
Revises:
Create Date: 2026-07-09

Chaîne du module tutorials. Crée `tutorials` et `lessons` (One-to-Many, Chap 4).
L'enum `userrole` est déjà créé par la chaîne core -> create_type=False pour ne
pas tenter de le recréer sous PostgreSQL.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_tutorials_tables"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_userrole = sa.Enum(
    "anonymous", "waitlist", "user", "premium", "admin",
    name="userrole",
    create_type=False,
)


def upgrade() -> None:
    op.create_table(
        "tutorials",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("lang", sa.String(length=5), nullable=False),
        sa.Column("access_role", _userrole, nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tutorials_id", "tutorials", ["id"], unique=False)
    op.create_index("ix_tutorials_slug", "tutorials", ["slug"], unique=True)
    op.create_index("ix_tutorials_lang", "tutorials", ["lang"], unique=False)

    op.create_table(
        "lessons",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tutorial_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["tutorial_id"], ["tutorials.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lessons_id", "lessons", ["id"], unique=False)
    op.create_index("ix_lessons_tutorial_id", "lessons", ["tutorial_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_lessons_tutorial_id", table_name="lessons")
    op.drop_index("ix_lessons_id", table_name="lessons")
    op.drop_table("lessons")
    op.drop_index("ix_tutorials_lang", table_name="tutorials")
    op.drop_index("ix_tutorials_slug", table_name="tutorials")
    op.drop_index("ix_tutorials_id", table_name="tutorials")
    op.drop_table("tutorials")
