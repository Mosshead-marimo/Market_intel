from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tradesentinel.providers.contracts import ProviderDescriptor, ProviderKind
from tradesentinel.providers.errors import ProviderNotFoundError, ProviderRegistryError
from tradesentinel.providers.interfaces import (
    EconomicDataProvider,
    FundamentalsProvider,
    LanguageModelProvider,
    MarketDataProvider,
    NewsProvider,
    SentimentProvider,
)

ProviderInterface = type[
    MarketDataProvider
    | NewsProvider
    | SentimentProvider
    | EconomicDataProvider
    | FundamentalsProvider
    | LanguageModelProvider
]

INTERFACE_BY_KIND: dict[ProviderKind, ProviderInterface] = {
    ProviderKind.MARKET_DATA: MarketDataProvider,
    ProviderKind.NEWS: NewsProvider,
    ProviderKind.SENTIMENT: SentimentProvider,
    ProviderKind.ECONOMIC_DATA: EconomicDataProvider,
    ProviderKind.FUNDAMENTALS: FundamentalsProvider,
    ProviderKind.LANGUAGE_MODEL: LanguageModelProvider,
}


@dataclass(frozen=True)
class ProviderRegistration:
    descriptor: ProviderDescriptor
    adapter_class: type[Any]


class ProviderRegistry:
    def __init__(self) -> None:
        self._items: dict[tuple[ProviderKind, str], ProviderRegistration] = {}

    def register(self, registration: ProviderRegistration) -> None:
        descriptor = registration.descriptor
        key = (descriptor.kind, descriptor.name)
        if key in self._items:
            raise ProviderRegistryError(
                "A provider name is registered more than once for its category.",
                {"kind": descriptor.kind.value, "provider": descriptor.name},
            )
        expected = INTERFACE_BY_KIND[descriptor.kind]
        if not issubclass(registration.adapter_class, expected):
            raise ProviderRegistryError(
                "A provider adapter does not implement its declared interface.",
                {
                    "kind": descriptor.kind.value,
                    "provider": descriptor.name,
                    "expected_interface": expected.__name__,
                },
            )
        self._items[key] = registration

    def get(self, kind: ProviderKind, name: str) -> ProviderRegistration:
        try:
            return self._items[(kind, name)]
        except KeyError as exc:
            raise ProviderNotFoundError(kind, name) from exc

    def list(self, kind: ProviderKind | None = None) -> tuple[ProviderRegistration, ...]:
        registrations = (
            item
            for (item_kind, _), item in self._items.items()
            if kind is None or item_kind == kind
        )
        return tuple(
            sorted(
                registrations,
                key=lambda item: (item.descriptor.kind.value, item.descriptor.name),
            )
        )

    def restore(self, registrations: tuple[ProviderRegistration, ...]) -> None:
        staged = ProviderRegistry()
        for registration in registrations:
            staged.register(registration)
        self._items = staged._items
