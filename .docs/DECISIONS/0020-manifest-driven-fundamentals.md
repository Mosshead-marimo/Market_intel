# ADR 0020: Manifest-driven deterministic fundamentals

- Status: Accepted
- Date: 2026-08-10

## Context

TradeSentinel needs comparable accounting trends without coupling capabilities to vendor schemas, routes, other modules' private code, or narrative generation. Annual and quarterly reports have different meanings, current valuation needs a current quote, and historical multiples cannot be reconstructed accurately without point-in-time prices.

## Decision

The `fundamentals` manifest owns discovery of its capabilities, workflows, commands, events, and API router. Provider adapters normalize statements and facts to canonical concepts; unknown concepts remain disclosed and are not substituted.

Annual and quarterly series remain separate. ROE uses net income divided by average equity. ROCE uses EBIT divided by average equity plus debt minus cash. Quarterly returns use four contiguous quarters and a prior-year balance; current valuation uses TTM flows when available and otherwise reports an explicit annual fallback warning.

Current calculated multiples and provider-reported multiples are separate fields. Historical valuation contains dated provider facts only. Missing quotes therefore produce a partial, reported-only valuation instead of reconstructing prices or failing a complete snapshot.

Explicit peers replace automatic peers. Automatic selection ranks exact-industry matches before sector matches, removes duplicate legal entities, and orders candidates deterministically. Comparisons expose individual dimensionless metrics, medians, and descriptive percentiles. They do not create composite scores or rank monetary values across currencies.

Profiles are cached for 24 hours and statements/facts for 6 hours using provider-chain fingerprints. Validated successful results are cached; failures are not. Fundamentals add no persistence schema.

## Consequences

- Vendor adapters must perform concept mapping and supply fiscal/provenance metadata.
- Missing line items remain visible as partial or empty sections.
- A missing fundamentals provider is an execution-time 503, so module discovery still succeeds.
- A missing market-data provider limits current valuation but does not hide reported valuation.
- Expanding the concept catalog is a versioned contract change.
- The module is descriptive historical accounting analysis, not a forecast or recommendation system.
