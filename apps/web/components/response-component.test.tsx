import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
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

  it("does not expose internal predictions in user-facing renderers", () => {
    render(
      <ResponseComponentView
        value={{
          id: "internal-prediction",
          type: "prediction_card",
          direction: "rise",
          confidence: 0.9,
          horizon: "5 sessions",
          generated_at: "2026-08-12T00:00:00Z",
          data_cutoff: "2026-08-11T00:00:00Z",
          model_version: "model-v1",
        }}
      />,
    );
    expect(screen.getByRole("status")).toHaveTextContent(
      "Internal prediction output is not available",
    );
    expect(screen.queryByText("0.9")).not.toBeInTheDocument();
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

  it("renders evidence citations and submits stored follow-up prompts", () => {
    const onFollowUp = vi.fn();
    const evidence = [
      {
        evidence_id: "ev_0123456789abcdef",
        kind: "calculated_metric" as const,
        title: "RSI",
        value: "54.2",
        producer: "technical.rsi",
        timestamp: "2026-08-08T00:00:00Z",
        source_ids: [],
        freshness: "fresh" as const,
        untrusted: false,
      },
    ];
    const { rerender } = render(
      <ResponseComponentView
        value={{
          id: "answer",
          type: "cited_narrative",
          claims: [
            {
              claim_id: "claim_rsi",
              text: "The reported RSI is 54.2.",
              evidence_ids: ["ev_0123456789abcdef"],
            },
          ],
        }}
        evidence={evidence}
        onFollowUp={onFollowUp}
      />,
    );
    expect(screen.getByTitle("RSI: 54.2")).toBeInTheDocument();
    rerender(
      <ResponseComponentView
        value={{
          id: "questions",
          type: "follow_up_questions",
          questions: [
            { id: "more", label: "Show more", prompt: "/technical TCS" },
          ],
        }}
        onFollowUp={onFollowUp}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Show more" }));
    expect(onFollowUp).toHaveBeenCalledWith("/technical TCS");
  });
});
