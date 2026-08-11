import { describe, expect, it } from "vitest";
import {
  benchmarkComparisonOutputSchema,
  fundamentalPeerComparisonSchema,
  fundamentalSectionSchema,
  instrumentResolveOutputSchema,
  instrumentSearchOutputSchema,
  researchClaimSchema,
  researchReportOutputSchema,
  responseComponentSchema,
  sentimentLabelSchema,
  sentimentShiftSchema,
  sentimentSnapshotSchema,
  stockQuoteOutputSchema,
  technicalRsiOutputSchema,
  technicalSnapshotSchema,
} from "./index";

describe("response component contract", () => {
  it("accepts a summary card", () => {
    expect(
      responseComponentSchema.parse({
        id: "status",
        type: "summary_card",
        heading: "Online",
        body: "Ready",
      }).type,
    ).toBe("summary_card");
  });

  it("rejects unsupported component types", () => {
    expect(() =>
      responseComponentSchema.parse({ id: "x", type: "unknown" }),
    ).toThrow();
  });

  it("validates reusable sections and event timelines", () => {
    const component = responseComponentSchema.parse({
      id: "market",
      type: "response_section",
      title: "Market data",
      status: "partial",
      items: [
        {
          id: "actions",
          type: "event_timeline",
          title: "Corporate actions",
          items: [
            {
              occurred_at: "2026-08-08T00:00:00Z",
              label: "Dividend",
              category: "dividend",
            },
          ],
        },
      ],
    });
    expect(component.type).toBe("response_section");
  });
});

describe("stock market data contracts", () => {
  const instrument = {
    instrument_id: "00000000-0000-4000-8000-000000000001",
    symbol: "TCS",
    name: "Tata Consultancy Services Limited",
    exchange: "NSE",
    asset_type: "equity",
    currency: "INR",
    aliases: [],
  };
  const provider = {
    provider: "test-market",
    source_id: "quote",
    retrieved_at: "2026-01-01T00:00:00Z",
    license: "internal",
    freshness: "fresh",
  };
  const cache = {
    disposition: "miss",
    cached_at: "2026-01-01T00:00:00Z",
    expires_at: "2026-01-01T00:00:15Z",
  };

  it("validates decimal-backed quote output", () => {
    expect(
      stockQuoteOutputSchema.parse({
        instrument,
        price: "110.25",
        currency: "INR",
        as_of: "2026-01-01T00:00:00Z",
        provider,
        cache,
      }).price,
    ).toBe("110.25");
    expect(() =>
      stockQuoteOutputSchema.parse({
        instrument,
        price: "not-a-number",
        currency: "INR",
        as_of: "2026-01-01T00:00:00Z",
        provider,
        cache,
      }),
    ).toThrow();
  });

  it("requires benchmark overlap metadata", () => {
    expect(() =>
      benchmarkComparisonOutputSchema.parse({ overlapping_observations: 1 }),
    ).toThrow();
  });
});

describe("instrument contracts", () => {
  const match = {
    instrument: {
      instrument_id: "00000000-0000-4000-8000-000000000001",
      symbol: "TCS",
      name: "Tata Consultancy Services Limited",
      exchange: "NSE",
      asset_type: "equity",
      currency: "INR",
      aliases: ["Tata Consultancy Services"],
    },
    confidence: 1,
    matched_on: "ticker",
    matched_value: "TCS",
  };

  it("validates instrument search output", () => {
    expect(
      instrumentSearchOutputSchema.parse({ query: "TCS", matches: [match] })
        .matches[0]?.instrument.exchange,
    ).toBe("NSE");
  });

  it("enforces typed ambiguity", () => {
    expect(() =>
      instrumentResolveOutputSchema.parse({
        query: "TCS",
        status: "ambiguous",
        match: null,
        candidates: [match],
      }),
    ).toThrow();
  });
});

describe("research evidence contracts", () => {
  const source = {
    source_id: "test-news:article-1",
    provider_source_id: "article-1",
    provider: "test-news",
    title: "Example reports earnings",
    url: "https://example.test/article-1",
    published_at: "2026-08-08T10:00:00Z",
    retrieved_at: "2026-08-08T10:01:00Z",
    timestamp: "2026-08-08T10:00:00Z",
    timestamp_basis: "published",
    license: "redistributable",
    freshness: "fresh",
    untrusted: true,
  } as const;
  const claim = {
    claim_id: "00000000-0000-4000-8000-000000000011",
    event_id: "00000000-0000-4000-8000-000000000012",
    text: "Example reports earnings",
    source,
    provider: source.provider,
    timestamp: source.timestamp,
    timestamp_basis: source.timestamp_basis,
    confidence: 0.95,
    confidence_basis: "strong_title_phrase",
    extraction_version: "rules-v1",
    evidence_excerpt: "Example reports earnings",
  } as const;

  it("requires complete claim evidence", () => {
    expect(researchClaimSchema.parse(claim).source.provider).toBe("test-news");
    expect(() =>
      researchClaimSchema.parse({ ...claim, source: undefined }),
    ).toThrow();
  });

  it("validates structured evidence-index reports", () => {
    const event = {
      event_id: claim.event_id,
      query: "Example",
      event_type: "earnings",
      headline: claim.text,
      observed_at: source.timestamp,
      timestamp_basis: source.timestamp_basis,
      confidence: claim.confidence,
      extraction_version: "rules-v1",
      claims: [claim],
      source_ids: [source.source_id],
    };
    expect(
      researchReportOutputSchema.parse({
        query: "Example",
        status: "completed",
        coverage: {
          source_count: 1,
          duplicate_count: 0,
          event_count: 1,
          claim_count: 1,
          unmatched_count: 0,
          document_failure_count: 0,
        },
        events: [event],
        sources: [source],
        duplicate_groups: [],
        warnings: [],
      }).events[0]?.event_type,
    ).toBe("earnings");
  });
});

describe("public sentiment contracts", () => {
  const instrument = {
    instrument_id: "00000000-0000-4000-8000-000000000001",
    symbol: "MSFT",
    name: "Microsoft Corporation",
    exchange: "NASDAQ",
    asset_type: "equity",
    currency: "USD",
    aliases: ["Microsoft"],
  } as const;

  it("preserves explicit empty metrics", () => {
    const window = {
      start: "2026-08-01T00:00:00Z",
      end: "2026-08-08T00:00:00Z",
      mention_count: 0,
      usable_count: 0,
      positive_share: null,
      neutral_share: null,
      negative_share: null,
      mean_score: null,
      agreement: null,
      mean_signal_confidence: null,
    };
    expect(
      sentimentSnapshotSchema.parse({
        snapshot_id: "00000000-0000-4000-8000-000000000002",
        target: instrument,
        status: "empty",
        as_of: window.end,
        current: window,
        previous: window,
        volume_change: null,
        confidence: null,
        co_mentions: [],
        warnings: ["No usable sentiment observations were available."],
        lexicon_version: "lexicon-v1",
      }).current.mean_score,
    ).toBeNull();
  });

  it("rejects predictive shift labels by contract", () => {
    expect(() =>
      sentimentShiftSchema.parse({
        target: instrument,
        status: "completed",
        shift_score: "0.25",
        sentiment_component: "0.20",
        volume_component: "0.40",
        description: "Observed change only.",
        prediction: "up",
      }),
    ).toThrow();
    expect(sentimentLabelSchema.safeParse("bullish").success).toBe(false);
  });
});

describe("technical analysis contracts", () => {
  const instrument = {
    instrument_id: "00000000-0000-4000-8000-000000000001",
    symbol: "MSFT",
    name: "Microsoft Corporation",
    exchange: "NASDAQ",
    asset_type: "equity",
    currency: "USD",
    aliases: ["Microsoft"],
  } as const;
  const rsi = {
    instrument,
    interval: "1d",
    series: {
      period: 14,
      latest: "55.25",
      points: [{ timestamp: "2026-08-08T00:00:00Z", value: "55.25" }],
    },
  } as const;

  it("validates Decimal indicator series", () => {
    expect(technicalRsiOutputSchema.parse(rsi).series.latest).toBe("55.25");
    expect(() =>
      technicalRsiOutputSchema.parse({
        ...rsi,
        series: { ...rsi.series, latest: 55.25 },
      }),
    ).toThrow();
  });

  it("preserves explicit partial snapshots and rejects prediction fields", () => {
    const snapshot = {
      instrument,
      status: "partial",
      interval: "1d",
      requested_start: "2025-08-08T00:00:00Z",
      requested_end: "2026-08-08T00:00:00Z",
      observed_start: "2026-07-01T00:00:00Z",
      observed_end: "2026-08-08T00:00:00Z",
      data_cutoff: "2026-08-08T00:00:00Z",
      observation_count: 30,
      price_basis: "adjusted_ohlc",
      calculation_version: "technical-v1",
      parameters: {
        rsi_period: 14,
        macd_fast_period: 12,
        macd_slow_period: 26,
        macd_signal_period: 9,
        ema_period: 20,
        sma_period: 20,
        atr_period: 14,
        adx_period: 14,
        momentum_roc_period: 10,
        volatility_period: 20,
        trend_fast_period: 20,
        trend_slow_period: 50,
        level_lookback: 60,
        pivot_span: 2,
        pivot_max_levels: 3,
        pivot_atr_multiplier: "0.5",
        trend_spread_threshold: "0.005",
        momentum_rsi_lower: "45",
        momentum_rsi_upper: "55",
        volatility_low_percentile: "0.25",
        volatility_high_percentile: "0.75",
      },
      provider: {
        provider: "test-market",
        source_id: "history",
        retrieved_at: "2026-08-08T00:00:00Z",
        license: "internal",
        freshness: "fresh",
      },
      cache: {
        disposition: "hit",
        cached_at: "2026-08-08T00:00:00Z",
        expires_at: "2026-08-08T06:00:00Z",
      },
      warnings: ["trend requires 50 observations; 30 were available."],
      rsi,
      trend: null,
    } as const;
    expect(technicalSnapshotSchema.parse(snapshot).status).toBe("partial");
    expect(() =>
      technicalSnapshotSchema.parse({ ...snapshot, prediction: "rising" }),
    ).toThrow();
  });
});

describe("fundamental contracts", () => {
  const instrument = {
    instrument_id: "00000000-0000-4000-8000-000000000001",
    symbol: "TCS",
    name: "Tata Consultancy Services Limited",
    exchange: "NSE",
    asset_type: "equity",
    currency: "INR",
    aliases: [],
  } as const;
  const provider = {
    provider: "test-fundamentals",
    source_id: "statement-2025",
    retrieved_at: "2026-01-01T00:00:00Z",
    license: "internal",
    freshness: "fresh",
  } as const;

  it("keeps annual and quarterly accounting trends separate", () => {
    const section = fundamentalSectionSchema.parse({
      instrument,
      section: "revenue",
      status: "completed",
      as_of: "2026-01-01T00:00:00Z",
      data_cutoff: "2025-12-31T00:00:00Z",
      metrics: [
        {
          concept: "revenue",
          label: "Revenue",
          unit: "currency",
          latest: "1400",
          annual: [
            {
              period_type: "annual",
              period_end: "2025-12-31T00:00:00Z",
              value: "1400",
              unit: "currency",
              currency: "INR",
              provider,
            },
          ],
          quarterly: [
            {
              period_type: "quarterly",
              period_end: "2025-12-28T00:00:00Z",
              value: "320",
              unit: "currency",
              currency: "INR",
              provider,
            },
          ],
        },
      ],
      warnings: [],
    });
    expect(section.metrics[0]?.annual).toHaveLength(1);
    expect(section.metrics[0]?.quarterly).toHaveLength(1);
  });

  it("validates descriptive peer percentiles and rejects composite fields", () => {
    const comparison = {
      target: instrument,
      peers: [
        {
          ...instrument,
          instrument_id: "00000000-0000-4000-8000-000000000002",
          symbol: "INFY",
        },
      ],
      status: "completed",
      as_of: "2026-01-01T00:00:00Z",
      comparisons: [
        {
          concept: "roe",
          median: "18.2",
          values: [{ instrument, value: "17.9", percentile: "0.5" }],
        },
      ],
      warnings: [],
    };
    expect(
      fundamentalPeerComparisonSchema.parse(comparison).comparisons,
    ).toHaveLength(1);
    expect(() =>
      fundamentalPeerComparisonSchema.parse({
        ...comparison,
        composite_score: "0.9",
      }),
    ).toThrow();
  });
});
