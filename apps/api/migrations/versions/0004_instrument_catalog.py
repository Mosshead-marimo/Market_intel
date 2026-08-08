"""Create the canonical multi-exchange instrument catalog."""

from uuid import UUID

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from tradesentinel.modules.instrument_resolution.seed import SEED_EXCHANGES, SEED_INSTRUMENTS
from tradesentinel.modules.instrument_resolution.service import normalize

revision = "0004_instrument_catalog"
down_revision = "0003_chat_worker_leases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS market")
    exchanges = op.create_table(
        "exchanges",
        sa.Column("code", sa.String(20), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("country", sa.String(2), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("currency", sa.String(12), nullable=False),
        schema="market",
    )
    instruments = op.create_table(
        "instruments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("normalized_symbol", sa.String(64), nullable=False),
        sa.Column("name", sa.String(240), nullable=False),
        sa.Column("normalized_name", sa.String(240), nullable=False),
        sa.Column("exchange_code", sa.String(20), nullable=False),
        sa.Column("asset_type", sa.String(32), nullable=False),
        sa.Column("currency", sa.String(12), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("catalog_source", sa.String(80), nullable=False),
        sa.ForeignKeyConstraint(["exchange_code"], ["market.exchanges.code"]),
        sa.UniqueConstraint("exchange_code", "symbol", name="uq_instruments_exchange_symbol"),
        schema="market",
    )
    aliases = op.create_table(
        "instrument_aliases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("alias", sa.String(240), nullable=False),
        sa.Column("normalized_alias", sa.String(240), nullable=False),
        sa.Column("alias_type", sa.String(32), nullable=False, server_default="common_name"),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["instrument_id"], ["market.instruments.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "instrument_id", "normalized_alias", name="uq_instrument_alias_normalized"
        ),
        schema="market",
    )
    op.create_index(
        "ix_instruments_normalized_symbol",
        "instruments",
        ["normalized_symbol"],
        schema="market",
    )
    op.create_index(
        "ix_instruments_normalized_name",
        "instruments",
        ["normalized_name"],
        schema="market",
    )
    op.create_index(
        "ix_instruments_exchange_asset_active",
        "instruments",
        ["exchange_code", "asset_type", "active"],
        schema="market",
    )
    op.create_index(
        "ix_instrument_aliases_normalized_alias",
        "instrument_aliases",
        ["normalized_alias"],
        schema="market",
    )

    op.bulk_insert(
        exchanges,
        [
            {
                "code": exchange.code,
                "name": exchange.name,
                "country": exchange.country,
                "timezone": exchange.timezone,
                "currency": exchange.currency,
            }
            for exchange in SEED_EXCHANGES
        ],
    )
    op.bulk_insert(
        instruments,
        [
            {
                "id": instrument.instrument_id,
                "symbol": instrument.symbol,
                "normalized_symbol": normalize(instrument.symbol),
                "name": instrument.name,
                "normalized_name": normalize(instrument.name),
                "exchange_code": instrument.exchange,
                "asset_type": instrument.asset_type.value,
                "currency": instrument.currency,
                "active": True,
                "catalog_source": "builtin_seed_v1",
            }
            for instrument in SEED_INSTRUMENTS
        ],
    )
    alias_rows: list[dict[str, object]] = []
    alias_number = 1
    for instrument in SEED_INSTRUMENTS:
        for position, alias in enumerate(instrument.aliases):
            alias_rows.append(
                {
                    "id": UUID(f"00000000-0000-4000-9000-{alias_number:012d}"),
                    "instrument_id": instrument.instrument_id,
                    "alias": alias,
                    "normalized_alias": normalize(alias),
                    "alias_type": "identifier" if alias.isdigit() else "common_name",
                    "position": position,
                }
            )
            alias_number += 1
    op.bulk_insert(aliases, alias_rows)


def downgrade() -> None:
    op.drop_index(
        "ix_instrument_aliases_normalized_alias",
        table_name="instrument_aliases",
        schema="market",
    )
    op.drop_index(
        "ix_instruments_exchange_asset_active",
        table_name="instruments",
        schema="market",
    )
    op.drop_index("ix_instruments_normalized_name", table_name="instruments", schema="market")
    op.drop_index("ix_instruments_normalized_symbol", table_name="instruments", schema="market")
    op.drop_table("instrument_aliases", schema="market")
    op.drop_table("instruments", schema="market")
    op.drop_table("exchanges", schema="market")
    op.execute("DROP SCHEMA market")
