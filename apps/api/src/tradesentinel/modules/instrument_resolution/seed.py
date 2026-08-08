from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from tradesentinel.domain.instruments import AssetType, InstrumentRef


@dataclass(frozen=True)
class SeedExchange:
    code: str
    name: str
    country: str
    timezone: str
    currency: str


@dataclass(frozen=True)
class SeedInstrument:
    instrument_id: UUID
    symbol: str
    name: str
    exchange: str
    asset_type: AssetType
    currency: str
    aliases: tuple[str, ...]

    def to_ref(self) -> InstrumentRef:
        return InstrumentRef(
            instrument_id=self.instrument_id,
            symbol=self.symbol,
            name=self.name,
            exchange=self.exchange,
            asset_type=self.asset_type,
            currency=self.currency,
            aliases=self.aliases,
        )


SEED_EXCHANGES = (
    SeedExchange("NSE", "National Stock Exchange of India", "IN", "Asia/Kolkata", "INR"),
    SeedExchange("BSE", "BSE Limited", "IN", "Asia/Kolkata", "INR"),
    SeedExchange("NASDAQ", "Nasdaq Stock Market", "US", "America/New_York", "USD"),
    SeedExchange("NYSE", "New York Stock Exchange", "US", "America/New_York", "USD"),
)


def _seed(
    number: int, symbol: str, name: str, exchange: str, currency: str, *aliases: str
) -> SeedInstrument:
    return SeedInstrument(
        instrument_id=UUID(f"00000000-0000-4000-8000-{number:012d}"),
        symbol=symbol,
        name=name,
        exchange=exchange,
        asset_type=AssetType.EQUITY,
        currency=currency,
        aliases=aliases,
    )


SEED_INSTRUMENTS = (
    _seed(
        1,
        "TCS",
        "Tata Consultancy Services Limited",
        "NSE",
        "INR",
        "Tata Consultancy Services",
        "Tata Consultancy",
        "TCS Limited",
    ),
    _seed(2, "INFY", "Infosys Limited", "NSE", "INR", "Infosys", "Infosys Ltd"),
    _seed(3, "RELIANCE", "Reliance Industries Limited", "NSE", "INR", "Reliance Industries", "RIL"),
    _seed(4, "HDFCBANK", "HDFC Bank Limited", "NSE", "INR", "HDFC Bank", "HDFC"),
    _seed(
        5,
        "TCS",
        "Tata Consultancy Services Limited",
        "BSE",
        "INR",
        "532540",
        "Tata Consultancy Services",
        "Tata Consultancy",
    ),
    _seed(6, "INFY", "Infosys Limited", "BSE", "INR", "500209", "Infosys", "Infosys Ltd"),
    _seed(
        7,
        "RELIANCE",
        "Reliance Industries Limited",
        "BSE",
        "INR",
        "500325",
        "Reliance Industries",
        "RIL",
    ),
    _seed(8, "HDFCBANK", "HDFC Bank Limited", "BSE", "INR", "500180", "HDFC Bank", "HDFC"),
    _seed(9, "AAPL", "Apple Inc.", "NASDAQ", "USD", "Apple", "Apple Computer"),
    _seed(10, "MSFT", "Microsoft Corporation", "NASDAQ", "USD", "Microsoft"),
    _seed(11, "GOOGL", "Alphabet Inc.", "NASDAQ", "USD", "Alphabet", "Google"),
    _seed(12, "AMZN", "Amazon.com, Inc.", "NASDAQ", "USD", "Amazon", "Amazon.com"),
    _seed(
        13,
        "IBM",
        "International Business Machines Corporation",
        "NYSE",
        "USD",
        "International Business Machines",
        "Big Blue",
    ),
    _seed(14, "JPM", "JPMorgan Chase & Co.", "NYSE", "USD", "JPMorgan Chase", "JP Morgan"),
    _seed(15, "KO", "The Coca-Cola Company", "NYSE", "USD", "Coca-Cola", "Coke"),
    _seed(16, "DIS", "The Walt Disney Company", "NYSE", "USD", "Walt Disney", "Disney"),
)
