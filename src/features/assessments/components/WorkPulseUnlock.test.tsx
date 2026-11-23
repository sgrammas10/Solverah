import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import WorkPulseUnlock from "./WorkPulseUnlock";

/** Shows where a link landed and the router state it carried. */
function Landing() {
  const location = useLocation();
  return (
    <div data-testid="landing">
      {location.pathname} {JSON.stringify(location.state)}
    </div>
  );
}

function renderCard() {
  render(
    <MemoryRouter initialEntries={["/job-seeker/dashboard"]}>
      <Routes>
        <Route path="/job-seeker/dashboard" element={<WorkPulseUnlock />} />
        <Route path="*" element={<Landing />} />
      </Routes>
    </MemoryRouter>
  );
}

describe("WorkPulseUnlock", () => {
  it("renders the completion card, with NO results link", () => {
    // The card for the CURRENT 24-item instrument, which has no results screen by
    // design (D-15): completion is the whole story. A link here would promise a payoff
    // the data layer deliberately withholds.
    renderCard();
    expect(
      screen.getByText(/work pulse complete — your answers now power your matching/i)
    ).toBeInTheDocument();
    const hrefs = screen.getAllByRole("link").map((a) => a.getAttribute("href"));
    expect(hrefs.sort()).toEqual(["/trait-preferences", "/work-pulse"]);
    expect(screen.queryByRole("link", { name: /result|analysis|score/i })).toBeNull();
  });

  it("no longer previews the retired 12-question quiz's archetype", () => {
    // The data branch was deleted with the retired instrument (2026-10-02).
    renderCard();
    expect(screen.queryByText(/unlocked/i)).toBeNull();
    expect(screen.queryByText(/read full analysis/i)).toBeNull();
  });

  it("links to a retake, straight into the form (G46)", () => {
    // Regression: once Work Pulse was complete nothing in the product reached
    // /work-pulse, so the retake was only reachable by typing the URL.
    renderCard();
    fireEvent.click(screen.getByRole("link", { name: /retake work pulse/i }));
    expect(screen.getByTestId("landing")).toHaveTextContent('/work-pulse {"retake":true}');
  });

  it("links to the tolerance step (G46)", () => {
    renderCard();
    fireEvent.click(
      screen.getByRole("link", { name: /change how much give you have on each area/i })
    );
    expect(screen.getByTestId("landing")).toHaveTextContent("/trait-preferences null");
  });
});
