import { describe, expect, it } from "vitest";
import {
  benchmarkComparisonOutputSchema,
  instrumentResolveOutputSchema,
  instrumentSearchOutputSchema,
  responseComponentSchema,
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
