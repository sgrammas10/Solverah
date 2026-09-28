/**
 * PulseCheckinPage.test.tsx -- the one-screen check-in and its "one thing
 * back" confirmation, over the real hooks and a real query client (only
 * `fetchWithAuth` is mocked, per ManagerPlaybookPage.test.tsx's precedent).
 *
 * ITEM ORDER IS ASSERTED. `experienced` renders last because
 * `pulse_items.py`'s anti-halo ordering puts the one evaluative item after
 * the descriptive ones -- a reorder that "tidied" the form would silently
 * undo that.
 *
 * THE PRIOR SCORE IS A FIXTURE THE MUTATION NEVER TOUCHES. `serve()` returns
 * the same `history` payload before and after submit -- the page must read
 * its own frozen snapshot (`priorRef`) rather than the live query, or the
 * "last week" figure in the confirmation would silently become the just-
 * submitted row once the post-submit refetch resolves. Test five asserts the
 * number actually shown, not just that a comparison rendered.
 */
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";

import PulseCheckinPage from "./PulseCheckinPage";
import { createQueryClient } from "../../../shared/api/queryClient";
import type { PulseNextCheckin, PulseHistory } from "../usePulse";

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
  sequence: 2,
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

const HISTORY_ONE_PRIOR: PulseHistory = {
  checkins: [
    {
      id: 9,
      taken_at: "2026-09-04T00:00:00Z",
      sequence: 1,
      item_scores: { environmental_friction: 2, recognition_friction: 3, fragmentation: 3 },
      experienced: 2,
      version: "pulse-v1-2026-09-11",
    },
  ],
  events: [],
};

const EMPTY_HISTORY: PulseHistory = { checkins: [], events: [] };

interface ServeOptions {
  nextCheckin?: PulseNextCheckin;
  history?: PulseHistory;
  submitResult?: unknown;
}

function serve({ nextCheckin = NEXT_CHECKIN, history = HISTORY_ONE_PRIOR, submitResult }: ServeOptions = {}) {
  mocks.fetchWithAuth.mockImplementation((path: string, init?: RequestInit) => {
    if (path === "/me/pulse/next-checkin") return Promise.resolve(nextCheckin);
    if (path === "/me/pulse/history?limit=11") return Promise.resolve(history);
    if (path === "/me/pulse/checkins" && init?.method === "POST") {
      if (submitResult) return submitResult instanceof Error ? Promise.reject(submitResult) : Promise.resolve(submitResult);
      const body = JSON.parse(init.body as string);
      return Promise.resolve({
        id: 10,
        sequence: nextCheckin.sequence,
        taken_at: "2026-09-11T00:00:00Z",
        item_scores: body.item_scores,
        experienced: body.experienced,
        version: nextCheckin.version,
      });
    }
    return Promise.reject(new Error(`unexpected call ${path}`));
  });
}

function renderPage() {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <PulseCheckinPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

/** Answer every row with `value`, in the order the server sent them. */
async function answerAll(value = 4) {
  await screen.findByText(NEXT_CHECKIN.items[0].stem);
  const allRows = [...NEXT_CHECKIN.items, NEXT_CHECKIN.experienced_item];
  for (const row of allRows) {
    const group = screen.getByRole("radiogroup", { name: row.stem });
    fireEvent.click(within(group).getByRole("radio", { name: `${value}` }));
  }
}

describe("PulseCheckinPage", () => {
  it("renders the three served dimensions in order, with experienced last", async () => {
    serve();
    renderPage();

    const stems = await screen.findAllByText(
      /focus without interruption|workload feel|pace match|is work working/,
    );
    const stemTexts = stems.map((el) => el.textContent);
    expect(stemTexts).toEqual([
      NEXT_CHECKIN.items[0].stem,
      NEXT_CHECKIN.items[1].stem,
      NEXT_CHECKIN.items[2].stem,
      NEXT_CHECKIN.experienced_item.stem,
    ]);
  });

  it("keeps Done disabled until all four rows are answered", async () => {
    serve();
    renderPage();
    await screen.findByText(NEXT_CHECKIN.items[0].stem);

    const done = screen.getByRole("button", { name: "Done" });
    expect(done).toBeDisabled();

    const firstGroup = screen.getByRole("radiogroup", { name: NEXT_CHECKIN.items[0].stem });
    fireEvent.click(within(firstGroup).getByRole("radio", { name: "3" }));
    expect(done).toBeDisabled();

    await answerAll(4);
    expect(done).toBeEnabled();
  });

  it("submits item_scores keyed by dimension, never by item_id", async () => {
    serve();
    renderPage();
    await answerAll(5);
    fireEvent.click(screen.getByRole("button", { name: "Done" }));

    await waitFor(() =>
      expect(mocks.fetchWithAuth).toHaveBeenCalledWith(
        "/me/pulse/checkins",
        expect.objectContaining({ method: "POST" }),
      ),
    );
    const call = mocks.fetchWithAuth.mock.calls.find(([path]) => path === "/me/pulse/checkins");
    const body = JSON.parse((call?.[1] as RequestInit).body as string);
    expect(body).toEqual({
      item_scores: { fragmentation: 5, sustainability: 5, work_pace: 5 },
      experienced: 5,
    });
  });

  it("shows the honest first-point message for a user's first-ever check-in, no comparison", async () => {
    serve({ nextCheckin: { ...NEXT_CHECKIN, sequence: 0 }, history: EMPTY_HISTORY });
    renderPage();
    await answerAll(3);
    fireEvent.click(screen.getByRole("button", { name: "Done" }));

    expect(await screen.findByText("That's your first pulse")).toBeInTheDocument();
    expect(
      screen.getByText(/Nothing to compare it to yet/),
    ).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("compares this check-in against the frozen prior snapshot, not a live refetch", async () => {
    serve({ nextCheckin: { ...NEXT_CHECKIN, sequence: 1 }, history: HISTORY_ONE_PRIOR });
    renderPage();
    await answerAll(5); // prior experienced was 2, so this should read "up"

    fireEvent.click(screen.getByRole("button", { name: "Done" }));

    expect(await screen.findByText("Two points make a trend")).toBeInTheDocument();
    expect(screen.getByText(/is up from last time\./)).toBeInTheDocument();
  });

  it("preserves answers and shows an inline error when the submit fails", async () => {
    serve({ submitResult: new Error("boom") });
    renderPage();
    await answerAll(4);
    fireEvent.click(screen.getByRole("button", { name: "Done" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("We couldn't save that just now");
    const firstGroup = screen.getByRole("radiogroup", { name: NEXT_CHECKIN.items[0].stem });
    expect(within(firstGroup).getByRole("radio", { name: "4" })).toHaveAttribute("aria-checked", "true");
  });
  it("plots every recent check-in plus the new one, not just the last two", async () => {
    // Regression: after the third check-in the chart showed 2 points, because
    // the page fetched history with limit=1 and drew [prior, current].
    const rec = (id: number, day: string, experienced: number) => ({
      id,
      taken_at: `2026-09-${day}T00:00:00Z`,
      sequence: id,
      item_scores: {},
      experienced,
      version: "pulse-v1-2026-09-11",
    });
    serve({
      nextCheckin: { ...NEXT_CHECKIN, sequence: 2 },
      // Newest first, as the wire sends it.
      history: { checkins: [rec(2, "04", 3), rec(1, "01", 2)], events: [] },
    });
    renderPage();
    await answerAll(5);
    fireEvent.click(screen.getByRole("button", { name: "Done" }));

    const chart = await screen.findByRole("img", { name: /recent check-ins/ });
    expect(chart.querySelectorAll("circle")).toHaveLength(3);
    // Compared against the newest prior (3), not the oldest (2).
    expect(screen.getByText(/is up from last week\./)).toBeInTheDocument();
    expect(mocks.fetchWithAuth).toHaveBeenCalledWith("/me/pulse/history?limit=11", expect.anything());
  });
});
