import { useState } from "react";
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
  const { fetchProfileData, saveProfileData } = useAuth();
  const navigate = useNavigate();

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

        const newProfileData = {
          ...profileData,
          quizResults: {
            careerJobSearch: answers,
            submittedAt: new Date().toISOString(),
          },
        };

        if (saveProfileData) {
          await saveProfileData(newProfileData);
          alert("Responses saved to your profile.");
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
      {/* Page title */}
      <h2 className="text-xl font-semibold mb-2">Career &amp; Job Search</h2>

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
        Submit
      </button>
    </div>
  );
}
