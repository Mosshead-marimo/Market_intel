"""Create privacy-bounded LLM generation audit records."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007_llm_audit"
down_revision = "0006_public_sentiment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS assistant")
    op.create_table(
        "generations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("stage", sa.String(80), nullable=False),
        sa.Column("provider", sa.String(120), nullable=False),
        sa.Column("model", sa.String(160), nullable=False),
        sa.Column("prompt_version", sa.String(80), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("output_hash", sa.String(64), nullable=False),
        sa.Column("evidence_ids", postgresql.JSONB(), nullable=False),
        sa.Column("planned_commands", postgresql.JSONB(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("validation_attempts", sa.Integer(), nullable=False),
        sa.Column("validation_status", sa.String(40), nullable=False),
        sa.Column("failure_code", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        schema="assistant",
    )
    op.create_index(
        "ix_assistant_generations_request_id",
        "generations",
        ["request_id"],
        schema="assistant",
    )
    op.create_index(
        "ix_assistant_generations_created_at",
        "generations",
        ["created_at"],
        schema="assistant",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_assistant_generations_created_at", table_name="generations", schema="assistant"
    )
    op.drop_index(
        "ix_assistant_generations_request_id", table_name="generations", schema="assistant"
    )
    op.drop_table("generations", schema="assistant")
    op.execute("DROP SCHEMA assistant")
