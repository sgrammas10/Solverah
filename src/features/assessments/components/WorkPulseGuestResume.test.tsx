/**
 * WorkPulseGuestResume.test.tsx — the guest resume, end to end.
 *
 * The flow this pins: a guest answers all twelve legacy Work Pulse questions
 * SIGNED OUT, then signs in, and the answers survive to be scored. It works
 * because `useWP` keeps in-progress answers in sessionStorage, which neither
 * knows nor cares about the session — that is the split documented in useWP's
 * header, and this file is the proof the audit asked for that converting the
 * hook to TanStack Query did not break it.
 *
 * `useWP` is deliberately REAL here (unlike WorkPulseResultsPage.test.tsx,
 * which stubs it): the claim under test is that the hook's storage carries the
 * answers across the auth boundary, so stubbing the hook would remove the
 * thing under test. The two phases use two different QueryClients on purpose —
 * signing in reloads the app, so nothing in the guest's in-memory query cache
 * survives; only sessionStorage does.
 *
 * The scoring-job hooks are mocked as the page tests mock them; the wire-level
 * behaviour of the job is proved in useScoringJob.test.tsx.
 */
import type { ReactNode } from "react";
import { render, renderHook, screen, waitFor, act } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";

import WorkPulseResultsPage from "./WorkPulseResultsPage";
import { useWP } from "../useWP";
import type { WpApiResponse } from "../useWP";
import { workPulseResultKeys } from "../useWorkPulseResult";
import { WP_QUESTIONS } from "../data/wpQuestions";
import { createQueryClient } from "../../../shared/api/queryClient";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  fetchWithAuth: vi.fn(),
  updateProfile: vi.fn(),
  startScoringMutate: vi.fn(),
  user: null as { wpl_completed: boolean } | null,
  job: { data: undefined as Record<string, unknown> | undefined, error: null as Error | null },
}));

vi.mock("react-router-dom", () => ({
  useNavigate: () => mocks.navigate,
}));

vi.mock("../../auth/useAuth", () => ({
  useAuth: () => ({
    fetchWithAuth: mocks.fetchWithAuth,
    updateProfile: mocks.updateProfile,
    user: mocks.user,
  }),
}));

vi.mock("../useScoringJob", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../useScoringJob")>();
  return {
    ...actual,
    useStartScoringJob: () => ({ mutate: mocks.startScoringMutate }),
    useScoringJobStatus: () => mocks.job,
  };
});

const MOCK_RESULT: WpApiResponse = {
  narrative: "You bring deep focus to your work.",
  emerging_signals: [],
  archetype: "Structured Deep Thinker",
  archetype_description: "Sustained concentration with clear structure.",
};

const ACCEPTED = {
  job_id: "wp-job-1",
  status: "queued",
  status_url: "/api/v1/assessments/work_pulse/scoring-jobs/wp-job-1",
};

describe("Work Pulse guest resume", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    mocks.user = null;
    mocks.job.data = undefined;
    mocks.job.error = null;
  });

  it("answers given signed out are scored after signing in", async () => {
    // ── Phase 1: a guest, signed out, answers all twelve questions ──────────
    const guestClient = createQueryClient();
    const guestWrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={guestClient}>{children}</QueryClientProvider>
    );
    const guest = renderHook(() => useWP(), { wrapper: guestWrapper });

    act(() => {
      WP_QUESTIONS.forEach((q) => {
        guest.result.current.setAnswer(q.id, q.options[0].id);
      });
    });
    expect(guest.result.current.isComplete).toBe(true);

    // The guest signs in: the SPA reloads, so the mounted tree and the query
    // cache are gone. sessionStorage is all that crosses over.
    guest.unmount();

    // ── Phase 2: signed in, the results page resumes from storage ───────────
    mocks.user = { wpl_completed: false }; // fresh account, nothing scored yet
    mocks.startScoringMutate.mockImplementation(
      (_body: unknown, opts: { onSuccess?: (a: typeof ACCEPTED) => void }) => {
        mocks.job.data = {
          job_id: "wp-job-1",
          status: "succeeded",
          result: MOCK_RESULT,
          error: null,
        };
        opts.onSuccess?.(ACCEPTED);
      }
    );

    const signedInClient = createQueryClient();
    render(
      <QueryClientProvider client={signedInClient}>
        <WorkPulseResultsPage />
      </QueryClientProvider>
    );

    // The page found the guest's answers and enqueued them — every one, in
    // the submit's body shape — with the signed-in session's credentials.
    await waitFor(() => expect(mocks.startScoringMutate).toHaveBeenCalledTimes(1));
    expect(mocks.startScoringMutate.mock.calls[0][0]).toEqual({
      answers: WP_QUESTIONS.map((q) => ({
        question_id: q.id,
        option_id: q.options[0].id,
      })),
    });
    expect(mocks.navigate).not.toHaveBeenCalled(); // no bounce back to the quiz

    // And the scored narrative rendered, written through the real useWP into
    // the shared stored-result query.
    await waitFor(() =>
      expect(screen.getByText("Structured Deep Thinker")).toBeInTheDocument()
    );
    expect(signedInClient.getQueryData(workPulseResultKeys.result())).toEqual(MOCK_RESULT);
    expect(mocks.updateProfile).toHaveBeenCalledWith({ wpl_completed: true });
  });
});
