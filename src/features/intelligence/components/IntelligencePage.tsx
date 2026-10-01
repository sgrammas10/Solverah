import { useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useWP, useWorkPulseResult } from "../../assessments";
import { useAuth } from "../../auth";
import { useProfileForm } from "../../profile";
import { useProfile } from "../../profile";
import AssessmentsTab from "./AssessmentsTab";
import type { FocusTypeResult } from "../../assessments";
import { useMM } from "../../assessments";
import type { MMResult } from "../../assessments";
import { useManagerPlaybook } from "../../assessments";
import { useSituationReport } from "../../assessments";
import { ApiError } from "../../../shared/api/apiError";

const ECOSYSTEM_STEPS = [
  { label: "Work Pulse Lite" },
  { label: "Work Pulse" },
  { label: "FocusType" },
  { label: "ManagerMatch" },
  { label: "CompanyLens" },
  { label: "Future Path" },
];

export default function IntelligencePage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { state, setCachedResult } = useWP();
  const { formData } = useProfileForm();

  const hasCached = state.cachedResult !== null;

  const { state: mmState } = useMM();
  const playbookQuery = useManagerPlaybook();
  const situationQuery = useSituationReport();

  const { data: profile, isLoading: profileLoading } = useProfile();
  const focusTypeResult = profile?.focus_type_result as FocusTypeResult | undefined;
  const managerMatchResult =
    mmState.cachedResult ?? (profile?.manager_match_result as MMResult | undefined);

  // Manager Decoder card state, driven by the two distinguishable 409 codes
  // GET /me/manager-playbook answers -- see useManagerPlaybook's header.
  const playbookErr = playbookQuery.error;
  const playbookNeedsManagerMatch =
    playbookErr instanceof ApiError && playbookErr.errorFor("manager_match")?.code === "no_manager_match";
  const playbookNeedsProfile =
    playbookErr instanceof ApiError && playbookErr.errorFor("manager_profile")?.code === "no_manager_profile";

  // Situation Report card state. `complete` is the only state with a report to
  // read; `needs_environment_report` is the prompt to describe the job, and it
  // is suppressed for a `first_job` user, who has no role to describe and gets
  // the forward-facing rendering on the report page itself rather than a form
  // prompt they cannot act on. `needs_core` cannot reach here -- this whole
  // block is behind `wp_v2_completed`.
  const situation = situationQuery.data;
  const hasSituationReport = situation?.state === "complete";
  const canDescribeJob =
    situation?.state === "needs_environment_report" && situation.can_submit_environment_report;
  // The one past-job report (PRODUCT_DECISIONS §2, 2026-10-01): offered once
  // the current-job report exists and until the past one is filed. Hidden for
  // a profile now reading `first_job`, which the server would refuse.
  const canDescribePastJob =
    hasSituationReport &&
    !situation.past_job_report_filed &&
    profile?.career_status !== "first_job";

  // The stored result, shared with WorkPulseResultsPage through one query.
  // Disabled while the sessionStorage cache already has the narrative, and
  // until wpl_completed — the gate the hand-rolled effect used to hold. When
  // the flag flips true mid-session (user navigated here mid-submission via
  // the header) the query fires on its own.
  const wpResult = useWorkPulseResult({
    enabled: Boolean(user?.wpl_completed) && !hasCached,
  });
  const result = state.cachedResult ?? wpResult.data ?? null;

  // Keep the sessionStorage cache primed for the other Work Pulse screens,
  // as the hand-rolled fetch did after every server read.
  useEffect(() => {
    if (wpResult.data && !hasCached) {
      setCachedResult(wpResult.data);
    }
    // hasCached/setCachedResult deliberately absent: this runs when a fetch
    // lands, not when the cache it writes to changes underneath it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wpResult.data]);

  // profileLoading joins the existing gate rather than getting its own branch:
  // the FocusType and ManagerMatch cards below render straight off the document,
  // and showing "Start FocusType" to someone who has finished it -- for the one
  // render before the query resolves -- is a worse artefact than a spinner.
  // The document *failing* is not folded in here: useProfile throws it to
  // RouteErrorBoundary, so it cannot arrive as a permanently empty document and
  // draw those cards as "not started" (or fall through to `return null`).
  if (wpResult.isLoading || profileLoading) {
    return (
      <div className="min-h-screen bg-cream-base flex flex-col items-center justify-center gap-4">
        <div className="w-8 h-8 rounded-full border-2 border-forest-light border-t-transparent animate-spin" />
        <p className="text-sm text-ink-secondary">Loading your profile…</p>
      </div>
    );
  }

  if (wpResult.isError) {
    return (
      <div className="min-h-screen bg-cream-base flex items-center justify-center px-6">
        <div className="max-w-sm w-full rounded-lg border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-700">
          <p className="font-medium mb-1">We couldn't load your profile right now.</p>
          <p className="text-xs">Please try again in a moment.</p>
          <button
            type="button"
            onClick={() => wpResult.refetch()}
            className="mt-3 text-xs font-semibold text-red-700 underline"
          >
            Try again
          </button>
        </div>
      </div>
    );
  }

  // Gates on the CURRENT instrument, not the legacy one. Until 2026-09-08 this
  // read `wpl_completed`, which is set only by the retired 12-item Work Pulse.
  // The button below starts `/work-pulse`, which serves the 24-item `core` and
  // sets `wp_v2_completed` -- so finishing it could never satisfy this gate and
  // the hub stayed locked forever, with its own CTA as the only way out. Found
  // by the real-stack E2E walkthrough; the legacy stepper is not mounted on any
  // route, so no user could reach the instrument this used to require.
  if (!user?.wp_v2_completed) {
    return (
      <div className="min-h-screen bg-cream-base flex flex-col items-center justify-center px-6 text-center">
        <div className="max-w-sm space-y-4">
          <h1 className="font-display text-2xl font-semibold text-ink-primary">
            Complete Work Pulse to unlock your profile.
          </h1>
          <p className="text-sm text-ink-secondary leading-relaxed">
            {/* "about 8 minutes" matches WorkPulseBanner, which is where most
                users meet this instrument first. It previously said 4 here and 8
                there, for the same 24 questions. Overstating is the safer of the
                two errors: someone who finishes early is pleased.

                The promise of "a personalized narrative and your work archetype"
                was also removed: that is what the retired 12-item instrument
                produced. `core` is rules-scored and deliberately returns no
                narrative -- see WorkPulsePage's own "nothing to optimize" copy --
                so the sentence described a payoff the flow cannot deliver. */}
            Work Pulse takes about 8 minutes and unlocks your Solverah profile —
            the foundation everything else in the ecosystem builds on.
          </p>
          <button
            type="button"
            onClick={() => navigate("/work-pulse")}
            className="w-full bg-forest-dark text-white font-semibold py-3 rounded hover:bg-forest-mid transition-colors"
          >
            Start Work Pulse
          </button>
        </div>
      </div>
    );
  }

  // NOT `if (!result) return null` any more. `result` is the narrative, which
  // only the retired 12-item instrument produced -- so once the gate above moved
  // to the current instrument, that early return rendered a blank page for every
  // new user: past the lock, but with nothing drawn. The narrative card below is
  // conditional instead, and the rest of the hub (progress, FocusType,
  // ManagerMatch) never depended on `result` at all.

  return (
    <div className="min-h-screen bg-cream-base">
      <div className="mx-auto max-w-3xl px-6 pt-12 pb-20 space-y-8">

        {/* Header */}
        <div className="space-y-1">
          <p className="text-xs font-semibold uppercase tracking-widest text-forest-light">
            Your Intelligence Hub
          </p>
          <h1 className="font-display text-2xl sm:text-3xl font-semibold text-ink-primary">
            Everything we know about how you work.
          </h1>
          <p className="text-sm text-ink-secondary pt-1">
            Your profile grows as you complete more of the Solverah ecosystem.
          </p>
        </div>

        {/* Progress indicator */}
        <div className="flex items-start gap-2 sm:gap-4 overflow-x-auto pb-1">
          {ECOSYSTEM_STEPS.map((step, i) => {
            // `i < 2` used to hard-code the first two steps as done, which put a
            // tick next to "Work Pulse Lite" for users who have never taken it --
            // the retired instrument nothing mounts any more. Step 1 now reflects
            // the flag it names.
            const complete =
              (i === 0 && !!user?.wpl_completed) ||
              (i === 1 && !!user?.wp_v2_completed) ||
              (i === 2 && !!focusTypeResult) ||
              (i === 3 && !!managerMatchResult);
            return (
              <div key={step.label} className="flex flex-col items-center gap-1.5 min-w-[56px]">
                <div
                  className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold shrink-0 ${
                    complete
                      ? "bg-forest-dark text-white"
                      : "bg-cream-muted text-ink-tertiary"
                  }`}
                >
                  {complete ? "✓" : ""}
                </div>
                <span className="text-xs text-ink-secondary text-center leading-tight">
                  {step.label}
                </span>
              </div>
            );
          })}
        </div>

        {/* WorkPulse card — unlocked.

            Two shapes. A legacy user carries a stored narrative and gets the
            archetype and signals below. A user of the current instrument has no
            narrative by design, so they get the completion statement instead of
            an empty card -- the same thing WorkPulsePage tells them on finishing,
            rather than a second place implying something is missing. */}
        {!result ? (
          <div className="rounded-xl border border-forest-light bg-forest-pale px-6 py-6 space-y-3">
            <p className="text-xs font-semibold uppercase tracking-widest text-forest-light">
              ✦ Unlocked · Work Pulse™
            </p>
            <p className="font-display text-2xl font-semibold text-forest-dark">
              Work Pulse complete
            </p>
            <p className="text-sm text-ink-primary leading-relaxed">
              It’s powering your matching in the background. There’s no score to
              check and nothing to optimise — what it learned about how you work
              is already shaping which environments we put in front of you.
            </p>
          </div>
        ) : (
        <div className="rounded-xl border border-forest-light bg-forest-pale px-6 py-6 space-y-4">
          <p className="text-xs font-semibold uppercase tracking-widest text-forest-light">
            ✦ Unlocked · Work Pulse™
          </p>
          <p className="font-display text-2xl font-semibold text-forest-dark">
            {result.archetype}
          </p>
          {result.archetype_description && (
            <p className="text-sm text-ink-primary leading-relaxed">
              {result.archetype_description}
            </p>
          )}
          {result.emerging_signals.length > 0 && (
            <>
              <hr className="border-forest-light/30" />
              <div className="flex flex-wrap gap-2">
                {result.emerging_signals.map((signal) => (
                  <span
                    key={signal.title}
                    className="rounded-full border border-forest-light bg-white px-3 py-1 text-xs font-semibold text-forest-mid"
                  >
                    {signal.title}
                  </span>
                ))}
              </div>
            </>
          )}
          <button
            type="button"
            onClick={() => navigate("/work-pulse/results")}
            className="text-sm font-semibold text-forest-dark hover:underline"
          >
            View full Work Pulse analysis →
          </button>
        </div>
        )}

        {/* Situation Report — BUILD_PLAN A-7.

            The Work Pulse card above used to be a dead end: "complete, and
            there is nothing for you to look at". There is now, because Work
            Pulse is one half of the Situation Report and the other half is a
            form away. This sits under BOTH shapes of that card rather than
            inside the no-narrative branch, so a legacy user carrying a stored
            narrative reaches the report too.

            Silent while the report state is still loading, and silent for a
            `first_job` user: `can_submit_environment_report` is false for them
            and the report page renders forward rather than prompting, so a
            "describe your job" button here would be a prompt they cannot act
            on. */}
        {hasSituationReport && (
          <div className="rounded-xl border border-forest-light bg-forest-pale px-6 py-5 space-y-2">
            <p className="text-xs font-semibold uppercase tracking-widest text-forest-light">
              ✦ Situation Report
            </p>
            <p className="text-sm text-ink-primary leading-relaxed">
              Your Work Pulse and your description of your job, read against each
              other — where the two are set the same way, and where they pull apart.
            </p>
            <button
              type="button"
              onClick={() => navigate("/situation-report")}
              className="text-sm font-semibold text-forest-dark hover:underline"
            >
              View your Situation Report →
            </button>
          </div>
        )}
        {canDescribeJob && (
          <div className="rounded-xl border border-cream-muted bg-white px-6 py-5 space-y-2">
            <p className="text-xs font-semibold uppercase tracking-widest text-forest-light">
              ✦ Situation Report
            </p>
            <p className="text-sm text-ink-primary leading-relaxed">
              Work Pulse knows how you work. What it can’t tell you on its own is how
              far your current job sits from that. Sixteen questions about the role
              close the gap and turn the two halves into your Situation Report.
            </p>
            <button
              type="button"
              onClick={() => navigate("/environment-report")}
              className="bg-forest-dark text-white font-semibold px-4 py-2 rounded text-xs hover:bg-forest-mid"
            >
              Describe your job →
            </button>
          </div>
        )}
        {canDescribePastJob && (
          <div className="rounded-xl border border-cream-muted bg-white px-6 py-5 space-y-2">
            <p className="text-xs font-semibold uppercase tracking-widest text-forest-light">
              ✦ Your earlier job
            </p>
            <p className="text-sm text-ink-primary leading-relaxed">
              Tell us about the job before your current or most recent one. It won’t
              change your Situation Report — it helps Solverah learn which gaps matter
              most. About five minutes.
            </p>
            <button
              type="button"
              onClick={() => navigate("/environment-report/past")}
              className="bg-forest-dark text-white font-semibold px-4 py-2 rounded text-xs hover:bg-forest-mid"
            >
              Describe your earlier job →
            </button>
          </div>
        )}

        {/* Ecosystem cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">

          {/* FocusType — completed */}
          {focusTypeResult ? (
            <div className="rounded-xl border border-forest-light bg-forest-pale px-5 py-5">
              <p className="text-xs font-semibold uppercase tracking-widest text-forest-light mb-1">
                ✦ Unlocked · FocusType™
              </p>
              <p className="font-display text-lg font-semibold text-forest-dark mb-3">
                {focusTypeResult.archetype}
              </p>
              <div className="flex items-center gap-4">
                <button
                  type="button"
                  onClick={() =>
                    navigate("/focus-type/results", {
                      state: { result: focusTypeResult },
                    })
                  }
                  className="text-sm font-semibold text-forest-dark hover:underline"
                >
                  View results →
                </button>
                <button
                  type="button"
                  onClick={() => navigate("/focus-type", { state: { retake: true } })}
                  className="text-xs text-ink-tertiary hover:underline"
                >
                  Retake
                </button>
              </div>
            </div>
          ) : (
            /* FocusType — not started */
            <div className="rounded-xl border border-cream-muted bg-white px-5 py-5">
              <p className="text-sm font-semibold text-ink-primary">FocusType™</p>
              <p className="text-xs text-ink-secondary mt-0.5 mb-2">
                Attention, focus, and energy patterns
              </p>
              <p className="text-xs text-ink-secondary leading-relaxed mb-4">
                Understand how your attention works and which environments protect it.
              </p>
              <button
                type="button"
                onClick={() => navigate("/focus-type")}
                className="bg-forest-dark text-white font-semibold px-3 py-1.5 rounded text-xs hover:bg-forest-mid"
              >
                Start FocusType™ →
              </button>
            </div>
          )}

          {/* ManagerMatch — completed */}
          {managerMatchResult ? (
            <div className="rounded-xl border border-forest-light bg-forest-pale px-5 py-5">
              <p className="text-xs font-semibold uppercase tracking-widest text-forest-light mb-1">
                ✦ Unlocked · ManagerMatch™
              </p>
              <p className="font-display text-lg font-semibold text-forest-dark mb-3">
                {managerMatchResult.archetype}
              </p>
              <div className="flex items-center gap-4">
                <button
                  type="button"
                  onClick={() => navigate("/manager-match/results")}
                  className="text-sm font-semibold text-forest-dark hover:underline"
                >
                  View results →
                </button>
                <button
                  type="button"
                  onClick={() => navigate("/manager-match", { state: { retake: true } })}
                  className="text-xs text-ink-tertiary hover:underline"
                >
                  Retake
                </button>
              </div>
            </div>
          ) : (
            /* ManagerMatch — not started */
            <div className="rounded-xl border border-cream-muted bg-white px-5 py-5">
              <p className="text-sm font-semibold text-ink-primary">ManagerMatch™</p>
              <p className="text-xs text-ink-secondary mt-0.5 mb-2">
                Leadership and management alignment
              </p>
              <p className="text-xs text-ink-secondary leading-relaxed mb-4">
                Discover which management styles bring out your best — and which create friction.
              </p>
              <button
                type="button"
                onClick={() => navigate("/manager-match")}
                className="bg-forest-dark text-white font-semibold px-3 py-1.5 rounded text-xs hover:bg-forest-mid"
              >
                Start ManagerMatch™ →
              </button>
            </div>
          )}

          {/* Manager Decoder — states: view playbook / start / take ManagerMatch
              first, driven by GET /me/manager-playbook's two distinguishable
              409 codes (useManagerPlaybook's header). */}
          {playbookQuery.isLoading ? (
            <div className="rounded-xl border border-cream-muted bg-white px-5 py-5 animate-pulse">
              <div className="h-4 w-32 bg-cream-muted rounded mb-3" />
              <div className="h-3 w-full bg-cream-muted rounded mb-2" />
              <div className="h-3 w-2/3 bg-cream-muted rounded" />
            </div>
          ) : playbookQuery.data ? (
            /* Manager Decoder — playbook ready */
            <div className="rounded-xl border border-forest-light bg-forest-pale px-5 py-5">
              <p className="text-xs font-semibold uppercase tracking-widest text-forest-light mb-1">
                ✦ Unlocked · Manager Decoder
              </p>
              <p className="font-display text-lg font-semibold text-forest-dark mb-3">
                {playbookQuery.data.playbook.grind_count === 0
                  ? "All four dimensions mesh"
                  : `${playbookQuery.data.playbook.grind_count} dimension${playbookQuery.data.playbook.grind_count === 1 ? "" : "s"} to work on`}
              </p>
              <div className="flex items-center gap-4">
                <button
                  type="button"
                  onClick={() => navigate("/manager-profile/playbook")}
                  className="text-sm font-semibold text-forest-dark hover:underline"
                >
                  View your playbook →
                </button>
                <button
                  type="button"
                  onClick={() => navigate("/manager-profile", { state: { retake: true } })}
                  className="text-xs text-ink-tertiary hover:underline"
                >
                  Retake
                </button>
              </div>
            </div>
          ) : playbookNeedsProfile ? (
            /* Manager Decoder — ManagerMatch done, profile not started */
            <div className="rounded-xl border border-cream-muted bg-white px-5 py-5">
              <p className="text-sm font-semibold text-ink-primary">Manager Decoder</p>
              <p className="text-xs text-ink-secondary mt-0.5 mb-2">
                A private playbook for working with your actual manager
              </p>
              <p className="text-xs text-ink-secondary leading-relaxed mb-4">
                Profile how your manager actually works, and we'll diff it against
                your ManagerMatch needs.
              </p>
              <button
                type="button"
                onClick={() => navigate("/manager-profile")}
                className="bg-forest-dark text-white font-semibold px-3 py-1.5 rounded text-xs hover:bg-forest-mid"
              >
                Profile your manager →
              </button>
            </div>
          ) : playbookNeedsManagerMatch ? (
            /* Manager Decoder — ManagerMatch not taken yet */
            <div className="rounded-xl border border-cream-muted bg-white px-5 py-5">
              <p className="text-sm font-semibold text-ink-primary">Manager Decoder</p>
              <p className="text-xs text-ink-secondary mt-0.5 mb-2">
                A private playbook for working with your actual manager
              </p>
              <p className="text-xs text-ink-secondary leading-relaxed mb-4">
                Take ManagerMatch first — the Decoder diffs your manager profile
                against it.
              </p>
              <button
                type="button"
                onClick={() => navigate("/manager-match")}
                className="bg-forest-dark text-white font-semibold px-3 py-1.5 rounded text-xs hover:bg-forest-mid"
              >
                Take ManagerMatch™ →
              </button>
            </div>
          ) : (
            /* Manager Decoder — an unexpected failure, not one of the two
               documented 409s. A real error, not a routing prompt. */
            <div className="rounded-xl border border-cream-muted bg-white px-5 py-5">
              <p className="text-sm font-semibold text-ink-primary">Manager Decoder</p>
              <p className="text-xs text-ink-secondary leading-relaxed mb-4">
                We couldn't check your Manager Decoder status just now.
              </p>
              <button
                type="button"
                onClick={() => playbookQuery.refetch()}
                className="text-xs font-semibold text-forest-dark hover:underline"
              >
                Try again
              </button>
            </div>
          )}

          {/* CompanyLens card — coming soon for everyone.
              Not a gate: ⚑3 (BUILD_PLAN.md §0.2) shelved the core→8-dim
              culture-preferences mapping this depends on, so GET /me/matches
              400s for every current-instrument user regardless of
              wp_v2_completed. There is nothing left for a user to unlock. */}
          <div className="rounded-xl border border-cream-muted bg-white px-5 py-5 opacity-60">
            <p className="text-sm font-semibold text-ink-primary">CompanyLens™</p>
            <p className="text-xs text-ink-secondary mt-0.5 mb-2">
              Company environment and cultural alignment
            </p>
            <p className="text-xs text-ink-secondary leading-relaxed mb-4">
              Our matching model is still being built. Your Work Pulse results
              are already saved and will feed it the moment it's ready.
            </p>
            <button
              type="button"
              disabled
              className="border border-cream-muted text-ink-tertiary text-xs font-semibold px-3 py-1.5 rounded cursor-not-allowed"
            >
              Coming soon
            </button>
          </div>

          {/* Path Intelligence */}
          <div className="rounded-xl border border-cream-muted bg-white px-5 py-5">
            <div className="flex items-center gap-2 mb-1">
              <p className="text-sm font-semibold text-ink-primary">Path Intelligence</p>
              <span className="rounded-full bg-forest-pale border border-forest-light px-2 py-0.5 text-xs font-semibold text-forest-mid">
                Pro · coming soon
              </span>
            </div>
            <p className="text-xs text-ink-secondary mt-0.5 mb-2">
              Career path scoring and guidance
            </p>
            <p className="text-xs text-ink-secondary leading-relaxed mb-4">
              See which career paths best match your skills and profile, with plain-language
              guidance on why each one fits.
            </p>
            <button
              type="button"
              onClick={() => navigate("/intelligence/paths")}
              className="bg-forest-dark text-white font-semibold px-3 py-1.5 rounded text-xs hover:bg-forest-mid transition-colors"
            >
              View Your Paths →
            </button>
          </div>
        </div>

        {/* Assessments section */}
        <AssessmentsTab formData={formData} />

        {/* Hub footer. The one place on this page that explains why the Work
            Pulse card above has no numbers on it — BUILD_PLAN D-3. Kept as a
            quiet footer link rather than a card: it is an answer for the user
            who went looking, not a claim to make on the way past. */}
        <div className="border-t border-cream-muted pt-6">
          <p className="text-xs text-ink-tertiary leading-relaxed">
            No scores here, and that is deliberate.{" "}
            <Link to="/trust" className="font-semibold text-forest-dark hover:underline">
              How this works, and what we hold back →
            </Link>
          </p>
        </div>

      </div>
    </div>
  );
}
