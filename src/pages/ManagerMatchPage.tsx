import { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "../contexts/useAuth";
import { useMM } from "../hooks/useMM";
import type { MMAnswer, MMResult } from "../hooks/useMM";
import { MM_QUESTIONS } from "../data/mmQuestions";

type Phase = 'intro' | 'questions' | 'submitting' | 'error';

function QuestionIndicator({ current, total }: { current: number; total: number }) {
  return (
    <div className="flex items-center gap-3">
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
  const { fetchWithAuth } = useAuth();
  const { state, setAnswer, setCachedResult, reset } = useMM();

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
      navigate('/manager-match/results', { replace: true });
    }
  }, []); // intentionally runs once on mount

  const submitAnswers = useCallback(async (answers: MMAnswer[]) => {
    if (hasFiredRef.current) return;
    hasFiredRef.current = true;
    setPhase('submitting');

    try {
      const data = await fetchWithAuth<MMResult>('/manager-match/submit', {
        method: 'POST',
        body: JSON.stringify({
          answers: answers.map((a) => ({ question_id: a.questionId, choice: a.choice })),
        }),
      });
      setCachedResult(data);
      navigate('/manager-match/results');
    } catch {
      hasFiredRef.current = false;
      setPhase('error');
    }
  }, [fetchWithAuth, navigate, setCachedResult]);

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

  // ── Submitting ──
  if (phase === 'submitting') {
    return (
      <div className="min-h-screen bg-cream-base flex flex-col items-center justify-center gap-4">
        <div className="w-8 h-8 rounded-full border-2 border-forest-light border-t-transparent animate-spin" />
        <p className="text-sm text-ink-secondary">Analysing your management preferences…</p>
      </div>
    );
  }

  // ── Error ──
  if (phase === 'error') {
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
    <div className="min-h-screen bg-cream-base">
      <div className="mx-auto max-w-2xl px-6 pt-10 pb-20 space-y-8">
        <QuestionIndicator current={questionIndex + 1} total={MM_QUESTIONS.length} />

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <button
            type="button"
            onClick={() => handleAnswer('a')}
            className="rounded-lg border border-cream-muted bg-white px-6 py-6 text-sm text-ink-primary text-center leading-relaxed hover:border-forest-light transition-colors"
          >
            {question.optionA}
          </button>
          <button
            type="button"
            onClick={() => handleAnswer('b')}
            className="rounded-lg border border-cream-muted bg-white px-6 py-6 text-sm text-ink-primary text-center leading-relaxed hover:border-forest-light transition-colors"
          >
            {question.optionB}
          </button>
        </div>
      </div>
    </div>
  );
}
