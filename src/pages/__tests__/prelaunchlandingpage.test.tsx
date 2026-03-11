import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import PrelaunchLandingPage from "../prelaunchlandingpage";

test("renders Solverah headline", () => {
  render(
    <MemoryRouter>
      <PrelaunchLandingPage />
    </MemoryRouter>
  );

  expect(screen.getAllByText(/Solverah/i).length).toBeGreaterThan(0);
});
