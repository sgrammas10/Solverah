/**
 * PulseDashboardCard.test.tsx -- over the real hook and a real query client
 * (only `fetchWithAuth` is mocked, per ManagerPlaybookPage.test.tsx's
 * precedent). Three states: no check-ins (invitation), one check-in (no
 * comparison to make yet), two-or-more (a direction sentence).
 */
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";

import PulseDashboardCard from "./PulseDashboardCard";
import { createQueryClient } from "../../../shared/api/queryClient";
import type { PulseHistory } from "../usePulse";

const mocks = vi.hoisted(() => ({ fetchWithAuth: vi.fn() }));

vi.mock("../../auth/useAuth", () => ({
  useAuth: () => ({ fetchWithAuth: mocks.fetchWithAuth }),
}));

function serve(history: PulseHistory) {
  mocks.fetchWithAuth.mockImplementation((path: string) => {
    if (path === "/me/pulse/history?limit=2") return Promise.resolve(history);
    return Promise.reject(new Error(`unexpected call ${path}`));
  });
}

function renderCard() {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <PulseDashboardCard />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("PulseDashboardCard", () => {
  it("invites a user with no check-ins yet", async () => {
    serve({ checkins: [], events: [] });
    renderCard();

    expect(await screen.findByText("Keep a pulse on work")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Take your first check-in →" })).toHaveAttribute(
      "href",
      "/pulse",
    );
  });

  it("says there's nothing to compare yet after exactly one check-in", async () => {
    serve({
      checkins: [
        {
          id: 1,
          taken_at: "2026-09-08T00:00:00Z",
          sequence: 0,
          item_scores: {},
          experienced: 3,
          version: "pulse-v1-2026-09-11",
        },
      ],
      events: [],
    });
    renderCard();

    expect(await screen.findByText("Your pulse this week")).toBeInTheDocument();
    expect(screen.getByText(/One check-in so far/)).toBeInTheDocument();
  });

  it("shows a direction sentence once there are two check-ins to compare", async () => {
    serve({
      checkins: [
        {
          id: 2,
          taken_at: "2026-09-08T00:00:00Z",
          sequence: 1,
          item_scores: {},
          experienced: 5,
          version: "pulse-v1-2026-09-11",
        },
        {
          id: 1,
          taken_at: "2026-09-01T00:00:00Z",
          sequence: 0,
          item_scores: {},
          experienced: 2,
          version: "pulse-v1-2026-09-11",
        },
      ],
      events: [],
    });
    renderCard();

    expect(await screen.findByText(/is up from before\./)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "See your trend →" })).toHaveAttribute(
      "href",
      "/pulse/trend",
    );
  });
});
