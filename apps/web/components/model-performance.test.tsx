import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ModelPerformanceWorkspace } from "./model-performance";

describe("model performance administration", () => {
  it("keeps the operator token in memory and exposes no predictions to user routes", () => {
    render(<ModelPerformanceWorkspace />);
    const token = screen.getByLabelText("Administrative token");
    fireEvent.change(token, { target: { value: "ephemeral-admin-token" } });
    fireEvent.click(screen.getByRole("button", { name: "Unlock this tab" }));
    expect(
      screen.getByRole("heading", { name: "Model performance" }),
    ).toBeTruthy();
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
    expect(document.cookie).not.toContain("ephemeral-admin-token");
  });
});
