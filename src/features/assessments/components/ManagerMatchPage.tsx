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
import { useMM } from "../useMM";
import type { MMAnswer, MMResult } from "../useMM";
import { profileKeys } from "../../profile";
import {
  isKnownScoringPhase,
  useScoringJobStatus,
  useStartScoringJob,
  type ScoringJobResult,
} from "../useScoringJob";
import { MM_QUESTIONS } from "../data/mmQuestions";
import HeroNetworkAnimation from "../../../shared/ui/HeroNetworkAnimation";
import ResumePrompt from "../../../shared/ui/ResumePrompt";
import { firstUnansweredIndex, useResumePrompt } from "../../../shared/lib/resumeDraft";

/**
 * Only the two genuinely local UI phases remain. "Submitting" and "error" are
 * not members any more: they were a hand-rolled mirror of state the scoring
 * job hooks already hold, kept in sync by effects — the parallel half of the
 * enqueue→poll pattern `useScoringJob` exists to own. Both are now derived at
 * render time from `useStartScoringJob`/`useScoringJobStatus`, so a failed
 * scoring still cannot present as one that is merely taking its time, but
 * nothing has to copy the job's state to make that true.
 */
type Phase = 'intro' | 'questions';

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
  // The enqueue failing is mutation state, but it arrives through a callback;
  // this one flag captures it for render. Everything else is read straight off
  // the hooks below.
  const [enqueueFailed, setEnqueueFailed] = useState(false);

  // ── The job's state, read where it lives instead of mirrored into a phase ──
  // A failed job and an unrecognised status are both terminal: the hook's
  // refetchInterval has already stopped polling either one, so rendering the
  // spinner through them would hang the screen (fail closed, as before).
  const jobFailed = job.data?.status === 'failed';
  const jobUnknown = job.data !== undefined && !isKnownScoringPhase(job.data.status);
  // A rejected poll (404 on a stale handle) is terminal too.
  const scoringFailed = enqueueFailed || jobFailed || Boolean(job.error) || jobUnknown;
  // Includes `succeeded`: the success effect below is about to navigate away,
  // and the spinner is the right thing to show until it does.
  const scoring = !scoringFailed && (startScoring.isPending || jobId !== null);
  // The scorer's own message where it authored one — never provider text,
  // which would carry prompt fragments and therefore the respondent's answers.
  const scoringError = jobFailed ? (job.data?.error ?? null) : null;

  // A part-finished draft used to resume silently. It now asks first: the
  // shared resume prompt stands in for the intro until the user chooses.
  const { showResumePrompt, dismissResumePrompt } = useResumePrompt(
    () => !isRetake && state.answers.length > 0 && state.answers.length < MM_QUESTIONS.length
  );
  const [phase, setPhase] = useState<Phase>('intro');
  const [questionIndex, setQuestionIndex] = useState(0);

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
    setEnqueueFailed(false);
    // Detach any previous (failed) job before enqueueing, so its terminal
    // state does not render as this attempt's.
    setJobId(null);

    startScoring.mutate(
      {
        answers: answers.map((a) => ({ question_id: a.questionId, choice: a.choice })),
      },
      {
        onSuccess: (accepted) => setJobId(accepted.job_id),
        onError: () => setEnqueueFailed(true),
      }
    );
  // `startScoring` is a stable TanStack Query mutation object; listing it would
  // rebuild this callback on every mutation state change.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // The one thing a terminal job still needs an effect for: the success side
  // effects. Everything the failure branches used to do here is derived above.
  useEffect(() => {
    const data = job.data;
    if (!data || data.status !== 'succeeded' || !data.result) return;

    setCachedResult(asMMResult(data.result));
    // The server has written this into the profile document, which is where
    // ManagerMatchResultsPage looks first (`profile.manager_match_result`).
    // Without this the results page reads a pre-completion copy for up to the
    // 60 s staleTime and falls through to a server fetch it did not need.
    queryClient.invalidateQueries({ queryKey: profileKeys.document() });
    // Detach from the finished job so re-renders before the navigation lands
    // early-return instead of repeating these side effects.
    setJobId(null);
    navigate('/manager-match/results');
  }, [job.data, navigate, setCachedResult, queryClient]);

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

  function handleResume() {
    const answered = new Set(answersRef.current.map((a) => a.questionId));
    setQuestionIndex(firstUnansweredIndex(MM_QUESTIONS, (q) => answered.has(q.id)));
    setPhase('questions');
    dismissResumePrompt();
  }

  function handleStartOver() {
    reset();
    answersRef.current = [];
    setQuestionIndex(0);
    setPhase('questions');
    dismissResumePrompt();
  }

  function handleRetry() {
    // Cleared so the guard lets the retry enqueue — it exists to stop a
    // double-fire of one submission, not to make failure final.
    hasFiredRef.current = false;
    submitAnswers(pendingAnswersRef.current);
  }

  // ── Failed: enqueue rejected, job failed, poll rejected, or a status this
  // client does not recognise. Checked before the spinner so a failed scoring
  // cannot present as one that is merely taking its time. ──
  if (scoringFailed) {
    return (
      <div className="min-h-screen bg-cream-base flex items-center justify-center px-6">
        <div
          className="max-w-sm w-full rounded-lg border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-700"
          role="alert"
        >
          <p className="font-medium mb-1">We couldn't generate your results right now.</p>
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

  // ── Pending: queued or running on the worker ──
  if (scoring) {
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

  // ── A saved draft: ask before resuming ──
  if (showResumePrompt) {
    return (
      <div className="min-h-screen bg-cream-base">
        <div className="mx-auto max-w-lg px-6 pt-16 pb-20">
          <ResumePrompt
            title="ManagerMatch™"
            answeredCount={state.answers.length}
            total={MM_QUESTIONS.length}
            onResume={handleResume}
            onStartOver={handleStartOver}
          />
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
            {/* Was "WorkPulse Pro": ManagerMatch is free and live, and Pro is
                not purchasable yet, so the eyebrow no longer names a tier. */}
            <p className="text-xs font-semibold uppercase tracking-widest text-forest-light">
              Manager fit
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
