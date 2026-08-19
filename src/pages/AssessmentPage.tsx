/**
 * AssessmentPage -- the person-side culture assessment.
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
 * The results screen deliberately does not exist yet. Returning a respondent's six dimension
 * scores hands a retaker a gradient to optimise against and teaches the item-to-dimension
 * mapping the shuffle and interleave exist to hide. Whatever is eventually shown has to be
 * designed against that pressure rather than falling out of the submit response.
 */
import { useNavigate } from "react-router-dom";

import AssessmentStepper from "../components/assessment/AssessmentStepper";
import HeroNetworkAnimation from "../components/HeroNetworkAnimation";
import { useAssessment } from "../hooks/useAssessment";

export default function AssessmentPage() {
  const navigate = useNavigate();
  const {
    items,
    answers,
    loadError,
    submitError,
    submitting,
    setAnswer,
    submit,
  } = useAssessment();

  async function handleComplete() {
    const result = await submit();
    if (result) {
      navigate("/dashboard", { replace: true });
    }
  }

  return (
    <div className="relative min-h-screen bg-cream-base overflow-hidden">
      <HeroNetworkAnimation theme="light" />
      <div className="relative z-10 mx-auto max-w-2xl px-6 pt-12 pb-16">
        <div className="mb-8 space-y-2">
          <h1 className="font-display text-2xl sm:text-3xl font-semibold text-ink-primary">
            How you work
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
            Employers never see your answers or your dimension scores.
          </p>
        </div>

        {loadError && (
          <p role="alert" className="text-sm text-red-700">
            {loadError}
          </p>
        )}

        {!loadError && items === null && (
          <p className="text-sm text-ink-secondary">Loading…</p>
        )}

        {items !== null && items.length > 0 && (
          <AssessmentStepper
            items={items}
            answers={answers}
            onAnswer={setAnswer}
            onComplete={handleComplete}
            submitting={submitting}
            submitError={submitError}
          />
        )}
      </div>
    </div>
  );
}
