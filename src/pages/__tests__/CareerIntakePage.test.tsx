import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { HttpResponse } from "msw";
import CareerIntakePage from "../CareerIntakePage";
import { mock } from "../../../tests/msw/contract";
import { server, useApiMocks } from "../../../tests/msw/server";

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mockNavigate };
});

/**
 * The only request this page makes is the WPLL teaser submission, issued by the
 * `TeaserResult` child on step 3. It is served by a contract-bound handler here
 * rather than by a `vi.fn()` over `globalThis.fetch`, so the path and the `{kind}`
 * in it are checked rather than assumed -- see tests/msw/contract.ts.
 */
useApiMocks();

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
    mock("post", "/api/v1/assessments/{kind}/submissions").reply(200, TEASER_RESPONSE),
  );
});

function renderPage() {
  render(
    <MemoryRouter>
      <CareerIntakePage />
    </MemoryRouter>
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
  it("step 3 shows loading state while fetch is in-flight", async () => {
    // Held open for the duration of the assertion. `delay("infinite")` would
    // leave a request pending at teardown; a gate the test owns does not.
    let release!: () => void;
    const inFlight = new Promise<void>((resolve) => { release = resolve; });
    server.use(
      mock("post", "/api/v1/assessments/{kind}/submissions").resolve(async () => {
        await inFlight;
        return HttpResponse.json(TEASER_RESPONSE);
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

  it("step 3 renders insight text after fetch resolves", async () => {
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
