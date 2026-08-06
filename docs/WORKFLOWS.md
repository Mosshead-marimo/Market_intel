# Workflows

## Workflow Rules

- Workflows are declarative.
- Every step names one capability.
- Dependencies are explicit.
- Optional steps may fail without aborting the workflow.
- Results and warnings must remain traceable.

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
