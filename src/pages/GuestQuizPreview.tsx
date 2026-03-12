import { Link } from "react-router-dom";
import { getPendingQuizSave, hasCompletedGuestQuiz } from "../utils/guestQuiz";

export default function GuestQuizPreview() {
  const lockedOut = hasCompletedGuestQuiz() || Boolean(getPendingQuizSave());
  const lockedButtons = (
    <div className="mt-4 flex flex-wrap gap-3">
      <Link
        to="/login"
        className="inline-flex rounded-full border border-cream-muted bg-white px-4 py-2 text-sm font-semibold text-ink-secondary hover:border-forest-light hover:text-forest-mid transition-colors"
      >
        Sign in
      </Link>
      <Link
        to="/register"
        className="inline-flex rounded-full bg-forest-light px-4 py-2 text-sm font-semibold text-white hover:bg-forest-mid transition-colors"
      >
        Create account
      </Link>
    </div>
  );

  const quizCards = [
    { title: "Early Career", desc: "Explore your motivations, feedback preferences, and ideal early-career environment.", to: "/quiz-preview/early-career" },
    { title: "Career Transition", desc: "Clarify what you want to leave behind and what success looks like in your next chapter.", to: "/quiz-preview/career-transition" },
    { title: "Career & Job Search", desc: "A reflection-based quiz for graduates and early-career professionals navigating their next chapter.", to: "/quiz-preview/career-job-search" },
    { title: "Mid-Career / Strategic", desc: "Define your leadership legacy, strategic growth areas, and ideal team environment.", to: "/quiz-preview/mid-career" },
  ];

  return (
    <div className="min-h-screen bg-cream-base font-sans text-ink-primary">
      <div className="mx-auto max-w-5xl px-6 py-12">
        <div className="flex flex-wrap items-start justify-between gap-6">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.08em] text-forest-light mb-2">Quiz Preview</p>
            <h1 className="font-display text-3xl font-bold text-ink-primary">
              Get a feel for what Solverah delivers
            </h1>
            <p className="mt-3 max-w-2xl text-sm text-ink-secondary">
              Take one quiz for free and get immediate, actionable insight. Create an account
              to save results and unlock full profile features.
            </p>
          </div>
          <Link
            to="/register"
            className="rounded-full bg-forest-light px-5 py-2.5 text-sm font-semibold text-white hover:bg-forest-mid transition-colors"
          >
            Create account
          </Link>
        </div>

        {lockedOut ? (
          <div className="mt-8 rounded-xl border border-cream-muted bg-white p-5 text-sm text-ink-secondary">
            You’ve already taken a guest quiz. Create an account or sign in to take more and save your results.
          </div>
        ) : null}

        <div className="mt-10 grid gap-6 md:grid-cols-2">
          {quizCards.map((card) => (
            <div key={card.to} className="rounded-xl border border-cream-muted bg-white p-6">
              <h3 className="font-display text-lg font-semibold text-ink-primary">{card.title}</h3>
              <p className="mt-2 text-sm text-ink-secondary">{card.desc}</p>
              {lockedOut ? lockedButtons : (
                <Link
                  to={card.to}
                  className="mt-4 inline-flex rounded-full bg-forest-light px-5 py-2.5 text-sm font-semibold text-white hover:bg-forest-mid transition-colors"
                >
                  Start quiz
                </Link>
              )}
            </div>
          ))}

          <div className="rounded-xl border border-cream-muted bg-white p-6 md:col-span-2">
            <h3 className="font-display text-lg font-semibold text-ink-primary">Your Future, Your Way (Teen-Focused)</h3>
            <p className="mt-2 text-sm text-ink-secondary">
              A fun, teen-focused quiz that helps you explore interests, personality, and future goals.
            </p>
            {lockedOut ? lockedButtons : (
              <Link
                to="/quiz-preview/teen-focused"
                className="mt-4 inline-flex rounded-full bg-forest-light px-5 py-2.5 text-sm font-semibold text-white hover:bg-forest-mid transition-colors"
              >
                Start quiz
              </Link>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
