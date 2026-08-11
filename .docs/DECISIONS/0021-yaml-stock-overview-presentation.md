# ADR 0021: YAML-owned stock overview execution and presentation

- Status: Accepted
- Date: 2026-08-11

## Context

A stock overview must combine existing market, research, sentiment, technical, and fundamentals capabilities without creating central orchestration conditionals or coupling rendering to completion timing. Optional providers may be absent while the market and technical core must remain authoritative.

## Decision

The `stock_overview` manifest owns both the dependency DAG and ordered presentation metadata. Workflow `depends_on` relationships determine readiness and concurrency. Presentation sections independently declare the workflow step results they render, their display order, and optional empty/error messages. Atomic loading rejects unknown step references, duplicate section IDs, and steps assigned to multiple sections.

The platform persists presentation metadata on `WorkflowResult` and renders it generically into `response_section` components. Sections contain validated reusable leaf components, including the new `event_timeline`. Platform and central API code contain no overview capability name, section list, or financial rendering conditional.

Instrument resolution, market data, and technical analysis are required. Research, sentiment, and fundamentals are optional. Optional failure produces an explicit unavailable section and partial response; required failure preserves typed 503/422 transport behavior. The technical branch reuses retrieved adjusted history, and fundamentals reuses the quote through explicit bindings.

## Consequences

- Execution order and presentation order can evolve through validated YAML without core-code changes.
- Independent branches run concurrently, while dependency reuse is visible and testable.
- A response can remain useful when optional providers are unavailable without hiding missing data.
- Reusable sections and timelines are available to future workflows without stock-specific renderer logic.
- Nested response sections are intentionally disallowed to keep validation and accessible presentation predictable.
- The overview performs no LLM generation, prediction, recommendation, provider access, or persistence of its own.
