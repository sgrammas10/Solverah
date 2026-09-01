import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import PrelaunchLandingPage from "./prelaunchlandingpage";
import { createQueryClient } from "../../../shared/api/queryClient";

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mockNavigate };
});

beforeEach(() => {
  vi.clearAllMocks();
});

// The page consumes useIntakeForm/useEarlyAccess, whose submits are mutations
// now, so the render needs a QueryClient. Fresh per render, per the
// useProfileForm.test precedent.
function renderPage() {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <PrelaunchLandingPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

test("renders Solverah headline", () => {
  renderPage();

  expect(screen.getAllByText(/Solverah/i).length).toBeGreaterThan(0);
});

it("primary CTAs navigate to /start, not the early access modal", () => {
  renderPage();

  // "Request early access" buttons navigate to /start (not open a modal)
  const requestButtons = screen.getAllByRole("button", { name: /Request early access/i });
  expect(requestButtons.length).toBeGreaterThan(0);

  fireEvent.click(requestButtons[0]);
  expect(mockNavigate).toHaveBeenCalledWith("/start");
});
