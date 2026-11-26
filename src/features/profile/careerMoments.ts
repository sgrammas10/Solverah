/**
 * The first-run "What brings you here?" vocabulary.
 *
 * The ids are stored (`profiles.career_moment`, `CAREER_MOMENTS` in
 * solverah/domain/profile.py, which also holds the CHECK's list) and must not
 * change without a migration. The labels are best-guess copy; Julie owns them
 * and revises on the built product.
 */
import type { CareerStatus } from "./types";

export const CAREER_MOMENT_IDS = [
  "off_at_work",
  "stay_or_go",
  "job_hunting",
  "between_jobs",
  "first_job",
  "curious",
] as const;

export type CareerMoment = (typeof CAREER_MOMENT_IDS)[number];

export interface CareerMomentOption {
  id: CareerMoment;
  label: string;
  /** The status this moment already says; `null` asks the follow-up. Mirrors
   *  the server's mapping, which applies it whatever the client sends. */
  impliedStatus: CareerStatus | null;
}

export const CAREER_MOMENT_OPTIONS: readonly CareerMomentOption[] = [
  { id: "off_at_work", label: "Something's off at work", impliedStatus: "employed" },
  { id: "stay_or_go", label: "Deciding whether to stay or go", impliedStatus: "employed" },
  { id: "job_hunting", label: "Looking for my next role", impliedStatus: null },
  { id: "between_jobs", label: "Between jobs", impliedStatus: "between_jobs" },
  { id: "first_job", label: "Looking for my first job", impliedStatus: "first_job" },
  { id: "curious", label: "Understanding how I work", impliedStatus: null },
];

export const WORKING_NOW_QUESTION = "Are you working right now?";

export const WORKING_NOW_OPTIONS: readonly { status: CareerStatus; label: string }[] = [
  { status: "employed", label: "Yes" },
  { status: "between_jobs", label: "Not right now" },
  { status: "first_job", label: "I haven't had my first job yet" },
];

/** Server-side cap on the own-words answer (`OWN_WORDS_MAX_CHARS`). */
export const OWN_WORDS_MAX_CHARS = 1000;
