# Frontend Architecture

## Evidence UI

The component registry validates cited narratives, balanced thesis sections, and follow-up buttons. Citation badges resolve evidence metadata, and follow-ups submit their stored prompt through the normal chat client.

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
- event_timeline
- response_section

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

The App Router application uses a ChatGPT-style shell with a responsive session sidebar, transcript, fixed composer, slash-command discovery, typing state, execution progress, reconnect state, and validated streamed response components. API access, session credentials, SSE parsing, replay deduplication, and stream reduction remain under `lib` outside presentation components.

The response registry implements reusable metric-grid, line-chart, timeline, table, source-list, summary, warning, and section renderers. `response_section` recursively composes validated leaf components but cannot nest another section. Zod validation occurs before dispatch; invalid values render the accessible unsupported-data state. Section status remains visible for partial, empty, stale, and error results.
