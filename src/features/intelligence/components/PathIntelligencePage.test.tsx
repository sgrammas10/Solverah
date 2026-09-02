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
