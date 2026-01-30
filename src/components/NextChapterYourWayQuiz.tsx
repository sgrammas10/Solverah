import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "../contexts/useAuth";
import { nextChapterSections } from "../data/nextChapterYourWayQuiz";

/* ===========================================================
   COMPONENT: CareerAndJobSearchTab
   -----------------------------------------------------------
   Responsibilities:
   ✔ Render quiz sections and questions
   ✔ Track selected answers in local state
   ✔ Persist results to profile via AuthContext
   =========================================================== */
export default function CareerAndJobSearchTab() {
  // answers maps questionId → selected option index (0–3)
  const [answers, setAnswers] = useState<Record<number, number>>({});
  const [isEditing, setIsEditing] = useState(false);
  const [hasSaved, setHasSaved] = useState(false);
  const { fetchProfileData, saveProfileData } = useAuth();
  const navigate = useNavigate();
  useEffect(() => {
    (async () => {
      try {
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
      } catch (err) {
        console.error(err);
        setIsEditing(true);
      }
    })();
  }, [fetchProfileData]);

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
          navigate("/job-seeker/profile?tab=assessments");
        } else {
          alert("Unable to save responses (not authenticated).");
        }
      } catch (err) {
        console.error(err);
        alert("Failed to save responses. Check console for details.");
      }
    })();
  };

  /* =======================================================
     RENDER
     ======================================================= */
  return (
    <div className="p-4 max-w-3xl mx-auto text-slate-100">
      {/* Page title */}
      <h2 className="text-xl font-semibold mb-2">Career &amp; Job Search</h2>

      {!isEditing && hasSaved ? (
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
            Save Answers
          </button>
        </>
      )}
    </div>
  );
}
