import { describe, expect, it } from "vitest";
import { responseComponentSchema } from "./index";

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
