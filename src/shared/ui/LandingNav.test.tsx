import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import LandingNav from "./LandingNav";

function renderNav() {
  return render(
    <MemoryRouter>
      <LandingNav />
    </MemoryRouter>
  );
}

describe("LandingNav - Get Started target", () => {
  it("desktop Get Started links to /start, not /register", () => {
    renderNav();
    const desktopCta = screen.getAllByRole("link", { name: "Get Started" })[0];
    expect(desktopCta).toHaveAttribute("href", "/start");
  });

  it("mobile menu Get Started links to /start, not /register", () => {
    renderNav();
    fireEvent.click(screen.getByRole("button", { name: "Open menu" }));

    const ctas = screen.getAllByRole("link", { name: "Get Started" });
    expect(ctas.length).toBe(2);
    ctas.forEach((cta) => expect(cta).toHaveAttribute("href", "/start"));
  });
});

describe("LandingNav - other route links", () => {
  it("Sign In links to /login", () => {
    renderNav();
    for (const loginLink of screen.getAllByRole("link", { name: "Sign In" })) {
      expect(loginLink).toHaveAttribute("href", "/login");
    }
  });

  it("logo links to /", () => {
    renderNav();
    expect(screen.getByRole("link", { name: "Solverah" })).toHaveAttribute("href", "/");
  });
});

describe("LandingNav - in-page section anchors are untouched", () => {
  it("keeps the section links as # anchors", () => {
    renderNav();
    expect(screen.getByRole("link", { name: "How it works" })).toHaveAttribute("href", "#features");
    expect(screen.getByRole("link", { name: "About" })).toHaveAttribute("href", "#about");
    expect(screen.getByRole("link", { name: "FAQ" })).toHaveAttribute("href", "#faq");
  });
});

describe("LandingNav - route links are react-router Links, not plain anchors", () => {
  // A plain <a href="/start"> that bypasses the router is indistinguishable from a
  // react-router <Link> by href alone once one is rendered inside a MemoryRouter.
  // react-router's <Link> reads router context via useContext and throws when none
  // exists, so rendering LandingNav with no Router wrapper is what actually catches
  // a regression back to plain <a> tags for the CTA/login/logo links: a real <Link>
  // throws here, a plain <a> would render fine.
  it("throws when rendered without a Router, proving the CTA/login/logo links are react-router Links", () => {
    expect(() => render(<LandingNav />)).toThrow();
  });
});

describe("LandingNav - mobile menu closes on Get Started click", () => {
  it("closes the mobile menu when Get Started is clicked, even when it targets the current route", () => {
    renderNav();
    fireEvent.click(screen.getByRole("button", { name: "Open menu" }));
    expect(screen.getByRole("button", { name: "Close menu" })).toBeInTheDocument();

    const mobileCta = screen.getAllByRole("link", { name: "Get Started" })[1];
    fireEvent.click(mobileCta);

    expect(screen.getByRole("button", { name: "Open menu" })).toBeInTheDocument();
  });
});
