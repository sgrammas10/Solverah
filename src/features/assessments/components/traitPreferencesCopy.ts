/**
 * Words for the tolerance and must-have step (TraitPreferencesStep). Kept apart from
 * the component so the component file exports only components (fast refresh).
 * Best-guess copy; Julie revises on the built product.
 */
import type { ToleranceSteps, TraitKey } from "../useTraitPreferences";

export const TRAIT_COPY: Record<TraitKey, { label: string; description: string }> = {
  autonomy: {
    label: "Autonomy",
    description: "How much say you have over how, and in what order, your work gets done.",
  },
  pace: {
    label: "Pace",
    description: "How fast the work moves and how quickly things are expected to happen.",
  },
  collaboration: {
    label: "Collaboration",
    description: "How much of the work happens together with other people rather than on your own.",
  },
  feedback: {
    label: "Feedback",
    description: "How often, and how directly, you hear how your work is landing.",
  },
  innovation: {
    label: "Innovation",
    description:
      "How much of the work is building new things and taking bets, rather than improving what exists.",
  },
  decision: {
    label: "Decision-making",
    description:
      "How much decisions rest on numbers and evidence, rather than judgement and experience.",
  },
};

export const TOLERANCE_OPTIONS: { steps: ToleranceSteps; label: string }[] = [
  { steps: 0, label: "Not at all" },
  { steps: 1, label: "A little is fine" },
  { steps: 2, label: "A lot is fine" },
];

/** Shown on the retake page only: the first-time step counts for its own sitting.
 *
 *  Must stay true for BOTH cases of the tolerance pin (situation_report_service, "THE
 *  TOLERANCE PIN", D-15): a report that has no tolerance answers yet takes the first
 *  ones saved at once (the answer that belongs to the pinned sitting), and any later
 *  change waits until a newer Work Pulse sitting and the report's Re-read move the pin.
 *  The old line ("picks them up the next time you re-read it against a new Work
 *  Pulse") was wrong for a first answer (G49). */
export const RETAKE_SITTING_NOTE =
  "Changes show up in CompanyLens right away. Your Situation Report takes the first answers you save here straight away, then holds them steady: a later change reaches it only after you retake Work Pulse and re-read the report.";

/** Shown on /work-pulse after a successful Save, from the step or from
 *  /trait-preferences (G48). Cancel and "Skip for now" show nothing. */
export const TRAIT_PREFERENCES_SAVED_MESSAGE =
  "Saved. Your answers on how much give you have on each area are in.";
