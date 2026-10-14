import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useProfileActions } from "../../profile";
import { nextChapterSections } from "../data/nextChapterYourWayQuiz";
import QuizInsightModal from "./QuizInsightModal";
import {
  CAREER_JOB_SEARCH_KEY,
  CAREER_QUIZ_GROUP,
  buildSingleQuizPayload,
  hasAnswers,
  quizDefinition,
  storedInsightFor,
  storedOverallInsight,
} from "../quizPayload";
import { useQuizSubmission } from "../useQuizSubmission";

/* ===========================================================
   COMPONENT: CareerAndJobSearchTab
   -----------------------------------------------------------
   Responsibilities:
   ✔ Render quiz sections and questions
   ✔ Track selected answers in local state
   ✔ Persist results to profile; submit through useQuizSubmission
   =========================================================== */
type CareerAndJobSearchTabProps = {
  guest?: boolean;
};

const QUIZ = quizDefinition(CAREER_JOB_SEARCH_KEY)!;

export default function CareerAndJobSearchTab({ guest }: CareerAndJobSearchTabProps) {
  // answers maps questionId → selected option index (0–3)
  const [answers, setAnswers] = useState<Record<number, number>>({});
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
  useEffect(() => {
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
        const saved = (profileData as any)?.quizResults?.[CAREER_JOB_SEARCH_KEY];
        if (saved && typeof saved === "object") {
          setAnswers(saved);
          setHasSaved(true);
          setIsEditing(false);
        } else {
          setIsEditing(true);
        }
        // Signed-in writes nest under careerQuizzes.<key>; the flat key is a
        // pre-2026-10-02 fallback (audit #7). This read used the flat key only,
        // so a stored insight never preloaded.
        const quizInsights = (profileData as any)?.quizInsights;
        const stored = storedInsightFor(quizInsights, CAREER_JOB_SEARCH_KEY);
        if (stored) {
          setInsightResponse({
            overallInsight: storedOverallInsight(quizInsights),
            insights: [{ ...stored, title: stored.title || QUIZ.title }],
          });
        }
      } catch (err) {
        console.error(err);
        setIsEditing(true);
      }
    })();
  }, [fetchProfileData, guest, setInsightResponse]);

  /* ---------------------------------------------------------
     handleChange
     ---------------------------------------------------------
     Update the selected answer for a given question.
     qid = question id
     idx = index of the chosen option
  --------------------------------------------------------- */
  const handleChange = (qid: number, idx: number) => {
    setAnswers((prev) => ({ ...prev, [qid]: idx }));
  };

  const canSubmit = hasAnswers(answers) && !saving && !insightLoading;

  /* ---------------------------------------------------------
     handleSubmit
     ---------------------------------------------------------
     - Guest: this quiz's preview insight; stored only on success
     - Signed in: save under quizResults.careerJobSearch, then generate
       insights for every saved quiz (careerQuizzes group)
  --------------------------------------------------------- */
  const handleSubmit = async () => {
    const quizResults = {
      [CAREER_JOB_SEARCH_KEY]: answers,
      [`${CAREER_JOB_SEARCH_KEY}SubmittedAt`]: new Date().toISOString(),
    };
    if (guest) {
      submitGuest(buildSingleQuizPayload(QUIZ, answers), quizResults);
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

  /* =======================================================
     RENDER
     ======================================================= */
  return (
    <div className="min-h-screen bg-cream-base font-sans text-ink-primary">
      <div className="mx-auto max-w-4xl px-6 py-12">
      {/* Page title */}
      <h2 className="font-display text-2xl font-bold text-ink-primary mb-6">Career &amp; Job Search</h2>

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
            {nextChapterSections.map((sec) => (
              <section key={sec.title}>
                <h4 className="text-xs font-semibold uppercase tracking-[0.08em] text-forest-light mb-4">{sec.title}</h4>
                <div className="space-y-4">
                  {sec.questions.map((q) => {
                    const selected = answers?.[q.id];
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
          {/* Render each section with its questions */}
          {nextChapterSections.map((sec) => (
            <section key={sec.title} className="mb-8">
              <h3 className="font-display text-lg font-semibold text-ink-primary mb-4">{sec.title}</h3>
              <div className="space-y-5">
                {sec.questions.map((q) => (
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
                              answers[q.id] === idx
                                ? "border-forest-light bg-forest-pale text-forest-dark"
                                : "border-cream-muted bg-cream-base text-ink-secondary hover:border-forest-light hover:text-ink-primary"
                            }`}
                          >
                            <input
                              type="radio"
                              name={`q${q.id}`}
                              checked={answers[q.id] === idx}
                              onChange={() => handleChange(q.id, idx)}
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

          {/* Submit button */}
          {saveError ? (
            <p role="alert" className="mb-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {saveError}
            </p>
          ) : null}
          <button
            onClick={handleSubmit}
            disabled={!canSubmit}
            className="rounded-full bg-gradient-to-r from-forest-light via-forest-mid to-forest-dark px-6 py-3 text-sm font-semibold text-white shadow-md hover:opacity-90 transition-opacity disabled:cursor-not-allowed disabled:opacity-50"
            type="button"
          >
            {saving ? "Saving…" : guest ? "Get Insight" : "Save Answers"}
          </button>
        </>
      )}

      <QuizInsightModal
        open={insightModalOpen}
        loading={insightLoading}
        progress={insightProgress}
        title="Career & Job Search Insight"
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
