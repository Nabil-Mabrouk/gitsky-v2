"""analytics: create visits table

Revision ID: 0001_analytics_visits
Revises:
Create Date: 2026-07-09

Migration initiale de la chaîne du module analytics. Crée la table `visits`
(tracking anonymisé RGPD — ip_hash, pas d'IP en clair ; Chap 4). Chaîne
indépendante de core : sa propre table de version `alembic_version_analytics`.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_analytics_visits"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "visits",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ip_hash", sa.String(), nullable=True),
        sa.Column("country_code", sa.String(length=2), nullable=True),
        sa.Column("city", sa.String(), nullable=True),
        sa.Column("path", sa.String(), nullable=True),
        sa.Column("user_role", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_visits_ip_hash", "visits", ["ip_hash"], unique=False)
    op.create_index("ix_visits_country_code", "visits", ["country_code"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_visits_country_code", table_name="visits")
    op.drop_index("ix_visits_ip_hash", table_name="visits")
    op.drop_table("visits")
