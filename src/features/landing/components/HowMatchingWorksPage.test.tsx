import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import HowMatchingWorksPage from "./HowMatchingWorksPage";

function renderPage() {
  render(
    <MemoryRouter>
      <HowMatchingWorksPage />
    </MemoryRouter>,
  );
}

describe("HowMatchingWorksPage", () => {
  it("renders the title and every section heading", () => {
    renderPage();
    expect(screen.getByRole("heading", { level: 1, name: "How matching works" })).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 2 })).toHaveLength(6);
    expect(screen.getByRole("heading", { level: 2, name: "Who sees your answers" })).toBeInTheDocument();
  });

  it("has no uppercase eyebrow label", () => {
    renderPage();
    expect(screen.queryByText(/^transparency$/i)).toBeNull();
    expect(document.querySelector(".uppercase")).toBeNull();
  });

  it("links back home and to both legal documents", () => {
    renderPage();
    expect(screen.getByRole("link", { name: "Back to Solverah" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: "Privacy policy" })).toHaveAttribute("href", "/privacy");
    expect(screen.getByRole("link", { name: "Terms of service" })).toHaveAttribute("href", "/terms");
  });
});
