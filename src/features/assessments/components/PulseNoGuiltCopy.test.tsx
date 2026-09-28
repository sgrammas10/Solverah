/**
 * PulseNoGuiltCopy.test.tsx -- PRODUCT_DECISIONS.md §2's anti-nag rule
 * ("silence is data, never a guilt trip") over every Pulse screen this
 * chunk ships, mirroring `test_no_guilt_copy_or_streak_language_anywhere_in_the_email`
 * (`tests/test_pulse_cadence_cli.py`): scanned against real rendered output,
 * not a hand-copied stand-in of the copy, and against the exact same banned
 * list the backend test uses.
 *
 * Deliberately covers the screens most likely to slip: a check-in whose
 * score went DOWN from last time (the tempting place for "you're
 * struggling" language to creep in), and the auto-dropped-to-monthly
 * cadence note (the email's own slowdown line, reused here almost
 * verbatim -- this test is what keeps that reuse honest rather than
 * assumed).
 */
import { render, screen, fireEvent, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";

import PulseCheckinPage from "./PulseCheckinPage";
import PulseTrendPage from "./PulseTrendPage";
import PulseDashboardCard from "./PulseDashboardCard";
import { createQueryClient } from "../../../shared/api/queryClient";
import type { PulseHistory, PulseNextCheckin } from "../usePulse";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  fetchWithAuth: vi.fn(),
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mocks.navigate };
});

vi.mock("../../auth/useAuth", () => ({
  useAuth: () => ({ fetchWithAuth: mocks.fetchWithAuth }),
}));

const NEXT_CHECKIN: PulseNextCheckin = {
  sequence: 1,
  version: "pulse-v1-2026-09-11",
  items: [
    {
      item_id: "pulse-fragmentation-1",
      dimension: "fragmentation",
      stem: "How well could you focus without interruption this week?",
      low_anchor: "Constantly pulled away",
      high_anchor: "Stayed focused",
    },
    {
      item_id: "pulse-sustainability-1",
      dimension: "sustainability",
      stem: "How sustainable did this week's workload feel?",
      low_anchor: "Draining",
      high_anchor: "Comfortable",
    },
    {
      item_id: "pulse-work_pace-1",
      dimension: "work_pace",
      stem: "How well did this week's pace match what works for you?",
      low_anchor: "Badly mismatched",
      high_anchor: "Matched well",
    },
  ],
  experienced_item: {
    item_id: "pulse-experienced",
    stem: "This week, how well is work working for you?",
    low_anchor: "Not working",
    high_anchor: "Working very well",
  },
};

/** Exactly `tests/test_pulse_cadence_cli.py`'s banned list. */
const BANNED = ["streak", "miss", "haven't", "you didn't", "still waiting", "come back"];

function assertNoGuiltCopy(text: string) {
  const lower = text.toLowerCase();
  for (const banned of BANNED) {
    expect(lower).not.toContain(banned);
  }
}

interface ServeOptions {
  checkinHistory?: PulseHistory;
  cardHistory?: PulseHistory;
  trendHistory?: PulseHistory;
  cadence?: "weekly" | "biweekly" | "monthly" | "off";
  autoSlowed?: boolean;
}

function serve({
  checkinHistory = { checkins: [], events: [] },
  cardHistory = { checkins: [], events: [] },
  trendHistory = { checkins: [], events: [] },
  cadence = "weekly",
  autoSlowed = false,
}: ServeOptions = {}) {
  mocks.fetchWithAuth.mockImplementation((path: string, init?: RequestInit) => {
    if (path === "/me/pulse/next-checkin") return Promise.resolve(NEXT_CHECKIN);
    if (path === "/me/pulse/history?limit=11") return Promise.resolve(checkinHistory);
    if (path === "/me/pulse/history?limit=2") return Promise.resolve(cardHistory);
    if (path === "/me/pulse/history") return Promise.resolve(trendHistory);
    if (path === "/me/pulse/settings" && (!init || init.method === undefined || init.method === "GET")) {
      return Promise.resolve({ cadence, auto_slowed: autoSlowed });
    }
    if (path === "/me/pulse/checkins" && init?.method === "POST") {
      const body = JSON.parse(init.body as string);
      return Promise.resolve({
        id: 1,
        sequence: NEXT_CHECKIN.sequence,
        taken_at: "2026-09-11T00:00:00Z",
        item_scores: body.item_scores,
        experienced: body.experienced,
        version: NEXT_CHECKIN.version,
      });
    }
    return Promise.reject(new Error(`unexpected call ${path}`));
  });
}

function withProviders(node: React.ReactNode) {
  return (
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("Pulse copy has no guilt/streak/nag language anywhere", () => {
  it("the check-in form itself", async () => {
    serve();
    const { container } = render(withProviders(<PulseCheckinPage />));
    await screen.findByText(NEXT_CHECKIN.items[0].stem);
    assertNoGuiltCopy(container.textContent ?? "");
  });

  it("the first-ever-check-in confirmation (no prior to compare to)", async () => {
    serve({ checkinHistory: { checkins: [], events: [] } });
    const { container } = render(
      withProviders(<PulseCheckinPage />),
    );
    await screen.findByText(NEXT_CHECKIN.items[0].stem);
    for (const row of [...NEXT_CHECKIN.items, NEXT_CHECKIN.experienced_item]) {
      const group = screen.getByRole("radiogroup", { name: row.stem });
      fireEvent.click(within(group).getByRole("radio", { name: "2" }));
    }
    fireEvent.click(screen.getByRole("button", { name: "Done" }));
    await screen.findByText("That's your first pulse");
    assertNoGuiltCopy(container.textContent ?? "");
  });

  it("a confirmation whose score went DOWN from last time -- the tempting spot for guilt copy", async () => {
    serve({
      checkinHistory: {
        checkins: [
          {
            id: 5,
            taken_at: "2026-09-04T00:00:00Z",
            sequence: 0,
            item_scores: { environmental_friction: 4, recognition_friction: 4 },
            experienced: 5,
            version: "pulse-v1-2026-09-11",
          },
        ],
        events: [],
      },
    });
    const { container } = render(withProviders(<PulseCheckinPage />));
    await screen.findByText(NEXT_CHECKIN.items[0].stem);
    for (const row of [...NEXT_CHECKIN.items, NEXT_CHECKIN.experienced_item]) {
      const group = screen.getByRole("radiogroup", { name: row.stem });
      fireEvent.click(within(group).getByRole("radio", { name: "1" }));
    }
    fireEvent.click(screen.getByRole("button", { name: "Done" }));
    await screen.findByText(/is down from last time\./);
    assertNoGuiltCopy(container.textContent ?? "");
  });

  it("the trend page's empty state", async () => {
    serve();
    const { container } = render(withProviders(<PulseTrendPage />));
    await screen.findByText(/Nothing to show yet/);
    assertNoGuiltCopy(container.textContent ?? "");
  });

  it("the trend page's auto-dropped-to-monthly cadence note -- reused from the email's own wording", async () => {
    serve({ cadence: "monthly", autoSlowed: true });
    const { container } = render(withProviders(<PulseTrendPage />));
    await screen.findByText(/We've slowed these down to once a month/);
    assertNoGuiltCopy(container.textContent ?? "");
  });

  it("the dashboard card's invitation state", async () => {
    serve();
    const { container } = render(withProviders(<PulseDashboardCard />));
    await screen.findByText("Keep a pulse on work");
    assertNoGuiltCopy(container.textContent ?? "");
  });

  it("the dashboard card comparing a score that went down", async () => {
    serve({
      cardHistory: {
        checkins: [
          {
            id: 2,
            taken_at: "2026-09-08T00:00:00Z",
            sequence: 1,
            item_scores: {},
            experienced: 1,
            version: "pulse-v1-2026-09-11",
          },
          {
            id: 1,
            taken_at: "2026-09-01T00:00:00Z",
            sequence: 0,
            item_scores: {},
            experienced: 5,
            version: "pulse-v1-2026-09-11",
          },
        ],
        events: [],
      },
    });
    const { container } = render(withProviders(<PulseDashboardCard />));
    await screen.findByText(/is down from before\./);
    assertNoGuiltCopy(container.textContent ?? "");
  });
});
