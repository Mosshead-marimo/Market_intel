# ADR 0014: Canonical Instrument Resolution and Module-Owned Routes

## Status

Accepted

## Context

Every later market, news, sentiment, fundamental, and prediction capability needs an unambiguous instrument identity. Tickers and company names are not globally unique, and selecting an exchange silently would corrupt downstream evidence. Feature HTTP routes must also remain discoverable without central API conditionals.

## Decision

Create UUID-backed canonical `InstrumentRef` contracts shared outside platform and feature internals. The `instrument_resolution` module owns a PostgreSQL catalog plus an equivalent memory repository and ships a labeled 16-listing bootstrap seed. It resolves normalized ticker, name, and alias text with fixed exact/prefix tiers and deterministic `SequenceMatcher` similarity. Near-tied cross-exchange matches return typed ambiguity.

Allow manifests to declare an optional FastAPI router entrypoint. A generic API adapter validates and includes these routers; module routes invoke registered capabilities through the shared pipeline. A generic persistence resource lets recursively constructed module services select memory or SQL without core knowledge of the module.

## Consequences

Resolution is explainable and consistent across persistence backends. Confidence is a match score rather than a probability. Callers must supply an exchange when ambiguity remains. The bootstrap catalog is useful but intentionally incomplete; provider-driven catalog ingestion is future work. Feature routes become automatically discoverable while platform remains transport- and domain-neutral.
