/**
 * ManagerMatchPage — ManagerMatch, scored by a job rather than by the submit.
 *
 * Phase 3c: `manager_match` is one of the three provider-scored instruments, so
 * finishing the 15 forced choices now enqueues
 * `POST /assessments/manager_match/scoring-jobs` and polls, instead of holding
 * a request open across the OpenAI call (A19). The succeeded job's `result` is
 * the same body the synchronous submit returned, so it is handed to
 * `setCachedResult` and the navigation is unchanged.
 */
import { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useMM } from "../hooks/useMM";
import type { MMAnswer, MMResult } from "../hooks/useMM";
import { profileKeys } from "../hooks/useProfile";
import {
  isKnownScoringPhase,
  useScoringJobStatus,
  useStartScoringJob,
  type ScoringJobResult,
} from "../hooks/useScoringJob";
import { MM_QUESTIONS } from "../data/mmQuestions";
import HeroNetworkAnimation from "../components/HeroNetworkAnimation";

/**
 * `submitting` is the job's pending state; `error` is its failed one. Kept
 * distinct so a scoring that failed cannot present as a scoring that is merely
 * taking its time.
 */
type Phase = 'intro' | 'questions' | 'submitting' | 'error';

/**
 * The job's `result` in the shape this page's consumers render.
 *
 * `ManagerMatchResult` as generated is open — every field nullable,
 * `dimension_scores?: { [key: string]: unknown }`, plus an index signature —
 * because the API documents it that way. `MMResult` is the narrower shape
 * ManagerMatchResultsPage renders, and the synchronous call this replaces
 * asserted the same narrowing with `fetchWithAuth<MMResult>(...)`.
 */
function asMMResult(result: ScoringJobResult<"manager_match">): MMResult {
  return result as unknown as MMResult;
}

function QuestionIndicator({ current, total }: { current: number; total: number }) {
  return (
    <div className="flex items-center justify-center gap-3">
      <p className="text-xs font-semibold uppercase tracking-widest text-ink-tertiary">
        Question {current} of {total}
      </p>
      <div className="flex gap-1.5">
        {Array.from({ length: total }, (_, i) => (
          <div
            key={i}
            className={`h-1 rounded-full transition-all duration-300 ${
              i < current ? "w-3 bg-forest-dark" : "w-3 bg-cream-muted"
            }`}
          />
        ))}
      </div>
    </div>
  );
}

export default function ManagerMatchPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const isRetake = (location.state as { retake?: boolean } | null)?.retake === true;
  const { state, setAnswer, setCachedResult, reset } = useMM();
  const queryClient = useQueryClient();

  const startScoring = useStartScoringJob("manager_match");
  const [jobId, setJobId] = useState<string | null>(null);
  const job = useScoringJobStatus("manager_match", jobId);
  const [scoringError, setScoringError] = useState<string | null>(null);

  const [phase, setPhase] = useState<Phase>(() => {
    if (isRetake) return 'intro';
    if (state.answers.length > 0 && state.answers.length < 15) return 'questions';
    return 'intro';
  });

  const [questionIndex, setQuestionIndex] = useState(() => {
    if (isRetake) return 0;
    return state.answers.length < 15 ? state.answers.length : 0;
  });

  const hasFiredRef = useRef(false);
  // Local accumulator — source of truth for the final submission payload.
  // Initialized from any existing answers (resume flow), or empty (fresh / retake).
  const answersRef = useRef<MMAnswer[]>(isRetake ? [] : state.answers.slice());
  const pendingAnswersRef = useRef<MMAnswer[]>([]);

  useEffect(() => {
    if (isRetake) {
      reset();
      answersRef.current = [];
    } else if (state.answers.length >= 15) {
      if (state.cachedResult) {
        navigate('/manager-match/results', { replace: true });
      } else {
        // Answers complete but no result (e.g. page reload, DB reset) — re-submit.
        pendingAnswersRef.current = state.answers;
        submitAnswers(state.answers);
      }
    }
  }, []); // intentionally runs once on mount

  const submitAnswers = useCallback((answers: MMAnswer[]) => {
    if (hasFiredRef.current) return;
    hasFiredRef.current = true;
    setPhase('submitting');
    setScoringError(null);

    startScoring.mutate(
      {
        answers: answers.map((a) => ({ question_id: a.questionId, choice: a.choice })),
      },
      {
        onSuccess: (accepted) => setJobId(accepted.job_id),
        onError: () => {
          // Cleared so `handleRetry` can enqueue again — the guard exists to
          // stop a double-fire of one submission, not to make failure final.
          hasFiredRef.current = false;
          setPhase('error');
        },
      }
    );
  // `startScoring` is a stable TanStack Query mutation object; listing it would
  // rebuild this callback on every mutation state change.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Route the job's terminal state into what the synchronous response drove.
  useEffect(() => {
    const data = job.data;
    if (!data) return;

    if (data.status === 'succeeded' && data.result) {
      setCachedResult(asMMResult(data.result));
      // The server has written this into the profile document, which is where
      // ManagerMatchResultsPage looks first (`profile.manager_match_result`).
      // Without this the results page reads a pre-completion copy for up to the
      // 60 s staleTime and falls through to a server fetch it did not need.
      queryClient.invalidateQueries({ queryKey: profileKeys.document() });
      setJobId(null);
      navigate('/manager-match/results');
      return;
    }

    if (data.status === 'failed') {
      setScoringError(data.error ?? null);
      setJobId(null);
      hasFiredRef.current = false;
      setPhase('error');
      return;
    }

    // Fail closed: the hook has already stopped polling an unrecognised status,
    // so staying on the spinner would hang the screen.
    if (!isKnownScoringPhase(data.status)) {
      setJobId(null);
      hasFiredRef.current = false;
      setPhase('error');
    }
  }, [job.data, navigate, setCachedResult, queryClient]);

  // A rejected poll (404 on a stale handle) is terminal too.
  useEffect(() => {
    if (!job.error) return;
    setJobId(null);
    hasFiredRef.current = false;
    setPhase('error');
  }, [job.error]);

  function handleAnswer(choice: 'a' | 'b') {
    const question = MM_QUESTIONS[questionIndex];
    setAnswer(question.id, choice);

    // Keep the local accumulator in sync — overwrite if this question was already answered.
    const rest = answersRef.current.filter((a) => a.questionId !== question.id);
    answersRef.current = [...rest, { questionId: question.id, choice }];

    if (questionIndex < MM_QUESTIONS.length - 1) {
      setQuestionIndex((i) => i + 1);
    } else {
      pendingAnswersRef.current = answersRef.current;
      submitAnswers(answersRef.current);
    }
  }

  function handleRetry() {
    submitAnswers(pendingAnswersRef.current);
  }

  // ── Pending: queued or running on the worker ──
  if (phase === 'submitting') {
    return (
      <div
        className="min-h-screen bg-cream-base flex flex-col items-center justify-center gap-4"
        aria-live="polite"
      >
        <div className="w-8 h-8 rounded-full border-2 border-forest-light border-t-transparent animate-spin" />
        <p className="text-sm text-ink-secondary">Analysing your management preferences…</p>
        <p className="text-xs text-ink-tertiary">
          This usually takes under a minute. You can leave this page open.
        </p>
      </div>
    );
  }

  // ── Failed ──
  if (phase === 'error') {
    return (
      <div className="min-h-screen bg-cream-base flex items-center justify-center px-6">
        <div
          className="max-w-sm w-full rounded-lg border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-700"
          role="alert"
        >
          <p className="font-medium mb-1">We couldn't generate your results right now.</p>
          {/* The scorer's own message where it authored one — never provider
              text, which would carry prompt fragments and therefore the
              respondent's answers. */}
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

  // ── Intro ──
  if (phase === 'intro') {
    return (
      <div className="min-h-screen bg-cream-base">
        <div className="mx-auto max-w-lg px-6 pt-16 pb-20">
          <div className="space-y-8">
            <p className="text-xs font-semibold uppercase tracking-widest text-forest-light">
              WorkPulse Pro
            </p>

            <div className="space-y-4">
              <h1 className="font-display text-3xl sm:text-4xl font-semibold text-ink-primary leading-tight">
                ManagerMatch™
              </h1>
              <p className="text-sm font-medium text-ink-secondary">
                Leadership and management alignment
              </p>
              <p className="text-base text-ink-secondary leading-relaxed">
                Discover which management styles bring out your best — and which create friction.
              </p>
            </div>

            <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
              <p className="text-sm font-semibold text-amber-800">
                Each choice is final — there is no going back.
              </p>
            </div>

            <button
              type="button"
              onClick={() => setPhase('questions')}
              className="w-full bg-forest-dark text-white font-semibold py-4 rounded hover:bg-forest-mid transition-colors text-base"
            >
              Start ManagerMatch™
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ── Questions ──
  const question = MM_QUESTIONS[questionIndex];

  return (
    <div className="relative min-h-screen bg-cream-base overflow-hidden flex flex-col justify-start px-6 pt-[26vh] pb-16">
      <HeroNetworkAnimation theme="light" />
      <div className="relative z-10 mx-auto w-full max-w-3xl space-y-10">
        <QuestionIndicator current={questionIndex + 1} total={MM_QUESTIONS.length} />

        <p className="text-xs font-semibold uppercase tracking-widest text-ink-tertiary text-center">
          Which feels more like you?
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          <button
            type="button"
            onClick={() => handleAnswer('a')}
            className="rounded-xl border-2 border-cream-muted bg-white/80 backdrop-blur-sm px-8 py-10 text-base text-ink-primary text-center leading-relaxed hover:border-forest-light hover:bg-forest-pale/90 transition-all duration-150 min-h-[180px] flex items-center justify-center"
          >
            {question.optionA}
          </button>
          <button
            type="button"
            onClick={() => handleAnswer('b')}
            className="rounded-xl border-2 border-cream-muted bg-white/80 backdrop-blur-sm px-8 py-10 text-base text-ink-primary text-center leading-relaxed hover:border-forest-light hover:bg-forest-pale/90 transition-all duration-150 min-h-[180px] flex items-center justify-center"
          >
            {question.optionB}
          </button>
        </div>
      </div>
    </div>
  );
}
