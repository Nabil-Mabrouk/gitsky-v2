"""core: users.token_version (révocation des refresh tokens)

Revision ID: 0002_core_token_version
Revises: 0001_core_users
Create Date: 2026-07-19

Durcissement Chap 7 : un refresh JWT stateless volé restait valable 7 jours
sans aucun levier de révocation. Le refresh embarque désormais un claim `tv`
comparé à cette colonne ; l'incrémenter (logout-all) invalide tous les refresh
émis pour le compte.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_core_token_version"
down_revision: Union[str, None] = "0001_core_users"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("users", "token_version")
