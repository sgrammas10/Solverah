/**
 * ManagerProfilePage -- the manager-profile forced-choice instrument
 * (BUILD_PLAN C-4).
 *
 * Reuses ManagerMatchPage's forced-choice UI wholesale (intro disclaimer,
 * question indicator, the two-card layout). What differs is the submit: this
 * instrument scores deterministically and instantly
 * (`solverah/services/manager_playbook_service.py` -- "like `focus_type` and
 * unlike `manager_match`"), so there is no scoring job to enqueue and poll,
 * just one synchronous `useMutation`, exactly FocusTypePage's shape.
 *
 * Gated (USER_SCENARIOS S14.1, Sebastian ruling 2026-09-14): a user with no
 * completed ManagerMatch sees a "Take ManagerMatch first" hand-off in place
 * of the intro, before any question renders. This is a client-side gate only
 * -- `POST /assessments/manager-profile` still persists the profile and
 * still returns `playbook: null` for a user without ManagerMatch (that
 * shape is pinned by `docs/contract_baseline.json` and
 * `test_manager_playbook_api.py`), it just becomes unreachable through this
 * page's own UI once the gate is in place. The gate reuses the same
 * `useManagerPlaybook()` query `ManagerPlaybookPage` already runs (`GET
 * /me/manager-playbook`), so a user arriving with it already cached (e.g.
 * from the Intelligence Hub) sees no extra loading state. A second 409 this
 * query can return -- ManagerMatch done, no manager-profile yet -- means
 * "go ahead": that is the ordinary state for a first-time visitor here.
 */
import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "../../auth";
import { useMP } from "../useMP";
import type { MPAnswer } from "../useMP";
import { MP_QUESTIONS } from "../data/mpQuestions";
import { isNoManagerMatch, isNoManagerProfile, managerPlaybookKeys, useManagerPlaybook } from "../useManagerPlaybook";
import type { ManagerPlaybook } from "../useManagerPlaybook";
import HeroNetworkAnimation from "../../../shared/ui/HeroNetworkAnimation";
import ResumePrompt from "../../../shared/ui/ResumePrompt";
import { firstUnansweredIndex, useResumePrompt } from "../../../shared/lib/resumeDraft";

interface ManagerProfileSubmitResponse {
  dimension_scores: Record<string, number>;
  scoring_key: string;
  version: string;
  playbook: ManagerPlaybook | null;
}

type Phase = "intro" | "questions";

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

/** The one screen a user with no completed ManagerMatch ever sees on this route. */
function TakeManagerMatchFirst() {
  const navigate = useNavigate();
  return (
    <div className="min-h-screen bg-cream-base flex items-center justify-center px-6">
      <div className="max-w-sm w-full rounded-xl border border-cream-muted bg-white px-6 py-8 text-center space-y-4">
        <h1 className="font-display text-xl font-semibold text-ink-primary">
          Take ManagerMatch first
        </h1>
        <p className="text-sm text-ink-secondary leading-relaxed">
          Your playbook diffs what you need from a manager against how your manager
          actually works. Take ManagerMatch so there's something to compare your
          manager profile against.
        </p>
        <button
          type="button"
          onClick={() => navigate("/manager-match")}
          className="w-full bg-forest-dark text-white font-semibold py-3 rounded hover:bg-forest-mid transition-colors"
        >
          Take ManagerMatch →
        </button>
      </div>
    </div>
  );
}

export default function ManagerProfilePage() {
  const navigate = useNavigate();
  const location = useLocation();
  const isRetake = (location.state as { retake?: boolean } | null)?.retake === true;
  const { fetchWithAuth } = useAuth();
  const queryClient = useQueryClient();
  const { answers, setAnswer, reset } = useMP();

  const gateQuery = useManagerPlaybook();
  const gateError = gateQuery.error;
  const blockedByGate = isNoManagerMatch(gateError);
  // "Go ahead": either the ordinary first-time state (ManagerMatch done, no
  // profile yet) or a retake (a playbook already exists).
  const gateReady = isNoManagerProfile(gateError) || gateQuery.isSuccess;
  // Refetching a failed gate query keeps `isError` true until the new attempt
  // settles -- folded into "loading" so "Try again" never looks dead.
  const gateLoading = gateQuery.isLoading || (gateQuery.isError && gateQuery.isFetching);
  const gateFailed = gateQuery.isError && !blockedByGate && !gateReady;

  // A part-finished draft asks before resuming (shared resume prompt) instead
  // of dropping the user silently mid-quiz.
  const { showResumePrompt, dismissResumePrompt } = useResumePrompt(
    () => !isRetake && answers.length > 0 && answers.length < MP_QUESTIONS.length
  );
  const [phase, setPhase] = useState<Phase>("intro");
  const [questionIndex, setQuestionIndex] = useState(0);

  // Local accumulator -- source of truth for the final submission payload,
  // exactly ManagerMatchPage's reason: state updates from setAnswer are not
  // guaranteed to have landed by the time the last question's handler reads
  // "all answers" back out.
  const answersRef = useRef<MPAnswer[]>(isRetake ? [] : answers.slice());

  const submitMutation = useMutation({
    mutationFn: (finalAnswers: MPAnswer[]) =>
      fetchWithAuth<ManagerProfileSubmitResponse>("/assessments/manager-profile", {
        method: "POST",
        body: JSON.stringify({
          answers: finalAnswers.map((a) => ({ question_id: a.questionId, choice: a.choice })),
        }),
      }),
    onSuccess: (result) => {
      if (result.playbook) {
        queryClient.setQueryData(managerPlaybookKeys.result(), {
          dimension_scores: result.dimension_scores,
          scoring_key: result.scoring_key,
          version: result.version,
          playbook: result.playbook,
        });
      }
      reset();
      navigate("/manager-profile/playbook");
    },
  });

  useEffect(() => {
    // Must not fire while the gate is still loading or has blocked this user:
    // an auto-resubmit here would send a complete draft's answers before the
    // hand-off has had a chance to render.
    if (!gateReady) return;
    if (isRetake) {
      reset();
      answersRef.current = [];
    } else if (answers.length >= MP_QUESTIONS.length && !submitMutation.isPending) {
      // Answers complete but no navigation happened yet (e.g. page reload
      // right after the last answer) -- re-submit rather than strand the user
      // on a blank intro screen.
      answersRef.current = answers;
      submitMutation.mutate(answers);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gateReady]);

  function handleAnswer(choice: "a" | "b") {
    const question = MP_QUESTIONS[questionIndex];
    setAnswer(question.id, choice);

    const rest = answersRef.current.filter((a) => a.questionId !== question.id);
    answersRef.current = [...rest, { questionId: question.id, choice }];

    if (questionIndex < MP_QUESTIONS.length - 1) {
      setQuestionIndex((i) => i + 1);
    } else {
      submitMutation.mutate(answersRef.current);
    }
  }

  function handleResume() {
    const answered = new Set(answersRef.current.map((a) => a.questionId));
    setQuestionIndex(firstUnansweredIndex(MP_QUESTIONS, (q) => answered.has(q.id)));
    setPhase("questions");
    dismissResumePrompt();
  }

  function handleStartOver() {
    reset();
    answersRef.current = [];
    setQuestionIndex(0);
    setPhase("questions");
    dismissResumePrompt();
  }

  function handleRetry() {
    submitMutation.mutate(answersRef.current);
  }

  // ── Gate: loading (resolves before anything else, including a mid-quiz
  // draft or a pending submission) ──
  if (gateLoading) {
    return (
      <div className="min-h-screen bg-cream-base flex flex-col items-center justify-center gap-4">
        <div className="w-8 h-8 rounded-full border-2 border-forest-light border-t-transparent animate-spin" />
        <p className="text-sm text-ink-secondary">Loading…</p>
      </div>
    );
  }

  // ── Gate: blocked -- no ManagerMatch sitting yet ──
  if (blockedByGate) {
    return <TakeManagerMatchFirst />;
  }

  // ── Gate: some other failure -- a real error, not a routing prompt ──
  if (gateFailed) {
    return (
      <div className="min-h-screen bg-cream-base flex items-center justify-center px-6">
        <div className="max-w-sm w-full rounded-lg border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-700">
          <p className="font-medium mb-1">We couldn't load your manager profile status right now.</p>
          <p className="text-xs">Please try again in a moment.</p>
          <button
            type="button"
            onClick={() => gateQuery.refetch()}
            className="mt-3 text-xs font-semibold text-red-700 underline"
          >
            Try again
          </button>
        </div>
      </div>
    );
  }

  // ── Submitting ──
  if (submitMutation.isPending) {
    return (
      <div className="min-h-screen bg-cream-base flex flex-col items-center justify-center gap-4">
        <div className="w-8 h-8 rounded-full border-2 border-forest-light border-t-transparent animate-spin" />
        <p className="text-sm text-ink-secondary">Scoring your manager profile…</p>
      </div>
    );
  }

  // ── Error ──
  if (submitMutation.isError) {
    return (
      <div className="min-h-screen bg-cream-base flex items-center justify-center px-6">
        <div
          className="max-w-sm w-full rounded-lg border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-700"
          role="alert"
        >
          <p className="font-medium mb-1">Something went wrong submitting your answers.</p>
          <p className="text-xs">Please try again — your answers are still saved.</p>
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

  // ── A saved draft: ask before resuming ──
  if (showResumePrompt) {
    return (
      <div className="min-h-screen bg-cream-base">
        <div className="mx-auto max-w-lg px-6 pt-16 pb-20">
          <ResumePrompt
            title="Manager Decoder"
            answeredCount={answers.length}
            total={MP_QUESTIONS.length}
            onResume={handleResume}
            onStartOver={handleStartOver}
          />
        </div>
      </div>
    );
  }

  // ── Intro ──
  if (phase === "intro") {
    return (
      <div className="min-h-screen bg-cream-base">
        <div className="mx-auto max-w-lg px-6 pt-16 pb-20">
          <div className="space-y-8">
            <p className="text-xs font-semibold uppercase tracking-widest text-forest-light">
              Manager Decoder
            </p>

            <div className="space-y-4">
              <h1 className="font-display text-3xl sm:text-4xl font-semibold text-ink-primary leading-tight">
                Profile your actual manager
              </h1>
              <p className="text-base text-ink-secondary leading-relaxed">
                16 questions about how your manager actually operates — not how you
                feel about it. We diff this against what you told ManagerMatch you
                need, and turn the distance into a private playbook for working with
                them.
              </p>
            </div>

            <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
              <p className="text-sm font-semibold text-amber-800">
                Each choice is final — there is no going back.
              </p>
            </div>

            <button
              type="button"
              onClick={() => setPhase("questions")}
              className="w-full bg-forest-dark text-white font-semibold py-4 rounded hover:bg-forest-mid transition-colors text-base"
            >
              Start
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ── Questions ──
  const question = MP_QUESTIONS[questionIndex];

  return (
    <div className="relative min-h-screen bg-cream-base overflow-hidden flex flex-col justify-start px-6 pt-[26vh] pb-16">
      <HeroNetworkAnimation theme="light" />
      <div className="relative z-10 mx-auto w-full max-w-3xl space-y-10">
        <QuestionIndicator current={questionIndex + 1} total={MP_QUESTIONS.length} />

        <p className="text-xs font-semibold uppercase tracking-widest text-ink-tertiary text-center">
          Which is closer to how your manager works?
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          <button
            type="button"
            onClick={() => handleAnswer("a")}
            className="rounded-xl border-2 border-cream-muted bg-white/80 backdrop-blur-sm px-8 py-10 text-base text-ink-primary text-center leading-relaxed hover:border-forest-light hover:bg-forest-pale/90 transition-all duration-150 min-h-[180px] flex items-center justify-center"
          >
            {question.optionA}
          </button>
          <button
            type="button"
            onClick={() => handleAnswer("b")}
            className="rounded-xl border-2 border-cream-muted bg-white/80 backdrop-blur-sm px-8 py-10 text-base text-ink-primary text-center leading-relaxed hover:border-forest-light hover:bg-forest-pale/90 transition-all duration-150 min-h-[180px] flex items-center justify-center"
          >
            {question.optionB}
          </button>
        </div>
      </div>
    </div>
  );
}
