import { describe, expect, it } from "vitest";
import {
  instrumentResolveOutputSchema,
  instrumentSearchOutputSchema,
  responseComponentSchema,
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
