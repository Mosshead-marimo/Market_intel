"""Add durable chat turns, streaming state, and transactional outbox."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_chat_runtime"
down_revision = "0001_platform_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chat_sessions",
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        schema="core",
    )
    op.add_column(
        "chat_sessions",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        schema="core",
    )
    op.create_index(
        "ix_chat_sessions_principal_status_updated",
        "chat_sessions",
        ["principal_id", "status", "updated_at"],
        schema="core",
    )

    op.add_column(
        "chat_messages",
        sa.Column("turn_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema="core",
    )
    op.add_column(
        "chat_messages",
        sa.Column("sequence", sa.Integer(), nullable=True),
        schema="core",
    )
    op.add_column(
        "chat_messages",
        sa.Column("status", sa.String(32), nullable=False, server_default="completed"),
        schema="core",
    )
    op.add_column(
        "chat_messages",
        sa.Column("rendered_response", postgresql.JSONB(), nullable=True),
        schema="core",
    )
    op.add_column(
        "chat_messages",
        sa.Column("error", postgresql.JSONB(), nullable=True),
        schema="core",
    )
    op.add_column(
        "chat_messages",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        schema="core",
    )
    op.execute("UPDATE core.chat_messages SET turn_id = id")
    op.execute(
        """
        WITH ordered AS (
            SELECT id, row_number() OVER (PARTITION BY session_id ORDER BY created_at, id) AS value
            FROM core.chat_messages
        )
        UPDATE core.chat_messages AS messages
        SET sequence = ordered.value
        FROM ordered
        WHERE messages.id = ordered.id
        """
    )
    op.alter_column("chat_messages", "turn_id", nullable=False, schema="core")
    op.alter_column("chat_messages", "sequence", nullable=False, schema="core")
    op.create_index(
        "ix_chat_messages_session_sequence",
        "chat_messages",
        ["session_id", "sequence"],
        unique=True,
        schema="core",
    )
    op.create_index("ix_chat_messages_turn_id", "chat_messages", ["turn_id"], schema="core")

    op.create_table(
        "chat_turns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("principal_id", sa.String(160), nullable=False),
        sa.Column("client_message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assistant_message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("error", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["core.chat_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_message_id"], ["core.chat_messages.id"]),
        sa.ForeignKeyConstraint(["assistant_message_id"], ["core.chat_messages.id"]),
        sa.UniqueConstraint(
            "principal_id", "client_message_id", name="uq_chat_turn_client_message"
        ),
        schema="core",
    )
    op.create_index("ix_chat_turns_principal_id", "chat_turns", ["principal_id"], schema="core")
    op.create_index("ix_chat_turns_session_id", "chat_turns", ["session_id"], schema="core")
    op.create_index("ix_chat_turns_status", "chat_turns", ["status"], schema="core")
    op.create_index(
        "uq_chat_turn_active_session",
        "chat_turns",
        ["session_id"],
        unique=True,
        schema="core",
        postgresql_where=sa.text("status IN ('queued', 'planning', 'executing', 'rendering')"),
    )

    op.create_table(
        "chat_outbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("turn_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["turn_id"], ["core.chat_turns.id"], ondelete="CASCADE"),
        schema="core",
    )
    op.create_index("ix_chat_outbox_published_at", "chat_outbox", ["published_at"], schema="core")


def downgrade() -> None:
    op.drop_index("ix_chat_outbox_published_at", table_name="chat_outbox", schema="core")
    op.drop_table("chat_outbox", schema="core")
    op.drop_index("uq_chat_turn_active_session", table_name="chat_turns", schema="core")
    op.drop_index("ix_chat_turns_status", table_name="chat_turns", schema="core")
    op.drop_index("ix_chat_turns_session_id", table_name="chat_turns", schema="core")
    op.drop_index("ix_chat_turns_principal_id", table_name="chat_turns", schema="core")
    op.drop_table("chat_turns", schema="core")

    op.drop_index("ix_chat_messages_turn_id", table_name="chat_messages", schema="core")
    op.drop_index("ix_chat_messages_session_sequence", table_name="chat_messages", schema="core")
    for column in (
        "completed_at",
        "error",
        "rendered_response",
        "status",
        "sequence",
        "turn_id",
    ):
        op.drop_column("chat_messages", column, schema="core")

    op.drop_index(
        "ix_chat_sessions_principal_status_updated", table_name="chat_sessions", schema="core"
    )
    op.drop_column("chat_sessions", "archived_at", schema="core")
    op.drop_column("chat_sessions", "status", schema="core")
