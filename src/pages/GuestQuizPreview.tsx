import { Link } from "react-router-dom";
import { getPendingQuizSave, hasCompletedGuestQuiz } from "../utils/guestQuiz";

export default function GuestQuizPreview() {
  const lockedOut = hasCompletedGuestQuiz() || Boolean(getPendingQuizSave());
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <div className="mx-auto max-w-5xl px-6 py-12">
        <div className="flex flex-wrap items-start justify-between gap-6">
          <div>
            <p className="text-xs uppercase tracking-[0.16em] text-emerald-300">Quiz Preview</p>
            <h1 className="mt-2 text-3xl font-semibold text-white">
              Get a feel for what Solverah delivers
            </h1>
            <p className="mt-3 max-w-2xl text-sm text-slate-200/85">
              Take one quiz for free and get immediate, actionable insight. Create an account
              to save results and unlock full profile features.
            </p>
          </div>
          <Link
            to="/register"
            className="rounded-full border border-emerald-300/50 bg-emerald-300/10 px-5 py-2 text-sm font-semibold text-emerald-100 hover:border-emerald-200 hover:text-white"
          >
            Create account
          </Link>
        </div>

        {lockedOut ? (
          <div className="mt-8 rounded-2xl border border-amber-400/30 bg-amber-500/10 p-5 text-sm text-amber-100">
            You’ve already taken a guest quiz. Create an account or sign in to take more and save your results.
          </div>
        ) : null}

        <div className="mt-10 grid gap-6 md:grid-cols-2">
          <div className="rounded-xl border border-white/10 bg-slate-900/60 p-5">
            <h3 className="text-lg font-semibold text-emerald-200">Early Career</h3>
            <p className="mt-2 text-sm text-slate-200/80">
              Explore your motivations, feedback preferences, and ideal early-career environment.
            </p>
            {lockedOut ? (
              <div className="mt-4 flex flex-wrap gap-3">
                <Link
                  to="/login"
                  className="inline-flex rounded-full border border-white/10 px-4 py-2 text-sm font-semibold text-slate-100 hover:border-emerald-300/60"
                >
                  Sign in
                </Link>
                <Link
                  to="/register"
                  className="inline-flex rounded-full border border-emerald-300/50 bg-emerald-300/10 px-4 py-2 text-sm font-semibold text-emerald-100 hover:border-emerald-200 hover:text-white"
                >
                  Create account
                </Link>
              </div>
            ) : (
              <Link
                to="/quiz-preview/early-career"
                className="mt-4 inline-flex rounded-full bg-gradient-to-r from-emerald-400 via-blue-500 to-indigo-500 px-4 py-2 text-sm font-semibold text-slate-950 shadow-lg shadow-emerald-500/25"
              >
                Start quiz
              </Link>
            )}
          </div>

          <div className="rounded-xl border border-white/10 bg-slate-900/60 p-5">
            <h3 className="text-lg font-semibold text-emerald-200">Career Transition</h3>
            <p className="mt-2 text-sm text-slate-200/80">
              Clarify what you want to leave behind and what success looks like in your next chapter.
            </p>
            {lockedOut ? (
              <div className="mt-4 flex flex-wrap gap-3">
                <Link
                  to="/login"
                  className="inline-flex rounded-full border border-white/10 px-4 py-2 text-sm font-semibold text-slate-100 hover:border-emerald-300/60"
                >
                  Sign in
                </Link>
                <Link
                  to="/register"
                  className="inline-flex rounded-full border border-emerald-300/50 bg-emerald-300/10 px-4 py-2 text-sm font-semibold text-emerald-100 hover:border-emerald-200 hover:text-white"
                >
                  Create account
                </Link>
              </div>
            ) : (
              <Link
                to="/quiz-preview/career-transition"
                className="mt-4 inline-flex rounded-full bg-gradient-to-r from-emerald-400 via-blue-500 to-indigo-500 px-4 py-2 text-sm font-semibold text-slate-950 shadow-lg shadow-emerald-500/25"
              >
                Start quiz
              </Link>
            )}
          </div>

          <div className="rounded-xl border border-white/10 bg-slate-900/60 p-5">
            <h3 className="text-lg font-semibold text-emerald-200">Career &amp; Job Search</h3>
            <p className="mt-2 text-sm text-slate-200/80">
              A reflection-based quiz for graduates and early-career professionals navigating their next chapter.
            </p>
            {lockedOut ? (
              <div className="mt-4 flex flex-wrap gap-3">
                <Link
                  to="/login"
                  className="inline-flex rounded-full border border-white/10 px-4 py-2 text-sm font-semibold text-slate-100 hover:border-emerald-300/60"
                >
                  Sign in
                </Link>
                <Link
                  to="/register"
                  className="inline-flex rounded-full border border-emerald-300/50 bg-emerald-300/10 px-4 py-2 text-sm font-semibold text-emerald-100 hover:border-emerald-200 hover:text-white"
                >
                  Create account
                </Link>
              </div>
            ) : (
              <Link
                to="/quiz-preview/career-job-search"
                className="mt-4 inline-flex rounded-full bg-gradient-to-r from-emerald-400 via-blue-500 to-indigo-500 px-4 py-2 text-sm font-semibold text-slate-950 shadow-lg shadow-emerald-500/25"
              >
                Start quiz
              </Link>
            )}
          </div>

          <div className="rounded-xl border border-white/10 bg-slate-900/60 p-5">
            <h3 className="text-lg font-semibold text-emerald-200">Mid-Career / Strategic</h3>
            <p className="mt-2 text-sm text-slate-200/80">
              Define your leadership legacy, strategic growth areas, and ideal team environment.
            </p>
            {lockedOut ? (
              <div className="mt-4 flex flex-wrap gap-3">
                <Link
                  to="/login"
                  className="inline-flex rounded-full border border-white/10 px-4 py-2 text-sm font-semibold text-slate-100 hover:border-emerald-300/60"
                >
                  Sign in
                </Link>
                <Link
                  to="/register"
                  className="inline-flex rounded-full border border-emerald-300/50 bg-emerald-300/10 px-4 py-2 text-sm font-semibold text-emerald-100 hover:border-emerald-200 hover:text-white"
                >
                  Create account
                </Link>
              </div>
            ) : (
              <Link
                to="/quiz-preview/mid-career"
                className="mt-4 inline-flex rounded-full bg-gradient-to-r from-emerald-400 via-blue-500 to-indigo-500 px-4 py-2 text-sm font-semibold text-slate-950 shadow-lg shadow-emerald-500/25"
              >
                Start quiz
              </Link>
            )}
          </div>

          <div className="rounded-xl border border-white/10 bg-slate-900/60 p-5 md:col-span-2">
            <h3 className="text-lg font-semibold text-emerald-200">Your Future, Your Way (Teen-Focused)</h3>
            <p className="mt-2 text-sm text-slate-200/80">
              A fun, teen-focused quiz that helps you explore interests, personality, and future goals.
            </p>
            {lockedOut ? (
              <div className="mt-4 flex flex-wrap gap-3">
                <Link
                  to="/login"
                  className="inline-flex rounded-full border border-white/10 px-4 py-2 text-sm font-semibold text-slate-100 hover:border-emerald-300/60"
                >
                  Sign in
                </Link>
                <Link
                  to="/register"
                  className="inline-flex rounded-full border border-emerald-300/50 bg-emerald-300/10 px-4 py-2 text-sm font-semibold text-emerald-100 hover:border-emerald-200 hover:text-white"
                >
                  Create account
                </Link>
              </div>
            ) : (
              <Link
                to="/quiz-preview/teen-focused"
                className="mt-4 inline-flex rounded-full bg-gradient-to-r from-emerald-400 via-blue-500 to-indigo-500 px-4 py-2 text-sm font-semibold text-slate-950 shadow-lg shadow-emerald-500/25"
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
