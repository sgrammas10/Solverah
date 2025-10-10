import React from 'react';
import { quizzes, archetypes, Quiz, QuizQuestion } from './quizzes';

type Answers = Record<string, string>; // key: questionId, value: optionId

const TitleBar: React.FC = () => (
  <div className="sticky top-0 z-20 bg-white/80 backdrop-blur border-b">
    <div className="max-w-5xl mx-auto px-4 py-4 flex items-center justify-between">
      <h1 className="text-xl sm:text-2xl font-semibold">Career Quizzes &amp; Archetypes</h1>
      <span className="text-xs sm:text-sm text-gray-500">Local save • No account</span>
    </div>
  </div>
);

function useLocalState<T>(key: string, initial: T) {
  const [state, setState] = React.useState<T>(() => {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : initial;
  });
  React.useEffect(() => {
    localStorage.setItem(key, JSON.stringify(state));
  }, [key, state]);
  return [state, setState] as const;
}

const QuestionCard: React.FC<{
  q: QuizQuestion;
  value?: string;
  onChange: (val: string) => void;
}> = ({ q, value, onChange }) => (
  <div className="rounded-2xl border p-4 sm:p-6 shadow-sm">
    <p className="font-medium mb-3">{q.prompt}</p>
    <div className="grid gap-2">
      {q.options.map((opt) => (
        <label key={opt.id} className={`flex items-center gap-3 rounded-xl border p-3 cursor-pointer hover:border-gray-400 ${value === opt.id ? 'border-gray-800 ring-2 ring-gray-200' : ''}`}>
          <input
            type="radio"
            className="size-4 accent-black"
            name={q.id}
            checked={value === opt.id}
            onChange={() => onChange(opt.id)}
          />
          <span>{opt.label}</span>
        </label>
      ))}
    </div>
  </div>
);

const QuizPane: React.FC<{
  quiz: Quiz;
  answers: Answers;
  setAnswers: (fn: (a: Answers) => Answers) => void;
}> = ({ quiz, answers, setAnswers }) => {
  const allAnswered = quiz.questions.every((q) => !!answers[q.id]);
  return (
    <div className="space-y-6">
      {quiz.questions.map((q) => (
        <QuestionCard
          key={q.id}
          q={q}
          value={answers[q.id]}
          onChange={(val) =>
            setAnswers((prev) => ({ ...prev, [q.id]: val }))
          }
        />
      ))}
      <div className="text-sm text-gray-600">
        {allAnswered ? 'All questions answered ✅' : 'Please answer all questions'}
      </div>
    </div>
  );
};

const ArchetypesPanel: React.FC = () => (
  <div className="grid sm:grid-cols-2 gap-4">
    {archetypes.map((a) => (
      <div key={a.id} className="rounded-2xl border p-4">
        <p className="font-semibold">{a.label}</p>
        <p className="text-sm text-gray-600">{a.desc}</p>
      </div>
    ))}
  </div>
);

const App: React.FC = () => {
  const [active, setActive] = useLocalState<number>('activeTab', 0);
  const [answers, setAnswers] = useLocalState<Answers>('quizAnswers', {});
  const [submitting, setSubmitting] = React.useState(false);
  const [submittedOk, setSubmittedOk] = React.useState<boolean | null>(null);

  async function handleSubmit() {
    setSubmitting(true);
    setSubmittedOk(null);
    try {
      const res = await fetch('/api/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          submittedAt: new Date().toISOString(),
          answers,
        }),
      });
      setSubmittedOk(res.ok);
    } catch (e) {
      setSubmittedOk(false);
    } finally {
      setSubmitting(false);
    }
  }

  const tabs = [...quizzes.map((q) => q.title), 'Archetypes', 'Review & Submit'];

  const answeredCount = quizzes
    .flatMap((q) => q.questions)
    .filter((q) => answers[q.id])
    .length;

  const totalCount = quizzes.reduce((acc, q) => acc + q.questions.length, 0);

  return (
    <div className="min-h-dvh bg-gray-50">
      <TitleBar />

      <main className="max-w-5xl mx-auto px-4 pb-20">
        <div className="pt-6">
          {/* Tabs */}
          <div className="flex gap-2 overflow-auto pb-2">
            {tabs.map((t, i) => (
              <button
                key={t}
                onClick={() => setActive(i)}
                className={`whitespace-nowrap rounded-full border px-4 py-2 text-sm ${
                  active === i ? 'bg-black text-white' : 'bg-white hover:bg-gray-100'
                }`}
              >
                {t}
              </button>
            ))}
          </div>

          {/* Header */}
          <div className="mt-4 mb-6 flex items-center justify-between">
            <h2 className="text-lg sm:text-xl font-semibold">{tabs[active]}</h2>
            <div className="text-sm text-gray-600">
              Progress: {answeredCount} / {totalCount}
            </div>
          </div>

          {/* Content */}
          <div className="space-y-6">
            {active < quizzes.length && (
              <QuizPane quiz={quizzes[active]} answers={answers} setAnswers={setAnswers} />
            )}
            {active === quizzes.length && <ArchetypesPanel />}
            {active === quizzes.length + 1 && (
              <div className="space-y-6">
                <div className="rounded-2xl border p-4 bg-white">
                  <p className="font-medium mb-2">Review your answers</p>
                  <div className="text-sm text-gray-600">(Only selected options are shown)</div>
                  <div className="mt-4 space-y-3">
                    {quizzes.map((qz) => (
                      <div key={qz.id}>
                        <p className="font-semibold">{qz.title}</p>
                        <ul className="list-disc pl-5 text-sm">
                          {qz.questions.map((q) => {
                            const optId = answers[q.id];
                            const opt = q.options.find((o) => o.id === optId);
                            if (!opt) return null;
                            return (
                              <li key={q.id}>
                                <span className="font-medium">{q.prompt}</span>{' '}
                                <span className="text-gray-600">— {opt.label}</span>
                              </li>
                            );
                          })}
                        </ul>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="flex gap-2">
                  <button
                    onClick={handleSubmit}
                    disabled={submitting}
                    className="rounded-full bg-black text-white px-5 py-3 disabled:opacity-60"
                  >
                    {submitting ? 'Submitting…' : 'Submit to Backend'}
                  </button>
                  <button
                    onClick={() => localStorage.removeItem('quizAnswers') || window.location.reload()}
                    className="rounded-full border px-5 py-3 bg-white"
                  >
                    Reset Answers
                  </button>
                </div>

                {submittedOk === true && (
                  <div className="text-green-700">Submitted successfully ✅</div>
                )}
                {submittedOk === false && (
                  <div className="text-red-700">Submission failed. Is the backend running?</div>
                )}
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
};

export default App;