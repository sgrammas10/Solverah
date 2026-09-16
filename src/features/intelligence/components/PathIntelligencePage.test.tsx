/**
 * PathIntelligencePage.test.tsx — the page's states, over a mocked suggestion job.
 *
 * Phase 3c moved this screen off the synchronous `GET /me/path-suggestions`,
 * which fanned out to O*NET and OpenAI inside the request, and onto
 * `POST /me/path-suggestion-jobs` plus a poll. The job hooks are mocked here
 * (as `useProfileForm.test.tsx` mocks `useResumeParseJob`) because this file is
 * about which screen the page puts up; the wire-level claims are proved against
 * a real network in `src/hooks/usePathSuggestionJob.test.tsx`.
 *
 * `fetchWithAuth` is still mocked and still asserted on: the `PUT /me/skills`
 * write in the proficiency modal did not move and is still a plain request.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import PathIntelligencePage from "./PathIntelligencePage";
import { createQueryClient } from "../../../shared/api/queryClient";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  fetchWithAuth: vi.fn(),
  startSuggestionsMutate: vi.fn(),
  /** The enqueue mutation's own state — the page derives its screen from it. */
  start: { isPending: false, isError: false, error: null as Error | null },
  user: {} as Record<string, unknown>,
  profile: { path_preferences: { move_type: "stay_in_field" } } as Record<string, unknown>,
  /** What `usePathSuggestionJobStatus` reports on the next render. */
  job: { data: undefined as any, error: null as Error | null },
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return {
    ...actual,
    useNavigate: () => mocks.navigate,
  };
});

vi.mock("../../auth/useAuth", () => ({
  useAuth: () => ({ fetchWithAuth: mocks.fetchWithAuth, user: mocks.user }),
}));

// Experience, skills and path preferences come from the profile query now.
vi.mock("../../profile/useProfile", () => ({
  // The query hook, resolved. `isLoading: false` is the point: consumers
  // branch on it, and a mock that omitted it would report undefined --
  // falsy, so the branches would run, but by accident rather than intent.
  useProfile: () => ({ data: mocks.profile, isLoading: false }),
  profileKeys: { all: ["profile"], document: () => ["profile", "document"] },
}));

vi.mock("../usePathSuggestionJob", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../usePathSuggestionJob")>();
  return {
    ...actual,
    useStartPathSuggestionJob: () => ({ mutate: mocks.startSuggestionsMutate, ...mocks.start }),
    usePathSuggestionJobStatus: () => mocks.job,
  };
});

/** The 202 the enqueue answers with. */
const ACCEPTED = {
  job_id: "path-job-1",
  status: "queued",
  status_url: "/api/v1/me/path-suggestion-jobs/path-job-1",
};

/**
 * Make the enqueue succeed, and make the poll that follows report `job`.
 *
 * The page sets its job id inside `onSuccess`, which re-renders and re-reads
 * `usePathSuggestionJobStatus`, so writing `mocks.job.data` first is what that
 * second render sees.
 */
function suggestionsSettleAs(job: Record<string, unknown>) {
  mocks.startSuggestionsMutate.mockImplementation(
    (_vars: unknown, opts: { onSuccess?: (a: typeof ACCEPTED) => void }) => {
      mocks.job.data = job;
      opts.onSuccess?.(ACCEPTED);
    }
  );
}

/** A job that succeeds with no suggestions -- enough for the screens below. */
function suggestionsSucceed() {
  suggestionsSettleAs({
    job_id: "path-job-1",
    status: "succeeded",
    result: { suggestions: [], career_status: "employed", generated_at: "2026-09-01T00:00:00Z" },
    error: null,
  });
}

/** A job that reaches `failed` carrying `code`, which is how the two
 *  recoverable conditions arrive now that this is scored out of band. */
function suggestionsFailWith(code: string) {
  suggestionsSettleAs({
    job_id: "path-job-1",
    status: "failed",
    result: null,
    error: code,
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.profile = { path_preferences: { move_type: "stay_in_field" } };
  mocks.start.isPending = false;
  mocks.start.isError = false;
  mocks.start.error = null;
  mocks.job.data = undefined;
  mocks.job.error = null;
  // The enqueue lands but nothing terminal follows: the page stays pending.
  suggestionsSettleAs({ job_id: "path-job-1", status: "queued", result: null, error: null });
});

function renderPage() {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <PathIntelligencePage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

// ─── loading state ─────────────────────────────────────────────────────────

describe("PathIntelligencePage - loading state", () => {
  it("shows 3 skeleton cards while the job is pending", () => {
    renderPage();
    const container = screen.getByLabelText(/loading suggestions/i);
    expect(container).toBeInTheDocument();
    expect(container.children).toHaveLength(3);
  });
});

// ─── error state ───────────────────────────────────────────────────────────

describe("PathIntelligencePage - error state", () => {
  it("shows the error message when the job fails", async () => {
    suggestionsFailWith("scoring_failed");
    renderPage();
    await waitFor(() =>
      expect(
        screen.getByText(/couldn't load your path suggestions/i)
      ).toBeInTheDocument()
    );
    // Failed is its own screen: the skeletons are gone, so "still scoring" and
    // "scoring failed" are not distinguishable only by how long you wait.
    expect(screen.queryByLabelText(/loading suggestions/i)).toBeNull();
  });

  it("shows the error message when the enqueue itself is rejected", async () => {
    // A19 gives the enqueue a rate limit the synchronous GET never had. The
    // page reads the failure off the mutation's own state now, so the mock
    // reports it there rather than through an onError callback. (Set before
    // render: this mock is a plain object, and mutating it inside `mutate`
    // would not re-render the page the way a real mutation's state change
    // does.)
    mocks.start.isError = true;
    mocks.start.error = new Error("Too many requests");
    mocks.startSuggestionsMutate.mockImplementation(() => {});
    renderPage();
    await waitFor(() =>
      expect(
        screen.getByText(/couldn't load your path suggestions/i)
      ).toBeInTheDocument()
    );
  });

  it("fails closed on a status this client does not recognise", async () => {
    suggestionsSettleAs({
      job_id: "path-job-1",
      status: "reticulating_splines",
      result: null,
      error: null,
    });
    renderPage();
    await waitFor(() =>
      expect(
        screen.getByText(/couldn't load your path suggestions/i)
      ).toBeInTheDocument()
    );
  });

  it("retry button enqueues another job", async () => {
    suggestionsFailWith("scoring_failed");
    renderPage();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument()
    );
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    await waitFor(() => expect(mocks.startSuggestionsMutate).toHaveBeenCalledTimes(2));
  });
});

// ─── career status not set ─────────────────────────────────────────────────

describe("PathIntelligencePage - career status not set", () => {
  it("renders the career status onboarding prompt when the job fails with career_status_not_set", async () => {
    // The synchronous GET answered this with a 400; the job carries the same
    // string in `error`, which is what lets one mapping serve both.
    suggestionsFailWith("career_status_not_set");
    renderPage();
    await waitFor(() =>
      expect(
        screen.getByText(/set your career status/i)
      ).toBeInTheDocument()
    );
  });
});

// ─── skill proficiency modal ───────────────────────────────────────────────

const baseUser = mocks.user;

describe("PathIntelligencePage - skill proficiency modal", () => {
  afterEach(() => {
    mocks.user = baseUser;
  });

  it("shows proficiency modal on first PI visit when skills are unrated", () => {
    mocks.profile = {
      path_preferences: { move_type: "stay_in_field" },
      skills: ["React", "Python"],
      skills_proficiency_confirmed: false,
    };

    renderPage();
    expect(screen.getByText("Rate your skills")).toBeInTheDocument();
  });

  it("skip closes modal and shows nudge banner after results load", async () => {
    mocks.profile = {
      path_preferences: { move_type: "stay_in_field" },
      skills: ["React"],
      skills_proficiency_confirmed: false,
    };
    suggestionsSucceed();

    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /skip for now/i }));

    await waitFor(() =>
      expect(
        screen.getByText(/rate your skills to get more accurate/i)
      ).toBeInTheDocument()
    );
  });

  it("saving ratings PATCHes proficiency then re-fetches suggestions", async () => {
    mocks.profile = {
      path_preferences: { move_type: "stay_in_field" },
      skills: ["React"],
      skills_proficiency_confirmed: false,
    };
    mocks.fetchWithAuth.mockResolvedValueOnce({
      skills_proficiency_confirmed: true,
      skill_levels: {},
    });
    suggestionsSucceed();

    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /save & continue/i }));

    // The ratings write did not move -- it is still a plain PUT.
    await waitFor(() =>
      expect(mocks.fetchWithAuth).toHaveBeenCalledWith(
        "/me/skills",
        expect.objectContaining({ method: "PUT" })
      )
    );
    // The scoring that follows it did: it is enqueued, not awaited inline.
    await waitFor(() => expect(mocks.startSuggestionsMutate).toHaveBeenCalledTimes(1));
  });
});

// ─── F-6: inline feedback, and the deep fit on click ───────────────────────
//
// The feedback and path-fit hooks are NOT mocked. They are three lines of
// `fetchWithAuth` each and mocking them would test the mock; driving them
// through the already-mocked transport exercises the real paths, the real
// methods and the real body, which is what `tests/test_frontend_contract.py`
// scans for on the other side.

const CARD_A = {
  onet_code: "11-2021.00",
  title: "Marketing Managers",
  why_text: "A",
  profile_dimensions: ["x", "y"],
  match_score: 0.8,
};
const CARD_B = {
  onet_code: "15-1252.00",
  title: "Software Developers",
  why_text: "B",
  profile_dimensions: ["x", "y"],
  match_score: 0.7,
};

function suggestionsSucceedWith(suggestions: unknown[]) {
  suggestionsSettleAs({
    job_id: "path-job-1",
    status: "succeeded",
    result: {
      suggestions,
      career_status: "employed",
      generated_at: "2026-09-01T00:00:00Z",
    },
    error: null,
  });
}

/** Route the shared transport double by path, so one mock serves every call. */
function routeFetch(handlers: Record<string, (init?: RequestInit) => unknown>) {
  mocks.fetchWithAuth.mockImplementation((path: string, init?: RequestInit) => {
    const handler = handlers[path];
    if (!handler) return Promise.resolve({});
    const result = handler(init);
    return result instanceof Error ? Promise.reject(result) : Promise.resolve(result);
  });
}

function cardTitles(): string[] {
  return Array.from(
    document.querySelectorAll<HTMLElement>(".font-display.text-lg")
  ).map((el) => el.textContent ?? "");
}

function verdictButtons(value: string): HTMLElement[] {
  return Array.from(document.querySelectorAll<HTMLElement>(`[data-verdict="${value}"]`));
}

describe("PathIntelligencePage - inline feedback", () => {
  it("sends the tapped verdict to the feedback endpoint", async () => {
    suggestionsSucceedWith([CARD_A, CARD_B]);
    routeFetch({
      "/me/path-feedback": () => ({
        suggestions: [CARD_B, CARD_A],
        career_status: "employed",
        generated_at: "2026-09-01T00:00:01Z",
        feedback: { "11-2021.00": "interesting" },
      }),
    });

    renderPage();
    fireEvent.click(verdictButtons("interesting")[0]);

    await waitFor(() =>
      expect(mocks.fetchWithAuth).toHaveBeenCalledWith(
        "/me/path-feedback",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ onet_code: "11-2021.00", verdict: "interesting" }),
        })
      )
    );
  });

  it("re-orders the list to whatever the server ranked", async () => {
    suggestionsSucceedWith([CARD_A, CARD_B]);
    routeFetch({
      "/me/path-feedback": () => ({
        suggestions: [CARD_B, CARD_A],
        career_status: "employed",
        generated_at: "2026-09-01T00:00:01Z",
        feedback: { "11-2021.00": "interesting" },
      }),
    });

    renderPage();
    expect(cardTitles()).toEqual(["Marketing Managers", "Software Developers"]);

    fireEvent.click(verdictButtons("interesting")[0]);
    await waitFor(() =>
      expect(cardTitles()).toEqual(["Software Developers", "Marketing Managers"])
    );
  });

  it("drops a dismissed card immediately, before the server answers", async () => {
    // The client cannot predict a Rocchio re-rank and does not try. What it
    // predicts is the one part it knows: a card called "too similar" is gone.
    suggestionsSucceedWith([CARD_A, CARD_B]);
    let release: (value: unknown) => void = () => {};
    mocks.fetchWithAuth.mockImplementation(
      () => new Promise((resolve) => { release = resolve; })
    );

    renderPage();
    fireEvent.click(verdictButtons("too_similar")[0]);

    await waitFor(() => expect(cardTitles()).toEqual(["Software Developers"]));
    release({
      suggestions: [CARD_B],
      career_status: "employed",
      generated_at: "2026-09-01T00:00:01Z",
      feedback: { "11-2021.00": "too_similar" },
    });
  });

  it("keeps a card the user liked, rather than making it vanish", async () => {
    suggestionsSucceedWith([CARD_A, CARD_B]);
    mocks.fetchWithAuth.mockImplementation(() => new Promise(() => {}));

    renderPage();
    fireEvent.click(verdictButtons("interesting")[0]);

    await waitFor(() => expect(verdictButtons("interesting")[0]).toBeDisabled());
    expect(cardTitles()).toContain("Marketing Managers");
  });

  it("reverts the list and explains itself when a tap fails", async () => {
    suggestionsSucceedWith([CARD_A, CARD_B]);
    routeFetch({ "/me/path-feedback": () => new Error("rate_limited") });

    renderPage();
    fireEvent.click(verdictButtons("too_similar")[0]);

    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(cardTitles()).toEqual(["Marketing Managers", "Software Developers"]);
    expect(verdictButtons("too_similar")[0]).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });

  it("takes the whole screen for a failure about the profile, not about the card", async () => {
    suggestionsSucceedWith([CARD_A, CARD_B]);
    routeFetch({ "/me/path-feedback": () => new Error("profile_incomplete") });

    renderPage();
    fireEvent.click(verdictButtons("interesting")[0]);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /complete your profile/i })).toBeInTheDocument()
    );
  });
});

describe("PathIntelligencePage - reset", () => {
  it("offers no reset until something has been tapped", () => {
    suggestionsSucceedWith([CARD_A, CARD_B]);
    renderPage();
    expect(screen.queryByRole("button", { name: /start over/i })).toBeNull();
  });

  it("clears every judgement and restores the default list", async () => {
    suggestionsSucceedWith([CARD_A, CARD_B]);
    routeFetch({
      "/me/path-feedback": (init) =>
        init?.method === "DELETE"
          ? {
              suggestions: [CARD_A, CARD_B],
              career_status: "employed",
              generated_at: "2026-09-01T00:00:02Z",
              feedback: {},
            }
          : {
              suggestions: [CARD_B],
              career_status: "employed",
              generated_at: "2026-09-01T00:00:01Z",
              feedback: { "11-2021.00": "too_similar" },
            },
    });

    renderPage();
    fireEvent.click(verdictButtons("too_similar")[0]);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /start over/i })).toBeInTheDocument()
    );

    fireEvent.click(screen.getByRole("button", { name: /start over/i }));

    await waitFor(() =>
      expect(mocks.fetchWithAuth).toHaveBeenCalledWith(
        "/me/path-feedback",
        expect.objectContaining({ method: "DELETE" })
      )
    );
    await waitFor(() =>
      expect(cardTitles()).toEqual(["Marketing Managers", "Software Developers"])
    );
    expect(screen.queryByRole("button", { name: /start over/i })).toBeNull();
  });
});

describe("PathIntelligencePage - the deep fit on click", () => {
  it("opens the panel and asks for the clicked occupation", async () => {
    suggestionsSucceedWith([CARD_A, CARD_B]);
    mocks.fetchWithAuth.mockImplementation(() => new Promise(() => {}));

    renderPage();
    fireEvent.click(screen.getAllByRole("button", { name: /how .* fits you/i })[0]);

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    await waitFor(() =>
      expect(mocks.fetchWithAuth).toHaveBeenCalledWith(
        "/me/path-fit/11-2021.00",
        expect.objectContaining({ method: "POST" })
      )
    );
  });

  it("shows the busy region while the fit is computed", async () => {
    suggestionsSucceedWith([CARD_A]);
    mocks.fetchWithAuth.mockImplementation(() => new Promise(() => {}));

    renderPage();
    fireEvent.click(screen.getAllByRole("button", { name: /how .* fits you/i })[0]);
    await waitFor(() => expect(screen.getByRole("status")).toBeInTheDocument());
  });

  it("renders the analysis when it arrives", async () => {
    suggestionsSucceedWith([CARD_A]);
    routeFetch({
      "/me/path-fit/11-2021.00": () => ({
        onet_code: "11-2021.00",
        title: "Marketing Managers",
        fit_score: 0.71,
        retrieval_cosine: 0.8,
        centroid_score: 0.6,
        coverage_score: 0.8,
        skills_score: 0.7,
        work_style_score: 0.4,
        zone: {
          user_zone: 4,
          user_zone_resolved: true,
          occupation_zone: 4,
          delta: 0,
          score: 0.6,
        },
        matched_skills: ["Python"],
        gap_skills: [],
        tasks: [],
        tech_stack: [],
        weights: {},
        onet_calls: 4,
        narrative: null,
        computed_at: "2026-09-16T12:00:00Z",
        cached: false,
      }),
    });

    renderPage();
    fireEvent.click(screen.getAllByRole("button", { name: /how .* fits you/i })[0]);
    await waitFor(() => expect(screen.getByText("Python")).toBeInTheDocument());
  });

  it("keeps a card-level failure inside the panel", async () => {
    // Nine good suggestions must not be thrown away because the tenth could not
    // be opened.
    suggestionsSucceedWith([CARD_A, CARD_B]);
    routeFetch({ "/me/path-fit/11-2021.00": () => new Error("corpus_unavailable") });

    renderPage();
    fireEvent.click(screen.getAllByRole("button", { name: /how .* fits you/i })[0]);

    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(cardTitles()).toEqual(["Marketing Managers", "Software Developers"]);
  });

  it("escalates a profile-level failure to the whole screen", async () => {
    suggestionsSucceedWith([CARD_A]);
    routeFetch({ "/me/path-fit/11-2021.00": () => new Error("career_status_not_set") });

    renderPage();
    fireEvent.click(screen.getAllByRole("button", { name: /how .* fits you/i })[0]);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /update profile/i })).toBeInTheDocument()
    );
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("closes without leaving the fit behind for the next card", async () => {
    suggestionsSucceedWith([CARD_A, CARD_B]);
    routeFetch({
      "/me/path-fit/11-2021.00": () => new Error("unknown_occupation"),
      "/me/path-fit/15-1252.00": () => new Promise(() => {}),
    });

    renderPage();
    fireEvent.click(screen.getAllByRole("button", { name: /how .* fits you/i })[0]);
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /close/i }));
    expect(screen.queryByRole("dialog")).toBeNull();

    fireEvent.click(screen.getAllByRole("button", { name: /how .* fits you/i })[1]);
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("PathIntelligencePage - judgements that outlive a page load", () => {
  it("lights up the verdicts the server says are standing", () => {
    // A returning user's list was already shaped by these. Showing it with no
    // lit controls and no reset would hand them a shortlist bent by state they
    // can neither see nor undo.
    suggestionsSettleAs({
      job_id: "path-job-1",
      status: "succeeded",
      result: {
        suggestions: [CARD_A, CARD_B],
        career_status: "employed",
        generated_at: "2026-09-01T00:00:00Z",
        feedback: { "11-2021.00": "interesting" },
      },
      error: null,
    });

    renderPage();
    const pressed = document.querySelector('[data-verdict="interesting"]');
    expect(pressed).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /start over/i })).toBeInTheDocument();
  });

  it("treats a payload with no feedback key as no judgements", () => {
    // A payload cached before F-6 shipped carries no `feedback`, and so does a
    // user who has never tapped. Both mean the same thing.
    suggestionsSucceedWith([CARD_A, CARD_B]);
    renderPage();
    expect(document.querySelector('[data-verdict="interesting"]')).toHaveAttribute(
      "aria-pressed",
      "false"
    );
    expect(screen.queryByRole("button", { name: /start over/i })).toBeNull();
  });

  it("a reset wins over the standing judgements the job reported", async () => {
    // The job query still holds the old result. Without the touched flag the
    // cleared map would be overwritten by it on the next render and the
    // controls would light back up a moment after the user cleared them.
    suggestionsSettleAs({
      job_id: "path-job-1",
      status: "succeeded",
      result: {
        suggestions: [CARD_A, CARD_B],
        career_status: "employed",
        generated_at: "2026-09-01T00:00:00Z",
        feedback: { "11-2021.00": "too_similar" },
      },
      error: null,
    });
    routeFetch({
      "/me/path-feedback": () => ({
        suggestions: [CARD_A, CARD_B],
        career_status: "employed",
        generated_at: "2026-09-01T00:00:02Z",
        feedback: {},
      }),
    });

    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /start over/i }));

    await waitFor(() =>
      expect(screen.queryByRole("button", { name: /start over/i })).toBeNull()
    );
    expect(document.querySelector('[data-verdict="too_similar"]')).toHaveAttribute(
      "aria-pressed",
      "false"
    );
  });
});
