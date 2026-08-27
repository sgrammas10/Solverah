import { useState, useEffect, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useWP } from "../hooks/useWP";
import type { WpApiResponse } from "../hooks/useWP";
import { useAuth } from "../contexts/useAuth";
import { WP_QUESTIONS } from "../data/wpQuestions";
import TierBar from "../components/intake/TierBar";

type FetchState = "loading" | "error" | "success";

export default function WorkPulseResultsPage() {
  const navigate = useNavigate();
  const { fetchWithAuth, user, updateProfile } = useAuth();
  const { state, setCachedResult } = useWP();

  const hasCached = state.cachedResult !== null;
  const [fetchState, setFetchState] = useState<FetchState>(hasCached ? "success" : "loading");
  const [result, setResult] = useState<WpApiResponse | null>(state.cachedResult);
  const hasFiredRef = useRef(false);

  const submitAnswers = useCallback(async () => {
    setFetchState("loading");
    try {
      const data = await fetchWithAuth<WpApiResponse>("/assessments/work_pulse/submissions", {
        method: "POST",
        body: JSON.stringify({
          answers: state.answers.map((a) => ({
            question_id: a.questionId,
            option_id: a.optionId,
          })),
        }),
      });
      setResult(data);
      setCachedResult(data);
      updateProfile({ wpl_completed: true });
      setFetchState("success");
    } catch {
      setFetchState("error");
    }
  }, [state.answers, fetchWithAuth, setCachedResult, updateProfile]);

  const fetchFromServer = useCallback(async () => {
    setFetchState("loading");
    try {
      const data = await fetchWithAuth<WpApiResponse>("/me/assessments/work_pulse/result");
      setResult(data);
      setCachedResult(data);
      updateProfile({ wpl_completed: true });
      setFetchState("success");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "";
      // Backend returns 422 when wpl_completed_at is set but wpl_result is missing
      // (e.g. pending migration). Resubmit to regenerate the narrative if answers
      // are still in sessionStorage.
      if (msg.includes("resubmit") && state.answers.length === WP_QUESTIONS.length) {
        submitAnswers();
        return;
      }
      setFetchState("error");
    }
  }, [fetchWithAuth, setCachedResult, updateProfile, state.answers, submitAnswers]);

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
    // Fresh session: user already completed WP but sessionStorage was cleared — refetch from server.
    if (user?.wpl_completed) {
      fetchFromServer();
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
      fetchFromServer();
    }
  }, [state.answers.length, fetchFromServer, submitAnswers]);

  if (fetchState === "loading") {
    return (
      <div className="min-h-screen bg-cream-base flex flex-col items-center justify-center gap-4">
        <div className="w-8 h-8 rounded-full border-2 border-forest-light border-t-transparent animate-spin" />
        <p className="text-sm text-ink-secondary">Analysing your responses…</p>
      </div>
    );
  }

  if (fetchState === "error") {
    return (
      <div className="min-h-screen bg-cream-base flex items-center justify-center px-6">
        <div className="max-w-sm w-full rounded-lg border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-700">
          <p className="font-medium mb-1">We couldn't generate your results right now.</p>
          <p className="text-xs">Please try again in a moment.</p>
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
                Work Pulse Pro maps your work patterns against real company environments.
                Some companies consistently amplify the friction you described. Others
                are built in ways that reduce it. CompanyLens shows you which is which.
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
              <button
                type="button"
                disabled
                className="w-full mt-4 bg-forest-dark text-white font-semibold py-3.5 rounded cursor-not-allowed opacity-80"
              >
                Unlock CompanyLens™
              </button>
            </div>
          );
        })()}

        {/* Tier progression */}
        <TierBar nextTierIndex={2} />

        {/* Upgrade CTA */}
        <div className="pt-2">
          <button
            type="button"
            className="w-full border-2 border-forest-dark text-forest-dark font-semibold py-3.5 rounded hover:bg-forest-pale transition-colors"
          >
            Unlock Work Pulse Pro
          </button>
          <p className="text-xs text-ink-tertiary text-center mt-2">
            Deeper analysis, personalised recommendations, and more.
          </p>
        </div>

      </div>
    </div>
  );
}
