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
