import { describe, expect, it } from "vitest";
import {
  benchmarkComparisonOutputSchema,
  instrumentResolveOutputSchema,
  instrumentSearchOutputSchema,
  researchClaimSchema,
  researchReportOutputSchema,
  responseComponentSchema,
  sentimentLabelSchema,
  sentimentShiftSchema,
  sentimentSnapshotSchema,
  stockQuoteOutputSchema,
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
