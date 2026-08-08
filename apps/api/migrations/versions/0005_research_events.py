"""Create normalized research evidence and event storage."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005_research_events"
down_revision = "0004_instrument_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS research")
    op.create_table(
        "sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider", sa.String(120), nullable=False),
        sa.Column("provider_source_id", sa.String(500), nullable=False),
        sa.Column("title", sa.String(1000), nullable=False),
        sa.Column("url", sa.String(2000), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("document_hash", sa.String(64), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint(
            "provider", "provider_source_id", name="uq_research_source_provider_id"
        ),
        schema="research",
    )
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("content_type", sa.String(120), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["research.sources.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("source_id", "content_hash", name="uq_research_document_hash"),
        schema="research",
    )
    op.create_table(
        "events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("fingerprint", sa.String(64), nullable=False, unique=True),
        sa.Column("query", sa.String(500), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_research_event_confidence"
        ),
        schema="research",
    )
    op.create_table(
        "event_sources",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.ForeignKeyConstraint(["event_id"], ["research.events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["research.sources.id"], ondelete="CASCADE"),
        schema="research",
    )
    op.create_table(
        "claims",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(120), nullable=False),
        sa.Column("evidence_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["research.events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["research.sources.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_research_claim_confidence"
        ),
        schema="research",
    )
    op.create_index("ix_research_sources_url", "sources", ["url"], schema="research")
    op.create_index(
        "ix_research_events_query_observed", "events", ["query", "observed_at"], schema="research"
    )
    op.create_index("ix_research_claims_event", "claims", ["event_id"], schema="research")


def downgrade() -> None:
    op.drop_index("ix_research_claims_event", table_name="claims", schema="research")
    op.drop_index("ix_research_events_query_observed", table_name="events", schema="research")
    op.drop_index("ix_research_sources_url", table_name="sources", schema="research")
    op.drop_table("claims", schema="research")
    op.drop_table("event_sources", schema="research")
    op.drop_table("events", schema="research")
    op.drop_table("documents", schema="research")
    op.drop_table("sources", schema="research")
    op.execute("DROP SCHEMA research")
