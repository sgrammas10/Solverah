import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { HttpResponse } from "msw";
import CareerIntakePage from "../CareerIntakePage";
import { createQueryClient } from "../../utils/queryClient";
import { mock } from "../../../tests/msw/contract";
import { server, useApiMocks } from "../../../tests/msw/server";
import {
  scoringJobAccepted,
  scoringJobProgresses,
} from "../../../tests/msw/scoringJobHandlers";

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mockNavigate };
});

/**
 * A signed-out session, stubbed rather than provided.
 *
 * The real `AuthProvider` withholds its children behind a spinner until the
 * session probe settles, which would make every assertion on this page await a
 * request that has nothing to do with it. `{ user: null }` *is* the state this
 * funnel runs in -- it is the pre-account journey -- and the WPLL job does not
 * use `fetchWithAuth` anyway: `wpll` is the one kind fetched without the
 * session's credentials, so the requests below are still real and still land on
 * the contract-bound handlers.
 */
vi.mock("../../contexts/useAuth", () => ({
  useAuth: () => ({ fetchWithAuth: vi.fn(), user: null }),
}));

/**
 * The only requests this page makes are the WPLL teaser's, issued by the
 * `TeaserResult` child on step 3. Phase 3c moved that from one synchronous
 * submit to `POST /assessments/wpll/scoring-jobs` plus a poll, so both are
 * served here -- by contract-bound handlers rather than by a `vi.fn()` over
 * `globalThis.fetch`, so the paths and the `{kind}` in them are checked rather
 * than assumed (see tests/msw/contract.ts).
 *
 * The query client is real because `TeaserResult` now reaches the network
 * through `useScoringJob`, which is a TanStack Query mutation plus a query.
 */
useApiMocks();

const TEASER_JOB_ID = "wpll-intake-job";

const TEASER_RESPONSE = {
  insight_text: "Test insight text.",
  locked_sections: [
    "Environmental Friction Score",
    "Work Rhythm Pattern",
    "Emerging Archetype Signals",
  ],
};

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  server.use(
    scoringJobAccepted("wpll", TEASER_JOB_ID),
    // One step: the component has no poll-interval override, so a queued ->
    // succeeded ladder would cost a real three seconds here. The ladder is
    // proved in src/hooks/useScoringJob.test.tsx.
    scoringJobProgresses("wpll", TEASER_JOB_ID, [
      { status: "succeeded", result: TEASER_RESPONSE },
    ]),
  );
});

function renderPage() {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <CareerIntakePage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

async function goToStep2() {
  fireEvent.click(screen.getAllByRole("checkbox")[0]);
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: /See what Solverah sees/i }));
  });
}

async function answerAllWpll() {
  for (let i = 0; i < 5; i++) {
    await act(async () => {
      fireEvent.click(screen.getAllByRole("radio")[0]);
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /^next$/i }));
    });
  }
}

async function goToStep3() {
  await goToStep2();
  await answerAllWpll();
}

async function goToStep4() {
  await goToStep3();
  await waitFor(() => screen.getByText("Test insight text."));
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: /Create my free account/i }));
  });
}

// ─── Step 1: Statement selection ──────────────────────────────────────────────

describe("CareerIntakePage — Step 1: Statement selection", () => {
  it("renders step 1 with the correct heading", () => {
    renderPage();
    expect(screen.getByText(/true for you right now/i)).toBeInTheDocument();
  });

  it("CTA is disabled on step 1 before any statement is selected", () => {
    renderPage();
    const cta = screen.getByRole("button", { name: /See what Solverah sees/i });
    expect(cta).toBeDisabled();
  });

  it("CTA enables after selecting at least one statement", async () => {
    renderPage();
    await act(async () => {
      fireEvent.click(screen.getAllByRole("checkbox")[0]);
    });
    expect(screen.getByRole("button", { name: /See what Solverah sees/i })).not.toBeDisabled();
  });

  it("clicking the CTA on step 1 advances to step 2", async () => {
    renderPage();
    await goToStep2();
    expect(screen.getByText(/Question 1 of 5/i)).toBeInTheDocument();
  });
});

// ─── Step 2: WPLL stepper ─────────────────────────────────────────────────────

describe("CareerIntakePage — Step 2: WPLL stepper", () => {
  it("renders the first WPLL question on step 2", async () => {
    renderPage();
    await goToStep2();
    expect(screen.getByText(/Question 1 of 5/i)).toBeInTheDocument();
  });

  it("back button on step 2 returns to step 1", async () => {
    renderPage();
    await goToStep2();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Back/i }));
    });
    expect(screen.getByText(/true for you right now/i)).toBeInTheDocument();
  });

  it("completing all 5 WPLL questions advances to step 3", async () => {
    renderPage();
    await goToStep3();
    await waitFor(() => {
      expect(screen.getByText(/Here.s what.s emerging/i)).toBeInTheDocument();
    });
  });
});

// ─── Step 3: Teaser result ────────────────────────────────────────────────────

describe("CareerIntakePage — Step 3: Teaser result", () => {
  it("step 3 shows the pending state while the scoring job is queued", async () => {
    // Held open for the duration of the assertion. `delay("infinite")` would
    // leave a request pending at teardown; a gate the test owns does not.
    let release!: () => void;
    const inFlight = new Promise<void>((resolve) => { release = resolve; });
    server.use(
      mock("post", "/api/v1/assessments/{kind}/scoring-jobs").resolve(async () => {
        await inFlight;
        return HttpResponse.json(
          {
            job_id: TEASER_JOB_ID,
            status: "queued",
            status_url: `/api/v1/assessments/wpll/scoring-jobs/${TEASER_JOB_ID}`,
          },
          { status: 202 }
        );
      }),
    );
    renderPage();
    await goToStep3();
    expect(screen.getByText(/Reading your responses/i)).toBeInTheDocument();

    await act(async () => {
      release();
      await inFlight;
    });
  });

  it("step 3 renders insight text once the scoring job succeeds", async () => {
    renderPage();
    await goToStep3();
    await waitFor(() => {
      expect(screen.getByText("Test insight text.")).toBeInTheDocument();
    });
  });

  it("step 3 CTA advances to step 4", async () => {
    renderPage();
    await goToStep4();
    expect(screen.getByText(/Unlock your full results/i)).toBeInTheDocument();
  });
});

// ─── Step 4: Account gate ─────────────────────────────────────────────────────

describe("CareerIntakePage — Step 4: Account gate", () => {
  it("step 4 renders the account gate with register and login links", async () => {
    renderPage();
    await goToStep4();
    const registerLink = screen.getByRole("link", { name: /Create my free account/i });
    expect(registerLink).toHaveAttribute("href", "/register?from=wpll");
    const loginLink = screen.getByRole("link", { name: /Already have an account/i });
    expect(loginLink).toHaveAttribute("href", "/login?from=wpll");
  });

  it("back button on step 4 returns to step 3", async () => {
    renderPage();
    await goToStep4();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Back/i }));
    });
    expect(screen.getByText(/Here.s what.s emerging/i)).toBeInTheDocument();
  });
});

// ─── sessionStorage persistence ───────────────────────────────────────────────

describe("CareerIntakePage — sessionStorage persistence", () => {
  it("selected statement IDs are persisted to sessionStorage", async () => {
    renderPage();
    await act(async () => {
      fireEvent.click(screen.getAllByRole("checkbox")[0]);
    });
    await waitFor(() => {
      const stored = JSON.parse(sessionStorage.getItem("solverah_intake") ?? "{}");
      expect(stored.selectedStatementIds).toContain("dir-1");
    });
  });

  it("WPLL answers are persisted to sessionStorage as the user answers", async () => {
    renderPage();
    await goToStep2();
    await act(async () => {
      fireEvent.click(screen.getAllByRole("radio")[0]);
    });
    await waitFor(() => {
      const stored = JSON.parse(sessionStorage.getItem("solverah_intake") ?? "{}");
      expect(stored.wpllAnswers).toBeDefined();
      expect(stored.wpllAnswers[0].questionId).toBe("wpll-q1");
      expect(stored.wpllAnswers[0].optionId).toBe("wpll-q1-a");
    });
  });
});
