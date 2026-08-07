# Frontend Architecture

## Stack

- Next.js
- TypeScript strict mode
- Tailwind CSS
- shadcn/ui
- SSE client
- Chart library

## Main Screens

- Chat
- Prediction history
- Research details
- Watchlist
- Settings

## Response Component Registry

- summary_card
- metric_grid
- price_chart
- sentiment_chart
- news_timeline
- prediction_card
- scenario_table
- comparison_table
- risk_card
- source_list
- warning_banner

## State Rules

- Separate server data from UI state.
- Preserve session and message IDs.
- Support streamed partial components.
- Display stale-data warnings.
- Display partial-success states.
- Do not render unsupported data shapes.

## Command Experience

- Slash-command autocomplete
- Command descriptions
- Argument hints
- Examples
- Natural-language fallback

## Foundation Console

The initial App Router application is a platform console rather than a market dashboard. It validates API responses with the shared contract package, displays readiness and registry discovery, executes `/ping`, and renders validated response components. API and SSE clients are isolated under `lib`; presentation components handle loading, empty, partial, stale, unsupported, and error states without trusting external shapes.
