"""agentic: execution_steps + credit_accounts + cost persisté

Revision ID: 0002_agentic_steps_credits
Revises: 0001_agentic_executions
Create Date: 2026-07-19

Rattrapage (durcissement) : les modèles `ExecutionStep` et `CreditAccount`
existaient dans le code SANS migration — le dev (create_all) masquait le trou,
la prod aurait cassé au premier insert. Ajoute aussi
`service_executions.cost_credits`, le coût débité persisté qui permet à
recovery.py de rembourser les jobs tués par un redémarrage.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_agentic_steps_credits"
down_revision: Union[str, None] = "0001_agentic_executions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "execution_steps",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("execution_id", sa.Integer(), nullable=False),
        sa.Column("idx", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("output", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["execution_id"], ["service_executions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_execution_steps_id", "execution_steps", ["id"], unique=False)
    op.create_index(
        "ix_execution_steps_execution_id",
        "execution_steps",
        ["execution_id"],
        unique=False,
    )

    op.create_table(
        "credit_accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("balance", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_credit_accounts_id", "credit_accounts", ["id"], unique=False)
    op.create_index(
        "ix_credit_accounts_user_id", "credit_accounts", ["user_id"], unique=False
    )

    op.add_column(
        "service_executions",
        sa.Column(
            "cost_credits", sa.Integer(), nullable=False, server_default="0"
        ),
    )


def downgrade() -> None:
    op.drop_column("service_executions", "cost_credits")
    op.drop_index("ix_credit_accounts_user_id", table_name="credit_accounts")
    op.drop_index("ix_credit_accounts_id", table_name="credit_accounts")
    op.drop_table("credit_accounts")
    op.drop_index("ix_execution_steps_execution_id", table_name="execution_steps")
    op.drop_index("ix_execution_steps_id", table_name="execution_steps")
    op.drop_table("execution_steps")
