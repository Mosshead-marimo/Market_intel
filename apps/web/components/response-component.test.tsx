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
});
