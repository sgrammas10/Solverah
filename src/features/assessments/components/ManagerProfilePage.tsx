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
 * The submit response's `playbook` is `null` when this user has no
 * ManagerMatch sitting yet -- that is a valid, non-error state (the profile
 * itself is stored either way), not something this page renders an error
 * for. Rather than branching on it here, every submission navigates to
 * `/manager-profile/playbook`: a non-null playbook is written into the
 * shared query cache first so that page renders with no extra request, and a
 * null one is simply not written, so the page's own `GET` fires and lands on
 * exactly the `no_manager_match` 409 state it already has to handle for a
 * user who opens that route directly. One bridge-rendering path instead of
 * two copies of the same copy.
 */
import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "../../auth";
import { useMP } from "../useMP";
import type { MPAnswer } from "../useMP";
import { MP_QUESTIONS } from "../data/mpQuestions";
import { managerPlaybookKeys } from "../useManagerPlaybook";
import type { ManagerPlaybook } from "../useManagerPlaybook";
import HeroNetworkAnimation from "../../../shared/ui/HeroNetworkAnimation";

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

export default function ManagerProfilePage() {
  const navigate = useNavigate();
  const location = useLocation();
  const isRetake = (location.state as { retake?: boolean } | null)?.retake === true;
  const { fetchWithAuth } = useAuth();
  const queryClient = useQueryClient();
  const { answers, setAnswer, reset } = useMP();

  const [phase, setPhase] = useState<Phase>(() => {
    if (isRetake) return "intro";
    if (answers.length > 0 && answers.length < MP_QUESTIONS.length) return "questions";
    return "intro";
  });

  const [questionIndex, setQuestionIndex] = useState(() => {
    if (isRetake) return 0;
    return answers.length < MP_QUESTIONS.length ? answers.length : 0;
  });

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
  }, []);

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

  function handleRetry() {
    submitMutation.mutate(answersRef.current);
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
