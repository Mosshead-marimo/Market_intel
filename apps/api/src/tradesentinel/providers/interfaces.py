from __future__ import annotations

from abc import ABC, abstractmethod

from tradesentinel.providers.contracts import (
    CompanyProfile,
    CompanyProfileRequest,
    CorporateActions,
    CorporateActionsRequest,
    EconomicObservationSeries,
    EconomicObservationsRequest,
    EconomicSeries,
    EconomicSeriesSearchRequest,
    FinancialStatement,
    FinancialStatementsRequest,
    FundamentalFact,
    FundamentalFactsRequest,
    InstrumentRecord,
    InstrumentSearchRequest,
    MarketQuote,
    NewsArticle,
    NewsDocument,
    NewsDocumentRequest,
    NewsSearchRequest,
    PriceHistory,
    PriceHistoryRequest,
    ProviderContext,
    QuoteRequest,
    SentimentObservation,
    SentimentRequest,
)


class MarketDataProvider(ABC):
    @abstractmethod
    async def search_instruments(
        self, context: ProviderContext, request: InstrumentSearchRequest
    ) -> tuple[InstrumentRecord, ...]: ...

    @abstractmethod
    async def get_quote(self, context: ProviderContext, request: QuoteRequest) -> MarketQuote: ...

    @abstractmethod
    async def get_history(
        self, context: ProviderContext, request: PriceHistoryRequest
    ) -> PriceHistory: ...

    @abstractmethod
    async def get_corporate_actions(
        self, context: ProviderContext, request: CorporateActionsRequest
    ) -> CorporateActions: ...


class NewsProvider(ABC):
    @abstractmethod
    async def search(
        self, context: ProviderContext, request: NewsSearchRequest
    ) -> tuple[NewsArticle, ...]: ...

    @abstractmethod
    async def get_document(
        self, context: ProviderContext, request: NewsDocumentRequest
    ) -> NewsDocument: ...


class SentimentProvider(ABC):
    @abstractmethod
    async def collect(
        self, context: ProviderContext, request: SentimentRequest
    ) -> tuple[SentimentObservation, ...]: ...


class EconomicDataProvider(ABC):
    @abstractmethod
    async def search_series(
        self, context: ProviderContext, request: EconomicSeriesSearchRequest
    ) -> tuple[EconomicSeries, ...]: ...

    @abstractmethod
    async def get_observations(
        self, context: ProviderContext, request: EconomicObservationsRequest
    ) -> EconomicObservationSeries: ...


class FundamentalsProvider(ABC):
    @abstractmethod
    async def get_company_profile(
        self, context: ProviderContext, request: CompanyProfileRequest
    ) -> CompanyProfile: ...

    @abstractmethod
    async def get_financial_statements(
        self, context: ProviderContext, request: FinancialStatementsRequest
    ) -> tuple[FinancialStatement, ...]: ...

    @abstractmethod
    async def get_fundamental_facts(
        self, context: ProviderContext, request: FundamentalFactsRequest
    ) -> tuple[FundamentalFact, ...]: ...
