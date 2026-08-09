from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Literal

from tradesentinel.domain.instruments import (
    InstrumentAutocompleteInput,
    InstrumentAutocompleteOutput,
    InstrumentCatalogOutput,
    InstrumentMatch,
    InstrumentRef,
    InstrumentResolveInput,
    InstrumentResolveOutput,
    InstrumentSearchInput,
    InstrumentSearchOutput,
)
from tradesentinel.modules.instrument_resolution.repository import InstrumentRepositoryFactory

MatchField = Literal["ticker", "name", "alias"]
SEARCH_THRESHOLD = 0.45
RESOLVE_THRESHOLD = 0.70
AMBIGUITY_DELTA = 0.03


def normalize(value: str) -> str:
    without_marks = "".join(
        " " if unicodedata.category(character)[0] in {"P", "S"} else character
        for character in value
    )
    normalized = unicodedata.normalize("NFKC", without_marks).casefold()
    return " ".join(re.sub(r"[^\w\s]", " ", normalized).split())


def _field_score(query: str, value: str, field: MatchField) -> float:
    candidate = normalize(value)
    if query == candidate:
        return {"ticker": 1.0, "alias": 0.98, "name": 0.97}[field]
    if candidate.startswith(query):
        return 0.94 if field == "ticker" else 0.90
    return round(SequenceMatcher(None, query, candidate, autojunk=False).ratio() * 0.85, 4)


def score_instrument(query: str, instrument: InstrumentRef) -> InstrumentMatch:
    normalized_query = normalize(query)
    fields: list[tuple[MatchField, str]] = [
        ("ticker", instrument.symbol),
        ("name", instrument.name),
        *(("alias", alias) for alias in instrument.aliases),
    ]
    scored = [
        (_field_score(normalized_query, value, field), field, value) for field, value in fields
    ]
    confidence, matched_on, matched_value = max(
        scored, key=lambda item: (item[0], item[1] == "ticker", normalize(item[2]))
    )
    return InstrumentMatch(
        instrument=instrument,
        confidence=confidence,
        matched_on=matched_on,
        matched_value=matched_value,
    )


def _ordered(matches: list[InstrumentMatch]) -> tuple[InstrumentMatch, ...]:
    return tuple(
        sorted(
            matches,
            key=lambda match: (
                -match.confidence,
                match.instrument.exchange,
                match.instrument.symbol,
                str(match.instrument.instrument_id),
            ),
        )
    )


class InstrumentResolutionService:
    def __init__(self, repository_factory: InstrumentRepositoryFactory) -> None:
        self._repository = repository_factory.create()

    async def search(self, request: InstrumentSearchInput) -> InstrumentSearchOutput:
        instruments = await self._repository.list_active(
            exchange=request.exchange, asset_type=request.asset_type
        )
        matches = _ordered(
            [
                match
                for instrument in instruments
                if (match := score_instrument(request.query, instrument)).confidence
                >= SEARCH_THRESHOLD
            ]
        )[: request.limit]
        return InstrumentSearchOutput(query=request.query.strip(), matches=matches)

    async def catalog(self) -> InstrumentCatalogOutput:
        return InstrumentCatalogOutput(instruments=await self._repository.list_active())

    async def autocomplete(
        self, request: InstrumentAutocompleteInput
    ) -> InstrumentAutocompleteOutput:
        instruments = await self._repository.list_active(
            exchange=request.exchange, asset_type=request.asset_type
        )
        query = normalize(request.query)
        matches = []
        for instrument in instruments:
            values = (instrument.symbol, instrument.name, *instrument.aliases)
            if any(normalize(value).startswith(query) for value in values):
                matches.append(score_instrument(request.query, instrument))
        return InstrumentAutocompleteOutput(
            query=request.query.strip(), matches=_ordered(matches)[: request.limit]
        )

    async def resolve(self, request: InstrumentResolveInput) -> InstrumentResolveOutput:
        search = await self.search(
            InstrumentSearchInput(
                query=request.query,
                exchange=request.exchange,
                asset_type=request.asset_type,
                limit=50,
            )
        )
        eligible = tuple(match for match in search.matches if match.confidence >= RESOLVE_THRESHOLD)
        if not eligible:
            return InstrumentResolveOutput(query=request.query.strip(), status="not_found")
        if len(eligible) > 1 and eligible[0].confidence - eligible[1].confidence <= AMBIGUITY_DELTA:
            top_score = eligible[0].confidence
            candidates = tuple(
                match for match in eligible if top_score - match.confidence <= AMBIGUITY_DELTA
            )
            return InstrumentResolveOutput(
                query=request.query.strip(), status="ambiguous", candidates=candidates
            )
        return InstrumentResolveOutput(
            query=request.query.strip(), status="resolved", match=eligible[0]
        )
