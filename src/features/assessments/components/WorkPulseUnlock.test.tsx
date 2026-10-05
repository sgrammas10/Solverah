import { render, screen } from "@testing-library/react";
import WorkPulseUnlock from "./WorkPulseUnlock";

describe("WorkPulseUnlock", () => {
  it("renders the completion card, with NO results link", () => {
    // The card for the CURRENT 24-item instrument, which has no results screen by
    // design (D-15): completion is the whole story. A link here would promise a payoff
    // the data layer deliberately withholds.
    render(<WorkPulseUnlock />);
    expect(
      screen.getByText(/work pulse complete — your answers now power your matching/i)
    ).toBeInTheDocument();
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("no longer previews the retired 12-question quiz's archetype", () => {
    // The data branch was deleted with the retired instrument (2026-10-02).
    render(<WorkPulseUnlock />);
    expect(screen.queryByText(/unlocked/i)).toBeNull();
    expect(screen.queryByText(/read full analysis/i)).toBeNull();
  });
});
