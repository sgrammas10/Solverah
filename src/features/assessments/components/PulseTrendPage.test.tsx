/**
 * PulseTrendPage.test.tsx -- the trend view, event log, and cadence settings,
 * over the real hooks and a real query client (only `fetchWithAuth` is
 * mocked, per ManagerPlaybookPage.test.tsx's precedent).
 *
 * PER-DIMENSION SPARSITY IS ASSERTED, NOT JUST THE HAPPY PATH. The fixture
 * below answers `fragmentation` on both check-ins but `sustainability` on
 * only one and `work_pace` on neither -- exactly the round-robin coverage
 * `pulse_items.dimensions_for_checkin` produces in the real system, and the
 * three different card states it should produce (two points / one point /
 * "Not answered yet") are each asserted rather than assumed.
 */
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";

import PulseTrendPage from "./PulseTrendPage";
import { createQueryClient } from "../../../shared/api/queryClient";
import type { PulseHistory } from "../usePulse";

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

const POPULATED_HISTORY: PulseHistory = {
  checkins: [
    {
      id: 2,
      taken_at: "2026-09-08T00:00:00Z",
      sequence: 1,
      item_scores: { fragmentation: 4, sustainability: 3, environmental_friction: 2 },
      experienced: 4,
      version: "pulse-v1-2026-09-11",
    },
    {
      id: 1,
      taken_at: "2026-09-01T00:00:00Z",
      sequence: 0,
      item_scores: { fragmentation: 2, recognition_friction: 3, environmental_friction: 3 },
      experienced: 2,
      version: "pulse-v1-2026-09-11",
    },
  ],
  events: [{ id: 1, at: "2026-09-05T00:00:00Z", event_type: "reorg" as const, note: "Team split in two" }],
};

const EMPTY_HISTORY: PulseHistory = { checkins: [], events: [] };

interface ServeOptions {
  history?: PulseHistory;
  cadence?: "weekly" | "biweekly" | "monthly" | "off";
}

function serve({ history = POPULATED_HISTORY, cadence = "weekly" }: ServeOptions = {}) {
  mocks.fetchWithAuth.mockImplementation((path: string, init?: RequestInit) => {
    if (path === "/me/pulse/history") return Promise.resolve(history);
    if (path === "/me/pulse/settings" && (!init || init.method === undefined || init.method === "GET")) {
      return Promise.resolve({ cadence });
    }
    if (path === "/me/pulse/settings" && init?.method === "PATCH") {
      const body = JSON.parse(init.body as string);
      return Promise.resolve({ cadence: body.cadence });
    }
    if (path === "/me/pulse/events" && init?.method === "POST") {
      const body = JSON.parse(init.body as string);
      return Promise.resolve({ id: 99, at: "2026-09-11T00:00:00Z", event_type: body.event_type, note: body.note });
    }
    return Promise.reject(new Error(`unexpected call ${path}`));
  });
}

function renderPage() {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <PulseTrendPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("PulseTrendPage", () => {
  it("shows the empty invitation when there are no check-ins yet, but still offers cadence settings", async () => {
    serve({ history: EMPTY_HISTORY });
    renderPage();

    expect(await screen.findByText(/Nothing to show yet/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Check in now →" })).toHaveAttribute("href", "/pulse");
    expect(await screen.findByText("Check-in cadence")).toBeInTheDocument();
  });

  it("degrades each dimension card by its own point count", async () => {
    serve();
    renderPage();
    await screen.findByText("By dimension");

    const fragmentation = screen.getByText("Focus").closest("div") as HTMLElement;
    expect(within(fragmentation).queryByText(/Not answered yet|One answer so far/)).not.toBeInTheDocument();

    const workload = screen.getByText("Workload").closest("div") as HTMLElement;
    expect(within(workload).getByText("One answer so far.")).toBeInTheDocument();

    const pace = screen.getByText("Pace").closest("div") as HTMLElement;
    expect(within(pace).getByText("Not answered yet.")).toBeInTheDocument();
  });

  it("logs a change and posts the selected type and note", async () => {
    serve();
    renderPage();
    await screen.findByText("Changes you've logged");

    fireEvent.click(screen.getByRole("button", { name: "+ Log a change" }));
    fireEvent.click(screen.getByRole("radio", { name: "New manager" }));
    fireEvent.change(screen.getByPlaceholderText("Add a short note (optional)"), {
      target: { value: "Started reporting to someone new" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(mocks.fetchWithAuth).toHaveBeenCalledWith(
        "/me/pulse/events",
        expect.objectContaining({ method: "POST" }),
      ),
    );
    const call = mocks.fetchWithAuth.mock.calls.find(([path]) => path === "/me/pulse/events");
    const body = JSON.parse((call?.[1] as RequestInit).body as string);
    expect(body).toEqual({ event_type: "new_manager", note: "Started reporting to someone new" });
  });

  it("lists an already-logged event with its date and note", async () => {
    serve();
    renderPage();
    expect(await screen.findByText("Reorg")).toBeInTheDocument();
    expect(screen.getByText('"Team split in two"')).toBeInTheDocument();
  });

  it("shows the honest slowdown note when the server has auto-dropped cadence to monthly, and offers no 'monthly' button", async () => {
    serve({ cadence: "monthly" });
    renderPage();

    expect(
      await screen.findByText(/We've slowed these down to once a month since it's been quiet/),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Monthly" })).not.toBeInTheDocument();
    ["Weekly", "Every two weeks", "Off"].forEach((label) =>
      expect(screen.getByRole("button", { name: label })).toBeInTheDocument(),
    );
  });

  it("turns cadence off with one click and no confirmation step", async () => {
    serve({ cadence: "weekly" });
    renderPage();
    await screen.findByText("Check-in cadence");

    fireEvent.click(screen.getByRole("button", { name: "Off" }));

    await waitFor(() =>
      expect(mocks.fetchWithAuth).toHaveBeenCalledWith(
        "/me/pulse/settings",
        expect.objectContaining({ method: "PATCH", body: JSON.stringify({ cadence: "off" }) }),
      ),
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
