import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Feed from "../Feed";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  user: { name: "Ada Lovelace" } as any,
  fetchWithAuth: vi.fn(),
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mocks.navigate };
});

vi.mock("../../contexts/useAuth", () => ({
  useAuth: () => ({ user: mocks.user, fetchWithAuth: mocks.fetchWithAuth }),
}));

beforeEach(() => {
  vi.clearAllMocks();
  mocks.user = { name: "Ada Lovelace" };
  mocks.fetchWithAuth.mockResolvedValue({ data: [], next_cursor: null });
});

function renderFeed() {
  render(
    <MemoryRouter>
      <Feed />
    </MemoryRouter>
  );
}

// ─── happy path ────────────────────────────────────────────────────────────────

describe("Feed - happy path", () => {
  it("shows welcome message with the user's first name", async () => {
    renderFeed();
    expect(screen.getByText(/Welcome to your feed, Ada!/i)).toBeInTheDocument();
  });

  it("renders the Job Feed tab as active by default", () => {
    renderFeed();
    expect(screen.getByRole("button", { name: /job feed/i })).toBeInTheDocument();
  });

  it("shows 'Job recommendations coming soon' when no recommendations", async () => {
    mocks.fetchWithAuth.mockResolvedValueOnce({ data: [], next_cursor: null });
    renderFeed();
    await waitFor(() =>
      expect(screen.getByText(/Job recommendations coming soon/i)).toBeInTheDocument()
    );
  });
});

// ─── tab switching ─────────────────────────────────────────────────────────────

describe("Feed - tab switching", () => {
  it("shows Messages tab content when Messages is clicked", () => {
    renderFeed();
    fireEvent.click(screen.getByRole("button", { name: /messages/i }));
    expect(screen.getByRole("heading", { name: /^messages$/i })).toBeInTheDocument();
  });

  it("shows Notifications tab content when Notifications is clicked", () => {
    renderFeed();
    fireEvent.click(screen.getByRole("button", { name: /notifications/i }));
    expect(screen.getByRole("heading", { name: /^notifications$/i })).toBeInTheDocument();
  });

  it("shows No notifications yet text", () => {
    renderFeed();
    fireEvent.click(screen.getByRole("button", { name: /notifications/i }));
    expect(screen.getByText(/No notifications yet/i)).toBeInTheDocument();
  });
});

// ─── search ───────────────────────────────────────────────────────────────────

describe("Feed - search", () => {
  it("navigates to /search with the query when search is submitted", async () => {
    renderFeed();
    const input = screen.getByPlaceholderText(/search jobs/i);
    fireEvent.change(input, { target: { value: "software engineer" } });
    await act(async () => {
      fireEvent.submit(input.closest("form")!);
    });
    expect(mocks.navigate).toHaveBeenCalledWith("/search?q=software%20engineer");
  });

  it("does not navigate when search query is empty", async () => {
    renderFeed();
    const input = screen.getByPlaceholderText(/search jobs/i);
    await act(async () => {
      fireEvent.submit(input.closest("form")!);
    });
    expect(mocks.navigate).not.toHaveBeenCalled();
  });
});

// ─── job recommendations ───────────────────────────────────────────────────────

describe("Feed - job recommendations", () => {
  it("renders job listings when recommendations are returned", async () => {
    mocks.fetchWithAuth.mockResolvedValueOnce({
      data: [
        {
          ID: "1",
          Title: "Senior Frontend Engineer",
          Company: "Stripe",
          Location: "Remote",
          EmploymentType: "Full-time",
          RoleDescription: "Build great UIs.",
          score: 0.9,
          Link: "https://stripe.com/jobs/1",
        },
      ],
    });
    renderFeed();
    await waitFor(() =>
      expect(screen.getByText("Senior Frontend Engineer")).toBeInTheDocument()
    );
    expect(screen.getByText("Stripe")).toBeInTheDocument();
  });
});
