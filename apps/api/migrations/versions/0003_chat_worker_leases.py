"""Add recoverable worker leases to durable chat turns."""

import sqlalchemy as sa
from alembic import op

revision = "0003_chat_worker_leases"
down_revision = "0002_chat_runtime"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chat_turns",
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        schema="core",
    )
    op.add_column(
        "chat_turns",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        schema="core",
    )


def downgrade() -> None:
    op.drop_column("chat_turns", "lease_expires_at", schema="core")
    op.drop_column("chat_turns", "attempt", schema="core")
