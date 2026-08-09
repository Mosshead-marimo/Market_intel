# Sentiment System

## Goal

Measure how public discussion and market narratives are changing around an instrument.

## Pipeline

1. Collect approved documents.
2. Normalize text and metadata.
3. Resolve company and symbol references.
4. Remove duplicates.
5. Detect spam and low-quality content.
6. Classify relevance.
7. Classify sentiment.
8. Extract topics and narratives.
9. Apply source weights.
10. Aggregate by window.
11. Calculate sentiment change and acceleration.

## Required Outputs

- Positive, neutral, and negative shares
- Sentiment score
- Sentiment change
- Mention-volume change
- Dominant narratives
- Source agreement
- Confidence

## Source Separation

The system must report separately:

- Public sentiment
- News sentiment
- Institutional or analyst sentiment
- Fundamental condition

Public sentiment is not verified financial truth.

## Quality Controls

- Duplicate detection
- Bot-like repetition detection
- Relevance threshold
- Source-quality weighting
- Language detection
- Timestamp normalization
- Confidence reduction for sparse data
## Implemented deterministic runtime

The `public_sentiment` module implements collection, spam removal, whole-catalog company detection, source weighting, aggregation, narratives, trends, and descriptive shifts as separate capabilities. Provider signal triples take precedence over `lexicon-v1`; unmatched text is explicitly unknown and excluded. Engagement uses `1 + min(log1p(count) / 10, 0.5)`. The shift score is bounded and descriptive, with no price or direction prediction. See ADR 0018 for rationale and privacy boundaries.
