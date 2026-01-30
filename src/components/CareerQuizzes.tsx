import { useEffect, useState } from "react";
import { useAuth } from '../contexts/useAuth';
import { useNavigate } from "react-router-dom";


// Single quiz question type: numeric id, question text, and list of options
type Question = { id: number; text: string; options: string[] };

// Quiz type: a unique key, display title, and a list of questions
type Quiz = { key: string; title: string; questions: Question[] };

// Static configuration for all quizzes shown in this tab
const quizzes: Quiz[] = [
  {
    key: "earlyCareer",
    title: "Quiz 1: Early Career",
    questions: [
      {
        id: 1,
        text: "What is one thing you would change about your current position?",
        options: [
          "More growth opportunities",
          "Better manager support",
          "Higher pay",
          "Different team or culture",
        ],
      },
      {
        id: 2,
        text: "What motivates you most at work?",
        options: [
          "Recognition and feedback",
          "Achieving results",
          "Helping others",
          "Learning new skills",
        ],
      },
      {
        id: 3,
        text: "How do you prefer to receive feedback?",
        options: [
          "In the moment, directly",
          "In private, with explanation",
          "Written feedback I can review",
          "Through regular check-ins",
        ],
      },
      {
        id: 4,
        text: "What type of projects excite you most?",
        options: [
          "Creative and innovative projects",
          "Problem-solving challenges",
          "Clear, structured tasks",
          "Collaborative team efforts",
        ],
      },
      {
        id: 5,
        text: "Do you prefer structured tasks or open-ended challenges?",
        options: [
          "Structured tasks with clear direction",
          "Open-ended challenges where I can decide",
          "A mix of both",
          "Depends on the situation",
        ],
      },
    ],
  },
  {
    key: "careerTransition",
    title: "Quiz 2: Career Transition",
    questions: [
      {
        id: 1,
        text: "Why are you considering a career change?",
        options: [
          "Burnout in current role",
          "Desire for new challenge",
          "Better pay and benefits",
          "Personal passion or interest",
        ],
      },
      {
        id: 2,
        text: "What skills from your past roles do you want to leverage most?",
        options: [
          "Leadership",
          "Technical expertise",
          "Creativity and innovation",
          "Problem-solving",
        ],
      },
      {
        id: 3,
        text: "What are you hoping to leave behind in your current/previous role?",
        options: [
          "Toxic work culture",
          "Lack of growth",
          "Work-life imbalance",
          "Repetitive tasks",
        ],
      },
      {
        id: 4,
        text: "What type of culture do you want in your next role?",
        options: [
          "Collaborative and team-focused",
          "Innovative and fast-paced",
          "Stable and predictable",
          "Supportive and developmental",
        ],
      },
      {
        id: 5,
        text: "What would success look like for you in a new career path?",
        options: [
          "Financial stability",
          "Work-life balance",
          "Recognition and growth",
          "Meaningful contribution",
        ],
      },
    ],
  },
  {
    key: "midCareer",
    title: "Quiz 3: Mid-Career / Strategic",
    questions: [
      {
        id: 1,
        text: "What do you want your leadership legacy to be?",
        options: [
          "Building strong teams",
          "Driving innovation",
          "Delivering results",
          "Developing future leaders",
        ],
      },
      {
        id: 2,
        text: "How do you balance strategic vision with day-to-day execution?",
        options: [
          "Delegate operational tasks",
          "Focus on strategy first",
          "Alternate between both",
          "Struggle with balance",
        ],
      },
      {
        id: 3,
        text: "Where do you want to grow in the next 3–5 years?",
        options: [
          "People leadership",
          "Technical expertise",
          "Strategic influence",
          "Entrepreneurial ventures",
        ],
      },
      {
        id: 4,
        text: "What type of team environment allows you to thrive?",
        options: [
          "High accountability",
          "Creative and open-minded",
          "Structured and organized",
          "Supportive and collaborative",
        ],
      },
      {
        id: 5,
        text: "How do you want to be remembered by your peers and reports?",
        options: [
          "As a trusted advisor",
          "As an innovator",
          "As a dependable operator",
          "As a mentor and coach",
        ],
      },
    ],
  },
  {
    key: "teenFocused",
    title: "Quiz 4: Your Future, Your Way (Teen-Focused)",
    questions: [
      {
        id: 1,
        text: "What is your least favorite subject and why?",
        options: [
          "Math – too many rules",
          "English – too much writing",
          "Science – too complicated",
          "History – too boring",
        ],
      },
      {
        id: 2,
        text:
          "What did your favorite teacher or coach do that made them stand out?",
        options: [
          "Made learning fun",
          "Believed in me",
          "Pushed me to do better",
          "Listened and cared",
        ],
      },
      {
        id: 3,
        text: "Do you like to stay busy all the time or chill out more?",
        options: [
          "Always busy – I like action",
          "Chill out – I need downtime",
          "A balance of both",
          "Depends on my mood",
        ],
      },
      {
        id: 4,
        text: "What do you want life to look like after high school?",
        options: [
          "Go to college",
          "Start working right away",
          "Travel and explore",
          "Not sure yet",
        ],
      },
      {
        id: 5,
        text: "How do you usually handle school projects?",
        options: [
          "Do it right away",
          "Wait until the last minute",
          "Bribe a sibling or friend to help",
          "Work with a group",
        ],
      },
    ],
  },
];

// Static copy that explains different "archetypes" the user might align with
const archetypes = [
  "The Builder – thrives on creating new systems, projects, and opportunities.",
  "The Strategist – excels in long-term planning and pattern recognition.",
  "The Operator – delivers reliable execution and stability.",
  "The Visionary – inspires others with big-picture thinking and innovation.",
  "The Connector – builds relationships and drives collaboration.",
];

export default function CareerQuizzesArchetypesTab() {
  // answers state structure:
  // answers[quizKey][questionId] = optionIndex (0-based index into options array)
  const [answers, setAnswers] = useState<Record<string, Record<number, number>>>({});
  const [isEditing, setIsEditing] = useState(false);
  const [hasSaved, setHasSaved] = useState(false);

  // Get profile-related actions from AuthContext
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
        const saved = (profileData as any)?.quizResults?.careerQuizzes;
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

  /**
   * Submit all quiz answers at once:
   * - Fetch existing profile data (if available)
   * - Merge quiz results into profileData
   * - Save via saveProfileData from AuthContext
   */
  const onSubmitAll = () => {
    (async () => {
      try {
        // Fetch current profile data so we don't overwrite other fields
        const current = await (fetchProfileData ? fetchProfileData() : Promise.resolve(null));
        // Some backends may nest data under profileData, so handle both shapes
        const profileData = current?.profileData || current || {};

        // New profile object with quiz results merged in
        const existingQuizResults = (profileData as any)?.quizResults || {};
        const newProfileData = {
          ...profileData,
          quizResults: {
            ...existingQuizResults,
            careerQuizzes: answers,
            careerQuizzesSubmittedAt: new Date().toISOString(),
          },
        };

        // If saveProfileData is available, persist the updated profile
        if (saveProfileData) {
          await saveProfileData(newProfileData);
          setHasSaved(true);
          setIsEditing(false);
          navigate("/job-seeker/profile?tab=assessments");
        } else {
          // If AuthContext doesn't expose saveProfileData, log and show a fallback message
          console.warn("saveProfileData not available on AuthContext");
          alert("Unable to save responses (not authenticated).");
        }
      } catch (err) {
        // On any error, log details and show user-friendly message
        console.error(err);
        alert("Failed to save responses. Check console for details.");
      }
    })();
  };

  return (
    <div className="p-4 max-w-4xl mx-auto text-slate-100">
      {/* Title for the overall tab */}
      <h2 className="text-xl font-semibold mb-2">Career Quizzes &amp; Archetypes</h2>

      {!isEditing && hasSaved ? (
        <div className="mb-8 rounded-2xl border border-white/10 bg-slate-900/60 p-6">
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
            {quizzes.map((quiz) => (
              <section key={quiz.key}>
                <h4 className="text-base font-semibold text-white">{quiz.title}</h4>
                <ul className="mt-3 space-y-3">
                  {quiz.questions.map((q) => {
                    const selected = answers?.[quiz.key]?.[q.id];
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
          {/* Render each quiz section */}
          {quizzes.map((quiz) => (
            <section key={quiz.key} className="mb-8">
              <h3 className="text-lg font-medium mb-2">{quiz.title}</h3>
              <ol start={1} className="space-y-4 pl-5">
                {quiz.questions.map((q) => (
                  <li key={q.id}>
                    <fieldset>
                      <legend className="mb-1">
                        {q.id}. {q.text}
                      </legend>
                      {/* Render options as radio buttons for each question */}
                      {q.options.map((opt, idx) => (
                        <label key={idx} className="block">
                          <input
                            type="radio"
                            // Use a unique name per question so radios are grouped correctly
                            name={`${quiz.key}-q${q.id}`}
                            // Check if this option is the selected index for this question
                            checked={(answers[quiz.key]?.[q.id] ?? -1) === idx}
                            // Update state when user selects this option
                            onChange={() => onChange(quiz.key, q.id, idx)}
                          />{" "}
                          {opt}
                        </label>
                      ))}
                    </fieldset>
                  </li>
                ))}
              </ol>
            </section>
          ))}
        </>
      )}

      {/* Static list of archetypes for the user to read */}
      <section className="mb-6">
        <h3 className="text-lg font-medium mb-2">Archetypes</h3>
        <ul className="list-disc pl-6 space-y-1">
          {archetypes.map((a, i) => (
            <li key={i}>{a}</li>
          ))}
        </ul>
      </section>

      {/* Button that triggers saving all responses to the profile */}
      {isEditing && (
        <button type="button" onClick={onSubmitAll} className="rounded-full bg-gradient-to-r from-emerald-400 via-blue-500 to-indigo-500 px-4 py-2 text-sm font-semibold text-slate-950 shadow-lg shadow-emerald-500/25">
          Save Answers
        </button>
      )}
    </div>
  );
}
