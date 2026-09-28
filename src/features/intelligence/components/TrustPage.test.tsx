/**
 * TrustPage — the page is content, so the tests are about the content.
 *
 * There is no state, no fetch and no branch to exercise here. What can break is
 * a section quietly disappearing in an edit, or the copy drifting back toward
 * the register the page exists to avoid — so those are what is pinned:
 *
 *  - each of the five sections still renders under its own heading;
 *  - the D-15 explanation survives, in user language rather than as a citation;
 *  - the calibration section still names all three disciplines AND still ends
 *    in its limits paragraph (the paragraph is the reason the section is not
 *    marketing; losing it silently is the realistic regression);
 *  - matching is still described as not-yet-live, because the page is wrong the
 *    day it implies CompanyLens works.
 */
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import TrustPage from "./TrustPage";

function renderTrustPage() {
  render(
    <MemoryRouter>
      <TrustPage />
    </MemoryRouter>,
  );
}

describe("TrustPage", () => {
  it("renders the page heading", () => {
    renderTrustPage();
    expect(
      screen.getByRole("heading", { level: 1, name: /how this works, and what we hold back/i }),
    ).toBeInTheDocument();
  });

  it("renders every section heading", () => {
    renderTrustPage();
    const headings = [
      /the questions are forced choices/i,
      /there is no score to see/i,
      /what matching will mean/i,
      /how we check our own instruments/i,
      /your answers/i,
    ];
    for (const name of headings) {
      expect(screen.getByRole("heading", { level: 2, name })).toBeInTheDocument();
    }
  });

  it("explains the instruments as forced choice with two legitimate poles", () => {
    renderTrustPage();
    expect(screen.getByText(/two options and ask which is more true of you/i)).toBeInTheDocument();
    expect(screen.getByText(/both options are written to be legitimate/i)).toBeInTheDocument();
  });

  it("scopes the forced-choice and reverse-keyed claims to the instruments they hold for", () => {
    // The two mistakes the first draft of this page made. FocusType is card
    // sorting, not forced choice; ManagerMatch has no reverse-keyed items
    // (MANAGER_PROFILE_ITEMS_BIAS_REVIEW.md Finding 1). Widening either
    // sentence makes the page state something untrue about its own
    // instruments, which is the failure this whole page is built against.
    renderTrustPage();
    expect(screen.getByText(/Work Pulse and ManagerMatch show you two options/i)).toBeInTheDocument();
    expect(screen.getByText(/FocusType works differently/i)).toBeInTheDocument();
    expect(screen.getByText(/Some Work Pulse items are deliberately reversed/i)).toBeInTheDocument();
  });

  it("explains why there is no score, in user language rather than by citation", () => {
    renderTrustPage();
    // The mechanism, not the decision number: a reader who has never heard of
    // D-15 has to come away understanding the argument.
    expect(screen.getByText(/a visible score becomes a target/i)).toBeInTheDocument();
    expect(screen.getByText(/no six numbers, no profile paragraph, no archetype/i)).toBeInTheDocument();
    expect(screen.queryByText(/D-15/)).toBeNull();
  });

  it("answers why FocusType shows a result when Work Pulse does not", () => {
    renderTrustPage();
    expect(screen.getByRole("heading", { name: /why does focustype show me a result/i })).toBeInTheDocument();
  });

  it("describes matching as not yet live, and as one output rather than the product", () => {
    renderTrustPage();
    expect(screen.getByText(/company matching is not live/i)).toBeInTheDocument();
    expect(screen.getByText(/one output, not the product/i)).toBeInTheDocument();
    expect(screen.getByText(/an estimate with uncertainty attached, not a verdict/i)).toBeInTheDocument();
  });

  it("states that employers see neither answers nor dimension scores", () => {
    renderTrustPage();
    expect(
      screen.getByText(/employers do not see your answers or your dimension scores/i),
    ).toBeInTheDocument();
  });

  it("names all three calibration disciplines in plain words", () => {
    renderTrustPage();
    expect(screen.getByText(/item sets are read for bias before people answer them/i)).toBeInTheDocument();
    expect(screen.getByText(/more than one trained rater, working blind/i)).toBeInTheDocument();
    expect(screen.getByText(/we attack our own anonymisation/i)).toBeInTheDocument();
    // Dissent kept rather than averaged — the part that distinguishes this from
    // a generic "reviewed by experts" claim.
    expect(screen.getByText(/we do not average it away or drop the odd one out/i)).toBeInTheDocument();
  });

  it("keeps the limits paragraph that stops the calibration section reading as marketing", () => {
    renderTrustPage();
    expect(screen.getByRole("heading", { name: /the honest limits of all that/i })).toBeInTheDocument();
    expect(screen.getByText(/the calibration set is small/i)).toBeInTheDocument();
  });

  it("links out to the public transparency and legal pages", () => {
    renderTrustPage();
    expect(screen.getByRole("link", { name: /how matching works/i })).toHaveAttribute(
      "href",
      "/how-matching-works",
    );
    expect(screen.getByRole("link", { name: /privacy policy/i })).toHaveAttribute("href", "/privacy");
    expect(screen.getByRole("link", { name: /terms of service/i })).toHaveAttribute("href", "/terms");
  });

  it("lists every section in the contents, each pointing at its heading", () => {
    renderTrustPage();
    const toc = screen.getByRole("navigation", { name: "Contents" });
    const links = within(toc).getAllByRole("link");
    expect(links).toHaveLength(5);
    for (const link of links) {
      const target = document.getElementById(link.getAttribute("href")!.slice(1));
      expect(target?.tagName).toBe("H2");
      expect(target).toHaveTextContent(link.textContent!);
    }
  });

  it("has no uppercase eyebrow label", () => {
    renderTrustPage();
    expect(screen.queryByText(/^transparency$/i)).toBeNull();
    expect(document.querySelector(".uppercase")).toBeNull();
  });

  it("offers a way back to the hub", () => {
    renderTrustPage();
    expect(screen.getByRole("link", { name: /back to your intelligence hub/i })).toHaveAttribute(
      "href",
      "/intelligence",
    );
  });
});
