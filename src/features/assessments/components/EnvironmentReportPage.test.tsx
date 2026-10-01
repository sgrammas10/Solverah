/**
 * EnvironmentReportPage.test.tsx -- the environment instrument's form, over the
 * real hooks and a real query client (only `fetchWithAuth` is mocked, per
 * ManagerPlaybookPage.test.tsx's precedent). The mock routes by path, so
 * `useProfile` and `useSituationReport` both run for real against it.
 *
 * The two `first_job` gates are fixtured separately and both must hold: the
 * report flag catches a direct visit and the submit 409 catches a profile that
 * changed under an open form. The 409 carries `errors[0].code`, never a
 * matching message, because that is what the page branches on.
 *
 * FORM ORDER IS ASSERTED, not assumed. `experienced` last, and `comp` and
 * `industry` at positions two and three, are anti-halo decisions in
 * `work_pulse/situation_items.py`, and a reorder that "tidied" the form would
 * silently change what the instrument measures. The test walks all sixteen
 * steps and checks the ends.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";

import EnvironmentReportPage from "./EnvironmentReportPage";
import { createQueryClient } from "../../../shared/api/queryClient";
import { ApiError } from "../../../shared/api/apiError";
import {
  COMP_ITEM,
  ENV_FORM_STEPS,
  ENV_ITEMS,
  EXPERIENCED_ITEM,
  INDUSTRY_ITEM,
  STAGE_SIZE_ITEM,
} from "../data/envQuestions";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  fetchWithAuth: vi.fn(),
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mocks.navigate };
});

vi.mock("../../auth/useAuth", () => ({
  useAuth: () => ({ user: { id: 1 }, fetchWithAuth: mocks.fetchWithAuth }),
}));

const NEEDS_ENV = {
  state: "needs_environment_report",
  manager: { has_profile: false },
  can_submit_environment_report: true,
};

interface ServeOptions {
  careerStatus?: string;
  report?: unknown;
  submit?: () => Promise<unknown>;
}

function serve({ careerStatus = "employed", report = NEEDS_ENV, submit }: ServeOptions = {}) {
  mocks.fetchWithAuth.mockImplementation((path: string) => {
    if (path === "/me/profile") return Promise.resolve({ profile: { career_status: careerStatus } });
    if (path === "/me/situation-report") return Promise.resolve(report);
    if (path === "/me/environment-report") {
      return submit
        ? submit()
        : Promise.resolve({
            dimension_scores: {},
            stage_size: 3,
            comp: null,
            industry: null,
            experienced: 3,
            career_status: careerStatus,
            version: "env-v2-2026-10-01",
          });
    }
    return Promise.reject(new Error(`unexpected path ${path}`));
  });
}

function renderPage() {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <EnvironmentReportPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
});

/** Get past the intro. */
async function start(past = false) {
  await screen.findByRole("heading", {
    name: past ? "Now the role you left" : "Now the other half — your job",
  });
  fireEvent.click(screen.getByRole("button", { name: "Start" }));
}

/** Answer every step, choosing option `pick(stepIndex)`, and press Finish. */
async function answerAll(pick: (i: number) => number = () => 0) {
  const total = ENV_FORM_STEPS.length;
  for (let i = 0; i < total; i += 1) {
    await screen.findByText(`Question ${i + 1} of ${total}`);
    const advance = screen.getByRole("button", { name: i === total - 1 ? "Finish" : "Next" });
    expect(advance).toBeDisabled();
    fireEvent.click(screen.getAllByRole("radio")[pick(i)]);
    await waitFor(() => expect(advance).toBeEnabled());
    fireEvent.click(advance);
  }
}

describe("EnvironmentReportPage", () => {
  it("introduces the instrument in the present tense for an employed user", async () => {
    serve();
    renderPage();

    expect(
      await screen.findByRole("heading", { name: "Now the other half — your job" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Twelve questions about the work, plus four about the setup/)).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /How this works, and what we hold back/ }),
    ).toHaveAttribute("href", "/trust");
  });

  it("introduces it in the past tense for a user between jobs", async () => {
    serve({ careerStatus: "between_jobs" });
    renderPage();

    expect(
      await screen.findByRole("heading", { name: "Now the role you left" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/your report comes back facing forward/)).toBeInTheDocument();
  });

  it("renders the past-tense prompt and options once the form starts", async () => {
    serve({ careerStatus: "between_jobs" });
    renderPage();
    await start(true);

    expect(await screen.findByText(STAGE_SIZE_ITEM.promptPast)).toBeInTheDocument();
    expect(screen.queryByText(STAGE_SIZE_ITEM.prompt)).not.toBeInTheDocument();
  });

  it("renders the form order the item bank specifies", async () => {
    serve();
    renderPage();
    await start();

    // Positions one to three: the three neutral context facts.
    expect(await screen.findByText(STAGE_SIZE_ITEM.prompt)).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("radio")[0]);
    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    expect(await screen.findByText(COMP_ITEM.prompt)).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("radio")[0]);
    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    expect(await screen.findByText(INDUSTRY_ITEM.prompt)).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("radio")[0]);
    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    // Then the twelve descriptive items, first one first.
    expect(await screen.findByText(ENV_ITEMS[0].prompt)).toBeInTheDocument();
  });

  it("asks the one evaluative item last", async () => {
    serve();
    renderPage();
    await start();

    const total = ENV_FORM_STEPS.length;
    for (let i = 0; i < total - 1; i += 1) {
      await screen.findByText(`Question ${i + 1} of ${total}`);
      fireEvent.click(screen.getAllByRole("radio")[0]);
      fireEvent.click(screen.getByRole("button", { name: "Next" }));
    }

    expect(await screen.findByText(EXPERIENCED_ITEM.prompt)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Finish" })).toBeInTheDocument();
  });

  it("offers comp's 'not sure' option", async () => {
    serve();
    renderPage();
    await start();

    await screen.findByText(STAGE_SIZE_ITEM.prompt);
    fireEvent.click(screen.getAllByRole("radio")[0]);
    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    expect(await screen.findByText("Not sure how this compares.")).toBeInTheDocument();
    expect(screen.getAllByRole("radio")).toHaveLength(COMP_ITEM.options.length);
  });

  it("renders industry in the past tense for a user between jobs", async () => {
    serve({ careerStatus: "between_jobs" });
    renderPage();
    await start(true);

    for (let i = 0; i < 2; i += 1) {
      await screen.findByText(`Question ${i + 1} of ${ENV_FORM_STEPS.length}`);
      fireEvent.click(screen.getAllByRole("radio")[0]);
      fireEvent.click(screen.getByRole("button", { name: "Next" }));
    }

    expect(await screen.findByText(INDUSTRY_ITEM.promptPast)).toBeInTheDocument();
    expect(screen.queryByText(INDUSTRY_ITEM.prompt)).not.toBeInTheDocument();
  });

  it("offers industry's levels plus a 'not sure / rather not say' option", async () => {
    serve();
    renderPage();
    await start();

    for (let i = 0; i < 2; i += 1) {
      await screen.findByText(`Question ${i + 1} of ${ENV_FORM_STEPS.length}`);
      fireEvent.click(screen.getAllByRole("radio")[0]);
      fireEvent.click(screen.getByRole("button", { name: "Next" }));
    }

    expect(await screen.findByText(INDUSTRY_ITEM.prompt)).toBeInTheDocument();
    expect(screen.getAllByRole("radio")).toHaveLength(INDUSTRY_ITEM.options.length);
    expect(screen.getByText("Not sure, or I’d rather not say.")).toBeInTheDocument();
    // Required like every step: a deliberate "not sure" is an answer, silence is not.
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  });

  it("lets the user go back and change an answer", async () => {
    serve();
    renderPage();
    await start();

    await screen.findByText(STAGE_SIZE_ITEM.prompt);
    fireEvent.click(screen.getAllByRole("radio")[0]);
    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    await screen.findByText(COMP_ITEM.prompt);
    fireEvent.click(screen.getByRole("button", { name: /Back/ }));

    expect(await screen.findByText(STAGE_SIZE_ITEM.prompt)).toBeInTheDocument();
    // The earlier answer survived the round trip.
    expect(screen.getAllByRole("radio")[0]).toHaveAttribute("aria-checked", "true");
  });

  it("submits the twelve item keys and the four raw context values", async () => {
    serve();
    renderPage();
    await start();
    await answerAll(() => 0);

    await waitFor(() =>
      expect(mocks.fetchWithAuth).toHaveBeenCalledWith(
        "/me/environment-report",
        expect.objectContaining({ method: "POST" }),
      ),
    );

    const call = mocks.fetchWithAuth.mock.calls.find((c) => c[0] === "/me/environment-report");
    const body = JSON.parse(call![1].body as string);

    expect(Object.keys(body.answers).sort()).toEqual(ENV_ITEMS.map((i) => i.itemId).sort());
    // Option KEYS, never poles or scores -- the client does not know the mapping.
    Object.values(body.answers).forEach((choice) => expect(choice).toBe("a"));
    expect(body.stage_size).toBe(STAGE_SIZE_ITEM.options[0].value);
    expect(body.comp).toBe(COMP_ITEM.options[0].value);
    expect(body.industry).toBe("tech");
    expect(body.experienced).toBe(EXPERIENCED_ITEM.options[0].value);
  });

  it("submits the industry level the user picked", async () => {
    serve();
    renderPage();
    await start();
    // industry is step three; option 2 is healthcare.
    await answerAll((i) => (i === 2 ? 2 : 0));

    await waitFor(() =>
      expect(mocks.fetchWithAuth).toHaveBeenCalledWith(
        "/me/environment-report",
        expect.objectContaining({ method: "POST" }),
      ),
    );
    const call = mocks.fetchWithAuth.mock.calls.find((c) => c[0] === "/me/environment-report");
    const body = JSON.parse(call![1].body as string);
    expect(body.industry).toBe("healthcare");
  });

  it("sends null for industry when the user is not sure or would rather not say", async () => {
    serve();
    renderPage();
    await start();
    // industry is step three; its "not sure" option is last.
    await answerAll((i) => (i === 2 ? INDUSTRY_ITEM.options.length - 1 : 0));

    await waitFor(() =>
      expect(mocks.fetchWithAuth).toHaveBeenCalledWith(
        "/me/environment-report",
        expect.objectContaining({ method: "POST" }),
      ),
    );
    const call = mocks.fetchWithAuth.mock.calls.find((c) => c[0] === "/me/environment-report");
    const body = JSON.parse(call![1].body as string);
    expect(body).toHaveProperty("industry", null);
  });

  it("sends null for comp when the user says they are not sure", async () => {
    serve();
    renderPage();
    await start();
    // comp is step two; its "not sure" option is last.
    await answerAll((i) => (i === 1 ? COMP_ITEM.options.length - 1 : 0));

    await waitFor(() =>
      expect(mocks.fetchWithAuth).toHaveBeenCalledWith(
        "/me/environment-report",
        expect.objectContaining({ method: "POST" }),
      ),
    );
    const call = mocks.fetchWithAuth.mock.calls.find((c) => c[0] === "/me/environment-report");
    const body = JSON.parse(call![1].body as string);
    expect(body.comp).toBeNull();
  });

  it("hands the user to their Situation Report on success", async () => {
    serve();
    renderPage();
    await start();
    await answerAll();

    await waitFor(() => expect(mocks.navigate).toHaveBeenCalledWith("/situation-report"));
  });

  describe("first_job", () => {
    it("never shows the form when the report says the user cannot submit one", async () => {
      serve({
        careerStatus: "first_job",
        report: { ...NEEDS_ENV, can_submit_environment_report: false },
      });
      renderPage();

      expect(
        await screen.findByRole("heading", { name: "There's no job to describe yet" }),
      ).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Start" })).not.toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: /Back to your Situation Report/ }));
      expect(mocks.navigate).toHaveBeenCalledWith("/situation-report");
    });

    it("lands on the same hand-off when the submit comes back 409, not on an error", async () => {
      // The report flag says yes; the live profile changed underneath. The 409
      // is the backstop, and it must not read as something the user broke.
      serve({
        careerStatus: "employed",
        submit: () =>
          Promise.reject(
            new ApiError("first_job has no role to describe", {
              status: 409,
              fieldErrors: [{ field: "career_status", code: "first_job_no_role" }],
            }),
          ),
      });
      renderPage();
      await start();
      await answerAll();

      expect(
        await screen.findByRole("heading", { name: "There's no job to describe yet" }),
      ).toBeInTheDocument();
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });
  });

  it("asks for a career status when the server has none to snapshot", async () => {
    serve({
      submit: () =>
        Promise.reject(new ApiError("career_status_not_set", { status: 400 })),
    });
    renderPage();
    await start();
    await answerAll();

    expect(
      await screen.findByRole("heading", { name: "One thing first: where are you right now?" }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Set your career status/ }));
    expect(mocks.navigate).toHaveBeenCalledWith("/job-seeker/profile?tab=experience", {
      state: {
        showCareerStatusModal: true,
        returnTo: { path: "/environment-report", label: "your Situation Report" },
      },
    });
  });

  it("keeps the answers and says so when the save fails for another reason", async () => {
    serve({
      submit: () => Promise.reject(new ApiError("nope", { status: 400 })),
    });
    renderPage();
    await start();
    await answerAll();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /Your answers are still here — try again/,
    );
  });

  // G6: `/me/situation-report` returns 200 in every legitimate state, so
  // `reportQuery.isError` here always means a real failure. Without the fix,
  // `blockedByReport` reads `undefined` off a failed `report` as "not
  // blocked" and the gate opens the intro on an unconfirmed first_job user.
  describe("the report gate fails to load", () => {
    function serveReportRejecting(onlyOnce = false) {
      let calls = 0;
      mocks.fetchWithAuth.mockImplementation((path: string) => {
        if (path === "/me/profile") {
          return Promise.resolve({ profile: { career_status: "employed" } });
        }
        if (path === "/me/situation-report") {
          calls += 1;
          if (!onlyOnce || calls === 1) {
            return Promise.reject(new ApiError("boom", { status: 403 }));
          }
          return Promise.resolve(NEEDS_ENV);
        }
        return Promise.reject(new Error(`unexpected path ${path}`));
      });
    }

    it("shows an error panel instead of the intro or a form", async () => {
      serveReportRejecting();
      renderPage();

      expect(
        await screen.findByText(/We couldn't load your report right now/),
      ).toBeInTheDocument();
      expect(
        screen.queryByRole("heading", { name: /Now the other half/ }),
      ).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Start" })).not.toBeInTheDocument();
    });

    it("shows the intro once Try again resolves", async () => {
      serveReportRejecting(true);
      renderPage();

      fireEvent.click(await screen.findByRole("button", { name: "Try again" }));

      expect(
        await screen.findByRole("heading", { name: "Now the other half — your job" }),
      ).toBeInTheDocument();
    });

    it("shows Loading…, not the intro, while the report is still pending", () => {
      mocks.fetchWithAuth.mockImplementation((path: string) => {
        if (path === "/me/profile") {
          return Promise.resolve({ profile: { career_status: "employed" } });
        }
        if (path === "/me/situation-report") return new Promise(() => {});
        return Promise.reject(new Error(`unexpected path ${path}`));
      });
      renderPage();

      expect(screen.getByText("Loading…")).toBeInTheDocument();
      expect(
        screen.queryByRole("heading", { name: /Now the other half/ }),
      ).not.toBeInTheDocument();
    });
  });
});

describe("EnvironmentReportPage — resume prompt for a saved draft", () => {
  const total = ENV_FORM_STEPS.length;

  function seedDraft() {
    // Steps 1 and 2 (stage_size, comp) answered; comp as "not sure" (null),
    // which must still count as answered -- key presence, not truthiness.
    const [stage, comp] = ENV_FORM_STEPS;
    sessionStorage.setItem(
      "env_report_answers",
      JSON.stringify({ answers: {}, context: { [stage.item.itemId]: 3, [comp.item.itemId]: null } }),
    );
  }

  it("asks before resuming instead of opening the intro at question 1", async () => {
    // Regression: stepIndex always started at 0 behind the intro.
    seedDraft();
    serve();
    renderPage();
    expect(
      await screen.findByRole("button", { name: "Pick up where you left off" }),
    ).toBeInTheDocument();
    expect(screen.getByText(new RegExp(`2 of ${total} questions`))).toBeInTheDocument();
  });

  it("'Pick up where you left off' lands on the first unanswered step", async () => {
    seedDraft();
    serve();
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Pick up where you left off" }));
    expect(await screen.findByText(`Question 3 of ${total}`)).toBeInTheDocument();
  });

  it("'Start over' clears the draft and lands on question 1", async () => {
    seedDraft();
    serve();
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Start over" }));
    expect(await screen.findByText(`Question 1 of ${total}`)).toBeInTheDocument();
    expect(sessionStorage.getItem("env_report_answers")).toBeNull();
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  });

  it("no draft: the intro, not the prompt", async () => {
    serve();
    renderPage();
    expect(
      await screen.findByRole("heading", { name: "Now the other half — your job" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Start over" })).toBeNull();
  });
});
