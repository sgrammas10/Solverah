import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "../contexts/useAuth";
import {
  yourFutureYourWayIntro,
  yourFutureYourWayQuestions,
} from "../data/solverahYourFutureYourWayQuiz";
import QuizInsightModal from "./QuizInsightModal";
import { API_BASE } from "../utils/api";
import { markGuestQuizCompleted, setPendingQuizSave } from "../utils/guestQuiz";

type QuizInsight = {
  title?: string;
  summary?: string;
  keyTakeaways?: string[];
  combinedMeaning?: string;
  nextSteps?: string[];
};

type QuizInsightResponse = {
  overallSummary?: string | null;
  insights: QuizInsight[];
};


/* ===========================================================
   COMPONENT: YourFutureYourWayTab
   -----------------------------------------------------------
   Responsibilities:
   ✔ Render the quiz UI
   ✔ Track selected answers
   ✔ Save results into the user's profile via AuthContext
   =========================================================== */
type YourFutureYourWayTabProps = {
  guest?: boolean;
};

export default function YourFutureYourWayTab({ guest }: YourFutureYourWayTabProps) {
  // answers: maps question id → selected option index (0–3)
  const [answers, setAnswers] = useState<Record<number, number>>({});
  const [isEditing, setIsEditing] = useState(false);
  const [hasSaved, setHasSaved] = useState(false);
  const [insightModalOpen, setInsightModalOpen] = useState(false);
  const [insightLoading, setInsightLoading] = useState(false);
  const [insightProgress, setInsightProgress] = useState(0);
  const [insightError, setInsightError] = useState<string | null>(null);
  const [insightResponse, setInsightResponse] = useState<QuizInsightResponse | null>(null);

  const { fetchProfileData, saveProfileData, fetchWithAuth } = useAuth();
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
        const saved = (profileData as any)?.quizResults?.yourFutureYourWay;
        if (saved && typeof saved === "object") {
          setAnswers(saved);
          setHasSaved(true);
          setIsEditing(false);
        } else {
          setIsEditing(true);
        }
        const stored = (profileData as any)?.quizInsights?.yourFutureYourWay;
        if (stored && typeof stored === "object") {
          setInsightResponse({
            overallSummary: stored.overallSummary || null,
            insights: [
              {
                title: stored.title,
                summary: stored.summary,
                keyTakeaways: stored.keyTakeaways,
                combinedMeaning: stored.combinedMeaning,
                nextSteps: stored.nextSteps,
              },
            ],
          });
        }
      } catch (err) {
        console.error(err);
        setIsEditing(true);
      }
    })();
  }, [fetchProfileData, guest]);

  useEffect(() => {
    if (!insightLoading) return;
    setInsightProgress(8);
    const id = setInterval(() => {
      setInsightProgress((prev) => (prev < 90 ? Math.min(90, prev + 6 + Math.random() * 6) : prev));
    }, 350);
    return () => clearInterval(id);
  }, [insightLoading]);


  /* ---------------------------------------------------------
     onChange
     ---------------------------------------------------------
     Updates the selected answer for a single question.
     qid = question id
     idx = index of chosen option
  --------------------------------------------------------- */
  const onChange = (qid: number, idx: number) =>
    setAnswers((prev) => ({ ...prev, [qid]: idx }));

  /* ---------------------------------------------------------
     onSubmit
     ---------------------------------------------------------
     - Fetch existing profile data
     - Adds/overwrites quizResults.yourFutureYourWay
     - Saves via saveProfileData from AuthContext
  --------------------------------------------------------- */
  const onSubmit = () => {
    (async () => {
      try {
        if (guest) {
          markGuestQuizCompleted();
          const payload = {
            quizGroup: "yourFutureYourWay",
            quizzes: [
              {
                key: "yourFutureYourWay",
                title: "Your Future, Your Way",
                items: yourFutureYourWayQuestions
                  .map((q) => {
                    const selectedIdx = answers?.[q.id];
                    if (typeof selectedIdx !== "number") return null;
                    return { question: q.text, selected: q.options[selectedIdx] };
                  })
                  .filter(Boolean),
              },
            ],
          };
          setPendingQuizSave({
            quizGroup: "yourFutureYourWay",
            quizResults: {
              yourFutureYourWay: answers,
              yourFutureYourWaySubmittedAt: new Date().toISOString(),
            },
            quizPayload: payload,
            createdAt: new Date().toISOString(),
          });
          setInsightModalOpen(true);
          setInsightLoading(true);
          setInsightError(null);
          try {
            const res = await fetch(`${API_BASE}/quiz-insights-guest`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(payload),
            });
            const data = await res.json().catch(() => null);
            if (!res.ok) {
              throw new Error(data?.error || "Failed to generate insights.");
            }
            setInsightResponse({
              overallSummary: data?.overallSummary || null,
              insights: data?.insights || [],
            });
            setInsightProgress(100);
          } catch (err) {
            setInsightError(err instanceof Error ? err.message : "Failed to generate insights.");
          } finally {
            setInsightLoading(false);
          }
          return;
        }
        // Get current profile data if available
        const current = await (fetchProfileData
          ? fetchProfileData()
          : Promise.resolve(null));

        // Handle shape { profileData: {...} } or raw object
        const profileData = current?.profileData || current || {};

        const existingQuizResults = (profileData as any)?.quizResults || {};
        const newProfileData = {
          ...profileData,
          quizResults: {
            ...existingQuizResults,
            yourFutureYourWay: answers,
            yourFutureYourWaySubmittedAt: new Date().toISOString(),
          },
        };

        if (saveProfileData) {
          await saveProfileData(newProfileData);
          setHasSaved(true);
          setIsEditing(false);
          if (fetchWithAuth) {
            const payload = {
              quizGroup: "yourFutureYourWay",
              quizzes: [
                {
                  key: "yourFutureYourWay",
                  title: "Your Future, Your Way",
                  items: yourFutureYourWayQuestions
                    .map((q) => {
                      const selectedIdx = answers?.[q.id];
                      if (typeof selectedIdx !== "number") return null;
                      return { question: q.text, selected: q.options[selectedIdx] };
                    })
                    .filter(Boolean),
                },
              ],
            };
            setInsightModalOpen(true);
            setInsightLoading(true);
            setInsightError(null);
            try {
              const res = await fetchWithAuth<QuizInsightResponse>("/quiz-insights", {
                method: "POST",
                body: JSON.stringify(payload),
              });
              setInsightResponse({
                overallSummary: res.overallSummary || null,
                insights: res.insights || [],
              });
              setInsightProgress(100);
            } catch (err) {
              setInsightError(err instanceof Error ? err.message : "Failed to generate insights.");
            } finally {
              setInsightLoading(false);
            }
          }
        } else {
          alert("Unable to save responses (not authenticated).");
        }
      } catch (err) {
        console.error(err);
        alert("Failed to save responses. Check console for details.");
      }
    })();
  };

  const handleInsightClose = () => {
    setInsightModalOpen(false);
    setInsightError(null);
    setInsightProgress(0);
  };

  const handleViewInsights = () => {
    if (guest) {
      navigate("/quiz-preview/insights", { state: { insight: insightResponse } });
      return;
    }
    if (insightResponse?.insights?.length) {
      navigate("/quiz-insights?group=yourFutureYourWay", { state: { insight: insightResponse } });
    } else {
      navigate("/quiz-insights?group=yourFutureYourWay");
    }
  };

  /* =======================================================
     RENDER
     ======================================================= */
  return (
    <div className="min-h-screen bg-cream-base font-sans text-ink-primary">
      <div className="mx-auto max-w-4xl px-6 py-12">
      {/* Intro block */}
      <h2 className="font-display text-2xl font-bold text-ink-primary">{yourFutureYourWayIntro.title}</h2>
      <p className="mt-1 text-ink-secondary">{yourFutureYourWayIntro.subtitle}</p>
      <p className="mt-1 mb-6 text-ink-secondary">{yourFutureYourWayIntro.blurb}</p>

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
                onClick={() => navigate("/job-seeker/profile?tab=assessments")}
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
          <div className="space-y-4">
            {yourFutureYourWayQuestions.map((q) => {
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
        </div>
      ) : (
        <>
          {/* Quiz header */}
          <h3 className="font-display text-lg font-semibold text-ink-primary mb-4">Your Future, Your Way Quiz</h3>

          {/* Question list */}
          <div className="space-y-5">
            {yourFutureYourWayQuestions.map((q) => (
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
                          onChange={() => onChange(q.id, idx)}
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

          {/* Submit button */}
          <button
            type="button"
            onClick={onSubmit}
            className="mt-6 rounded-full bg-gradient-to-r from-forest-light via-forest-mid to-forest-dark px-6 py-3 text-sm font-semibold text-white shadow-md hover:opacity-90 transition-opacity"
          >
            {guest ? "Get Insight" : "Save Answers"}
          </button>
        </>
      )}

      <QuizInsightModal
        open={insightModalOpen}
        loading={insightLoading}
        progress={insightProgress}
        title="Your Future, Your Way Insight"
        error={insightError}
        onClose={handleInsightClose}
        onViewInsights={handleViewInsights}
        onBackToAssessments={() =>
          navigate(guest ? "/quiz-preview" : "/job-seeker/profile?tab=assessments")
        }
        backLabel={guest ? "Back to quizzes" : undefined}
        viewLabel={guest ? "View insights" : undefined}
      />
      </div>
    </div>
  );
}
