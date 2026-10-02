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
import { MemoryRouter, useLocation } from "react-router-dom";
import PathIntelligencePage from "./PathIntelligencePage";
import { createQueryClient } from "../../../shared/api/queryClient";
import { ApiError } from "../../../shared/api/apiError";

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
  /**
   * W-15: run the REAL job hooks over the mocked transport instead of the
   * doubles above. The doubles hand back one constant object, which cannot
   * reproduce anything that depends on the query's own lifecycle.
   */
  realJob: false,
  /**
   * Serve the profile out of the query cache (seeded from `profile`) instead of
   * as a constant, so a test can see what the page itself wrote into that
   * cache. Off by default: the constant is what every other test is about.
   */
  profileFromCache: false,
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
vi.mock("../../profile/useProfile", async () => {
  const { useQuery } = await import("@tanstack/react-query");
  // Always subscribed, so the hook order never depends on the flag; the flag
  // only picks which copy is handed back.
  function useProfile() {
    const cached = useQuery({
      queryKey: ["profile", "document"],
      queryFn: () => mocks.profile,
      initialData: mocks.profile,
      staleTime: Infinity,
    }).data;
    // The query hook, resolved. `isLoading: false` is the point: consumers
    // branch on it, and a mock that omitted it would report undefined --
    // falsy, so the branches would run, but by accident rather than intent.
    return { data: mocks.profileFromCache ? cached : mocks.profile, isLoading: false };
  }
  return {
    useProfile,
    profileKeys: { all: ["profile"], document: () => ["profile", "document"] },
  };
});

vi.mock("../usePathSuggestionJob", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../usePathSuggestionJob")>();
  return {
    ...actual,
    useStartPathSuggestionJob: () =>
      mocks.realJob
        ? actual.useStartPathSuggestionJob()
        : { mutate: mocks.startSuggestionsMutate, ...mocks.start },
    usePathSuggestionJobStatus: (jobId: string | null) =>
      mocks.realJob ? actual.usePathSuggestionJobStatus(jobId) : mocks.job,
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

const READY_PROFILE = {
  path_preferences: { move_type: "stay_in_field" },
  career_status: "employed",
  skills: ["Python"],
  skills_proficiency_confirmed: true,
};

beforeEach(() => {
  vi.clearAllMocks();
  // A profile that clears both entry gates (career status, at least one
  // skill) and the proficiency modal, so the job starts on mount.
  mocks.profile = { ...READY_PROFILE };
  mocks.start.isPending = false;
  mocks.start.isError = false;
  mocks.start.error = null;
  mocks.job.data = undefined;
  mocks.job.error = null;
  mocks.realJob = false;
  mocks.profileFromCache = false;
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

// ─── the header ────────────────────────────────────────────────────────────

describe("PathIntelligencePage - the subtitle", () => {
  it("says the paths are matched, never scored", () => {
    // Ruling flag 12: no percentage, no score, and no grade word standing in
    // for one reaches this screen -- which has to include the page's own
    // description of what it is doing. Wording is Julie's; the ban is not.
    renderPage();
    expect(screen.getByText(/matched to your skills and work profile/i)).toBeInTheDocument();
    expect(screen.queryByText(/scored against/i)).toBeNull();
  });
});

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

// ─── entry gates: career status first, then skills ─────────────────────────

describe("PathIntelligencePage - entry order", () => {
  it("asks for career status first, before the proficiency modal or preferences", () => {
    mocks.profile = { skills: ["React"], skills_proficiency_confirmed: false };
    renderPage();
    expect(screen.getByText(/set your career status to get started/i)).toBeInTheDocument();
    expect(screen.queryByText("Rate your skills")).toBeNull();
    expect(mocks.startSuggestionsMutate).not.toHaveBeenCalled();
    expect(screen.queryByLabelText(/loading suggestions/i)).toBeNull();
  });

  it("asks for career status before the preferences form when nothing is set", () => {
    mocks.profile = { skills: ["React"], skills_proficiency_confirmed: true };
    renderPage();
    expect(screen.getByText(/set your career status to get started/i)).toBeInTheDocument();
    // The preferences form (no path_preferences here) must not be what shows.
    expect(screen.queryByText(/question 1 of/i)).toBeNull();
  });

  it("treats a current role in experience as a career status, as the server does", () => {
    mocks.profile = {
      ...READY_PROFILE,
      career_status: undefined,
      experience: [{ position: "Analyst", endDate: "Present" }],
    };
    renderPage();
    expect(screen.queryByText(/set your career status/i)).toBeNull();
    expect(mocks.startSuggestionsMutate).toHaveBeenCalledTimes(1);
  });

  it("carries a returnTo back to this page when sending the user to set it", () => {
    mocks.profile = { skills: ["React"] };
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /update profile/i }));
    expect(mocks.navigate).toHaveBeenCalledWith("/job-seeker/profile?tab=experience", {
      state: {
        showCareerStatusModal: true,
        returnTo: { path: "/", label: "Path Intelligence" },
      },
    });
  });

  it("asks for skills, with a link to add them, before the preferences form", () => {
    mocks.profile = { career_status: "between_jobs", skills: [] };
    renderPage();
    expect(screen.getByText(/add a few skills to get started/i)).toBeInTheDocument();
    expect(screen.queryByText(/question 1 of/i)).toBeNull();
    expect(screen.getByRole("link", { name: /add skills/i })).toHaveAttribute(
      "href",
      "/job-seeker/profile?tab=experience"
    );
    expect(mocks.startSuggestionsMutate).not.toHaveBeenCalled();
    expect(screen.queryByLabelText(/loading suggestions/i)).toBeNull();
  });
});

describe("PathIntelligencePage - Pro badge", () => {
  it("reads as coming soon, not as a live tier", () => {
    renderPage();
    expect(screen.getByText(/pro · coming soon/i)).toBeInTheDocument();
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
      career_status: "employed",
      skills: ["React", "Python"],
      skills_proficiency_confirmed: false,
    };

    renderPage();
    expect(screen.getByText("Rate your skills")).toBeInTheDocument();
  });

  it("skip closes modal and shows nudge banner after results load", async () => {
    mocks.profile = {
      path_preferences: { move_type: "stay_in_field" },
      career_status: "employed",
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
      career_status: "employed",
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
const CARD_C = {
  onet_code: "29-1141.00",
  title: "Registered Nurses",
  why_text: "C",
  profile_dimensions: ["x", "y"],
  match_score: 0.6,
};
const CARD_D = {
  onet_code: "47-2111.00",
  title: "Electricians",
  why_text: "D",
  profile_dimensions: ["x", "y"],
  match_score: 0.5,
};

/** A complete `PathFitResponse`, which the panel renders every field of. */
function fitPayload(onetCode: string, title: string) {
  return {
    onet_code: onetCode,
    title,
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
    // Zero since W-9: the four O*NET calls moved into the corpus sidecar.
    onet_calls: 0,
    narrative: null,
    computed_at: "2026-09-16T12:00:00Z",
    cached: false,
  };
}

/** Every deep-fit POST this render has made, in order. */
function fitRequests(): string[] {
  return mocks.fetchWithAuth.mock.calls
    .map((call) => String(call[0]))
    .filter((path) => path.startsWith("/me/path-fit/"));
}

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

// ─── W-9: the three cards on screen are warm before anybody clicks ─────────
//
// Sebastian's first click-through: "the loading of a position when i click on
// it takes so long to load going to need to have a better approach to caching
// these things." The server half of the answer is the fit sidecar; this is the
// client half, and these are the four ways it could be wrong -- warming the
// wrong cards, warming them twice, not being used by the click, or being
// visible when it fails.

describe("PathIntelligencePage - warming the cards on screen", () => {
  it("warms exactly the three cards that rendered, not the whole list", async () => {
    // `PathSuggestionList` pages at three. Warming all ten would spend seven
    // requests on cards nobody has scrolled to.
    suggestionsSucceedWith([CARD_A, CARD_B, CARD_C, CARD_D]);
    routeFetch({});

    renderPage();

    await waitFor(() => expect(fitRequests()).toHaveLength(3));
    expect(fitRequests().sort()).toEqual([
      "/me/path-fit/11-2021.00",
      "/me/path-fit/15-1252.00",
      "/me/path-fit/29-1141.00",
    ]);
  });

  it("warms the next three when Show more reveals them", async () => {
    suggestionsSucceedWith([CARD_A, CARD_B, CARD_C, CARD_D]);
    routeFetch({});
    renderPage();
    await waitFor(() => expect(fitRequests()).toHaveLength(3));

    fireEvent.click(screen.getByRole("button", { name: /show 1 more path/i }));

    await waitFor(() => expect(fitRequests()).toHaveLength(4));
    expect(fitRequests()).toContain("/me/path-fit/47-2111.00");
  });

  it("warms nothing a second time when the list re-ranks under it", async () => {
    // A re-rank changes the order, so the list reports a different set of
    // codes -- but they are the same occupations, and the cache already has
    // them. Re-requesting here is what burned the old 10/min limit.
    suggestionsSucceedWith([CARD_A, CARD_B, CARD_C]);
    routeFetch({
      "/me/path-feedback": () => ({
        suggestions: [CARD_C, CARD_A, CARD_B],
        career_status: "employed",
        generated_at: "2026-09-01T00:00:01Z",
        feedback: { "11-2021.00": "interesting" },
      }),
    });
    renderPage();
    await waitFor(() => expect(fitRequests()).toHaveLength(3));

    fireEvent.click(verdictButtons("interesting")[0]);

    await waitFor(() =>
      expect(cardTitles()).toEqual([
        "Registered Nurses",
        "Marketing Managers",
        "Software Developers",
      ])
    );
    expect(fitRequests()).toHaveLength(3);
  });

  it("opens a warm card without asking again", async () => {
    suggestionsSucceedWith([CARD_A]);
    routeFetch({
      "/me/path-fit/11-2021.00": () => fitPayload("11-2021.00", "Marketing Managers"),
    });
    renderPage();
    await waitFor(() => expect(fitRequests()).toHaveLength(1));

    fireEvent.click(screen.getAllByRole("button", { name: /how .* fits you/i })[0]);

    await waitFor(() => expect(screen.getByText("Python")).toBeInTheDocument());
    expect(fitRequests()).toHaveLength(1);
  });

  it("reopening a card makes no second request", async () => {
    suggestionsSucceedWith([CARD_A]);
    routeFetch({
      "/me/path-fit/11-2021.00": () => fitPayload("11-2021.00", "Marketing Managers"),
    });
    renderPage();
    await waitFor(() => expect(fitRequests()).toHaveLength(1));

    fireEvent.click(screen.getAllByRole("button", { name: /how .* fits you/i })[0]);
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /close/i }));
    fireEvent.click(screen.getAllByRole("button", { name: /how .* fits you/i })[0]);

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(fitRequests()).toHaveLength(1);
  });

  it("renders nothing at all when a prefetch is refused", async () => {
    // A 429 on something the user never asked for. No alert, no panel, no
    // change to the list -- they find out nothing, because there is nothing
    // they needed to know.
    suggestionsSucceedWith([CARD_A, CARD_B, CARD_C]);
    mocks.fetchWithAuth.mockImplementation((path: string) =>
      path.startsWith("/me/path-fit/")
        ? Promise.reject(new Error("rate_limited"))
        : Promise.resolve({})
    );

    renderPage();

    await waitFor(() => expect(fitRequests()).toHaveLength(3));
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(cardTitles()).toEqual([
      "Marketing Managers",
      "Software Developers",
      "Registered Nurses",
    ]);
  });

  it("a click after a refused prefetch still gets its own error handling", async () => {
    suggestionsSucceedWith([CARD_A, CARD_B]);
    mocks.fetchWithAuth.mockImplementation((path: string) =>
      path.startsWith("/me/path-fit/")
        ? Promise.reject(new Error("corpus_unavailable"))
        : Promise.resolve({})
    );
    renderPage();
    await waitFor(() => expect(fitRequests()).toHaveLength(2));

    fireEvent.click(screen.getAllByRole("button", { name: /how .* fits you/i })[0]);

    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});

// ─── W-5: the wants panel, which must never stand in front of the results ──
//
// `PathWantsPanel` is NOT mocked, for the reason the feedback hooks are not:
// the claim being made here is that the panel cannot delay, block or break the
// list, and a stub of the panel cannot make that claim about the real one.

const WANTS_PANEL = {
  status: "ok",
  anchor: { onet_code: "15-1252.00", title: "Software Developers" },
  tasks: [{ key: "t_a1b2c3d4e5f6", label: "Write and test code", verdict: null }],
  conditions: [{ axis: "people", label: "Time with other people", verdict: null }],
};

/** GET the panel, accept any PUT, and hand everything else back an empty body. */
function serveWants(panel: unknown = WANTS_PANEL) {
  mocks.fetchWithAuth.mockImplementation((path: string, init?: RequestInit) => {
    if (path !== "/me/path-wants") return Promise.resolve({});
    if ((init?.method ?? "GET") === "GET") {
      return panel instanceof Error ? Promise.reject(panel) : Promise.resolve(panel);
    }
    return Promise.resolve(panel);
  });
}

function wantsToggle(): HTMLElement | null {
  return screen.queryByRole("button", { name: /what should change about your job/i });
}

describe("PathIntelligencePage - the wants panel never blocks the results", () => {
  it("shows the suggestions while the panel's own request is still in flight", async () => {
    suggestionsSucceedWith([CARD_A, CARD_B]);
    mocks.fetchWithAuth.mockImplementation(() => new Promise(() => {}));

    renderPage();

    expect(cardTitles()).toEqual(["Marketing Managers", "Software Developers"]);
    expect(wantsToggle()).toBeNull();
  });

  it("shows the suggestions when the panel's request fails outright", async () => {
    suggestionsSucceedWith([CARD_A, CARD_B]);
    serveWants(new Error("corpus_unavailable"));

    renderPage();

    await waitFor(() =>
      expect(mocks.fetchWithAuth).toHaveBeenCalledWith(
        "/me/path-wants",
        expect.objectContaining({ method: "GET" })
      )
    );
    expect(cardTitles()).toEqual(["Marketing Managers", "Software Developers"]);
    // Silent: no alert, no empty panel, no retry link for something the user
    // never asked for.
    expect(wantsToggle()).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("renders the panel above the suggestion list once it lands", async () => {
    suggestionsSucceedWith([CARD_A, CARD_B]);
    serveWants();

    renderPage();

    const control = await screen.findByRole("button", {
      name: /what should change about your job/i,
    });
    const firstCard = document.querySelector("[data-onet-code]")!;
    expect(
      control.compareDocumentPosition(firstCard) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
    expect(cardTitles()).toEqual(["Marketing Managers", "Software Developers"]);
  });

  it("re-scores through the page's existing job flow after a save", async () => {
    suggestionsSucceedWith([CARD_A, CARD_B]);
    serveWants();

    renderPage();
    const control = await screen.findByRole("button", {
      name: /what should change about your job/i,
    });
    // One enqueue so far: the mount.
    expect(mocks.startSuggestionsMutate).toHaveBeenCalledTimes(1);

    fireEvent.click(control);
    fireEvent.click(
      document.querySelector<HTMLInputElement>(
        'input[name="want-condition-people"][value="more"]'
      )!
    );
    fireEvent.click(document.querySelector<HTMLElement>("[data-wants-save]")!);

    await waitFor(() =>
      expect(mocks.fetchWithAuth).toHaveBeenCalledWith(
        "/me/path-wants",
        expect.objectContaining({ method: "PUT" })
      )
    );
    // The same enqueue-and-poll the page runs for a cache miss -- not a second
    // job flow living in the panel.
    await waitFor(() => expect(mocks.startSuggestionsMutate).toHaveBeenCalledTimes(2));
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

  it("renders the whole bar off the server's map, with no local tap", () => {
    // W-13, from the third browser test: tap "Not for me" on two cards and
    // reload, and the cards stayed removed while the bar and its "Start over"
    // were gone -- judgements in force with no way to see or undo them. The
    // page was right and the payload was wrong (`intelligence_service._rescore`
    // cached itself without `feedback`); this pins the page's half, which is
    // that the whole bar comes from the job result alone.
    suggestionsSettleAs({
      job_id: "path-job-1",
      status: "succeeded",
      result: {
        suggestions: [CARD_A, CARD_B],
        career_status: "employed",
        generated_at: "2026-09-01T00:00:00Z",
        feedback: { "11-2021.00": "not_for_me" },
      },
      error: null,
    });

    renderPage();

    expect(screen.getByText(/shaped by what you/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /start over/i })).toBeEnabled();
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

// --- W-15: "Show 3 more paths" after a full reload -------------------------
//
// Fourth user test: reload /intelligence/paths, three cards show, "Show 3 more
// paths" does nothing however often it is clicked. The job doubles above hand
// back one constant object, so this runs the real enqueue + poll hooks over
// the mocked transport, with a job that is already `succeeded` on its first
// poll -- which is what a warm `path_cache` produces.
//
// NOT REPRODUCED (W-15): this passes on HEAD, and so did six reload scenarios
// driven in real Chrome against the real stack. It stays as the guard for the
// claim "a warm-cache mount pages correctly", which the doubles cannot make.

function tenCards() {
  return Array.from({ length: 10 }, (_, i) => ({
    onet_code: `11-10${String(i).padStart(2, "0")}.00`,
    title: `Path ${i}`,
    why_text: `why ${i}`,
    profile_dimensions: ["x", "y"],
    match_score: 0.9 - i * 0.01,
  }));
}

describe("PathIntelligencePage - Show more after a reload (W-15)", () => {
  it("reveals six cards on a warm-cache job", async () => {
    mocks.realJob = true;
    const result = {
      suggestions: tenCards(),
      career_status: "employed",
      generated_at: "2026-09-01T00:00:00Z",
      feedback: {},
    };
    mocks.fetchWithAuth.mockImplementation((path: string, init?: RequestInit) => {
      if (path === "/me/path-suggestion-jobs" && init?.method === "POST") {
        return Promise.resolve(ACCEPTED);
      }
      if (path === "/me/path-suggestion-jobs/path-job-1") {
        return Promise.resolve({
          job_id: "path-job-1",
          status: "succeeded",
          result,
          error: null,
        });
      }
      if (path.startsWith("/me/path-fit/")) {
        return Promise.resolve(fitPayload(path.split("/").pop()!, "x"));
      }
      return Promise.resolve({});
    });

    renderPage();
    await waitFor(() => expect(cardTitles()).toHaveLength(3));
    // Let the prefetches for the first three land before the click.
    await waitFor(() => expect(fitRequests()).toHaveLength(3));

    fireEvent.click(screen.getByRole("button", { name: /show 3 more paths/i }));

    await waitFor(() => expect(cardTitles()).toHaveLength(6));
  });
});

// ─── W-16: cards first, sentences after ────────────────────────────────────

const UNWRITTEN_B = { ...CARD_B, why_text: "", profile_dimensions: [] };

function scoredResult(suggestions: unknown[], narrationPending: boolean) {
  return {
    suggestions,
    career_status: "employed",
    generated_at: "2026-09-01T00:00:00Z",
    feedback: {},
    narration_pending: narrationPending,
  };
}

function pendingSentences(): Element[] {
  return Array.from(document.querySelectorAll("[data-sentence-pending]"));
}

function renderPageWithRerender() {
  const client = createQueryClient();
  const tree = () => (
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <PathIntelligencePage />
      </MemoryRouter>
    </QueryClientProvider>
  );
  const view = render(tree());
  return () => view.rerender(tree());
}

describe("PathIntelligencePage - cards before their sentences (W-16)", () => {
  it("renders the cards as soon as the scored result arrives, shimmering only the unwritten sentence", () => {
    suggestionsSettleAs({
      job_id: "path-job-1",
      status: "succeeded",
      result: scoredResult([CARD_A, UNWRITTEN_B], true),
      error: null,
    });

    renderPage();

    expect(cardTitles()).toEqual(["Marketing Managers", "Software Developers"]);
    expect(screen.queryByLabelText(/loading suggestions/i)).toBeNull();
    expect(screen.getByText("A")).toBeInTheDocument();
    const pending = pendingSentences();
    expect(pending).toHaveLength(1);
    expect(pending[0].closest("[data-onet-code]")?.getAttribute("data-onet-code")).toBe(
      "15-1252.00"
    );
  });

  it("puts each sentence in place when the narration lands, without moving the cards", async () => {
    mocks.realJob = true;
    let polls = 0;
    mocks.fetchWithAuth.mockImplementation((path: string, init?: RequestInit) => {
      if (path === "/me/path-suggestion-jobs" && init?.method === "POST") {
        return Promise.resolve(ACCEPTED);
      }
      if (path === "/me/path-suggestion-jobs/path-job-1") {
        polls += 1;
        const narrated = polls > 1;
        return Promise.resolve({
          job_id: "path-job-1",
          status: "succeeded",
          result: scoredResult([CARD_A, narrated ? CARD_B : UNWRITTEN_B], !narrated),
          error: null,
        });
      }
      return Promise.resolve({});
    });

    renderPage();
    await waitFor(() => expect(pendingSentences()).toHaveLength(1));
    expect(cardTitles()).toEqual(["Marketing Managers", "Software Developers"]);

    await waitFor(() => expect(screen.getByText("B")).toBeInTheDocument(), { timeout: 5000 });
    expect(pendingSentences()).toHaveLength(0);
    expect(cardTitles()).toEqual(["Marketing Managers", "Software Developers"]);
  });

  it("keeps the cards and stops the shimmer when a poll fails mid-narration", () => {
    suggestionsSettleAs({
      job_id: "path-job-1",
      status: "succeeded",
      result: scoredResult([CARD_A, UNWRITTEN_B], true),
      error: null,
    });
    mocks.job.error = new Error("Too Many Requests");

    renderPage();

    expect(cardTitles()).toEqual(["Marketing Managers", "Software Developers"]);
    expect(pendingSentences()).toHaveLength(0);
    expect(screen.queryByText(/couldn't load your path suggestions/i)).toBeNull();
  });

  it("fills a card a mid-narration tap left empty once the narration is over", async () => {
    suggestionsSettleAs({
      job_id: "path-job-1",
      status: "succeeded",
      result: scoredResult([CARD_A, UNWRITTEN_B], true),
      error: null,
    });
    routeFetch({
      "/me/path-feedback": () => ({
        ...scoredResult([UNWRITTEN_B, CARD_A], true),
        feedback: { "15-1252.00": "interesting" },
      }),
      "/me/path-suggestions": () => ({
        ...scoredResult([CARD_B, CARD_A], false),
        feedback: { "15-1252.00": "interesting" },
      }),
    });

    const rerender = renderPageWithRerender();
    fireEvent.click(verdictButtons("interesting")[1]);
    await waitFor(() =>
      expect(cardTitles()).toEqual(["Software Developers", "Marketing Managers"])
    );
    expect(pendingSentences()).toHaveLength(1);
    // Still narrating: nothing to read back yet.
    expect(mocks.fetchWithAuth).not.toHaveBeenCalledWith("/me/path-suggestions", expect.anything());

    // The job's poll reports the narration over.
    mocks.job.data = {
      job_id: "path-job-1",
      status: "succeeded",
      result: scoredResult([CARD_A, CARD_B], false),
      error: null,
    };
    rerender();

    await waitFor(() => expect(screen.getByText("B")).toBeInTheDocument());
    expect(pendingSentences()).toHaveLength(0);
    expect(cardTitles()).toEqual(["Software Developers", "Marketing Managers"]);
  });

  it("ends the wants panel's busy state when the cards arrive, not when the sentences do", async () => {
    mocks.realJob = true;
    let enqueued = 0;
    let secondJobPolls = 0;
    mocks.fetchWithAuth.mockImplementation((path: string, init?: RequestInit) => {
      if (path === "/me/path-wants") return Promise.resolve(WANTS_PANEL);
      if (path === "/me/path-suggestion-jobs" && init?.method === "POST") {
        enqueued += 1;
        return Promise.resolve({ ...ACCEPTED, job_id: `path-job-${enqueued}` });
      }
      if (path === "/me/path-suggestion-jobs/path-job-1") {
        return Promise.resolve({
          job_id: "path-job-1",
          status: "succeeded",
          result: scoredResult([CARD_A, CARD_B], false),
          error: null,
        });
      }
      if (path === "/me/path-suggestion-jobs/path-job-2") {
        secondJobPolls += 1;
        // Queued once, then scored with its sentences still coming -- forever,
        // so the only way the busy state can end is on the cards.
        return Promise.resolve(
          secondJobPolls === 1
            ? { job_id: "path-job-2", status: "queued", result: null, error: null }
            : {
                job_id: "path-job-2",
                status: "succeeded",
                result: scoredResult([CARD_B, { ...CARD_A, why_text: "", profile_dimensions: [] }], true),
                error: null,
              }
        );
      }
      return Promise.resolve({});
    });

    renderPage();
    const control = await screen.findByRole("button", {
      name: /what should change about your job/i,
    });
    fireEvent.click(control);
    fireEvent.click(
      document.querySelector<HTMLInputElement>(
        'input[name="want-condition-people"][value="more"]'
      )!
    );
    fireEvent.click(document.querySelector<HTMLElement>("[data-wants-save]")!);

    await waitFor(() => expect(screen.getByText(/re-sorting your paths/i)).toBeInTheDocument());
    await waitFor(() => expect(pendingSentences()).toHaveLength(1), { timeout: 8000 });
    await waitFor(() => expect(screen.queryByText(/re-sorting your paths/i)).toBeNull());
    expect(pendingSentences()).toHaveLength(1);
  });
});

// ─── W-18: an O*NET summary on every card, from the first poll ─────────────

describe("PathIntelligencePage - the summary arrives with the card (W-18)", () => {
  it("shows each card's summary with the scored result, before its sentence is written", () => {
    suggestionsSettleAs({
      job_id: "path-job-1",
      status: "succeeded",
      result: scoredResult(
        [
          { ...CARD_A, summary: "Plan and run marketing programs." },
          { ...UNWRITTEN_B, summary: "Build and test software." },
        ],
        true
      ),
      error: null,
    });

    renderPage();

    expect(screen.getByText("Plan and run marketing programs.")).toBeInTheDocument();
    expect(screen.getByText("Build and test software.")).toBeInTheDocument();
    const pending = pendingSentences();
    expect(pending).toHaveLength(1);
    const card = pending[0].closest("[data-onet-code]");
    expect(card?.querySelector("[data-summary]")?.textContent).toBe("Build and test software.");
  });
});

// ─── Fix wave 2026-10-02: the audit's four defects ─────────────────────────

/** Every `PUT /me/skills` body this render has sent, parsed. */
function skillsPuts(): unknown[] {
  return mocks.fetchWithAuth.mock.calls
    .filter((call) => call[0] === "/me/skills")
    .map((call) => JSON.parse(String((call[1] as RequestInit).body)));
}

/** Every `POST /me/path-feedback` body this render has sent, parsed. */
function feedbackPosts(): unknown[] {
  return mocks.fetchWithAuth.mock.calls
    .filter((call) => call[0] === "/me/path-feedback" && (call[1] as RequestInit)?.method === "POST")
    .map((call) => JSON.parse(String((call[1] as RequestInit).body)));
}

describe("PathIntelligencePage - skill ratings saved here reach the profile cache", () => {
  it("reopens Edit skill ratings on the ratings just saved, and a second Save sends those", async () => {
    // The page used to write the ratings and leave the cached profile alone,
    // so the modal reopened on the page-load values and its Save wrote them
    // straight back over the new ones.
    mocks.profileFromCache = true;
    mocks.profile = { ...READY_PROFILE, skills: ["React"], skill_levels: { React: "beginner" } };
    suggestionsSucceedWith([CARD_A]);
    routeFetch({
      "/me/skills": (init) => {
        const body = JSON.parse(String(init?.body)) as {
          skills: Array<{ name: string; proficiency: string }>;
        };
        return {
          skills_proficiency_confirmed: true,
          skill_levels: Object.fromEntries(body.skills.map((s) => [s.name, s.proficiency])),
        };
      },
    });

    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /edit skill ratings/i }));
    fireEvent.click(screen.getByRole("button", { name: "Advanced" }));
    fireEvent.click(screen.getByRole("button", { name: /save & continue/i }));
    await waitFor(() => expect(screen.queryByText("Rate your skills")).toBeNull());

    fireEvent.click(screen.getByRole("button", { name: /edit skill ratings/i }));
    expect(screen.getByRole("button", { name: "Advanced" })).toHaveClass("bg-forest-dark");
    expect(screen.getByRole("button", { name: "Beginner" })).not.toHaveClass("bg-forest-dark");

    fireEvent.click(screen.getByRole("button", { name: /save & continue/i }));
    await waitFor(() => expect(skillsPuts()).toHaveLength(2));
    expect(skillsPuts()[1]).toEqual({ skills: [{ name: "React", proficiency: "advanced" }] });
  });
});

describe("PathIntelligencePage - a deep fit never outlives a fresh scoring", () => {
  it("asks for the fit again after the user leaves the page and comes back", async () => {
    // The QueryClient survives a trip to the profile page, and the fit query
    // is cached forever -- so a user who changed their skills or title came
    // back to the analysis from before the change.
    suggestionsSucceedWith([CARD_A]);
    routeFetch({
      "/me/path-fit/11-2021.00": () => fitPayload("11-2021.00", "Marketing Managers"),
    });
    const client = createQueryClient();
    const tree = () => (
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <PathIntelligencePage />
        </MemoryRouter>
      </QueryClientProvider>
    );

    const first = render(tree());
    await waitFor(() => expect(fitRequests()).toHaveLength(1));
    first.unmount();

    // ...skills edited on the profile page, then back here.
    render(tree());
    fireEvent.click(screen.getAllByRole("button", { name: /how .* fits you/i })[0]);

    await waitFor(() => expect(fitRequests()).toHaveLength(2));
    await waitFor(() => expect(screen.getByText("Python")).toBeInTheDocument());
  });
});

describe("PathIntelligencePage - a failed tap can be sent again", () => {
  it("Try again resends the verdict that failed", async () => {
    suggestionsSucceedWith([CARD_A, CARD_B]);
    let posts = 0;
    routeFetch({
      "/me/path-feedback": () => {
        posts += 1;
        return posts === 1
          ? new Error("rate_limited")
          : {
              suggestions: [CARD_B],
              career_status: "employed",
              generated_at: "2026-09-01T00:00:01Z",
              feedback: { "11-2021.00": "too_similar" },
            };
      },
    });

    renderPage();
    fireEvent.click(verdictButtons("too_similar")[0]);
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(cardTitles()).toEqual(["Marketing Managers", "Software Developers"]);

    fireEvent.click(screen.getByRole("button", { name: /try again/i }));

    await waitFor(() => expect(cardTitles()).toEqual(["Software Developers"]));
    const sent = { onet_code: "11-2021.00", verdict: "too_similar" };
    expect(feedbackPosts()).toEqual([sent, sent]);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("Try again resends a Start over that failed", async () => {
    suggestionsSucceedWith([CARD_A, CARD_B]);
    let deletes = 0;
    routeFetch({
      "/me/path-feedback": (init) => {
        if (init?.method !== "DELETE") {
          return {
            suggestions: [CARD_B],
            career_status: "employed",
            generated_at: "2026-09-01T00:00:01Z",
            feedback: { "11-2021.00": "too_similar" },
          };
        }
        deletes += 1;
        return deletes === 1
          ? new Error("rate_limited")
          : {
              suggestions: [CARD_A, CARD_B],
              career_status: "employed",
              generated_at: "2026-09-01T00:00:02Z",
              feedback: {},
            };
      },
    });

    renderPage();
    fireEvent.click(verdictButtons("too_similar")[0]);
    fireEvent.click(await screen.findByRole("button", { name: /start over/i }));
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /try again/i }));

    await waitFor(() =>
      expect(cardTitles()).toEqual(["Marketing Managers", "Software Developers"])
    );
    expect(deletes).toBe(2);
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("PathIntelligencePage - a sentence that is never coming falls back", () => {
  const UNWRITTEN_B_WITH_SKILLS = { ...UNWRITTEN_B, overlapping_skills: ["Python", "SQL"] };

  it("fills the house sentence when the read-back after a mid-narration tap fails", async () => {
    suggestionsSettleAs({
      job_id: "path-job-1",
      status: "succeeded",
      result: scoredResult([CARD_A, UNWRITTEN_B_WITH_SKILLS], true),
      error: null,
    });
    routeFetch({
      "/me/path-feedback": () => ({
        ...scoredResult([UNWRITTEN_B_WITH_SKILLS, CARD_A], true),
        feedback: { "15-1252.00": "interesting" },
      }),
      "/me/path-suggestions": () => new Error("internal_error"),
    });

    const rerender = renderPageWithRerender();
    fireEvent.click(verdictButtons("interesting")[1]);
    await waitFor(() =>
      expect(cardTitles()).toEqual(["Software Developers", "Marketing Managers"])
    );

    mocks.job.data = {
      job_id: "path-job-1",
      status: "succeeded",
      result: scoredResult([CARD_A, CARD_B], false),
      error: null,
    };
    rerender();

    await waitFor(() =>
      expect(mocks.fetchWithAuth).toHaveBeenCalledWith("/me/path-suggestions", expect.anything())
    );
    await waitFor(() => expect(screen.getByText("Uses your Python and SQL.")).toBeInTheDocument());
    expect(pendingSentences()).toHaveLength(0);
    expect(cardTitles()).toEqual(["Software Developers", "Marketing Managers"]);
  });

  it("fills the house sentence when the job's poll gives up mid-narration", () => {
    suggestionsSettleAs({
      job_id: "path-job-1",
      status: "succeeded",
      result: scoredResult([CARD_A, UNWRITTEN_B], true),
      error: null,
    });
    mocks.job.error = new Error("Too Many Requests");

    renderPage();

    expect(pendingSentences()).toHaveLength(0);
    expect(
      screen.getByText("A different direction. Open it to see how it lines up with your skills.")
    ).toBeInTheDocument();
  });
});

describe("PathIntelligencePage - a refused re-score keeps the list", () => {
  it("leaves the cards up and says so inline when a wants save's re-score is rate limited", async () => {
    mocks.realJob = true;
    let enqueued = 0;
    mocks.fetchWithAuth.mockImplementation((path: string, init?: RequestInit) => {
      if (path === "/me/path-wants") return Promise.resolve(WANTS_PANEL);
      if (path === "/me/path-suggestion-jobs" && init?.method === "POST") {
        enqueued += 1;
        return enqueued === 1
          ? Promise.resolve(ACCEPTED)
          : Promise.reject(new ApiError("rate_limited", { status: 429, code: "rate_limited" }));
      }
      if (path === "/me/path-suggestion-jobs/path-job-1") {
        return Promise.resolve({
          job_id: "path-job-1",
          status: "succeeded",
          result: scoredResult([CARD_A, CARD_B], false),
          error: null,
        });
      }
      return Promise.resolve({});
    });

    renderPage();
    const control = await screen.findByRole("button", {
      name: /what should change about your job/i,
    });
    expect(cardTitles()).toEqual(["Marketing Managers", "Software Developers"]);

    fireEvent.click(control);
    fireEvent.click(
      document.querySelector<HTMLInputElement>(
        'input[name="want-condition-people"][value="more"]'
      )!
    );
    fireEvent.click(document.querySelector<HTMLElement>("[data-wants-save]")!);

    await waitFor(() => expect(enqueued).toBe(2));
    await waitFor(() =>
      expect(document.querySelector("[data-rescore-error]")).not.toBeNull()
    );
    expect(screen.getByText(/a lot of updates at once/i)).toBeInTheDocument();
    expect(cardTitles()).toEqual(["Marketing Managers", "Software Developers"]);
    expect(screen.queryByText(/couldn't load your path suggestions/i)).toBeNull();

    // And the way out of it is the same enqueue, not a reload.
    fireEvent.click(screen.getByRole("button", { name: /update my paths/i }));
    await waitFor(() => expect(enqueued).toBe(3));
  });

  it("still shows the full error card when there is no list to keep", async () => {
    mocks.start.isError = true;
    mocks.start.error = new ApiError("rate_limited", { status: 429 });
    mocks.startSuggestionsMutate.mockImplementation(() => {});

    renderPage();

    await waitFor(() =>
      expect(screen.getByText(/couldn't load your path suggestions/i)).toBeInTheDocument()
    );
    expect(document.querySelector("[data-rescore-error]")).toBeNull();
  });
});

describe("PathIntelligencePage - the add-skills prompt carries a way back", () => {
  it("sends the user to the profile with the same returnTo the career-status prompt uses", () => {
    mocks.profile = { career_status: "between_jobs", skills: [] };
    function LocationProbe() {
      const location = useLocation();
      return (
        <pre data-testid="location">
          {JSON.stringify({ path: location.pathname, state: location.state })}
        </pre>
      );
    }
    render(
      <QueryClientProvider client={createQueryClient()}>
        <MemoryRouter initialEntries={["/intelligence/paths"]}>
          <PathIntelligencePage />
          <LocationProbe />
        </MemoryRouter>
      </QueryClientProvider>
    );

    fireEvent.click(screen.getByRole("link", { name: /add skills/i }));

    expect(JSON.parse(screen.getByTestId("location").textContent ?? "{}")).toEqual({
      path: "/job-seeker/profile",
      state: { returnTo: { path: "/intelligence/paths", label: "Path Intelligence" } },
    });
  });
});
