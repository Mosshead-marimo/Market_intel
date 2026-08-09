# Workflows

## Workflow Rules

- Workflows are declarative.
- Every step names one capability.
- Dependencies are explicit.
- Optional steps may fail without aborting the workflow.
- Results and warnings must remain traceable.
- The workflow engine compiles the dependency graph into deterministic concurrent layers.
- Step input contains the original workflow payload plus outputs from explicitly named dependencies only.
- Capabilities are always invoked through the shared capability executor.

## Stock Overview Workflow

Trigger:

- `/analyze`
- "How is TCS doing?"

Steps:

1. Resolve instrument.
2. Fetch current quote.
3. Fetch five-year adjusted history.
4. Calculate performance and benchmark comparison.
5. Gather current news and exchange events.
6. Analyze public sentiment and narratives.
7. Calculate technical indicators.
8. Retrieve fundamental snapshot.
9. Calculate market-shift score.
10. Run prediction model if required data is available.
11. Generate scenarios.
12. Validate evidence and freshness.
13. Render response components.

## Prediction Workflow

1. Resolve instrument.
2. Validate supported market and horizon.
3. Load point-in-time market features.
4. Load sentiment features.
5. Load fundamental and event features.
6. Run versioned prediction model.
7. Calibrate probabilities.
8. Generate ranges and scenarios.
9. Persist prediction and features.
10. Generate explanation.
11. Apply response guard.

## Sentiment Workflow

1. Resolve instrument.
2. Gather approved public documents.
3. Normalize text and metadata.
4. Remove duplicates.
5. Detect spam and low-quality content.
6. Classify relevance.
7. Classify sentiment.
8. Extract topics and narratives.
9. Apply source weights.
10. Aggregate by time window.
11. Calculate sentiment shift.

## Failure Policy

If public sentiment fails:

- Continue with available market, news, technical, and fundamental data.
- Skip sentiment-dependent model features.
- Add a warning.
- Never invent sentiment values.

## Execution Pipeline

Commands are parsed from manifest argument/option definitions. Natural-language requests use the injected intent resolver; the foundation resolver matches normalized manifest examples exactly. Direct capability and workflow requests bypass only target resolution, not permission checks, context scopes, retries, persistence, lifecycle events, or rendering.

Retryable typed errors and built-in timeout/connection failures use bounded exponential backoff when the target is idempotent. Validation, permission, discovery, registry, cancellation, and permanent failures are never retried. Required workflow failures fail the run and skip dependents; optional failures preserve usable output and produce partial success.

The conversation planner maps slash-prefixed input to command requests and other text to intent requests. Exact manifest intents precede the optional fallback. `conversation.mock` is a deterministic two-step reference workflow with no LLM or financial behavior.

Research manifests define `research.news.request` as search → deduplicate → extract → timeline and `research.report.request` as the same graph followed by report assembly. Full-document failures preserve source metadata, produce partial warnings, and never invent an event. Extraction persists normalized events before downstream timeline/report steps.

Workflow steps may declare `input_bindings`. Sources use `input.<path>` or `steps.<declared-dependency>.data.<path>`; optional missing sources are omitted and required missing sources raise `WORKFLOW_INPUT_BINDING_FAILED`. Bound steps receive only declared fields. Steps without bindings retain the original input-plus-dependencies behavior. Market-data command workflows use bindings to resolve canonical instruments before execution.
## Public sentiment workflow

`sentiment.public.request` resolves the requested instrument and loads the full active catalog concurrently. It then collects equal current/previous windows, removes spam, detects companies, retains target-relevant discussions, applies source weights, and runs aggregation, narrative extraction, and trend detection before the final shift calculation. Every step receives only manifest-declared input bindings. An ambiguous resolution or unavailable provider fails required dependents without selecting a listing or inventing data.
