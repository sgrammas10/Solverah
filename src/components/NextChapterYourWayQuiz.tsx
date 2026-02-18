import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "../contexts/useAuth";
import { nextChapterSections } from "../data/nextChapterYourWayQuiz";
import QuizInsightModal from "./QuizInsightModal";
import { API_BASE } from "../utils/api";
import { setPendingQuizSave } from "../utils/guestQuiz";

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
   COMPONENT: CareerAndJobSearchTab
   -----------------------------------------------------------
   Responsibilities:
   ✔ Render quiz sections and questions
   ✔ Track selected answers in local state
   ✔ Persist results to profile via AuthContext
   =========================================================== */
type CareerAndJobSearchTabProps = {
  guest?: boolean;
};

export default function CareerAndJobSearchTab({ guest }: CareerAndJobSearchTabProps) {
  // answers maps questionId → selected option index (0–3)
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
        const saved = (profileData as any)?.quizResults?.careerJobSearch;
        if (saved && typeof saved === "object") {
          setAnswers(saved);
          setHasSaved(true);
          setIsEditing(false);
        } else {
          setIsEditing(true);
        }
        const stored = (profileData as any)?.quizInsights?.careerJobSearch;
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
     handleChange
     ---------------------------------------------------------
     Update the selected answer for a given question.
     qid = question id
     idx = index of the chosen option
  --------------------------------------------------------- */
  const handleChange = (qid: number, idx: number) => {
    setAnswers((prev) => ({ ...prev, [qid]: idx }));
  };

  /* ---------------------------------------------------------
     handleSubmit
     ---------------------------------------------------------
     - Fetch existing profile data (if any)
     - Merge in this quiz's results under quizResults.careerJobSearch
     - Save via saveProfileData from AuthContext
  --------------------------------------------------------- */
  const handleSubmit = () => {
    (async () => {
      try {
        if (guest) {
          const items = nextChapterSections.flatMap((section) =>
            section.questions
              .map((q) => {
                const selectedIdx = answers?.[q.id];
                if (typeof selectedIdx !== "number") return null;
                return { question: q.text, selected: q.options[selectedIdx] };
              })
              .filter(Boolean),
          );
          const payload = {
            quizGroup: "careerJobSearch",
            quizzes: [
              {
                key: "careerJobSearch",
                title: "Career & Job Search",
                items,
              },
            ],
          };
          setPendingQuizSave({
            quizGroup: "careerJobSearch",
            quizResults: {
              careerJobSearch: answers,
              careerJobSearchSubmittedAt: new Date().toISOString(),
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
        // Fetch current profile data if function exists
        const current = await (fetchProfileData
          ? fetchProfileData()
          : Promise.resolve(null));

        // Support both { profileData: {...} } or plain object formats
        const profileData = current?.profileData || current || {};

        const existingQuizResults = (profileData as any)?.quizResults || {};
        const newProfileData = {
          ...profileData,
          quizResults: {
            ...existingQuizResults,
            careerJobSearch: answers,
            careerJobSearchSubmittedAt: new Date().toISOString(),
          },
        };

        if (saveProfileData) {
          await saveProfileData(newProfileData);
          setHasSaved(true);
          setIsEditing(false);
          if (fetchWithAuth) {
            const items = nextChapterSections.flatMap((section) =>
              section.questions
                .map((q) => {
                  const selectedIdx = answers?.[q.id];
                  if (typeof selectedIdx !== "number") return null;
                  return { question: q.text, selected: q.options[selectedIdx] };
                })
                .filter(Boolean),
            );
            const payload = {
              quizGroup: "careerJobSearch",
              quizzes: [
                {
                  key: "careerJobSearch",
                  title: "Career & Job Search",
                  items,
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
      navigate("/quiz-insights?group=careerJobSearch", { state: { insight: insightResponse } });
    } else {
      navigate("/quiz-insights?group=careerJobSearch");
    }
  };

  /* =======================================================
     RENDER
     ======================================================= */
  return (
    <div className="p-4 max-w-3xl mx-auto text-slate-100">
      {/* Page title */}
      <h2 className="text-xl font-semibold mb-2">Career &amp; Job Search</h2>

      {!guest && !isEditing && hasSaved ? (
        <div className="mt-4 rounded-2xl border border-white/10 bg-slate-900/60 p-6">
          <div className="flex items-center justify-between gap-4">
            <div>
              <h3 className="text-lg font-semibold text-white">Your Results</h3>
              <p className="text-sm text-slate-200/80">
                Review your saved responses. You can update them anytime.
              </p>
            </div>
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={handleViewInsights}
                className="rounded-full border border-emerald-300/60 px-4 py-2 text-sm font-semibold text-emerald-100 hover:border-emerald-200"
              >
                View Insight
              </button>
              <button
                type="button"
                onClick={() => navigate("/job-seeker/profile?tab=assessments")}
                className="rounded-full border border-white/10 px-4 py-2 text-sm font-semibold text-slate-100 hover:border-emerald-300/60"
              >
                Back to Assessments
              </button>
              <button
                type="button"
                onClick={() => setIsEditing(true)}
                className="rounded-full border border-white/10 px-4 py-2 text-sm font-semibold text-slate-100 hover:border-emerald-300/60"
              >
                Change Answers
              </button>
            </div>
          </div>
          <div className="mt-6 space-y-6">
            {nextChapterSections.map((sec) => (
              <section key={sec.title}>
                <h4 className="text-base font-semibold text-white">{sec.title}</h4>
                <ul className="mt-3 space-y-3">
                  {sec.questions.map((q) => {
                    const selected = answers?.[q.id];
                    const answerText =
                      typeof selected === "number" ? q.options[selected] : "No answer selected";
                    return (
                      <li key={q.id} className="rounded-lg border border-white/10 bg-white/5 p-3">
                        <p className="text-sm text-slate-100">{q.text}</p>
                        <p className="mt-1 text-sm text-emerald-200">{answerText}</p>
                      </li>
                    );
                  })}
                </ul>
              </section>
            ))}
          </div>
        </div>
      ) : (
        <>
          {/* Render each section with its questions */}
          {nextChapterSections.map((sec) => (
            <div key={sec.title} className="mb-6">
              {/* Section header */}
              <h3 className="text-lg font-medium mb-2">{sec.title}</h3>

              {/* Ordered list with correct starting index for numbering */}
              <ol start={sec.startId} className="space-y-4 pl-5">
                {sec.questions.map((q) => (
                  <li key={q.id}>
                    <fieldset>
                      {/* Question text */}
                      <legend className="mb-1">{q.text}</legend>

                      {/* Options as grouped radio buttons */}
                      {q.options.map((opt, idx) => (
                        <label key={idx} className="block">
                          <input
                            type="radio"
                            name={`q${q.id}`}              // group by question id
                            checked={answers[q.id] === idx}
                            onChange={() => handleChange(q.id, idx)}
                          />{" "}
                          {opt}
                        </label>
                      ))}
                    </fieldset>
                  </li>
                ))}
              </ol>
            </div>
          ))}

          {/* Submit button */}
          <button
            onClick={handleSubmit}
            className="rounded-full bg-gradient-to-r from-emerald-400 via-blue-500 to-indigo-500 px-4 py-2 text-sm font-semibold text-slate-950 shadow-lg shadow-emerald-500/25"
            type="button"
          >
            {guest ? "Get Insight" : "Save Answers"}
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
          navigate(guest ? "/quiz-preview" : "/job-seeker/profile?tab=assessments")
        }
        backLabel={guest ? "Back to quizzes" : undefined}
        viewLabel={guest ? "View insights" : undefined}
      />
    </div>
  );
}
