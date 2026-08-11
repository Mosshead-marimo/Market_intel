import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ResponseComponentView } from "./response-component";

describe("ResponseComponentView", () => {
  it("renders valid summary components", () => {
    render(
      <ResponseComponentView
        value={{
          id: "one",
          type: "summary_card",
          heading: "Online",
          body: "Ready",
        }}
      />,
    );
    expect(screen.getByRole("heading", { name: "Online" })).toBeInTheDocument();
  });

  it("rejects unsupported data", () => {
    render(<ResponseComponentView value={{ type: "invented" }} />);
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Unsupported response data",
    );
  });

  it("renders a validated section with metrics and a timeline", () => {
    render(
      <ResponseComponentView
        value={{
          id: "market",
          type: "response_section",
          title: "Market data",
          status: "partial",
          items: [
            {
              id: "quote",
              type: "metric_grid",
              metrics: [{ label: "Price", value: "100.00", detail: "USD" }],
            },
            {
              id: "actions",
              type: "event_timeline",
              items: [
                {
                  occurred_at: "2026-08-08T00:00:00Z",
                  label: "Dividend",
                },
              ],
            },
          ],
        }}
      />,
    );
    expect(
      screen.getByRole("heading", { name: "Market data" }),
    ).toBeInTheDocument();
    expect(screen.getByText("100.00")).toBeInTheDocument();
    expect(screen.getByText("Dividend")).toBeInTheDocument();
    expect(screen.getByText("partial")).toBeInTheDocument();
  });
});
