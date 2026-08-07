# Product Requirements

## Problem Statement

Retail users often receive fragmented stock information from charts, news sites, social media, and financial statements. TradeSentinel combines these sources into one conversational research experience.

## Product Vision

Users should be able to ask a normal market question and receive an evidence-backed response explaining:

- How the stock has performed historically
- What is happening now
- How public sentiment is changing
- Which narratives are influencing the market
- Whether current evidence suggests possible upside, downside, or uncertainty

## Target Users

- Retail investors performing independent research
- Students learning market analysis
- Analysts who want a rapid research summary
- Beta users testing sentiment-driven market intelligence

## Core User Journey

1. User opens the chat.
2. User asks, "How is TCS doing?"
3. System resolves the instrument.
4. System retrieves five years of adjusted market history.
5. System compares performance against an appropriate benchmark.
6. System collects current news and public discussion.
7. System extracts sentiment, events, and narratives.
8. System calculates technical and fundamental signals.
9. System calculates a market-shift score.
10. System generates probabilistic scenarios.
11. System validates sources and safety rules.
12. System returns a structured response with timestamps and evidence.

## MVP Functional Requirements

- Chat sessions and message history
- Natural-language intent detection
- Slash-command support
- NSE symbol resolution
- Current quote retrieval
- Five-year adjusted price history
- Benchmark comparison
- News collection and event extraction
- Public sentiment aggregation
- Narrative detection
- Technical indicators
- Fundamental snapshots
- Market-shift scoring
- Five-day and twenty-day predictions
- Bull, base, and bear scenarios
- Prediction history and evaluation
- Source inspection

## Non-Functional Requirements

- Modular extensibility
- Partial-failure tolerance
- Typed contracts
- Data freshness visibility
- Auditable predictions
- Provider replaceability
- Secure secret handling
- Observability and run tracing
- Responsive chat experience

## Non-Goals

- Real-money execution
- Broker connectivity
- Fully autonomous trading
- Options or leveraged-product recommendations
- Guaranteed returns
- Personalized portfolio allocation

## Success Metrics

- Correct symbol resolution rate
- Percentage of responses with valid sources
- Median response latency
- Public sentiment classification quality
- Prediction calibration
- User-rated usefulness
- Provider failure recovery rate
- Cost per completed analysis
