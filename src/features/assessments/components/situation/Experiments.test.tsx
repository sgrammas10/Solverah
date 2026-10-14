/**
 * Experiments.test.tsx -- `ExperimentControl` on its own, over the real hooks
 * and a real query client (only `fetchWithAuth` is mocked). The page-level
 * flows live in SituationReportPage.test.tsx; this file pins the cell-level
 * states the 2026-10-02 fix wave added: trying again after a natural end, a
 * visible message on the server's 409, and the Pulse note while running.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";

import { ExperimentControl } from "./Experiments";
import { createQueryClient } from "../../../../shared/api/queryClient";
import { ApiError } from "../../../../shared/api/apiError";
import type { Experiment } from "../../useExperiments";

const mocks = vi.hoisted(() => ({ fetchWithAuth: vi.fn() }));

vi.mock("../../../auth/useAuth", () => ({
  useAuth: () => ({ fetchWithAuth: mocks.fetchWithAuth }),
}));

const ENDED: Experiment = {
  id: 1,
  dimension: "autonomy",
  direction: "under",
  started_at: "2026-08-01T00:00:00Z",
  ends_at: "2026-08-15T00:00:00Z",
  status: "completed",
  abandoned_at: null,
  phase: "ended",
  experiment_name: "One piece, your method, for a fortnight",
  readout: { verdict: "moved_up", before_count: 2, after_count: 3 },
};

const RUNNING: Experiment = {
  ...ENDED,
  id: 2,
  started_at: "2026-09-20T00:00:00Z",
  ends_at: "2026-10-04T00:00:00Z",
  status: "active",
  phase: "running",
  readout: { verdict: "not_enough_data", before_count: 0, after_count: 0 },
};

function renderControl(props: Partial<React.ComponentProps<typeof ExperimentControl>> = {}) {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <ExperimentControl
          dimension="autonomy"
          direction="under"
          experiments={[]}
          hasActiveElsewhere={false}
          status="ready"
          {...props}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("ExperimentControl", () => {
  it("offers to try again under the readout once an experiment has ended", async () => {
    mocks.fetchWithAuth.mockResolvedValue({ ...RUNNING, id: 3 });
    renderControl({ experiments: [ENDED] });

    expect(screen.getByText("Your numbers moved up over those two weeks.")).toBeInTheDocument();
    const again = screen.getByRole("button", { name: "Try this again for two weeks" });
    expect(again).toBeEnabled();

    fireEvent.click(again);

    await waitFor(() =>
      expect(mocks.fetchWithAuth).toHaveBeenCalledWith(
        "/me/experiments",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ dimension: "autonomy", direction: "under" }),
        }),
      ),
    );
  });

  it("keeps the try-again button disabled, with the reason, while another cell's experiment runs", () => {
    renderControl({ experiments: [ENDED], hasActiveElsewhere: true });

    expect(screen.getByRole("button", { name: "Try this again for two weeks" })).toBeDisabled();
    expect(screen.getByText(/Only one experiment can run at a time/)).toBeInTheDocument();
  });

  it("says so, and refetches, when the server answers 409 -- never a silent click", async () => {
    // The page's list said nothing was running; the server disagrees.
    mocks.fetchWithAuth.mockImplementation((path: string, init?: RequestInit) => {
      if (path === "/me/experiments" && init?.method === "POST") {
        return Promise.reject(
          new ApiError("An experiment is already running", {
            status: 409,
            code: "conflict",
            fieldErrors: [{ field: "experiment", code: "experiment_already_active" }],
          }),
        );
      }
      return Promise.resolve({ experiments: [] });
    });
    renderControl();

    fireEvent.click(screen.getByRole("button", { name: "Try this for two weeks" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /Another experiment is already running/,
    );
  });

  it("shows a generic message on any other failure", async () => {
    mocks.fetchWithAuth.mockRejectedValue(new Error("boom"));
    renderControl();

    fireEvent.click(screen.getByRole("button", { name: "Try this for two weeks" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/couldn't start that just now/);
  });

  it("tells a running experiment's owner the readout needs Pulse check-ins, with a link", () => {
    renderControl({ experiments: [RUNNING] });

    expect(screen.getByText(/Running since/)).toBeInTheDocument();
    expect(screen.getByText(/compares your Pulse check-ins/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Check in now" })).toHaveAttribute("href", "/pulse");
  });
});
