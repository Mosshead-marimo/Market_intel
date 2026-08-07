# Prediction System

## Goal

Estimate probabilistic market direction and ranges based on point-in-time research features.

## Supported MVP Horizons

- 5 trading days
- 20 trading days

## Output Classes

- rise
- sideways
- decline
- uncertain

## Target Definition

Thresholds should be volatility-aware. A fixed starting definition may be used during experimentation, but production thresholds must be calibrated by instrument or volatility regime.

## Feature Groups

- Returns and momentum
- Volatility and volume
- Technical indicators
- Benchmark-relative performance
- Public sentiment
- Sentiment velocity
- Discussion volume
- News events
- Fundamentals
- Sector conditions
- Macro conditions

## Initial Models

- Logistic regression baseline
- LightGBM or XGBoost classifier
- Quantile regression for price ranges
- Probability calibration layer

## Rules

- LLMs must never invent probabilities.
- Every prediction must include model version and data cutoff.
- Every feature must have a `known_at` timestamp.
- Use walk-forward testing.
- Prevent survivorship bias and future leakage.
- Store generated predictions before displaying them.
- Return `uncertain` below configured confidence.

## Evaluation

- Directional accuracy
- Precision and recall by class
- Brier score
- Log loss
- Calibration error
- Range coverage
- Performance by sector and regime
- Sentiment-added lift over baseline
