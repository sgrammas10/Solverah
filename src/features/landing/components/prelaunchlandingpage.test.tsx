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
function renderPage(state?: unknown) {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[{ pathname: "/", state }]}>
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

/**
 * The account-deletion confirmation. This is the only place a deleted user is
 * ever told the deletion worked: the page they asked from is behind RequireAuth
 * and their session is gone by the time this renders, so if the note does not
 * appear here it appears nowhere, and the deletion looks like a logout bug.
 *
 * It reads router state and nothing else, so an ordinary visit to / must stay
 * clean — a stranger opening the landing page must never see it.
 */
describe("account deletion confirmation", () => {
  it("confirms the deletion when routed here with the flag", () => {
    renderPage({ accountDeleted: true, filesLeftBehind: false });

    expect(screen.getByText(/Your account has been deleted\./)).toBeInTheDocument();
    expect(screen.queryByText(/couldn't be removed from storage/)).toBeNull();
  });

  it("says so when uploaded files could not be removed yet", () => {
    renderPage({ accountDeleted: true, filesLeftBehind: true });

    expect(screen.getByText(/couldn't be removed from storage yet/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "info@solverah.com" })).toHaveAttribute(
      "href",
      "mailto:info@solverah.com"
    );
  });

  it("stays out of the way of an ordinary visit", () => {
    renderPage();

    expect(screen.queryByText(/Your account has been deleted\./)).toBeNull();
  });

  it("can be dismissed", () => {
    renderPage({ accountDeleted: true, filesLeftBehind: false });

    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));

    expect(screen.queryByText(/Your account has been deleted\./)).toBeNull();
  });
});
