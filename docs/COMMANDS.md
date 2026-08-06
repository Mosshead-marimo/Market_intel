# Command Specification

## Command Format

```text
/<command> <required arguments> --optional-key value
```

Natural-language requests must map to the same internal command handlers.

## Core Commands

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

### `/history`

Returns adjusted OHLCV history and chart-ready series.

### `/performance`

Returns returns across multiple periods, CAGR, drawdown, volatility, and benchmark comparison.

### `/compare`

Compares multiple stocks across performance, fundamentals, sentiment, valuation, and risk.

### `/research`

Builds a sourced company research report.

### `/news`

Returns recent relevant news and extracted events.

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
