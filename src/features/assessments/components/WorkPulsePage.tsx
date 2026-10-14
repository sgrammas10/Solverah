/**
 * WorkPulsePage -- the person-side culture assessment, shipped under the Work Pulse name.
 *
 * HISTORY. Work Pulse was originally a 12-question Likert quiz whose questions lived
 * client-side and fed an LLM narrative plus the 7-dimension culture_preferences. That
 * instrument is superseded: this page serves the 24-item forced-choice assessment behind
 * the Bayesian matching model. The old quiz was RETIRED on 2026-10-02 -- its questions,
 * stepper and submit paths are deleted and its write routes answer 410 -- and only its
 * stored narrative stays, read-only, at /work-pulse/results for users who took it.
 *
 * RETAKES (ruling 2026-10-02: retakeable, no cooldown "for now"). The completion card
 * offers "Retake Work Pulse", which opens the normal form: same stepper, same resume
 * prompt, same sessionStorage draft. Each finished sitting is stored as its own; the
 * first is kept. The Situation Report stays pinned to the sitting it was built from
 * until the user presses its Re-read button (situation-report owns that pin).
 *
 * WHILE A RETAKE IS UNFINISHED, WORK PULSE IS STILL COMPLETE. The in-progress answers
 * live only in this tab's sessionStorage until Finish, so the server's
 * `wp_v2_completed`, the dashboard and the hub all keep showing the finished state, and
 * every finished result stays where it was. Nothing on the server knows a retake has
 * started. Coming back to /work-pulse with a draft shows the completion card with
 * "Continue your retake", which reopens the form at the resume prompt.
 *
 * A cooldown, if one is ever wanted, is `assessment_service.CORE_RETAKE_COOLDOWN` on the
 * server. This page does not know about it: turning it on should come with a way for
 * the card below to hide the Retake button inside the window.
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
 * TOLERANCE STEP (six-trait match model, 2026-10-13). Right after a sitting is saved --
 * a first sitting or a retake -- the page shows TraitPreferencesStep before the
 * completion card's next steps: per trait, how much more or less than preferred is
 * fine, plus up to two must-haves. "Skip for now" writes nothing and leaves the user
 * unanswered, which keeps matching and the Situation Report exactly as they were.
 * The card links to /trait-preferences to change the answers later.
 *
 * THE RESULTS SCREEN DELIBERATELY DOES NOT EXIST for this instrument (decided 2026-08-19:
 * completion state only). Returning a respondent's six dimension scores hands a retaker a
 * gradient to optimise against and teaches the item-to-dimension mapping the shuffle and
 * interleave exist to hide (D-15). Whatever is eventually shown has to be designed against
 * that pressure rather than falling out of the submit response.
 */
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import AssessmentStepper from "./AssessmentStepper";
import TraitPreferencesStep from "./TraitPreferencesStep";
import HeroNetworkAnimation from "../../../shared/ui/HeroNetworkAnimation";
import ResumePrompt from "../../../shared/ui/ResumePrompt";
import { firstUnansweredIndex, useResumePrompt } from "../../../shared/lib/resumeDraft";
import { flattenItems, hasAssessmentDraft, useAssessment } from "../useAssessment";
import { situationReportKeys, useSituationReport } from "../useSituationReport";
import { useAuth } from "../../auth";

/** The dashboard document's query key. Spelled out rather than imported:
 *  `dashboardKeys` is not on the profile slice's public surface, and slices
 *  may not deep-import each other. WorkPulsePage.test.tsx pins it to
 *  `dashboardKeys.all`, so a rename there fails a test here. */
export const DASHBOARD_QUERY_KEY = ["dashboard"] as const;

/** Shown for any submit failure. The server's own text is never shown: it is
 *  written for developers, and for a stale form it names opaque item tokens. */
export const SUBMIT_ERROR_MESSAGE =
  "We couldn't save your Work Pulse. Your answers are still here. Reload the questions, then press Finish again.";

/** The live form. Mounted only while the current instrument is incomplete or a retake is
 * open, so a completed user's visit does not fetch (and rebuild) a form they did not ask
 * for. */
interface WorkPulseFormProps {
  showLegacyLink: boolean;
  onCompleted: () => void;
  /** Set when this is a second (or later) sitting; offers the way back to the card. */
  onCancelRetake?: () => void;
}

function WorkPulseForm({ showLegacyLink, onCompleted, onCancelRetake }: WorkPulseFormProps) {
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
  // Bumped to remount the stepper at `startIndex` after the questions reload.
  const [stepperKey, setStepperKey] = useState(0);
  // The hook keeps its last submit error until the next submit. Reloading the
  // questions answers it, so the message is hidden from then until Finish.
  const [submitErrorDismissed, setSubmitErrorDismissed] = useState(false);
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
    setSubmitErrorDismissed(false);
    const result = await submit();
    if (result) {
      onCompleted();
    }
  }

  /** The action on a failed submit. A form that changed under the respondent
   *  (a new item file, so new tokens) is the failure a reload can fix: the hook
   *  drops answers to items no longer in it, and the stepper reopens at the
   *  first question still unanswered. */
  async function handleReloadQuestions() {
    setSubmitErrorDismissed(true);
    const refreshed = await reloadForm();
    const fresh = refreshed?.data ? flattenItems(refreshed.data) : items;
    if (fresh && fresh.length > 0) {
      setStartIndex(firstUnansweredIndex(fresh, (i) => answers[i.token] !== undefined));
      setStepperKey((k) => k + 1);
    }
  }

  return (
    <>
      <div className="mb-8 space-y-2">
        <h1 className="font-display text-2xl sm:text-3xl font-semibold text-ink-primary">
          Work Pulse
        </h1>
        {onCancelRetake && (
          <p className="text-sm text-ink-secondary">
            You're retaking Work Pulse. This is a new sitting: the one you finished before
            stays stored, and your Situation Report keeps reading it until you choose to
            re-read the report.{" "}
            <button
              type="button"
              onClick={onCancelRetake}
              className="font-semibold text-forest-dark hover:underline"
            >
              Not now
            </button>
          </p>
        )}
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
          key={stepperKey}
          initialIndex={startIndex}
          items={items}
          answers={answers}
          onAnswer={setAnswer}
          onComplete={handleComplete}
          submitting={submitting}
          submitError={submitError && !submitErrorDismissed ? SUBMIT_ERROR_MESSAGE : null}
          onReloadQuestions={handleReloadQuestions}
        />
      )}
    </>
  );
}

/** Which next step the completion card leads with. */
type NextStep = "describe_job" | "see_report" | "first_job" | "pending";

export default function WorkPulsePage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user, updateProfile } = useAuth();
  const [justCompleted, setJustCompleted] = useState(false);
  // A second (or later) sitting is open. Local state on purpose: nothing on the
  // server changes until Finish, so completion holds while this is true.
  const [retaking, setRetaking] = useState(false);
  const [justRetook, setJustRetook] = useState(false);
  // The tolerance step, shown once right after a sitting is saved and before the
  // card's next steps. Closed by saving or skipping.
  const [traitStepOpen, setTraitStepOpen] = useState(false);

  const isCompleted = justCompleted || Boolean(user?.wp_v2_completed);
  const hasLegacyResults = Boolean(user?.wpl_completed);
  // Read on render: the form clears the draft on a successful submit, and the
  // card is only drawn while the form is not mounted.
  const retakeDraftSaved = isCompleted && !retaking && hasAssessmentDraft();

  // The report decides the next step, because it already knows the two cases
  // the plain "describe your job" bridge got wrong: a `first_job` user has no
  // job to describe (the server refuses the form), and a user who described
  // the job before taking Work Pulse already has a report.
  const situation = useSituationReport({ enabled: isCompleted });
  const report = situation.data;
  let nextStep: NextStep;
  if (situation.isPending || (situation.isFetching && report?.state === "needs_core")) {
    // Nothing yet, or only a pre-completion copy being refetched. Waiting
    // keeps a first_job user from seeing a button they cannot use.
    nextStep = "pending";
  } else if (report?.state === "complete") {
    nextStep = "see_report";
  } else if (
    report?.state === "needs_environment_report" &&
    !report.can_submit_environment_report
  ) {
    nextStep = "first_job";
  } else {
    // Includes a failed fetch: the environment report page handles its own refusals.
    nextStep = "describe_job";
  }

  function handleCompleted() {
    if (retaking) {
      setRetaking(false);
      setJustRetook(true);
    }
    // Optimistic local flip only -- the server derives the durable value from the stored
    // submission, so a refresh converges on the same answer.
    updateProfile({ wp_v2_completed: true });
    // The Situation Report and the dashboard document both read core completion,
    // and both may be cached from before it. Without this the dashboard's card
    // and the report page disagree with this screen until a reload.
    queryClient.invalidateQueries({ queryKey: situationReportKeys.all });
    queryClient.invalidateQueries({ queryKey: DASHBOARD_QUERY_KEY });
    setJustCompleted(true);
    setTraitStepOpen(true);
  }

  const secondary =
    "inline-flex items-center border border-forest-dark text-forest-dark text-sm font-semibold px-6 py-3 rounded hover:bg-forest-pale transition-colors";
  const primary =
    "inline-flex items-center bg-forest-dark text-white text-sm font-semibold px-6 py-3 rounded hover:bg-forest-mid transition-colors";

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
        {isCompleted && !retaking && traitStepOpen ? (
          <div className="space-y-4">
            <p className="text-xs font-semibold uppercase tracking-widest text-forest-mid">
              ✦ Work Pulse Complete
            </p>
            <TraitPreferencesStep onFinished={() => setTraitStepOpen(false)} />
          </div>
        ) : isCompleted && !retaking ? (
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
                secondary rather than disappearing.

                Two exceptions, both read off the report. A `first_job` user has
                no job to describe, so FocusType leads instead, matching the
                report page's own first_job screen. A user who described the job
                first already has a report, so the primary button opens it. */}
            {nextStep === "describe_job" && (
              <>
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
                    className={primary}
                  >
                    Describe your job →
                  </button>
                </div>
              </>
            )}
            {nextStep === "see_report" && (
              <>
                {justRetook ? (
                  // The pin (situation-report's D-15 pin) does not follow a retake on
                  // its own; saying so here is what makes the Re-read button findable.
                  <p className="text-sm text-ink-secondary">
                    Your Situation Report still reads the sitting it was built from. To
                    move it to this one, open the report and choose “Re-read this against
                    my latest Work Pulse”.
                  </p>
                ) : (
                  <p className="text-sm text-ink-secondary">
                    You've already described your job, so both halves of your Situation
                    Report are in. It's ready to read.
                  </p>
                )}
                <div className="mt-2">
                  <button
                    type="button"
                    onClick={() => navigate("/situation-report")}
                    className={primary}
                  >
                    See your Situation Report →
                  </button>
                </div>
              </>
            )}
            {nextStep === "first_job" && (
              <p className="text-sm text-ink-secondary">
                When you start a job, sixteen questions about it turn this into your
                Situation Report. Until then, FocusType and ManagerMatch need no employer,
                and they're most useful while you're choosing between offers.
              </p>
            )}
            <div className="mt-2 flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={() => navigate("/focus-type")}
                className={nextStep === "first_job" ? primary : secondary}
              >
                Start FocusType →
              </button>
              <button
                type="button"
                onClick={() => navigate("/manager-match")}
                className={secondary}
              >
                Start ManagerMatch →
              </button>
              <button
                type="button"
                onClick={() => navigate("/job-seeker/dashboard", { replace: true })}
                className={secondary}
              >
                Back to dashboard
              </button>
            </div>
            {/* Retake (ruling 2026-10-02). Last on the card and secondary: the next
                steps above are what most people want, and a retake is for when
                something has changed, not a way to check a score -- there is none. */}
            <div className="mt-6 border-t border-cream-muted pt-5 space-y-3">
              <p className="text-sm text-ink-secondary">
                {retakeDraftSaved
                  ? "You started a new sitting and didn't finish it. Your answers so far are saved in this browser."
                  : "If the way you work has changed, you can take Work Pulse again. Your earlier sitting stays stored."}
              </p>
              <button
                type="button"
                onClick={() => {
                  setJustRetook(false);
                  setRetaking(true);
                }}
                className={secondary}
              >
                {retakeDraftSaved ? "Continue your retake →" : "Retake Work Pulse"}
              </button>
              {/* A button, not a link: the card carries no links at all, so a
                  results link cannot creep back in unnoticed (D-15 test). */}
              <p className="text-sm text-ink-secondary">
                <button
                  type="button"
                  onClick={() => navigate("/trait-preferences")}
                  className="font-semibold text-forest-dark hover:underline"
                >
                  Change how much give you have on each area →
                </button>
              </p>
            </div>
          </div>
        ) : (
          <WorkPulseForm
            showLegacyLink={hasLegacyResults && !isCompleted}
            onCompleted={handleCompleted}
            onCancelRetake={retaking ? () => setRetaking(false) : undefined}
          />
        )}
        </div>
      </div>
    </div>
  );
}
