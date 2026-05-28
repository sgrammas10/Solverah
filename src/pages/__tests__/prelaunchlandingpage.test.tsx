import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import PrelaunchLandingPage from "../prelaunchlandingpage";

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mockNavigate };
});

beforeEach(() => {
  vi.clearAllMocks();
});

test("renders Solverah headline", () => {
  render(
    <MemoryRouter>
      <PrelaunchLandingPage />
    </MemoryRouter>
  );

  expect(screen.getAllByText(/Solverah/i).length).toBeGreaterThan(0);
});

it("primary CTAs navigate to /start, not the early access modal", () => {
  render(
    <MemoryRouter>
      <PrelaunchLandingPage />
    </MemoryRouter>
  );

  // "Request early access" buttons navigate to /start (not open a modal)
  const requestButtons = screen.getAllByRole("button", { name: /Request early access/i });
  expect(requestButtons.length).toBeGreaterThan(0);

  fireEvent.click(requestButtons[0]);
  expect(mockNavigate).toHaveBeenCalledWith("/start");
});
