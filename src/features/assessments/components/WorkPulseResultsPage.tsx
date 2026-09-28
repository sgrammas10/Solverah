/**
 * WorkPulseResultsPage — Work Pulse, scored by a job rather than by the submit.
 *
 * Phase 3c: `work_pulse` is one of the three provider-scored instruments, so
 * generating a narrative now means `POST /assessments/work_pulse/scoring-jobs`
 * and then polling, instead of holding a request open for the tens of seconds
 * the OpenAI call can take (A19). The succeeded job's `result` is the same body
 * the synchronous submit returned, so everything downstream of it here is
 * unchanged.
 *
 * `GET /me/assessments/work_pulse/result` — the "I already did this, show me
 * the stored one" path — is untouched. It reads a persisted row and opens no
 * socket; it was never the slow one.
 */
import { useState, useEffect, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useWP } from "../useWP";
import type { WpApiResponse } from "../useWP";
import { useAuth } from "../../auth";
import { profileKeys } from "../../profile";
import {
  isKnownScoringPhase,
  useScoringJobStatus,
  useStartScoringJob,
  type ScoringJobResult,
} from "../useScoringJob";
import { useWorkPulseResult } from "../useWorkPulseResult";
import { WP_QUESTIONS } from "../data/wpQuestions";
import { TierBar } from "../../intake";

/**
 * The job's `result` in the shape this page renders.
 *
 * `WorkPulseResult` as generated from the OpenAPI document is deliberately open
 * — `emerging_signals?: unknown[]`, `archetype_description: string | null`,
 * plus an index signature — because the API documents it that way. `WpApiResponse`
 * is the narrower shape the page has always rendered, and the synchronous call
 * this replaces asserted exactly the same narrowing by writing
 * `fetchWithAuth<WpApiResponse>(...)`. The assertion has moved, not appeared.
 */
function asWpApiResponse(result: ScoringJobResult<"work_pulse">): WpApiResponse {
  return result as unknown as WpApiResponse;
}

export default function WorkPulseResultsPage() {
  const navigate = useNavigate();
  const { user, updateProfile } = useAuth();
  const { state, setCachedResult } = useWP();
  const queryClient = useQueryClient();

  const hasCached = state.cachedResult !== null;
  const hasFiredRef = useRef(false);

  const startScoring = useStartScoringJob("work_pulse");
  const [jobId, setJobId] = useState<string | null>(null);
  const job = useScoringJobStatus("work_pulse", jobId);
  // The enqueue failing is mutation state, but it arrives through a callback;
  // this one flag captures it for render. The old `FetchState` machine that
  // mirrored the rest of the job's lifecycle into local state is gone — the
  // scoring/failed states are derived from the job hooks below, which is what
  // the `useWorkPulseResult` dedup left this page still hand-rolling.
  const [enqueueFailed, setEnqueueFailed] = useState(false);

  // A failed job and an unrecognised status are both terminal: the hook's
  // refetchInterval has already stopped polling either one, so rendering the
  // spinner through them would hang the screen (fail closed, as before). A
  // rejected poll (404 on a stale handle) is terminal the same way. And a
  // failed scoring must stay distinguishable from a slow one by more than the
  // user's patience — the failed check comes before the spinner in render.
  const jobFailed = job.data?.status === "failed";
  const jobUnknown = job.data !== undefined && !isKnownScoringPhase(job.data.status);
  const scoringFailed = enqueueFailed || jobFailed || Boolean(job.error) || jobUnknown;
  const scoring = !scoringFailed && (startScoring.isPending || jobId !== null);
  const scoringError = jobFailed ? (job.data?.error ?? null) : null;

  // The stored result, shared with IntelligencePage through one query.
  // Enabled exactly when the old mount effect called fetchFromServer: no
  // sessionStorage copy, and the server says the instrument is completed.
  const wpQuery = useWorkPulseResult({
    enabled: !hasCached && Boolean(user?.wpl_completed),
  });

  const result = state.cachedResult ?? wpQuery.data ?? null;

  const submitAnswers = useCallback(() => {
    setEnqueueFailed(false);
    // Detach any previous (failed) job before enqueueing, so its terminal
    // state does not render as this attempt's.
    setJobId(null);
    startScoring.mutate(
      {
        answers: state.answers.map((a) => ({
          question_id: a.questionId,
          option_id: a.optionId,
        })),
      },
      {
        onSuccess: (accepted) => setJobId(accepted.job_id),
        // The enqueue itself failing (a 429 on the shared per-instrument budget,
        // say) is a failure to start, not a failure to score, but the user's
        // recovery is the same one: try again.
        onError: () => setEnqueueFailed(true),
      }
    );
  // `startScoring` is a stable mutation object from TanStack Query; including it
  // would rebuild this callback on every mutation state change, and the mount
  // effect below depends on it being stable across the submit it triggers.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.answers]);

  // The one thing a terminal job still needs an effect for: the success side
  // effects. The failure branches this effect used to hold are derived above,
  // and the old "prime the cache from a landed read" effect is gone with them
  // — `setCachedResult` writes `workPulseResultKeys.result()` now (see
  // `useWP`'s header), so a landed read of that very key has nothing left to
  // prime, and the fetch only fires when `wpl_completed` is already true.
  useEffect(() => {
    const data = job.data;
    if (!data || data.status !== "succeeded" || !data.result) return;

    // Writing the shared query key (`setCachedResult`) is what hands the
    // narrative to every consumer of `useWorkPulseResult` — a consumer
    // mounting after a retake must not be handed the pre-retake narrative for
    // the staleTime window.
    setCachedResult(asWpApiResponse(data.result));
    // The session flag the shell gates on (IntelligencePage, JobSeekerDashboard).
    updateProfile({ wpl_completed: true });
    // And the profile document, which the server has now written this result
    // into. Without this, a screen reading it through useProfile() shows a
    // pre-completion copy for up to the 60 s staleTime.
    queryClient.invalidateQueries({ queryKey: profileKeys.document() });
    // Detach from the finished job so `scoring` derives false and the
    // narrative renders.
    setJobId(null);
  }, [job.data, setCachedResult, updateProfile, queryClient]);

  // Backend returns 422 when wpl_completed_at is set but wpl_result is missing
  // (e.g. pending migration). Resubmit to regenerate the narrative if answers
  // are still in sessionStorage. A 422 is not retryable in shouldRetry's
  // classification, so it arrives here without retry delay.
  const queryErrorMsg = wpQuery.error instanceof Error ? wpQuery.error.message : "";
  const canResubmitAfterQueryError =
    queryErrorMsg.includes("resubmit") && state.answers.length === WP_QUESTIONS.length;

  useEffect(() => {
    if (!wpQuery.error) return;
    if (canResubmitAfterQueryError) {
      submitAnswers();
    }
    // Narrow on purpose: refires per failed fetch, not per render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wpQuery.error]);

  useEffect(() => {
    if (hasCached && user?.wpl_completed) {
      // Cache and server agree — nothing to do.
      return;
    }
    if (hasCached && !user?.wpl_completed) {
      // Stale cache: server has no record. Re-submit if answers are available,
      // otherwise the cache is useless — redirect back to the quiz.
      if (state.answers.length === WP_QUESTIONS.length) {
        if (!hasFiredRef.current) {
          hasFiredRef.current = true;
          submitAnswers();
        }
      } else {
        navigate("/work-pulse", { replace: true });
      }
      return;
    }
    // Fresh session: user already completed WP but sessionStorage was cleared —
    // the stored result arrives through useWorkPulseResult, enabled for exactly
    // this state.
    if (user?.wpl_completed) {
      return;
    }
    if (state.answers.length < WP_QUESTIONS.length) {
      navigate("/work-pulse", { replace: true });
      return;
    }
    if (!hasFiredRef.current) {
      hasFiredRef.current = true;
      submitAnswers();
    }
  }, []);  // intentionally runs once on mount; hasFiredRef guards against Strict Mode double-fire

  const handleRetry = useCallback(() => {
    if (state.answers.length === WP_QUESTIONS.length) {
      // Prefer resubmitting when answers are available — covers both first-time
      // and the case where the narrative blob failed to persist.
      submitAnswers();
    } else {
      wpQuery.refetch();
    }
  }, [state.answers.length, wpQuery, submitAnswers]);

  // `isError && isFetching` is the retry in flight: the error object survives
  // a refetch, and rendering the card through it would make "Try again" look
  // dead. It draws the spinner the hand-rolled "loading" state did.
  if (
    !scoring &&
    (wpQuery.isLoading || (wpQuery.isError && wpQuery.isFetching))
  ) {
    return (
      <div className="min-h-screen bg-cream-base flex flex-col items-center justify-center gap-4">
        <div className="w-8 h-8 rounded-full border-2 border-forest-light border-t-transparent animate-spin" />
        <p className="text-sm text-ink-secondary">Loading your results…</p>
      </div>
    );
  }

  // Pending. Says that the work is queued and still running, so that waiting is
  // an informed choice rather than a guess about whether anything is happening.
  if (scoring) {
    return (
      <div
        className="min-h-screen bg-cream-base flex flex-col items-center justify-center gap-4"
        aria-live="polite"
      >
        <div className="w-8 h-8 rounded-full border-2 border-forest-light border-t-transparent animate-spin" />
        <p className="text-sm text-ink-secondary">Analysing your responses…</p>
        <p className="text-xs text-ink-tertiary">
          This usually takes under a minute. You can leave this page open.
        </p>
      </div>
    );
  }

  if (scoringFailed || (wpQuery.isError && !canResubmitAfterQueryError)) {
    return (
      <div className="min-h-screen bg-cream-base flex items-center justify-center px-6">
        <div
          className="max-w-sm w-full rounded-lg border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-700"
          role="alert"
        >
          <p className="font-medium mb-1">We couldn't generate your results right now.</p>
          {/* The scorer's own message when it authored one. Never provider text
              — the server sends either a validation message it wrote or a fixed
              generic string, because provider text carries prompt fragments and
              therefore the respondent's own answers. */}
          <p className="text-xs">{scoringError || "Please try again in a moment."}</p>
          <button
            type="button"
            onClick={handleRetry}
            className="mt-3 text-xs font-semibold text-red-700 underline"
          >
            Try again
          </button>
        </div>
      </div>
    );
  }

  if (!result) return null;

  const paragraphs = result.narrative
    .split(/\n\n+/)
    .map((p) => p.trim())
    .filter(Boolean);

  return (
    <div className="min-h-screen bg-cream-base">
      <div className="mx-auto max-w-2xl px-6 pt-12 pb-20 space-y-8">

        {/* Back nav */}
        <button
          type="button"
          onClick={() => navigate("/intelligence")}
          className="flex items-center gap-1.5 text-sm font-semibold text-forest-dark hover:underline"
        >
          <span aria-hidden>←</span> Intelligence Hub
        </button>

        {/* Header */}
        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-widest text-forest-light">
            Your Work Pulse
          </p>
          <h1 className="font-display text-2xl sm:text-3xl font-semibold text-ink-primary">
            Here's how you work
          </h1>
        </div>

        {/* Narrative */}
        <div className="rounded-xl border border-cream-muted bg-white p-6 space-y-4">
          {paragraphs.map((para, i) => (
            <p key={i} className="text-base text-ink-primary leading-relaxed">
              {para}
            </p>
          ))}
        </div>

        {/* Emerging signals */}
        {result.emerging_signals.length > 0 && (
          <div className="space-y-3">
            <h2 className="text-sm font-semibold uppercase tracking-widest text-forest-light">
              Emerging signals
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {result.emerging_signals.map((signal) => (
                <div
                  key={signal.title}
                  className="rounded-lg border border-cream-muted bg-white px-5 py-4"
                >
                  <p className="text-sm font-semibold text-ink-primary mb-1">{signal.title}</p>
                  <p className="text-xs text-ink-secondary leading-relaxed">{signal.description}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Archetype callout */}
        <div className="rounded-xl border border-forest-light bg-forest-pale px-6 py-5">
          <p className="text-xs font-semibold uppercase tracking-widest text-forest-light mb-1">
            Your primary work archetype
          </p>
          <p className="font-display text-xl font-semibold text-forest-dark">{result.archetype}</p>
          {result.archetype_description && (
            <p className="text-sm text-forest-dark leading-relaxed mt-3">
              {result.archetype_description}
            </p>
          )}
        </div>

        {/* What this unlocks */}
        <div className="rounded-xl border border-cream-muted bg-white px-6 py-5">
          <p className="text-xs font-semibold uppercase tracking-widest text-forest-light mb-2">
            What completing Work Pulse unlocks
          </p>
          <p className="text-sm text-ink-secondary leading-relaxed">
            Your archetype and narrative are now visible on your Solverah profile,
            giving employers a window into how you actually work — not just what you've done.
          </p>
          <button
            type="button"
            onClick={() => navigate("/intelligence")}
            className="mt-4 w-full bg-forest-dark text-white font-semibold py-3.5 rounded hover:bg-forest-mid transition-colors"
          >
            Go to Intelligence Hub →
          </button>
        </div>

        {/* CompanyLens teaser */}
        {(() => {
          const topSignalTitle =
            result.emerging_signals.length > 0
              ? result.emerging_signals[0].title
              : result.archetype;
          return (
            <div className="rounded-xl border border-cream-muted bg-white px-6 py-5">
              <p className="text-xs font-semibold uppercase tracking-widest text-forest-light mb-2">
                Based on your results
              </p>
              <h2 className="font-display text-lg font-semibold text-ink-primary">
                Your {topSignalTitle} signals may reveal something about company fit.
              </h2>
              <p className="text-sm text-ink-secondary leading-relaxed mt-2">
                Work Pulse Pro, coming soon, will map your work patterns against real
                company environments. Some companies consistently amplify the friction you
                described. Others are built in ways that reduce it. CompanyLens will show
                you which is which.
              </p>
              <div className="grid grid-cols-2 gap-3 mt-4">
                <div className="rounded-lg border border-cream-muted bg-cream-subtle px-4 py-3">
                  <div className="h-3 w-24 rounded bg-gray-200 blur-sm mb-2" />
                  <span className="text-xs text-ink-tertiary">Fit score: --</span>
                </div>
                <div className="rounded-lg border border-cream-muted bg-cream-subtle px-4 py-3">
                  <div className="h-3 w-20 rounded bg-gray-200 blur-sm mb-2" />
                  <span className="text-xs text-ink-tertiary">Fit score: --</span>
                </div>
              </div>
              {/* Pro is visible but not buyable yet (product owner, 2026-09-28):
                  a label, not a button, so nothing looks clickable-but-dead. */}
              <p className="mt-4 rounded-[4px] border border-dashed border-cream-muted bg-cream-base px-4 py-3 text-center text-sm font-semibold text-ink-secondary">
                CompanyLens™ · Pro · coming soon
              </p>
            </div>
          );
        })()}

        {/* Tier progression */}
        <TierBar nextTierIndex={2} />

        {/* Pro teaser -- a label, not a button: there is nothing to buy yet. */}
        <div className="pt-2">
          <p className="rounded-[4px] border border-dashed border-cream-muted bg-white px-4 py-3.5 text-center text-sm font-semibold text-ink-secondary">
            Work Pulse Pro · coming soon
          </p>
          <p className="text-xs text-ink-tertiary text-center mt-2">
            Deeper analysis, personalised recommendations, and more.
          </p>
        </div>

      </div>
    </div>
  );
}
