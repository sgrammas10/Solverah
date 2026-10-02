import { useEffect, useMemo, useState } from "react";
import { useProfileActions } from '../../profile';
import { useNavigate } from "react-router-dom";
import QuizInsightModal from "./QuizInsightModal";
import { careerArchetypes as archetypes, careerQuizzes as quizzes } from "../data/careerQuizzes";
import {
  CAREER_QUIZ_GROUP,
  buildSingleQuizPayload,
  hasAnswers,
  quizDefinition,
  storedInsightFor,
  storedOverallInsight,
} from "../quizPayload";
import { useQuizSubmission } from "../useQuizSubmission";
import type { QuizInsight } from "../useQuizInsight";

type CareerQuizzesProps = {
  quizKey?: string;
  guest?: boolean;
};

export default function CareerQuizzesArchetypesTab({ quizKey, guest }: CareerQuizzesProps) {
  // answers state structure:
  // answers[quizKey][questionId] = optionIndex (0-based index into options array)
  const [answers, setAnswers] = useState<Record<string, Record<number, number>>>({});
  const [isEditing, setIsEditing] = useState(false);
  const [hasSaved, setHasSaved] = useState(false);

  const {
    insightModalOpen,
    insightLoading,
    insightProgress,
    insightError,
    insightResponse,
    setInsightResponse,
    handleInsightClose,
    saveError,
    saving,
    submitGuest,
    submitSignedIn,
  } = useQuizSubmission();

  const { fetchProfileData } = useProfileActions();
  const navigate = useNavigate();

  const visibleQuizzes = useMemo(() => {
    if (!quizKey) return quizzes;
    return quizzes.filter((quiz) => quiz.key === quizKey);
  }, [quizKey]);

  const headerTitle = useMemo(() => {
    if (!quizKey) return "Career Quizzes & Archetypes";
    return visibleQuizzes[0]?.title ?? "Career Quiz";
  }, [quizKey, visibleQuizzes]);

  const showArchetypes = !quizKey;
  const quizNotFound = Boolean(quizKey) && visibleQuizzes.length === 0;

  // Above the not-found return, so the hook order cannot change between
  // renders; the not-found case simply has nothing to load.
  useEffect(() => {
    if (quizNotFound) return;
    (async () => {
      try {
        if (guest) {
          setIsEditing(true);
          setHasSaved(false);
          return;
        }
        if (!fetchProfileData) {
          setIsEditing(true);
          return;
        }
        const current = await fetchProfileData();
        const profileData = current?.profileData || current || {};
        const saved = (profileData as any)?.quizResults?.careerQuizzes;
        if (saved && typeof saved === "object") {
          setAnswers(saved);
          if (quizKey) {
            const hasQuiz = typeof (saved as Record<string, unknown>)[quizKey] === "object";
            setHasSaved(hasQuiz);
            setIsEditing(!hasQuiz);
          } else {
            setHasSaved(true);
            setIsEditing(false);
          }
        } else {
          setIsEditing(true);
        }
        const quizInsights = (profileData as any)?.quizInsights;
        const insightList = visibleQuizzes
          .map((quiz) => {
            const entry = storedInsightFor(quizInsights, quiz.key);
            return entry ? { ...entry, title: entry.title || quiz.title } : null;
          })
          .filter(Boolean) as QuizInsight[];
        if (insightList.length > 0) {
          setInsightResponse({
            overallInsight: storedOverallInsight(quizInsights),
            insights: insightList,
          });
        }
      } catch (err) {
        console.error(err);
        setIsEditing(true);
      }
    })();
  }, [fetchProfileData, guest, quizKey, quizNotFound, visibleQuizzes, setInsightResponse]);

  if (quizNotFound) {
    // G19: a guest who lands on an unknown quiz goes back to the public quiz
    // list, not to /intelligence -- a signed-in page that bounces them to login.
    return (
      <div className="p-4 max-w-3xl mx-auto text-ink-primary">
        <h2 className="font-display text-xl font-semibold mb-2">Career Quiz</h2>
        <p className="text-sm text-ink-secondary mb-4">
          {guest
            ? "That quiz could not be found. Go back to the quiz list to choose one."
            : "That quiz could not be found. Please return to assessments to choose a quiz."}
        </p>
        <button
          type="button"
          onClick={() => navigate(guest ? "/quiz-preview" : "/intelligence")}
          className="border border-cream-muted bg-white text-ink-secondary text-sm font-semibold px-5 py-2.5 rounded hover:border-forest-pale hover:text-forest-mid transition-colors"
        >
          {guest ? "Back to quizzes" : "Back to Assessments"}
        </button>
      </div>
    );
  }

  /**
   * Handle change for an individual question's selected option.
   * - quizKey: which quiz this question belongs to
   * - qid: question ID
   * - idx: selected option index
   */
  const onChange = (quizKey: string, qid: number, idx: number) => {
    setAnswers((prev) => ({
      // keep existing quizzes' answers
      ...prev,
      // for this quiz, merge existing question answers with this new one
      [quizKey]: { ...(prev[quizKey] || {}), [qid]: idx },
    }));
  };

  const visibleAnswers = visibleQuizzes.reduce<Record<string, Record<number, number>>>((acc, quiz) => {
    const quizAnswers = answers?.[quiz.key];
    if (hasAnswers(quizAnswers)) acc[quiz.key] = quizAnswers;
    return acc;
  }, {});
  const canSubmit = Object.keys(visibleAnswers).length > 0 && !saving && !insightLoading;

  /**
   * Submit the visible quizzes' answers.
   * - Guest: one quiz's preview insight; nothing is stored until it succeeds.
   * - Signed in: save the answers, then generate insights for every saved quiz.
   */
  const onSubmitAll = async () => {
    const quizResults = {
      careerQuizzes: visibleAnswers,
      careerQuizzesSubmittedAt: new Date().toISOString(),
    };
    if (guest) {
      // The preview is one quiz; the guest routes each mount exactly one.
      const quiz = quizDefinition(visibleQuizzes[0]?.key ?? "");
      if (!quiz) return;
      submitGuest(buildSingleQuizPayload(quiz, visibleAnswers[quiz.key]), quizResults);
      return;
    }
    if (await submitSignedIn(quizResults)) {
      setHasSaved(true);
      setIsEditing(false);
    }
  };

  const handleViewInsights = () => {
    if (guest) {
      navigate("/quiz-preview/insights", { state: { insight: insightResponse } });
      return;
    }
    if (insightResponse?.insights?.length) {
      navigate(`/quiz-insights?group=${CAREER_QUIZ_GROUP}`, { state: { insight: insightResponse } });
    } else {
      navigate(`/quiz-insights?group=${CAREER_QUIZ_GROUP}`);
    }
  };

  return (
    <div className="min-h-screen bg-cream-base font-sans text-ink-primary">
      <div className="mx-auto max-w-4xl px-6 py-12">
      {/* Title for the overall tab */}
      <h2 className="font-display text-2xl font-bold text-ink-primary mb-6">{headerTitle}</h2>

      {!guest && !isEditing && hasSaved ? (
        <div className="mb-8 rounded-xl border border-cream-muted bg-white p-6">
          <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
            <div>
              <h3 className="font-display text-lg font-semibold text-ink-primary">Your Results</h3>
              <p className="text-sm text-ink-secondary mt-1">
                Review your saved responses. You can update them anytime.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={handleViewInsights}
                className="border border-forest-light bg-forest-light text-white text-sm font-semibold px-5 py-2.5 rounded-full hover:bg-forest-mid transition-colors"
              >
                View Insight
              </button>
              <button
                type="button"
                onClick={() => navigate("/intelligence")}
                className="border border-cream-muted bg-white text-ink-secondary text-sm font-semibold px-5 py-2.5 rounded-full hover:border-forest-pale hover:text-forest-mid transition-colors"
              >
                Back to Assessments
              </button>
              <button
                type="button"
                onClick={() => setIsEditing(true)}
                className="border border-cream-muted bg-white text-ink-secondary text-sm font-semibold px-5 py-2.5 rounded-full hover:border-forest-pale hover:text-forest-mid transition-colors"
              >
                Change Answers
              </button>
            </div>
          </div>
          <div className="space-y-8">
            {visibleQuizzes.map((quiz) => (
              <section key={quiz.key}>
                <h4 className="text-xs font-semibold uppercase tracking-[0.08em] text-forest-light mb-4">{quiz.title}</h4>
                <div className="space-y-4">
                  {quiz.questions.map((q) => {
                    const selected = answers?.[quiz.key]?.[q.id];
                    return (
                      <div key={q.id} className="rounded-xl border border-cream-muted bg-white p-5">
                        <p className="text-sm font-semibold text-ink-primary mb-3">
                          {q.id}. {q.text}
                        </p>
                        <div className="space-y-2">
                          {q.options.map((opt, idx) => (
                            <div
                              key={idx}
                              className={`flex items-center gap-3 rounded-lg border px-4 py-3 text-sm ${
                                selected === idx
                                  ? "border-forest-light bg-forest-pale text-forest-dark font-medium"
                                  : "border-cream-muted bg-cream-base text-ink-tertiary"
                              }`}
                            >
                              <span
                                className={`h-3.5 w-3.5 shrink-0 rounded-full border-2 flex items-center justify-center ${
                                  selected === idx
                                    ? "border-forest-mid bg-forest-mid"
                                    : "border-cream-muted bg-white"
                                }`}
                              >
                                {selected === idx && (
                                  <span className="h-1.5 w-1.5 rounded-full bg-white" />
                                )}
                              </span>
                              {opt}
                            </div>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </section>
            ))}
          </div>
        </div>
      ) : (
        <>
          {/* Render each quiz section */}
          {visibleQuizzes.map((quiz) => (
            <section key={quiz.key} className="mb-8">
              <h3 className="font-display text-lg font-semibold text-ink-primary mb-4">{quiz.title}</h3>
              <div className="space-y-5">
                {quiz.questions.map((q) => (
                  <div key={q.id} className="rounded-xl border border-cream-muted bg-white p-5">
                    <fieldset>
                      <legend className="text-sm font-semibold text-ink-primary mb-3">
                        {q.id}. {q.text}
                      </legend>
                      <div className="space-y-2">
                        {q.options.map((opt, idx) => (
                          <label
                            key={idx}
                            className={`flex items-center gap-3 rounded-lg border px-4 py-3 cursor-pointer transition-colors ${
                              (answers[quiz.key]?.[q.id] ?? -1) === idx
                                ? "border-forest-light bg-forest-pale text-forest-dark"
                                : "border-cream-muted bg-cream-base text-ink-secondary hover:border-forest-light hover:text-ink-primary"
                            }`}
                          >
                            <input
                              type="radio"
                              name={`${quiz.key}-q${q.id}`}
                              checked={(answers[quiz.key]?.[q.id] ?? -1) === idx}
                              onChange={() => onChange(quiz.key, q.id, idx)}
                              className="accent-forest-mid"
                            />
                            <span className="text-sm">{opt}</span>
                          </label>
                        ))}
                      </div>
                    </fieldset>
                  </div>
                ))}
              </div>
            </section>
          ))}
        </>
      )}

      {/* Static list of archetypes for the user to read */}
      {showArchetypes ? (
        <section className="mb-6 rounded-xl border border-cream-muted bg-white p-5">
          <h3 className="font-display text-lg font-semibold text-ink-primary mb-3">Archetypes</h3>
          <ul className="space-y-2">
            {archetypes.map((a, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-ink-secondary">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-forest-light" />
                {a}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {/* Button that triggers saving all responses to the profile */}
      {isEditing && (
        <div className="space-y-3">
          {saveError ? (
            <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {saveError}
            </p>
          ) : null}
          <button
            type="button"
            onClick={onSubmitAll}
            disabled={!canSubmit}
            className="rounded-full bg-gradient-to-r from-forest-light via-forest-mid to-forest-dark px-6 py-3 text-sm font-semibold text-white shadow-md hover:opacity-90 transition-opacity disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saving ? "Saving…" : guest ? "Get Insight" : "Save Answers"}
          </button>
        </div>
      )}

      <QuizInsightModal
        open={insightModalOpen}
        loading={insightLoading}
        progress={insightProgress}
        title="Career Quizzes Insight"
        error={insightError}
        onClose={handleInsightClose}
        onViewInsights={handleViewInsights}
        onBackToAssessments={() =>
          navigate(guest ? "/quiz-preview" : "/intelligence")
        }
        backLabel={guest ? "Back to quizzes" : undefined}
        viewLabel={guest ? "View insights" : undefined}
      />
      </div>
    </div>
  );
}
