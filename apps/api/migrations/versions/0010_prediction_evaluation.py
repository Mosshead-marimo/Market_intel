"""Add durable prediction evaluation schedules and performance aggregates."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010_prediction_evaluation"
down_revision = "0009_market_shift"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evaluation_schedules",
        sa.Column("schedule_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "prediction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("prediction.predictions.prediction_id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("state", sa.String(30), nullable=False),
        sa.Column("next_check_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_owner", sa.String(160), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        schema="prediction",
    )
    op.create_index(
        "ix_prediction_evaluation_due",
        "evaluation_schedules",
        ["state", "next_check_at", "lease_expires_at"],
        schema="prediction",
    )
    op.create_table(
        "evaluation_attempts",
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "schedule_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("prediction.evaluation_schedules.schedule_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("prediction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        schema="prediction",
    )
    op.create_index(
        "ix_prediction_evaluation_attempts",
        "evaluation_attempts",
        ["prediction_id", "completed_at"],
        schema="prediction",
    )
    op.create_table(
        "performance_aggregates",
        sa.Column("aggregate_key", sa.String(240), primary_key=True),
        sa.Column("metrics_version", sa.String(120), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        schema="prediction",
    )
    op.create_table(
        "calibration_buckets",
        sa.Column("bucket_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("aggregate_key", sa.String(240), nullable=False),
        sa.Column("class_name", sa.String(20), nullable=False),
        sa.Column("bucket_index", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint(
            "aggregate_key",
            "class_name",
            "bucket_index",
            name="uq_prediction_calibration_bucket",
        ),
        schema="prediction",
    )
    op.create_table(
        "evaluation_dead_letters",
        sa.Column("dead_letter_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("schedule_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("error_code", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        schema="prediction",
    )
    for name, column_type in (
        ("realized_adjusted_close", sa.Numeric(38, 12)),
        ("provider", sa.String(160)),
        ("source_id", sa.String(240)),
        ("observed_at", sa.DateTime(timezone=True)),
        ("market_key", sa.String(160)),
        ("sector", sa.String(160)),
    ):
        op.add_column(
            "prediction_outcomes",
            sa.Column(name, column_type, nullable=True),
            schema="prediction",
        )


def downgrade() -> None:
    for name in (
        "sector",
        "market_key",
        "observed_at",
        "source_id",
        "provider",
        "realized_adjusted_close",
    ):
        op.drop_column("prediction_outcomes", name, schema="prediction")
    op.drop_table("evaluation_dead_letters", schema="prediction")
    op.drop_table("calibration_buckets", schema="prediction")
    op.drop_table("performance_aggregates", schema="prediction")
    op.drop_index(
        "ix_prediction_evaluation_attempts",
        table_name="evaluation_attempts",
        schema="prediction",
    )
    op.drop_table("evaluation_attempts", schema="prediction")
    op.drop_index(
        "ix_prediction_evaluation_due",
        table_name="evaluation_schedules",
        schema="prediction",
    )
    op.drop_table("evaluation_schedules", schema="prediction")
