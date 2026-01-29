import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "../contexts/useAuth";
import {
  yourFutureYourWayIntro,
  yourFutureYourWayQuestions,
} from "../data/solverahYourFutureYourWayQuiz";


/* ===========================================================
   COMPONENT: YourFutureYourWayTab
   -----------------------------------------------------------
   Responsibilities:
   ✔ Render the quiz UI
   ✔ Track selected answers
   ✔ Save results into the user's profile via AuthContext
   =========================================================== */
export default function YourFutureYourWayTab() {
  // answers: maps question id → selected option index (0–3)
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
        const saved = (profileData as any)?.quizResults?.yourFutureYourWay;
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
          navigate("/job-seeker/profile?tab=quizzes");
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
      {/* Intro block */}
      <h2 className="text-xl font-semibold">{yourFutureYourWayIntro.title}</h2>
      <p className="mt-1">{yourFutureYourWayIntro.subtitle}</p>
      <p className="mt-1 mb-4">{yourFutureYourWayIntro.blurb}</p>

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
          <ul className="mt-6 space-y-3">
            {yourFutureYourWayQuestions.map((q) => {
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
        </div>
      ) : (
        <>
          {/* Quiz header */}
          <h3 className="text-lg font-medium mb-2">Your Future, Your Way Quiz</h3>

          {/* Question list */}
          <ol start={1} className="space-y-4 pl-5">
            {yourFutureYourWayQuestions.map((q) => (
              <li key={q.id}>
                <fieldset>
                  {/* Question text */}
                  <legend className="mb-1">
                    {q.id}. {q.text}
                  </legend>

                  {/* Options as radio inputs */}
                  {q.options.map((opt, idx) => (
                    <label key={idx} className="block">
                      <input
                        type="radio"
                        name={`q${q.id}`}               // group radios per question
                        checked={answers[q.id] === idx} // controlled radio
                        onChange={() => onChange(q.id, idx)}
                      />{" "}
                      {String.fromCharCode(65 + idx)}) {opt}
                    </label>
                  ))}
                </fieldset>
              </li>
            ))}
          </ol>

          {/* Submit button */}
          <button
            type="button"
            onClick={onSubmit}
            className="rounded-full bg-gradient-to-r from-emerald-400 via-blue-500 to-indigo-500 px-4 py-2 mt-4 text-sm font-semibold text-slate-950 shadow-lg shadow-emerald-500/25"
          >
            Save Answers
          </button>
        </>
      )}
    </div>
  );
}
