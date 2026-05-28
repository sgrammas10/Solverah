import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import AccountGate from "../AccountGate";

function renderAccountGate() {
  return render(
    <MemoryRouter>
      <AccountGate />
    </MemoryRouter>
  );
}

describe("AccountGate", () => {
  it("renders the heading", () => {
    renderAccountGate();
    expect(screen.getByText("Unlock your full results")).toBeInTheDocument();
  });

  it("renders all 4 unlock list items", () => {
    renderAccountGate();
    expect(
      screen.getByText("Your full 12-question Work Pulse Lite assessment")
    ).toBeInTheDocument();
    expect(
      screen.getByText("A complete snapshot narrative of how you work")
    ).toBeInTheDocument();
    expect(
      screen.getByText("Emerging signals about your friction and flow")
    ).toBeInTheDocument();
    expect(
      screen.getByText("A partial Solverah profile you can build over time")
    ).toBeInTheDocument();
  });

  it("register link points to /register?from=wpll", () => {
    renderAccountGate();
    const link = screen.getByRole("link", { name: /create my free account/i });
    expect(link).toHaveAttribute("href", "/register?from=wpll");
  });

  it("login link points to /login?from=wpll", () => {
    renderAccountGate();
    const link = screen.getByRole("link", { name: /already have an account/i });
    expect(link).toHaveAttribute("href", "/login?from=wpll");
  });
});
