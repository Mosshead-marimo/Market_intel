"""Create platform-owned core and audit records."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_platform_core"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS core")
    op.execute("CREATE SCHEMA IF NOT EXISTS audit")
    op.create_table(
        "chat_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("principal_id", sa.String(160), nullable=False),
        sa.Column("title", sa.String(240), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        schema="core",
    )
    op.create_table(
        "chat_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["core.chat_sessions.id"], ondelete="CASCADE"),
        schema="core",
    )
    op.create_table(
        "workflow_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workflow", sa.String(160), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        schema="core",
    )
    op.create_table(
        "capability_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workflow_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("capability", sa.String(160), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.ForeignKeyConstraint(["workflow_run_id"], ["core.workflow_runs.id"], ondelete="CASCADE"),
        schema="core",
    )
    op.create_table(
        "workflow_steps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workflow_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("step_id", sa.String(160), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("detail", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.ForeignKeyConstraint(["workflow_run_id"], ["core.workflow_runs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("workflow_run_id", "step_id"),
        schema="core",
    )
    op.create_table(
        "event_deliveries",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("consumer", sa.String(160), primary_key=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        schema="audit",
    )
    op.create_table(
        "dead_letters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_name", sa.String(200), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=False),
        schema="audit",
    )


def downgrade() -> None:
    op.drop_table("dead_letters", schema="audit")
    op.drop_table("event_deliveries", schema="audit")
    op.drop_table("workflow_steps", schema="core")
    op.drop_table("capability_runs", schema="core")
    op.drop_table("workflow_runs", schema="core")
    op.drop_table("chat_messages", schema="core")
    op.drop_table("chat_sessions", schema="core")
    op.execute("DROP SCHEMA audit")
    op.execute("DROP SCHEMA core")
