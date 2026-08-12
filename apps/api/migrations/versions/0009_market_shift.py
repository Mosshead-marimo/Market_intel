"""Create immutable Market Shift evidence and history storage."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009_market_shift"
down_revision = "0008_prediction_engine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS market_shift")
    op.create_table(
        "observations",
        sa.Column("observation_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("idempotency_key", sa.String(160), nullable=False, unique=True),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("scope", sa.String(160), nullable=False),
        sa.Column("metric", sa.String(160), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("known_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        schema="market_shift",
    )
    op.create_index(
        "ix_market_shift_observation_lookup",
        "observations",
        ["instrument_id", "category", "metric", "observed_at"],
        schema="market_shift",
    )
    op.create_table(
        "calculations",
        sa.Column("calculation_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("idempotency_key", sa.String(160), nullable=False, unique=True),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        schema="market_shift",
    )
    op.create_index(
        "ix_market_shift_history",
        "calculations",
        ["instrument_id", "completed_at"],
        schema="market_shift",
    )
    for table_name in (
        "category_contributions",
        "evidence_links",
        "catalysts",
        "risks",
        "narratives",
    ):
        op.create_table(
            table_name,
            sa.Column("record_id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "calculation_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("market_shift.calculations.calculation_id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("position", sa.Integer(), nullable=False),
            sa.Column("payload", postgresql.JSONB(), nullable=False),
            sa.UniqueConstraint(
                "calculation_id",
                "position",
                name=f"uq_market_shift_{table_name}_position",
            ),
            schema="market_shift",
        )
    op.create_table(
        "watchlist",
        sa.Column("watchlist_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_owner", sa.String(160), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        schema="market_shift",
    )
    op.create_index(
        "ix_market_shift_watchlist_due",
        "watchlist",
        ["enabled", "next_run_at"],
        schema="market_shift",
    )
    op.create_table(
        "schedule_runs",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "watchlist_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("market_shift.watchlist.watchlist_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("error_code", sa.String(120), nullable=True),
        schema="market_shift",
    )


def downgrade() -> None:
    op.drop_table("schedule_runs", schema="market_shift")
    op.drop_index("ix_market_shift_watchlist_due", table_name="watchlist", schema="market_shift")
    op.drop_table("watchlist", schema="market_shift")
    for table_name in (
        "narratives",
        "risks",
        "catalysts",
        "evidence_links",
        "category_contributions",
    ):
        op.drop_table(table_name, schema="market_shift")
    op.drop_index("ix_market_shift_history", table_name="calculations", schema="market_shift")
    op.drop_table("calculations", schema="market_shift")
    op.drop_index(
        "ix_market_shift_observation_lookup",
        table_name="observations",
        schema="market_shift",
    )
    op.drop_table("observations", schema="market_shift")
    op.execute("DROP SCHEMA IF EXISTS market_shift")
