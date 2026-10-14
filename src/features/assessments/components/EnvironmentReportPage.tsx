/**
 * EnvironmentReportPage -- the environment-side instrument (BUILD_PLAN A-7).
 *
 * A stepper rather than a scrolling form, and that is a correctness decision
 * rather than a layout preference. `experienced` ("overall, how well is this
 * role working for you?") is the only evaluative item in the instrument and is
 * asked LAST on purpose, so its verdict cannot colour the twelve descriptive
 * items -- and a single scrolling form hands the reader every question at
 * once, which defeats exactly that. One question per screen is what makes the
 * anti-halo ordering in `work_pulse/situation_items.py` real instead of
 * decorative. `envQuestions.ts`'s header carries the rest of the reasoning.
 *
 * Going BACK is allowed here, unlike the Manager Decoder's forced-choice
 * instrument. This one is not ground-truth-sensitive: the user is describing a
 * job, not themselves, so there is no gaming pressure to defend against
 * (`situation_items.py`, "Not ground-truth-sensitive") and a mistyped answer
 * they cannot correct is pure cost.
 *
 * TENSE. `between_jobs` describes the role most recently held, so every prompt
 * and every option has a past-tense twin. The tense is chosen from the LIVE
 * profile document; the server snapshots `career_status` itself at submit time
 * and never takes it from the body, so a stale client cannot mislabel a
 * stored row. Tense changes no score -- the score lives on the option's pole,
 * which both twins share.
 *
 * `first_job` NEVER REACHES THE FORM. A user who has not held a role has
 * nothing to describe, and forcing the form would record a decline as a real
 * answer (PRODUCT_DECISIONS §2, 2026-09-10). Two gates, because either alone
 * has a hole: the report's own `can_submit_environment_report` flag catches a
 * direct visit before a question renders, and the submit's 409
 * (`first_job_no_role`) catches the case where the profile changed under a
 * form already open. Both land on the same friendly hand-off, never on an
 * error card -- there is nothing here for this user to fix.
 *
 * A THIRD failure -- the report call itself erroring, rather than resolving
 * to one of the states above -- gets the opposite treatment. `/me/situation-
 * report` returns 200 in every legitimate state, so `reportQuery.isError`
 * here always means a real failure, never "nothing yet." A failed gate is an
 * error card, never an open form: rendering the intro anyway would let this
 * user reach a form the page never got to confirm they may submit.
 *
 * OPTIONAL OUTCOME STEPS (PRODUCT_DECISIONS §2, 2026-10-13). Five exploratory
 * outcome questions follow `experienced`, never precede it. Each can be
 * skipped: `Next` / `Finish` behave as on every other step (disabled until an
 * option is chosen), and an unanswered optional step also offers a separate
 * "Skip" button. A skip is recorded in the draft as `null` (key presence, like
 * comp's "not sure"), so a resumed draft does not land back on it, and it is
 * sent as null.
 *
 * PAST MODE (`subject="past"`, `/environment-report/past`; PRODUCT_DECISIONS
 * §2, 2026-10-01). The same questions about the job before the
 * user's current or most recent one -- one such report per user, only once a
 * current one exists. Always past tense, its own draft key (useEnvReport), and
 * it never builds or changes the Situation Report, so it ends on a thank-you
 * screen here rather than handing off to `/situation-report`. Three gates, each
 * read from the report up front AND from the submit's 409 as a backstop, the
 * same two-layer pattern as `first_job` above: first_job (no role at all),
 * already filed (`past_job_report_filed` / `past_report_limit`) and no current
 * report yet (`current_report_required`).
 */
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { useProfile } from "../../profile";
import { useEnvReport } from "../useEnvReport";
import {
  isCareerStatusNotSet,
  isCurrentReportRequiredRefusal,
  isFirstJobRefusal,
  isPastReportLimitRefusal,
  useSituationReport,
  useSubmitEnvironmentReport,
} from "../useSituationReport";
import type { EnvironmentReportSubmission, SituationReport } from "../useSituationReport";
import { ENV_FORM_STEPS, ENV_ITEMS } from "../data/envQuestions";
import HeroNetworkAnimation from "../../../shared/ui/HeroNetworkAnimation";
import ResumePrompt from "../../../shared/ui/ResumePrompt";
import { firstUnansweredIndex, useResumePrompt } from "../../../shared/lib/resumeDraft";
import type { EnvReportDraft, EnvReportSubject } from "../useEnvReport";
import type { EnvIndustry, EnvOutcomeItemId, EnvStep } from "../data/envQuestions";

/** `work_pulse.situation_items.TENSE_BY_CAREER_STATUS`, client side. Unknown
 *  or unset statuses render present tense -- the common case by far, and the
 *  server's snapshot is what the stored row is labelled with either way. */
function isPastTense(careerStatus: string | undefined): boolean {
  return careerStatus === "between_jobs" || careerStatus === "first_job";
}

type Phase = "intro" | "questions";

/** Whether a report about the CURRENT job is on file. `complete` implies one;
 *  `needs_core` echoes it as `environment` when it exists; and
 *  `needs_environment_report` is, by name, the state without one. */
function hasCurrentReport(report: SituationReport): boolean {
  if (report.state === "complete") return true;
  if (report.state === "needs_core") return report.environment !== null;
  return false;
}

/** Where a past-mode gate or the done screen sends the user back to. */
const PAST_HOME = { path: "/intelligence", label: "Back to your Intelligence Hub →" };

/** Answered = key PRESENCE (see useEnvReport: comp's and industry's "not sure",
 *  and a skipped outcome step, are a stored null). */
function isStepAnswered(draft: EnvReportDraft, step: EnvStep): boolean {
  return step.kind === "dimension"
    ? draft.answers[step.item.itemId] !== undefined
    : Object.prototype.hasOwnProperty.call(draft.context, step.item.itemId);
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative min-h-screen bg-cream-base overflow-hidden">
      <HeroNetworkAnimation theme="light" />
      <div className="relative z-10 mx-auto max-w-2xl px-6 pt-12 pb-16">{children}</div>
    </div>
  );
}

/** A centred card: the frame every past-mode gate and the done screen share. */
function GateCard({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-cream-base flex items-center justify-center px-6">
      <div className="max-w-md w-full rounded-xl border border-cream-muted bg-white px-6 py-8 space-y-4">
        {children}
      </div>
    </div>
  );
}

/** The five optional outcome steps' item ids, in form order. */
const OUTCOME_ITEM_IDS: EnvOutcomeItemId[] = ENV_FORM_STEPS.flatMap((st) =>
  st.kind === "outcome" ? [st.item.itemId] : [],
);

const PRIMARY_BUTTON =
  "w-full bg-forest-dark text-white font-semibold py-3 rounded hover:bg-forest-mid transition-colors";

/** The one screen a `first_job` user ever sees on this route. */
function NoRoleToDescribe({ pastSubject }: { pastSubject: boolean }) {
  const navigate = useNavigate();
  if (pastSubject) {
    return (
      <GateCard>
        <h1 className="font-display text-xl font-semibold text-ink-primary">
          There's no earlier job to describe
        </h1>
        <p className="text-sm text-ink-secondary leading-relaxed">
          This form asks about a job you've held before, and you've told us you're
          heading into your first one. There's nothing to fill in here.
        </p>
        <button type="button" onClick={() => navigate(PAST_HOME.path)} className={PRIMARY_BUTTON}>
          {PAST_HOME.label}
        </button>
      </GateCard>
    );
  }
  return (
    <div className="min-h-screen bg-cream-base flex items-center justify-center px-6">
      <div className="max-w-md w-full rounded-xl border border-cream-muted bg-white px-6 py-8 space-y-4">
        <p className="text-xs font-semibold uppercase tracking-widest text-forest-light">
          Situation Report
        </p>
        <h1 className="font-display text-xl font-semibold text-ink-primary">
          There's no job to describe yet
        </h1>
        <p className="text-sm text-ink-secondary leading-relaxed">
          These questions ask about a role you've held, and you've told us you're
          heading into your first one. So we skip the form rather than ask you to
          invent answers about a job you haven't had.
        </p>
        <button
          type="button"
          onClick={() => navigate("/situation-report")}
          className="w-full bg-forest-dark text-white font-semibold py-3 rounded hover:bg-forest-mid transition-colors"
        >
          Back to your Situation Report →
        </button>
      </div>
    </div>
  );
}

/**
 * The server snapshots `career_status` itself and refuses when it has none to
 * snapshot. Reached only on submit, because the value can be absent from the
 * profile document and still derivable server-side (`derive_career_status`
 * reads experience), so the client cannot decide this up front without
 * duplicating that derivation.
 */
function CareerStatusNeeded({ returnTo }: { returnTo: { path: string; label: string } }) {
  const navigate = useNavigate();
  return (
    <div className="min-h-screen bg-cream-base flex items-center justify-center px-6">
      <div className="max-w-md w-full rounded-xl border border-cream-muted bg-white px-6 py-8 space-y-4">
        <h1 className="font-display text-xl font-semibold text-ink-primary">
          One thing first: where are you right now?
        </h1>
        <p className="text-sm text-ink-secondary leading-relaxed">
          These questions read differently depending on whether you're describing the
          job you're in or the one you most recently left, and we don't have that on
          file yet. Set your career status and come straight back — your answers so
          far are saved.
        </p>
        <button
          type="button"
          onClick={() =>
            navigate("/job-seeker/profile?tab=experience", {
              // returnTo: the profile page offers to bring the user back here
              // once the status is saved (shared/lib/careerStatusReturn).
              state: {
                showCareerStatusModal: true,
                returnTo,
              },
            })
          }
          className="w-full bg-forest-dark text-white font-semibold py-3 rounded hover:bg-forest-mid transition-colors"
        >
          Set your career status →
        </button>
      </div>
    </div>
  );
}

/** Past mode: the user's one past-job report is already on file. */
function PastAlreadyFiled() {
  const navigate = useNavigate();
  return (
    <GateCard>
      <h1 className="font-display text-xl font-semibold text-ink-primary">
        You've already described your earlier job
      </h1>
      <p className="text-sm text-ink-secondary leading-relaxed">
        We only ask about one earlier job, and yours is saved. Thanks for filling it in.
      </p>
      <button type="button" onClick={() => navigate(PAST_HOME.path)} className={PRIMARY_BUTTON}>
        {PAST_HOME.label}
      </button>
    </GateCard>
  );
}

/** Past mode: no report about the current job yet, which has to come first. */
function CurrentReportFirst() {
  const navigate = useNavigate();
  return (
    <GateCard>
      <h1 className="font-display text-xl font-semibold text-ink-primary">
        Start with your current job
      </h1>
      <p className="text-sm text-ink-secondary leading-relaxed">
        Describe your current or most recent job first. Once that's done, you can
        come back and tell us about the one before it.
      </p>
      <button
        type="button"
        onClick={() => navigate("/environment-report")}
        className={PRIMARY_BUTTON}
      >
        Describe your current job →
      </button>
      <button
        type="button"
        onClick={() => navigate(PAST_HOME.path)}
        className="w-full text-sm text-ink-secondary hover:text-ink-primary"
      >
        Not now
      </button>
    </GateCard>
  );
}

/** Past mode's ending. No numbers (D-15) and no hand-off to the Situation
 *  Report: a past report changes nothing there. */
function PastSaved() {
  const navigate = useNavigate();
  return (
    <GateCard>
      <p className="text-xs font-semibold uppercase tracking-widest text-forest-light">
        Saved
      </p>
      <h1 className="font-display text-xl font-semibold text-ink-primary">
        Thanks — your earlier job is saved
      </h1>
      <p className="text-sm text-ink-secondary leading-relaxed">
        This doesn't change your Situation Report. It helps Solverah learn which
        gaps between a person and a job matter most, so the guidance gets better
        for you and for everyone after you.
      </p>
      <button type="button" onClick={() => navigate(PAST_HOME.path)} className={PRIMARY_BUTTON}>
        {PAST_HOME.label}
      </button>
    </GateCard>
  );
}

/** Past mode's intro. */
function PastIntro({ onStart }: { onStart: () => void }) {
  return (
    <div className="space-y-5">
      <p className="text-xs font-semibold uppercase tracking-widest text-forest-light">
        Your earlier job
      </p>
      <h1 className="font-display text-2xl sm:text-3xl font-semibold text-ink-primary">
        Now the job before that one
      </h1>
      <p className="text-sm text-ink-secondary leading-relaxed">
        The same questions you answered about your work, asked about the job before
        your current or most recent one. Twelve about the work, four about the
        setup, and five optional ones at the end. About five minutes.
      </p>
      <p className="text-sm text-ink-secondary leading-relaxed">
        Describe it as it actually was. It won't change your Situation Report — it
        helps Solverah learn which gaps matter most.
      </p>
      <p className="text-xs text-ink-secondary leading-relaxed">
        This is a private working note. Nobody at any employer can see it.{" "}
        <Link to="/trust" className="font-semibold text-forest-dark hover:underline">
          How this works, and what we hold back →
        </Link>
      </p>
      <button
        type="button"
        onClick={onStart}
        className="w-full bg-forest-dark text-white font-semibold py-4 rounded hover:bg-forest-mid transition-colors text-base"
      >
        Start
      </button>
    </div>
  );
}

function Intro({ past, onStart }: { past: boolean; onStart: () => void }) {
  return (
    <div className="space-y-5">
      <p className="text-xs font-semibold uppercase tracking-widest text-forest-light">
        Situation Report
      </p>
      <h1 className="font-display text-2xl sm:text-3xl font-semibold text-ink-primary">
        {past ? "Now the role you left" : "Now the other half — your job"}
      </h1>
      <p className="text-sm text-ink-secondary leading-relaxed">
        {past
          ? "Work Pulse asked how you work. These ask what your most recent role actually offered — how much of the how was yours, what the tempo was, how decisions got made. Twelve questions about the work, plus four about the setup, then five optional ones about how it went. About five minutes."
          : "Work Pulse asked how you work. These ask what your role actually offers — how much of the how is yours, what the tempo is, how decisions get made. Twelve questions about the work, plus four about the setup, then five optional ones about how it's going. About five minutes."}
      </p>
      <p className="text-sm text-ink-secondary leading-relaxed">
        {past
          ? "Describe the role as it actually was, not as the job description had it. Both ends of every question are a legitimate way to organise work — there is no answer here that makes a job a good one, and the report is only useful if it has the real thing to work from."
          : "Describe the job as it actually is, not as it was advertised or as it ought to be. Both ends of every question are a legitimate way to organise work — there is no answer here that makes a job a good one, and the report is only useful if it has the real thing to work from."}
      </p>
      {past && (
        <p className="text-sm text-ink-secondary leading-relaxed">
          Because that role is behind you, your report comes back facing forward —
          what to look for next, rather than what to change where you are.
        </p>
      )}
      <p className="text-xs text-ink-secondary leading-relaxed">
        This is a private working note. Nobody at your employer is told you filled it
        in, and nobody there can see it.{" "}
        <Link to="/trust" className="font-semibold text-forest-dark hover:underline">
          How this works, and what we hold back →
        </Link>
      </p>
      <button
        type="button"
        onClick={onStart}
        className="w-full bg-forest-dark text-white font-semibold py-4 rounded hover:bg-forest-mid transition-colors text-base"
      >
        Start
      </button>
    </div>
  );
}

interface EnvironmentReportPageProps {
  /** Which job the form describes. `past` is `/environment-report/past`. */
  subject?: EnvReportSubject;
}

export default function EnvironmentReportPage({ subject = "current" }: EnvironmentReportPageProps) {
  const navigate = useNavigate();
  const pastSubject = subject === "past";
  const { data: profile } = useProfile();
  const reportQuery = useSituationReport();
  const submitMutation = useSubmitEnvironmentReport();
  const { draft, setAnswer, setContext, reset } = useEnvReport(subject);

  const [phase, setPhase] = useState<Phase>("intro");
  const [stepIndex, setStepIndex] = useState(0);
  // A saved draft gets the shared resume prompt in place of the intro.
  const { showResumePrompt, dismissResumePrompt } = useResumePrompt(
    () => Object.keys(draft.answers).length + Object.keys(draft.context).length > 0
  );
  const draftAnsweredCount = ENV_FORM_STEPS.filter((st) => isStepAnswered(draft, st)).length;

  function handleResume() {
    setStepIndex(firstUnansweredIndex(ENV_FORM_STEPS, (st) => isStepAnswered(draft, st)));
    setPhase("questions");
    dismissResumePrompt();
  }

  function handleStartOver() {
    reset();
    setStepIndex(0);
    setPhase("questions");
    dismissResumePrompt();
  }

  // `ProfileData` is an open `Record<string, unknown>`, so this narrows rather
  // than trusting the index signature.
  const careerStatus =
    typeof profile?.career_status === "string" ? profile.career_status : undefined;
  // A past-job report is about a job that ended, whatever the user's status.
  const past = pastSubject || isPastTense(careerStatus);

  // Gate one: the report says this user cannot submit. Only ever false for
  // `first_job`, and only carried in the state where it is decidable.
  const report = reportQuery.data;
  const blockedByReport =
    report?.state === "needs_environment_report" && !report.can_submit_environment_report;
  // Gate two: the live profile, which is what the server snapshots.
  const blockedByProfile = careerStatus === "first_job";
  // Gate three: the submit itself came back 409.
  const blockedBySubmit = isFirstJobRefusal(submitMutation.error);

  // Past mode's done screen comes before every gate: the successful submit
  // refetches the report, which then says `past_job_report_filed`.
  if (pastSubject && submitMutation.isSuccess) {
    return <PastSaved />;
  }

  if (blockedByReport || blockedByProfile || blockedBySubmit) {
    return <NoRoleToDescribe pastSubject={pastSubject} />;
  }

  if (isCareerStatusNotSet(submitMutation.error)) {
    return (
      <CareerStatusNeeded
        returnTo={
          // The label names where the path actually goes back to: in past mode
          // that is this form about the earlier job, not the Situation Report
          // (which a past report never changes) -- audit 2026-10-02, F7.
          pastSubject
            ? { path: "/environment-report/past", label: "the form about your earlier job" }
            : { path: "/environment-report", label: "your Situation Report" }
        }
      />
    );
  }

  if (pastSubject) {
    if (report?.past_job_report_filed || isPastReportLimitRefusal(submitMutation.error)) {
      return <PastAlreadyFiled />;
    }
    if (
      (report && !hasCurrentReport(report)) ||
      isCurrentReportRequiredRefusal(submitMutation.error)
    ) {
      return <CurrentReportFirst />;
    }
  }

  const step = ENV_FORM_STEPS[stepIndex];
  const total = ENV_FORM_STEPS.length;
  const isLast = stepIndex === total - 1;

  const isAnswered = isStepAnswered(draft, step);
  const isOptional = step.kind === "outcome";

  /** Skipping an optional step records it as decided (null), so a resumed
   *  draft moves past it, then advances like Next. */
  function handleSkip() {
    setContext(step.item.itemId, null);
    handleNext({ [step.item.itemId]: null });
  }

  /** `skipped` carries a skip made this instant: the submit reads it directly
   *  rather than waiting for that state update to land. */
  function handleNext(skipped: Record<string, null> = {}) {
    if (!isLast) {
      setStepIndex((i) => i + 1);
      return;
    }
    const context = { ...draft.context, ...skipped };
    const outcomes = Object.fromEntries(
      OUTCOME_ITEM_IDS.map((id) => [id, (context[id] as number | null | undefined) ?? null]),
    ) as Record<EnvOutcomeItemId, number | null>;
    const body: EnvironmentReportSubmission = {
      answers: Object.fromEntries(
        ENV_ITEMS.map((item) => [item.itemId, draft.answers[item.itemId]]),
      ) as Record<string, string>,
      stage_size: draft.context.stage_size as number,
      comp: (draft.context.comp as number | null | undefined) ?? null,
      industry: (draft.context.industry as EnvIndustry | null | undefined) ?? null,
      experienced: draft.context.experienced as number,
      ...outcomes,
      subject,
    };
    submitMutation.mutate(body, {
      onSuccess: () => {
        reset();
        // Past mode stays here and renders PastSaved; the hook has already
        // invalidated the report so `past_job_report_filed` refreshes.
        if (!pastSubject) navigate("/situation-report");
      },
    });
  }

  // ── Loading the gate ── `isError && isFetching` covers a retry in flight,
  // so "Try again" below doesn't look dead while it resolves.
  if (reportQuery.isLoading || (reportQuery.isError && reportQuery.isFetching)) {
    return (
      <div className="min-h-screen bg-cream-base flex flex-col items-center justify-center gap-4">
        <div className="w-8 h-8 rounded-full border-2 border-forest-light border-t-transparent animate-spin" />
        <p className="text-sm text-ink-secondary">Loading…</p>
      </div>
    );
  }

  // ── The gate failed to load -- see the file header's third gate failure ──
  if (reportQuery.isError) {
    return (
      <div className="min-h-screen bg-cream-base flex items-center justify-center px-6">
        <div className="max-w-sm w-full rounded-lg border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-700">
          <p className="font-medium mb-1">We couldn't load your report right now.</p>
          <p className="text-xs">Please try again in a moment.</p>
          <button
            type="button"
            onClick={() => reportQuery.refetch()}
            className="mt-3 text-xs font-semibold text-red-700 underline"
          >
            Try again
          </button>
        </div>
      </div>
    );
  }

  // ── Submitting ──
  if (submitMutation.isPending) {
    return (
      <div className="min-h-screen bg-cream-base flex flex-col items-center justify-center gap-4">
        <div className="w-8 h-8 rounded-full border-2 border-forest-light border-t-transparent animate-spin" />
        <p className="text-sm text-ink-secondary">
          {pastSubject ? "Saving your answers…" : "Building your Situation Report…"}
        </p>
      </div>
    );
  }

  // ── A saved draft: ask before resuming ──
  if (showResumePrompt && draftAnsweredCount > 0) {
    return (
      <Shell>
        <ResumePrompt
          title={pastSubject ? "Your earlier job" : "Situation Report"}
          answeredCount={draftAnsweredCount}
          total={total}
          onResume={handleResume}
          onStartOver={handleStartOver}
        />
      </Shell>
    );
  }

  // ── Intro ──
  if (phase === "intro") {
    return (
      <Shell>
        {pastSubject ? (
          <PastIntro onStart={() => setPhase("questions")} />
        ) : (
          <Intro past={past} onStart={() => setPhase("questions")} />
        )}
      </Shell>
    );
  }

  // ── Questions ──
  const prompt = past ? step.item.promptPast : step.item.prompt;
  const progressPct = ((stepIndex + 1) / total) * 100;

  return (
    <Shell>
      <div className="space-y-4">
        <p className="text-xs font-semibold uppercase tracking-widest text-forest-light">
          Question {stepIndex + 1} of {total}
        </p>

        <div className="w-full h-1 bg-cream-muted rounded-full overflow-hidden">
          <div
            className="h-full bg-forest-dark transition-all duration-300"
            style={{ width: `${progressPct}%` }}
          />
        </div>

        <h2 className="font-display text-xl sm:text-2xl font-semibold text-ink-primary mt-6">
          {prompt}
        </h2>
        {isOptional && (
          <p className="text-sm text-ink-secondary">
            Optional. Skip any of these you'd rather not answer.
          </p>
        )}

        {/* Rendered in the order authored. Do not sort, do not randomise:
            within each dimension one item runs low-pole-first and one
            high-pole-first, and that alternation is what stops a
            straight-lined answer sheet from landing on an anchor. */}
        <div className="space-y-3 pt-2">
          {step.kind === "dimension"
            ? step.item.options.map((option) => {
                const isSelected = draft.answers[step.item.itemId] === option.key;
                return (
                  <button
                    key={option.key}
                    type="button"
                    role="radio"
                    aria-checked={isSelected}
                    onClick={() => setAnswer(step.item.itemId, option.key)}
                    className={[
                      "w-full text-left px-5 py-3.5 rounded transition-colors text-sm flex items-start justify-between gap-3",
                      isSelected
                        ? "border-2 border-forest-dark bg-forest-pale/90 text-ink-primary font-medium"
                        : "border border-cream-muted bg-white/80 backdrop-blur-sm text-ink-primary hover:border-forest-light",
                    ].join(" ")}
                  >
                    <span className="leading-relaxed">
                      {past ? option.textPast : option.text}
                    </span>
                    {isSelected && (
                      <span
                        className="text-forest-dark text-sm font-bold shrink-0"
                        aria-hidden="true"
                      >
                        ✓
                      </span>
                    )}
                  </button>
                );
              })
            : step.item.options.map((option) => {
                const answered = Object.prototype.hasOwnProperty.call(
                  draft.context,
                  step.item.itemId,
                );
                const isSelected = answered && draft.context[step.item.itemId] === option.value;
                return (
                  <button
                    key={option.value === null ? "not-sure" : option.value}
                    type="button"
                    role="radio"
                    aria-checked={isSelected}
                    onClick={() => setContext(step.item.itemId, option.value)}
                    className={[
                      "w-full text-left px-5 py-3.5 rounded transition-colors text-sm flex items-start justify-between gap-3",
                      isSelected
                        ? "border-2 border-forest-dark bg-forest-pale/90 text-ink-primary font-medium"
                        : "border border-cream-muted bg-white/80 backdrop-blur-sm text-ink-primary hover:border-forest-light",
                    ].join(" ")}
                  >
                    <span className="leading-relaxed">
                      {past ? option.textPast : option.text}
                    </span>
                    {isSelected && (
                      <span
                        className="text-forest-dark text-sm font-bold shrink-0"
                        aria-hidden="true"
                      >
                        ✓
                      </span>
                    )}
                  </button>
                );
              })}
        </div>

        {submitMutation.isError && (
          <p role="alert" className="text-sm text-red-700 pt-2">
            We couldn't save that just now. Your answers are still here — try again.
          </p>
        )}

        <div className="flex items-center justify-between pt-4">
          {stepIndex > 0 ? (
            <button
              type="button"
              onClick={() => setStepIndex((i) => i - 1)}
              className="text-sm text-ink-secondary hover:text-ink-primary"
            >
              ← Back
            </button>
          ) : (
            <div />
          )}
          <div className="flex items-center gap-4">
            {isOptional && !isAnswered && (
              <button
                type="button"
                onClick={handleSkip}
                disabled={submitMutation.isPending}
                className="text-sm text-ink-secondary hover:text-ink-primary"
              >
                Skip
              </button>
            )}
            <button
              type="button"
              onClick={() => handleNext()}
              disabled={!isAnswered || submitMutation.isPending}
              className="bg-forest-dark text-white font-semibold px-8 py-3 rounded hover:bg-forest-mid transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isLast ? "Finish" : "Next"}
            </button>
          </div>
        </div>
      </div>
    </Shell>
  );
}
