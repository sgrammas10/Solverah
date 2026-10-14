/**
 * Small pieces the CompanyLens list and the company read share: the next-step chip,
 * a flag badge, the must-have marker. Words only, never a number.
 */
import type { NextStep, TraitFlag } from "../useCompanyLens";
import { FLAG_LABELS, NEXT_STEP_LABELS } from "../companyLensCopy";
import { BODY_MUTED, CHIP } from "../lensStyles";

const FLAG_CLASSES: Record<TraitFlag, string> = {
  must_have_break: "border-amber-300 bg-amber-50 text-amber-800",
  risk: "border-amber-200 bg-amber-50/60 text-amber-800",
  investigate: "border-forest-light bg-forest-pale/60 text-forest-dark",
};

interface FlagBadgeProps {
  flag: TraitFlag;
}

export function FlagBadge({ flag }: FlagBadgeProps) {
  return <span className={`${CHIP} ${FLAG_CLASSES[flag]}`}>{FLAG_LABELS[flag]}</span>;
}

export function MustHaveBadge() {
  return (
    <span className={`${CHIP} border-forest-mid/40 bg-white text-forest-dark`}>Must-have</span>
  );
}

interface NextStepChipProps {
  step: NextStep;
  /** Show the server's reason under the chip. */
  withReason?: boolean;
}

export function NextStepChip({ step, withReason = true }: NextStepChipProps) {
  return (
    <div className="space-y-1">
      <p className="flex flex-wrap items-center gap-2">
        <span className="text-[0.8rem] font-semibold uppercase tracking-[0.08em] text-ink-secondary">
          Next step
        </span>
        <span className={`${CHIP} border-forest-dark bg-forest-dark text-white`}>
          {NEXT_STEP_LABELS[step.category] ?? step.category}
        </span>
      </p>
      {withReason && step.reason && <p className={BODY_MUTED}>{step.reason}</p>}
    </div>
  );
}
