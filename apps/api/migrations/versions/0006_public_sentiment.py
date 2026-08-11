"""Create privacy-bounded public sentiment storage."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006_public_sentiment"
down_revision = "0005_research_events"
branch_labels = None
depends_on = None


def _derived_table(name: str) -> None:
    op.create_table(
        name,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        schema="sentiment",
    )


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS sentiment")
    op.create_table(
        "discussions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider", sa.String(120), nullable=False),
        sa.Column("provider_source_id", sa.String(500), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("author_hash", sa.String(64), nullable=True),
        sa.Column("text_excerpt", sa.String(2000), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint(
            "provider", "provider_source_id", name="uq_sentiment_discussion_source"
        ),
        schema="sentiment",
    )
    for name in (
        "spam_decisions",
        "company_mentions",
        "source_weights",
        "snapshots",
        "narratives",
        "trends",
        "shifts",
    ):
        _derived_table(name)
    op.create_index(
        "ix_sentiment_discussions_occurred", "discussions", ["occurred_at"], schema="sentiment"
    )
    op.create_index(
        "ix_sentiment_discussions_content_hash", "discussions", ["content_hash"], schema="sentiment"
    )


def downgrade() -> None:
    op.drop_index(
        "ix_sentiment_discussions_content_hash", table_name="discussions", schema="sentiment"
    )
    op.drop_index("ix_sentiment_discussions_occurred", table_name="discussions", schema="sentiment")
    for name in reversed(
        (
            "spam_decisions",
            "company_mentions",
            "source_weights",
            "snapshots",
            "narratives",
            "trends",
            "shifts",
        )
    ):
        op.drop_table(name, schema="sentiment")
    op.drop_table("discussions", schema="sentiment")
    op.execute("DROP SCHEMA sentiment")
