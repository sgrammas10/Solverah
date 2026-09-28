/**
 * Words and class strings shared by the Situation Report's pieces.
 *
 * Words only, never numbers (D-15): magnitude is one of three bucket words and
 * direction one of two phrases. See SituationReportPage.tsx's header.
 */
import type { SituationDimensionEntry } from "../../useSituationReport";

const DIMENSION_LABELS: Record<string, string> = {
  autonomy: "Autonomy",
  pace: "Pace",
  collaboration: "Collaboration",
  feedback: "Feedback",
  innovation: "Innovation",
  decision: "Decision-making",
};

/** Magnitude, as words. Never a number, never a bar. */
export const BUCKET_LABELS: Record<SituationDimensionEntry["bucket"], string> = {
  straining: "Straining",
  notable: "Notable",
  aligned: "Aligned",
};

/** Direction, as a phrase. Past tense where the role is behind the reader. */
export function directionLabel(direction: "under" | "over", past: boolean): string {
  if (direction === "under") return past ? "Less than you needed" : "Less than you need";
  return past ? "More than you needed" : "More than you need";
}

export function dimensionLabel(dimension: string): string {
  return DIMENSION_LABELS[dimension] ?? dimension;
}

/** "A", "A and B", "A, B and C". */
export function joinNames(names: string[]): string {
  if (names.length <= 1) return names.join("");
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

/** A calendar date, never a raw ISO string (digits are fine here; it is
 *  score-shaped digits -- decimals, percentages -- the no-digits guard forbids). */
export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    year: "numeric", month: "short", day: "numeric",
  });
}

/** Section heading inside the report (h2). */
export const REPORT_H2 =
  "font-headline text-[1.3rem] font-bold leading-tight tracking-[-0.01em] text-ink-primary";

/** Body text inside panels. */
export const BODY = "text-[0.98rem] leading-[1.65] text-ink-primary";
export const BODY_MUTED = "text-[0.95rem] leading-[1.6] text-ink-secondary";

/** A quiet in-text action link. */
export const TEXT_LINK =
  "font-semibold text-forest-dark underline decoration-forest-light/50 underline-offset-4 transition-colors hover:decoration-forest-dark focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-light";

/** Small bordered button for in-page controls (toggles, retries). */
export const QUIET_BUTTON =
  "inline-flex items-center gap-2 rounded-[4px] border border-cream-muted bg-white px-3.5 py-2 text-[0.9rem] font-semibold text-forest-dark transition-colors hover:border-forest-light hover:bg-forest-pale/40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-light disabled:cursor-not-allowed disabled:opacity-50";

/** A plain white panel. */
export const PANEL = "rounded-[6px] border border-cream-muted bg-white";
