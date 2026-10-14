/**
 * Words for CompanyLens. Best-guess copy; Julie revises on the built product.
 *
 * Words only. The API sends no probability, score or percentage and nothing here
 * makes one: direction is a phrase, tolerance is "inside/outside your give", and
 * the only numbers are coverage counts ("4 of 6") and dates.
 *
 * Direction convention (the server's, restated): `more` means the company offers
 * more of the trait than you prefer -- further toward the HIGH pole; `less` means
 * further toward the LOW pole; `even` means the two agree. (This is
 * `match_core.fit_gap`'s sign, gap = person - env, already turned into a word by
 * the server; the page never sees the gap.)
 */
import type { components } from "../../shared/api/schema";

type Schemas = components["schemas"];
type Direction = NonNullable<Schemas["TraitReadSummary"]["direction"]>;
type TraitFlag = NonNullable<Schemas["TraitReadSummary"]["flag"]>;
type NextStepCategory = Schemas["NextStep"]["category"];
type TraitKey = Schemas["TraitReadSummary"]["dimension"];

/** The poles a phrase needs. Every trait read on the wire carries both. */
export interface Poles {
  low_pole: string;
  high_pole: string;
}

/**
 * "More on the fast side than you prefer". Phrased around the pole rather than as
 * "more fast" / "less fast" because several poles are phrases ("invent what does
 * not"), which do not take "more" or "less" in front of them.
 */
export function directionPhrase(direction: Direction | null | undefined, poles: Poles): string {
  if (direction === "more") return `More on the ${poles.high_pole} side than you prefer`;
  if (direction === "less") return `More on the ${poles.low_pole} side than you prefer`;
  if (direction === "even") return "About where you prefer";
  return "";
}

/** Tolerance, in the same word the trait-preferences step uses for it. */
export function toleranceWord(within: boolean | null | undefined): string {
  if (within === true) return "inside your give";
  if (within === false) return "outside your give";
  return "";
}

/** One trait read as a single line: direction, then tolerance. */
export function knownReadLine(
  read: Poles & { direction?: Direction | null; within_tolerance?: boolean | null },
): string {
  const direction = directionPhrase(read.direction, read);
  if (read.direction === "even" || read.within_tolerance == null) return direction;
  return `${direction}, ${toleranceWord(read.within_tolerance)}`;
}

export const STATUS_LINES: Record<"mixed" | "unknown", string> = {
  mixed: "The evidence disagrees",
  unknown: "Not enough evidence yet",
};

export const FLAG_LABELS: Record<TraitFlag, string> = {
  must_have_break: "Must-have outside your give",
  risk: "Must-have at risk",
  investigate: "Must-have to find out about",
};

export const NEXT_STEP_LABELS: Record<NextStepCategory, string> = {
  decide: "Decide",
  investigate: "Investigate",
  prepare: "Prepare",
  explore: "Explore",
  act: "Act",
  dont_act_yet: "Don't act yet",
};

/** Our own trait names, used where the wire gives only a key (`missing`). */
export const TRAIT_NAMES: Record<TraitKey, string> = {
  autonomy: "Autonomy",
  pace: "Pace",
  collaboration: "Collaboration",
  feedback: "Feedback",
  innovation: "Innovation",
  decision: "Decision basis",
};

export function traitName(key: TraitKey): string {
  return TRAIT_NAMES[key] ?? key;
}

/** "Autonomy, Pace and Feedback". */
export function joinNames(names: string[]): string {
  if (names.length <= 1) return names.join("");
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

/**
 * "Based on 4 of 6 traits". Mixed traits count: they are read (both ends) and the
 * ranking uses the worse end. Unknown traits do not.
 */
export function coverageLine(coverage: Schemas["CoverageCounts"]): string {
  return `Based on ${coverage.known + coverage.mixed} of ${coverage.total} traits`;
}

/** The breakdown under the coverage line. Empty parts are left out. */
export function coverageDetail(coverage: Schemas["CoverageCounts"]): string {
  const parts: string[] = [];
  if (coverage.known > 0) parts.push(`${coverage.known} clear`);
  if (coverage.mixed > 0) parts.push(`${coverage.mixed} where the evidence disagrees`);
  if (coverage.unknown > 0) parts.push(`${coverage.unknown} with too little evidence`);
  return parts.join(", ");
}

/** "1 must-have outside your give", "2 to find out about". Zero counts are left out. */
export function flagCountLines(flags: Schemas["FlagCounts"]): string[] {
  const lines: string[] = [];
  if (flags.must_have_breaks > 0) {
    lines.push(
      flags.must_have_breaks === 1
        ? "1 must-have outside your give"
        : `${flags.must_have_breaks} must-haves outside your give`,
    );
  }
  if (flags.risks > 0) {
    lines.push(flags.risks === 1 ? "1 must-have at risk" : `${flags.risks} must-haves at risk`);
  }
  if (flags.investigate > 0) {
    lines.push(`${flags.investigate} to find out about`);
  }
  return lines;
}

export const SOURCE_TYPE_LABELS: Record<string, string> = {
  careers_page: "Careers page",
  employee_review: "Employee review",
  job_posting: "Job posting",
  first_person: "First-person account",
  news: "News",
  disclosure: "Public disclosure",
  user_pasted_posting: "Your pasted posting",
};

export function sourceTypeLabel(sourceType: string): string {
  return SOURCE_TYPE_LABELS[sourceType] ?? sourceType.replace(/_/g, " ");
}

/** "Mar 2025". Dates are the one other number the page shows. */
export function formatMonth(iso: string | null | undefined): string {
  if (!iso) return "";
  const date = new Date(iso.length === 10 ? `${iso}T00:00:00` : iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString(undefined, { year: "numeric", month: "short" });
}

/** "Mar 2023 to Sep 2025", or one month when both ends agree. */
export function dateRange(first: string | null | undefined, last: string | null | undefined): string {
  const a = formatMonth(first);
  const b = formatMonth(last);
  if (a && b && a !== b) return `${a} to ${b}`;
  return a || b;
}

/** A full calendar date for "You took this job on ...". */
export function formatDay(iso: string): string {
  const date = new Date(iso.length === 10 ? `${iso}T00:00:00` : iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

/**
 * The posting-vs-company line for one trait. Both directions are relative to the
 * user, so their order says which way the posting leans: less < even < more.
 * When both lean the same way the server still calls them far apart, but which is
 * further cannot be told from words alone, so the line says only that they differ.
 */
export function disagreementPhrase(
  label: string,
  company: Direction | null | undefined,
  posting: Direction | null | undefined,
  poles: Poles,
): string {
  const order: Record<Direction, number> = { less: 0, even: 1, more: 2 };
  if (company && posting && order[posting] !== order[company]) {
    const pole = order[posting] > order[company] ? poles.high_pole : poles.low_pole;
    return `This posting describes ${label.toLowerCase()} as more on the ${pole} side than the company evidence does.`;
  }
  return `This posting and the company evidence describe ${label.toLowerCase()} differently.`;
}
