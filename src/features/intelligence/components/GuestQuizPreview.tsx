import { Link } from "react-router-dom";
import { getPendingQuizSave, hasCompletedGuestQuiz } from "../../../shared/lib/guestQuiz";
import { CONTAINER, LEAD, PAGE_H1, PRIMARY, SECONDARY } from "../../../shared/ui/publicStyles";

interface QuizRow {
  title: string;
  desc: string;
  to: string;
}

const QUIZZES: QuizRow[] = [
  {
    title: "Early Career",
    desc: "Explore your motivations, feedback preferences, and ideal early-career environment.",
    to: "/quiz-preview/early-career",
  },
  {
    title: "Career Transition",
    desc: "Clarify what you want to leave behind and what success looks like in your next chapter.",
    to: "/quiz-preview/career-transition",
  },
  {
    title: "Career & Job Search",
    desc: "A reflection-based quiz for graduates and early-career professionals navigating their next chapter.",
    to: "/quiz-preview/career-job-search",
  },
  {
    title: "Mid-Career / Strategic",
    desc: "Define your leadership legacy, strategic growth areas, and ideal team environment.",
    to: "/quiz-preview/mid-career",
  },
  {
    title: "Your Future, Your Way (Teen-Focused)",
    desc: "A teen-focused quiz that helps you explore interests, personality, and future goals.",
    to: "/quiz-preview/teen-focused",
  },
];

function LockIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true" className="shrink-0">
      <rect x="3" y="7" width="10" height="7" rx="1" stroke="currentColor" strokeWidth="1.5" />
      <path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}

/**
 * The guest quiz list at /quiz-preview. One free quiz per visitor; after that
 * every row is locked and the only ways forward are the account actions at the
 * top of the page, so they are not repeated on each row.
 */
export default function GuestQuizPreview() {
  const lockedOut = hasCompletedGuestQuiz() || Boolean(getPendingQuizSave());

  return (
    <div className="landing min-h-screen bg-cream-base font-body text-ink-primary antialiased">
      <div className={`${CONTAINER} pb-20 pt-12 md:pb-28 md:pt-16`}>
        <div className="flex flex-col gap-8 md:flex-row md:items-end md:justify-between md:gap-12">
          <div className="max-w-[60ch]">
            <h1 className={PAGE_H1}>Try a quiz before you sign up.</h1>
            <p className={`mt-5 ${LEAD}`}>
              Take one quiz for free and get your insight straight away. Create an account to save
              your results and take the rest.
            </p>
          </div>
          <div className="flex shrink-0 flex-wrap gap-3">
            <Link to="/register" className={PRIMARY}>
              Create account
            </Link>
            <Link to="/login" className={SECONDARY}>
              Sign in
            </Link>
          </div>
        </div>

        {lockedOut && (
          <p
            role="status"
            className="mt-10 border-l-[3px] border-forest-dark bg-white px-5 py-4 text-[0.97rem] leading-[1.6] text-ink-primary"
          >
            You’ve already taken a guest quiz. Create an account or sign in to take more and save
            your results.
          </p>
        )}

        <ul className="mt-12 border-t border-cream-muted">
          {QUIZZES.map((quiz) => (
            <li
              key={quiz.to}
              className="grid gap-4 border-b border-cream-muted py-7 md:grid-cols-[minmax(0,3fr)_minmax(0,5fr)_auto] md:items-center md:gap-10"
            >
              <h2
                className={`font-headline text-[1.35rem] font-bold leading-tight ${
                  lockedOut ? "text-ink-secondary" : ""
                }`}
              >
                {quiz.title}
              </h2>
              <p className="text-[0.97rem] leading-[1.6] text-ink-secondary">{quiz.desc}</p>
              {lockedOut ? (
                <p className="flex items-center gap-2 text-[0.86rem] font-semibold text-ink-secondary md:justify-end">
                  <LockIcon />
                  Sign in above to unlock
                </p>
              ) : (
                <Link to={quiz.to} className={SECONDARY} aria-label={`Start quiz: ${quiz.title}`}>
                  Start quiz
                </Link>
              )}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
