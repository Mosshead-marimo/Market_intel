"""Create immutable point-in-time prediction engine storage."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008_prediction_engine"
down_revision = "0007_llm_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS prediction")
    op.create_table(
        "feature_observations",
        sa.Column("idempotency_key", sa.String(160), primary_key=True),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        schema="prediction",
    )
    op.create_index(
        "ix_prediction_observations_instrument",
        "feature_observations",
        ["instrument_id"],
        schema="prediction",
    )
    op.create_table(
        "dataset_versions",
        sa.Column("dataset_version", sa.String(160), primary_key=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        schema="prediction",
    )
    op.create_table(
        "feature_vectors",
        sa.Column("vector_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "dataset_version",
            sa.String(160),
            sa.ForeignKey("prediction.dataset_versions.dataset_version"),
            nullable=False,
        ),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cutoff", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False, unique=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        schema="prediction",
    )
    op.create_table(
        "labels",
        sa.Column(
            "vector_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("prediction.feature_vectors.vector_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("definition_version", sa.String(120), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        schema="prediction",
    )
    op.create_table(
        "jobs",
        sa.Column("job_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("idempotency_key", sa.String(160), nullable=False, unique=True),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_owner", sa.String(160), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(120), nullable=True),
        schema="prediction",
    )
    op.create_index(
        "ix_prediction_jobs_status_created", "jobs", ["status", "created_at"], schema="prediction"
    )
    op.create_table(
        "outbox",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("prediction.jobs.job_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_name", sa.String(160), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        schema="prediction",
    )
    op.create_table(
        "dead_letters",
        sa.Column("job_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("failure_code", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        schema="prediction",
    )
    op.create_table(
        "model_versions",
        sa.Column("model_version", sa.String(160), primary_key=True),
        sa.Column("horizon_sessions", sa.Integer(), nullable=False),
        sa.Column("asset_type", sa.String(80), nullable=False),
        sa.Column("universe", sa.String(120), nullable=False),
        sa.Column("profile_key", sa.String(240), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        schema="prediction",
    )
    op.create_index(
        "ix_prediction_models_lookup",
        "model_versions",
        ["horizon_sessions", "asset_type", "universe", "profile_key", "active"],
        schema="prediction",
    )
    op.create_table(
        "model_metrics",
        sa.Column(
            "model_version",
            sa.String(160),
            sa.ForeignKey("prediction.model_versions.model_version", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("metrics", postgresql.JSONB(), nullable=False),
        schema="prediction",
    )
    op.create_table(
        "model_activations",
        sa.Column("activation_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "model_version",
            sa.String(160),
            sa.ForeignKey("prediction.model_versions.model_version"),
            nullable=False,
        ),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_by", sa.String(160), nullable=False),
        schema="prediction",
    )
    op.create_table(
        "predictions",
        sa.Column("prediction_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        schema="prediction",
    )
    op.create_index(
        "ix_prediction_history",
        "predictions",
        ["instrument_id", "generated_at"],
        schema="prediction",
    )
    op.create_table(
        "prediction_features",
        sa.Column(
            "prediction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("prediction.predictions.prediction_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("feature_fingerprint", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        schema="prediction",
    )
    op.create_table(
        "prediction_scenarios",
        sa.Column(
            "prediction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("prediction.predictions.prediction_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        schema="prediction",
    )
    op.create_table(
        "prediction_outcomes",
        sa.Column(
            "prediction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("prediction.predictions.prediction_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        schema="prediction",
    )


def downgrade() -> None:
    for table in (
        "prediction_outcomes",
        "prediction_scenarios",
        "prediction_features",
        "predictions",
        "model_activations",
        "model_metrics",
        "model_versions",
        "dead_letters",
        "outbox",
        "jobs",
        "labels",
        "feature_vectors",
        "dataset_versions",
        "feature_observations",
    ):
        op.drop_table(table, schema="prediction")
    op.execute("DROP SCHEMA prediction")
