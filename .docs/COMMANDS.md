# Command Specification

## Command Format

```text
/<command> <required arguments> --optional-key value
```

Natural-language requests must map to the same internal command handlers.

## Core Commands

### `/search`

Searches ticker, company-name, and alias fields using deterministic fuzzy matching.

```text
/search <query> --exchange NSE --asset-type equity --limit 20
```

### `/resolve`

Returns one canonical instrument, typed ambiguity, or not-found status. Cross-listed instruments require an exchange when top scores are tied.

```text
/resolve <query> --exchange NSE --asset-type equity
```

### `/analyze`

Purpose: Complete stock overview.

Syntax:

```text
/analyze <stock> --period 5y --horizon 20d
```

Capabilities:

- instrument.resolve
- stock.quote
- stock.performance
- news.research
- sentiment.public
- technical.overview
- fundamental.overview
- market_shift.calculate
- prediction.direction
- scenario.generate
- response.stock_overview

### `/quote`

Returns current quote, daily movement, volume, market status, and timestamp.

```text
/quote TCS --exchange NSE
```

### `/history`

Returns adjusted OHLCV history and chart-ready series.

```text
/history TCS 2025-01-01T00:00:00Z 2026-01-01T00:00:00Z --exchange NSE
```

### `/performance`

Returns total return, CAGR, maximum drawdown, annualized volatility, and a rebased series for one explicit period.

Market-data performance uses adjusted closes only. Benchmark comparison remains an explicit operation.

### `/compare`

Compares adjusted performance for two resolved instruments.

### `/corporate-actions`

Returns normalized actions over an explicit time range.

### `/five-year-performance`

Calculates adjusted performance beginning five calendar years before `as_of`.

### `/benchmark-compare`

Compares an instrument with an explicitly named benchmark; no index is inferred.

### `/research`

Builds a structured, sourced evidence index for a free-text query without LLM prose.

### `/news`

Returns normalized news and deterministically extracted events. Optional `--start`, `--end`, and `--limit` values constrain provider search.

### `/public-sentiment`

Returns weighted public sentiment by time window.

### `/sentiment-trend`

Shows sentiment direction and acceleration.

### `/narratives`

Shows dominant positive and negative market narratives.

### `/technical`

Returns indicators, market regime, momentum, support, resistance, and volatility.

### `/fundamentals`

Returns revenue, profit, EPS, margins, debt, cash flow, and growth trends.

### `/valuation`

Returns current, historical, and peer valuation context.

### `/risk`

Returns business, valuation, volatility, event, liquidity, and sentiment risks.

### `/market-shift`

Returns current narrative direction, shift score, and confidence.

### `/predict`

Returns rise, sideways, and decline probabilities with horizon and model version.

### `/direction`

Returns directional classification only.

### `/price-range`

Returns expected base and wider uncertainty ranges.

### `/scenarios`

Returns bull, base, and bear scenarios with conditions and probabilities.

### `/why-prediction`

Explains feature contributions and evidence behind the prediction.

### `/prediction-history`

Shows previous predictions and actual outcomes.

### `/model-performance`

Shows calibration, direction accuracy, Brier score, and range coverage.

### `/sources`

Displays sources used in the current or specified analysis.

### `/help`

Displays registered commands and examples.
## Public sentiment

- `/public-sentiment <query>` executes the complete descriptive analysis.
- `/sentiment-trend <query>` executes the same evidence pipeline and exposes trend output.
- `/narratives <query>` executes the same evidence pipeline and exposes deterministic narratives.
- `/sentiment-shift <query>` executes the same evidence pipeline and exposes adjacent-window shift.

All accept `--exchange`, `--as-of`, `--window-days`, and `--limit`. The manifest owns parsing and workflow targets; command code contains no sentiment conditionals.
