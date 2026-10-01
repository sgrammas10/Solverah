/**
 * WorkPulsePage -- the person-side culture assessment, shipped under the Work Pulse name.
 *
 * HISTORY. Work Pulse was originally a 12-question Likert quiz whose questions lived
 * client-side in src/data/wpQuestions.ts and fed an LLM narrative plus the retired
 * 7-dimension culture_preferences. That instrument is superseded: this page now serves the
 * 24-item forced-choice assessment behind the Bayesian matching model. The old questions,
 * hook (useWP) and results page remain only so users who completed the original quiz keep
 * access to their stored narrative at /work-pulse/results until they retake.
 *
 * WHY THE QUESTIONS ARE NOT IN A DATA FILE. Item order is a correctness requirement, not a
 * presentation choice. The 24 items form a graduated-difficulty ladder, shuffled per
 * respondent and interleaved across dimensions by the server (D-04, design rules 3/7); items
 * are addressed by opaque tokens and carry no ids or dimension labels. The client renders
 * exactly what the server sends, in the order it was sent.
 *
 * NOTE ON COPY. Two lines below are load-bearing and neither should be softened without
 * re-reading the reasoning:
 *
 *  1. "There are no right answers" is not reassurance, it is the mitigation the whole
 *     instrument depends on. The documented threat is a respondent answering as the person who
 *     gets matched to the job they want rather than as themselves, and a self-profiling user
 *     feels that pull harder than a candidate mid-application, not less.
 *  2. The employer line states a durable data commitment, not a marketing point: employers never
 *     see these answers or the six dimension scores behind them, and that is scoped to hold
 *     after employers join the platform.
 *
 * Neither line is a substitute for the server-side shuffle -- that remains the primary defense.
 * Do not let the copy grow into a promise the data layer does not keep.
 *
 * Both lines now carry a link to /trust (BUILD_PLAN D-3), which is where the reasoning behind
 * them lives at length. The link sits on the employer line rather than replacing either claim:
 * a reader who wants the short version should not have to leave this page to get it.
 *
 * THE RESULTS SCREEN DELIBERATELY DOES NOT EXIST for this instrument (decided 2026-08-19:
 * completion state only). Returning a respondent's six dimension scores hands a retaker a
 * gradient to optimise against and teaches the item-to-dimension mapping the shuffle and
 * interleave exist to hide (D-15). Whatever is eventually shown has to be designed against
 * that pressure rather than falling out of the submit response.
 */
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import AssessmentStepper from "./AssessmentStepper";
import HeroNetworkAnimation from "../../../shared/ui/HeroNetworkAnimation";
import ResumePrompt from "../../../shared/ui/ResumePrompt";
import { firstUnansweredIndex, useResumePrompt } from "../../../shared/lib/resumeDraft";
import { useAssessment } from "../useAssessment";
import { useAuth } from "../../auth";

/** The live form. Mounted only while the current instrument is incomplete, so a completed
 * user's visit does not fetch (and rebuild) a form they will never see. */
function WorkPulseForm({
  showLegacyLink,
  onCompleted,
}: {
  showLegacyLink: boolean;
  onCompleted: () => void;
}) {
  const {
    items,
    answers,
    loadError,
    submitError,
    submitting,
    setAnswer,
    clearAnswers,
    submit,
    reloadForm,
  } = useAssessment();

  // A draft found on arrival (answers are read from sessionStorage synchronously, so
  // the first render already holds them) gets the resume prompt instead of a silent
  // drop back at question 1 with old answers pre-selected.
  const { showResumePrompt, dismissResumePrompt } = useResumePrompt(
    () => Object.keys(answers).length > 0
  );
  const [startIndex, setStartIndex] = useState(0);
  // Counted against the loaded form, not the raw draft: the hook prunes answers whose
  // tokens are not in this form, and a draft pruned to nothing is no draft at all.
  const answeredCount = items
    ? items.filter((i) => answers[i.token] !== undefined).length
    : 0;
  const promptVisible = showResumePrompt && items !== null && answeredCount > 0;

  function handleResume() {
    if (items) {
      setStartIndex(firstUnansweredIndex(items, (i) => answers[i.token] !== undefined));
    }
    dismissResumePrompt();
  }

  function handleStartOver() {
    clearAnswers();
    setStartIndex(0);
    dismissResumePrompt();
  }

  async function handleComplete() {
    const result = await submit();
    if (result) {
      onCompleted();
    }
  }

  return (
    <>
      <div className="mb-8 space-y-2">
        <h1 className="font-display text-2xl sm:text-3xl font-semibold text-ink-primary">
          Work Pulse
        </h1>
        <p className="text-sm text-ink-secondary">
          24 either-or questions about the conditions you do your best work in — about
          eight minutes.
        </p>
        <p className="text-sm text-ink-secondary">
          There are no right answers, and nothing here is scored as better or worse. The
          profile is only useful if it describes you rather than the version of you that
          sounds most employable.
        </p>
        <p className="text-xs text-ink-secondary">
          Employers never see your answers or your dimension scores.{" "}
          <Link to="/trust" className="font-semibold text-forest-dark hover:underline">
            How this works, and what we hold back →
          </Link>
        </p>
        {showLegacyLink && (
          <p className="text-xs text-ink-secondary">
            You completed the original Work Pulse — this new version replaces it.{" "}
            <Link
              to="/work-pulse/results"
              className="font-semibold text-forest-dark hover:underline"
            >
              View your previous analysis →
            </Link>
          </p>
        )}
      </div>

      {loadError && (
        <div
          role="alert"
          className="rounded-lg border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-700"
        >
          <p className="font-medium mb-1">We couldn't load Work Pulse right now.</p>
          <p className="text-xs">Please try again in a moment.</p>
          <button
            type="button"
            onClick={() => reloadForm()}
            className="mt-3 text-xs font-semibold text-red-700 underline"
          >
            Try again
          </button>
        </div>
      )}

      {!loadError && items === null && (
        <p className="text-sm text-ink-secondary">Loading…</p>
      )}

      {promptVisible && items !== null && (
        <ResumePrompt
          title="Work Pulse"
          answeredCount={answeredCount}
          total={items.length}
          onResume={handleResume}
          onStartOver={handleStartOver}
        />
      )}

      {!promptVisible && items !== null && items.length > 0 && (
        <AssessmentStepper
          initialIndex={startIndex}
          items={items}
          answers={answers}
          onAnswer={setAnswer}
          onComplete={handleComplete}
          submitting={submitting}
          submitError={submitError}
        />
      )}
    </>
  );
}

export default function WorkPulsePage() {
  const navigate = useNavigate();
  const { user, updateProfile } = useAuth();
  const [justCompleted, setJustCompleted] = useState(false);

  const isCompleted = justCompleted || Boolean(user?.wp_v2_completed);
  const hasLegacyResults = Boolean(user?.wpl_completed);

  function handleCompleted() {
    // Optimistic local flip only -- the server derives the durable value from the stored
    // submission, so a refresh converges on the same answer.
    updateProfile({ wp_v2_completed: true });
    setJustCompleted(true);
  }

  return (
    <div className="relative min-h-screen bg-cream-base overflow-hidden">
      <HeroNetworkAnimation theme="light" />
      {/* The content sits on a near-solid panel rather than straight over the
          animation: small ink-secondary copy drawn across moving network lines
          dropped below WCAG AA in user testing. The animation itself is shared
          with the landing page and stays untouched. */}
      <div className="relative z-10 mx-auto max-w-2xl px-4 sm:px-6 pt-12 pb-16">
        <div
          data-testid="work-pulse-panel"
          className="rounded-xl border border-cream-muted bg-cream-base/95 backdrop-blur-sm px-5 py-8 sm:px-8 shadow-sm"
        >
        {isCompleted ? (
          <div className="space-y-4">
            <p className="text-xs font-semibold uppercase tracking-widest text-forest-mid">
              ✦ Work Pulse Complete
            </p>
            <h1 className="font-display text-2xl sm:text-3xl font-semibold text-ink-primary">
              That's everything we need
            </h1>
            <p className="text-sm text-ink-secondary">
              Your Work Pulse now powers your matching. There's no score to check and nothing
              to optimize — it works quietly in the background as we line up the environments
              where you'd do your best work.
            </p>
            {/* The A-7 bridge, upgrading D-2's. What follows Work Pulse is no
                longer a choice between two side instruments and the door: the
                Situation Report is the other half of this one, and describing
                the job is what completes it. The env-report CTA is therefore
                primary and the FocusType / ManagerMatch CTAs step down to
                secondary rather than disappearing. */}
            <p className="text-sm text-ink-primary font-medium">
              24 questions about you. Now 16 about your job.
            </p>
            <p className="text-sm text-ink-secondary">
              Work Pulse is half of your Situation Report. The other half is your own
              description of the role you're in — what it actually offers, not what it
              was advertised as — and the report is the distance between the two.
            </p>
            <div className="mt-2">
              <button
                type="button"
                onClick={() => navigate("/environment-report")}
                className="inline-flex items-center bg-forest-dark text-white text-sm font-semibold px-6 py-3 rounded hover:bg-forest-mid transition-colors"
              >
                Describe your job →
              </button>
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={() => navigate("/focus-type")}
                className="inline-flex items-center border border-forest-dark text-forest-dark text-sm font-semibold px-6 py-3 rounded hover:bg-forest-pale transition-colors"
              >
                Start FocusType →
              </button>
              <button
                type="button"
                onClick={() => navigate("/manager-match")}
                className="inline-flex items-center border border-forest-dark text-forest-dark text-sm font-semibold px-6 py-3 rounded hover:bg-forest-pale transition-colors"
              >
                Start ManagerMatch →
              </button>
              <button
                type="button"
                onClick={() => navigate("/job-seeker/dashboard", { replace: true })}
                className="inline-flex items-center border border-forest-dark text-forest-dark text-sm font-semibold px-6 py-3 rounded hover:bg-forest-pale transition-colors"
              >
                Back to dashboard
              </button>
            </div>
          </div>
        ) : (
          <WorkPulseForm showLegacyLink={hasLegacyResults} onCompleted={handleCompleted} />
        )}
        </div>
      </div>
    </div>
  );
}
