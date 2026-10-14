import { render, screen, fireEvent, within, configure } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import LandingPage from "./LandingPage";
import { createQueryClient } from "../../../shared/api/queryClient";

// The ecosystem section is a lazy chunk. The first test to render it pays
// its cold import, which under a full-suite run can
// take longer than Testing Library's one-second default.
configure({ asyncUtilTimeout: 5000 });

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mockNavigate };
});

beforeEach(() => {
  vi.clearAllMocks();
});

// The page consumes useIntakeForm, whose submits are mutations
// now, so the render needs a QueryClient. Fresh per render, per the
// useProfileForm.test precedent.
function renderPage(state?: unknown, search = "") {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[{ pathname: "/", search, state }]}>
        <LandingPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

test("renders Solverah headline", async () => {
  renderPage();

  expect(screen.getAllByText(/Solverah/i).length).toBeGreaterThan(0);
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("See how you actually work.");
});

describe("scroll story hero", () => {
  it("the scroll story has a step for each part, with dots to jump between them", async () => {
    renderPage();

    const dots = await screen.findByRole("navigation", { name: "Story steps" });
    const buttons = within(dots).getAllByRole("button");
    expect(buttons).toHaveLength(5);
    expect(buttons[0]).toHaveAttribute("aria-current", "step");
    for (const heading of [
      "Answer twelve questions.",
      "See what your job is costing you.",
      "Work with the manager you have.",
      "Checked by a person. Kept from employers.",
    ]) {
      expect(screen.getByRole("heading", { name: heading })).toBeInTheDocument();
    }
    expect(screen.getByText(/Example results\./)).toBeInTheDocument();
  });
});

describe("calls to action", () => {
  it("every Get started points at the intake section on this page", async () => {
    renderPage();
    await screen.findByRole("heading", { level: 1 });

    const starts = screen.getAllByRole("link", { name: "Get started" });
    expect(starts.length).toBeGreaterThan(0);
    for (const link of starts) expect(link).toHaveAttribute("href", "#intake");
    expect(document.getElementById("intake")).not.toBeNull();
  });

  it("the Work Pulse row sends people to create an account", () => {
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: "Create an account" }));
    expect(mockNavigate).toHaveBeenCalledWith("/register");
  });

  it("quiz previews route to the guest preview, from the hero and the Work Pulse row", async () => {
    renderPage();
    await screen.findByRole("heading", { level: 1 });

    const previews = screen.getAllByRole("button", { name: "Preview a quiz" });
    expect(previews.length).toBeGreaterThanOrEqual(2);
    for (const button of previews) {
      mockNavigate.mockClear();
      fireEvent.click(button);
      expect(mockNavigate).toHaveBeenCalledWith("/quiz-preview");
    }
  });

  it("still renders the intake form and its submit", () => {
    renderPage();

    expect(screen.getByRole("button", { name: /Begin setting up my account/i })).toBeInTheDocument();
  });
});

/**
 * Product-truth guards. Work Pulse Lite is retired in code (nothing mounts
 * it), Work Pulse Pro is roadmap, and the O*NET attribution is a licence
 * obligation, so a redesign must not advertise the first, must label the
 * second, and must keep the third.
 */
describe("claims match the product", () => {
  it("does not advertise Work Pulse Lite", () => {
    renderPage();

    expect(screen.queryByText(/Work Pulse Lite/)).toBeNull();
  });

  it("labels Work Pulse Pro as unavailable and gives it no call to action", () => {
    renderPage();

    expect(screen.getByText("Not yet available")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Coming soon/i })).toBeNull();
  });

  it("reads as a launched product: no early access, waitlist or prelaunch wording", async () => {
    renderPage();
    await screen.findByRole("heading", { level: 1 });

    expect(document.body.textContent).not.toMatch(/early[- ]access|waitlist|soft launch|pre-?launch/i);
    expect(document.getElementById("waitlist")).toBeNull();
  });

  it("keeps the O*NET attribution", () => {
    renderPage();

    expect(screen.getByRole("link", { name: "O*NET 30.3 Database" })).toHaveAttribute(
      "href",
      "https://www.onetcenter.org/database.html"
    );
    expect(screen.getByRole("link", { name: "CC BY 4.0" })).toBeInTheDocument();
  });
});

describe("navigation", () => {
  it("has a skip link, a primary nav and a mobile menu toggle", () => {
    renderPage();

    expect(screen.getByRole("link", { name: "Skip to main content" })).toHaveAttribute("href", "#main");
    const nav = screen.getByRole("navigation", { name: "Primary" });
    expect(within(nav).getByRole("link", { name: "FAQ" })).toHaveAttribute("href", "#faq");

    const toggle = screen.getByRole("button", { name: "Open menu" });
    fireEvent.click(toggle);
    expect(screen.getByRole("button", { name: "Close menu" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("navigation", { name: "Primary, mobile" })).toBeInTheDocument();
  });
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
