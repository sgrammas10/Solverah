import { useState } from "react";

type Question = { id: number; text: string; options: string[] };
type Quiz = { key: string; title: string; questions: Question[] };

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

const archetypes = [
  "The Builder – thrives on creating new systems, projects, and opportunities.",
  "The Strategist – excels in long-term planning and pattern recognition.",
  "The Operator – delivers reliable execution and stability.",
  "The Visionary – inspires others with big-picture thinking and innovation.",
  "The Connector – builds relationships and drives collaboration.",
];

export default function CareerQuizzesArchetypesTab() {
  // answers[quizKey][questionId] = optionIndex
  const [answers, setAnswers] = useState<Record<string, Record<number, number>>>(
    {}
  );

  const onChange = (quizKey: string, qid: number, idx: number) => {
    setAnswers((prev) => ({
      ...prev,
      [quizKey]: { ...(prev[quizKey] || {}), [qid]: idx },
    }));
  };

  const onSubmitAll = () => {
    console.log("Career Quizzes & Archetypes responses:", answers);
    alert("Responses saved (see console).");
  };

  return (
    <div className="p-4 max-w-4xl mx-auto">
      <h2 className="text-xl font-semibold mb-2">Career Quizzes &amp; Archetypes</h2>

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
                  {q.options.map((opt, idx) => (
                    <label key={idx} className="block">
                      <input
                        type="radio"
                        name={`${quiz.key}-q${q.id}`}
                        checked={(answers[quiz.key]?.[q.id] ?? -1) === idx}
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

      <section className="mb-6">
        <h3 className="text-lg font-medium mb-2">Archetypes</h3>
        <ul className="list-disc pl-6 space-y-1">
          {archetypes.map((a, i) => (
            <li key={i}>{a}</li>
          ))}
        </ul>
      </section>

      <button type="button" onClick={onSubmitAll} className="border px-3 py-2">
        Submit All
      </button>
    </div>
  );
}
