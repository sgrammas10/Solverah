/**
 * useSituationReport.ts -- `GET /me/situation-report`, as one query, plus the
 * two writes that surround it (BUILD_PLAN A-5 / A-7).
 *
 * THE PAYLOAD IS A DISCRIMINATED UNION AND THE TYPES SAY SO. The server's
 * pydantic model is deliberately open (`extra="allow"`) because the shape
 * genuinely varies by `state` -- `needs_core` carries `environment`,
 * `needs_environment_report` carries `can_submit_environment_report`, and
 * `complete` carries `dimensions`, `career_status`, `needs_forward` and
 * `guidance_notice`. Flattening all of that into optional fields on one
 * interface would let a component read `dimensions` in a state that never has
 * them and typecheck. The union makes `state` the thing you have to narrow on
 * first, which is exactly the order the page renders in.
 *
 * D-15, ON THE CLIENT SIDE OF THE WIRE. `env_score` is the only number the
 * server sends per dimension, and it is an echo of the user's own answer about
 * their own job -- there is no person-side score, no numeric gap and no
 * magnitude in this payload, by construction. It is typed here because it
 * arrives, and `SituationReportPage` renders it nowhere: buckets and
 * directions become words and layout, never digits, bars, meters or
 * percentages. A future consumer that wants to draw a gauge has to break the
 * report's own rule to do it, not merely reach for a field.
 *
 * THE 409s. `POST /me/environment-report` refuses a `first_job` caller with
 * `errors[0].code === "first_job_no_role"`; `POST
 * /me/situation-report/recalibrate` refuses a caller with no core sitting with
 * `errors[0].code === "no_core_sitting"`. Both are branched on by code and
 * never by the prose in `error.message` -- see `useManagerPlaybook`'s header
 * for the precedent and the reason.
 *
 * THE PAST-JOB REPORT (PRODUCT_DECISIONS §2, 2026-10-01). The same submit with
 * `subject: "past"` files the user's one report about the job before their
 * current or most recent one. It never changes this report beyond the
 * `past_job_report_filed` flag every state carries, and its refusals are 409s
 * coded `first_job_no_role`, `current_report_required` or `past_report_limit`.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "../auth";
import { ApiError } from "../../shared/api/apiError";
import type { PulseEventType } from "./usePulse";
import type { EnvIndustry } from "./data/envQuestions";
import type { EnvReportSubject } from "./useEnvReport";

/** The six model dimensions, as the server names them. */
export type SituationDimension =
  | "autonomy"
  | "pace"
  | "collaboration"
  | "feedback"
  | "innovation"
  | "decision";

/** Magnitude only, since the 2026-09-10 rename (PRODUCT_DECISIONS §2). */
export type SituationBucket = "aligned" | "notable" | "straining";

/** Sign, carried separately from magnitude. `null` on an aligned dimension. */
export type SituationDirection = "under" | "over";

export type SituationRegister = "change_in_place" | "negotiate" | "rarely_moves";

/** `work_pulse.situation_content.ChangeInPlaceCell`. In the needs-forward
 *  rendering the server sends `signal` alone -- the rest of the cell describes
 *  a job the reader no longer holds. */
export interface ChangeInPlaceCell {
  experiment_name?: string;
  experiment?: string;
  steps?: string[];
  signal: string;
}

/** `work_pulse.situation_content.NegotiateCell`. Absent entirely in the
 *  needs-forward rendering. */
export interface NegotiateCell {
  who_and_where: string;
  opening: string;
  scripts: string[];
  if_no: string;
}

/** `work_pulse.situation_content.RarelyMovesCell`. Carried over unchanged in
 *  both renderings. */
export interface RarelyMovesCell {
  why_fixed: string;
  cost_of_staying: string;
  what_it_implies: string;
}

export interface SituationRegisters {
  change_in_place?: ChangeInPlaceCell;
  negotiate?: NegotiateCell;
  rarely_moves?: RarelyMovesCell;
}

/** A dimension the gap engine bucketed `aligned`: one note, no direction, no
 *  registers. Dropped entirely from the needs-forward rendering -- an
 *  alignment does not survive the move (`aligned_note_for`'s docstring). */
export interface AlignedDimensionEntry {
  dimension: SituationDimension;
  env_score: number;
  bucket: "aligned";
  direction: null;
  rank: number;
  aligned_note: string;
}

/** A dimension the gap engine bucketed `notable` or `straining`. */
export interface StrainDimensionEntry {
  dimension: SituationDimension;
  env_score: number;
  bucket: "notable" | "straining";
  direction: SituationDirection;
  rank: number;
  diagnosis: { headline: string; text: string };
  registers: SituationRegisters;
  defers_to_decoder: boolean;
  decoder_crossref: string | null;
}

export type SituationDimensionEntry = AlignedDimensionEntry | StrainDimensionEntry;

/** Present on every state. */
export interface SituationManagerSection {
  has_profile: boolean;
}

/** Fields every state carries. */
interface SituationReportCommon {
  manager: SituationManagerSection;
  /** Whether the user's one past-job environment report exists. The wire
   *  sends it in every state. */
  past_job_report_filed: boolean;
}

/** One Pulse life/work event logged after the environment report's own
 *  `submitted_at` (BUILD_PLAN B-4) -- `type` and `date` only, never `note`:
 *  `pulse_events.note` is free text a user typed, and D-15 holds here the same
 *  as everywhere else in this payload. Newest first, matching
 *  `pulse_store.pulse_events_in_range`'s order. */
export interface SituationReportEventSinceReport {
  type: PulseEventType;
  date: string;
}

/** No completed `core` sitting yet. An already-submitted environment report is
 *  echoed as bare dimension scores -- there is nothing to diff it against. */
export interface SituationNeedsCore extends SituationReportCommon {
  state: "needs_core";
  environment: {
    dimensions: Array<{ dimension: SituationDimension; env_score: number }>;
    career_status: string;
    submitted_at: string;
  } | null;
  /** Present (true) only when a Work Pulse sitting exists but the one this
   *  report is pinned to can't be read -- so the page says "we couldn't read
   *  it" rather than "you haven't taken it". Retaking Work Pulse is still the
   *  way back. */
  core_unreadable?: boolean;
}

/** Core done, no environment report. `can_submit_environment_report` is false
 *  for a `first_job` user, who has no role to describe and never sees the
 *  form. */
export interface SituationNeedsEnvironmentReport extends SituationReportCommon {
  state: "needs_environment_report";
  can_submit_environment_report: boolean;
}

/** Both halves in hand. `needs_forward` is true when the pinned
 *  `career_status` snapshot is past-tense, and the server has already sliced
 *  the payload accordingly: aligned rows dropped, `change_in_place` reduced to
 *  its signal, `negotiate` and `decoder_crossref` suppressed. */
export interface SituationComplete extends SituationReportCommon {
  state: "complete";
  career_status: string;
  needs_forward: boolean;
  dimensions: SituationDimensionEntry[];
  guidance_notice: string;
  /** BUILD_PLAN B-4. Empty when nothing has happened since this report was
   *  filed -- that is the common case, and it is what keeps the resubmission
   *  banner from ever nagging. */
  events_since_report: SituationReportEventSinceReport[];
  /** True when the user's LIVE career status now reads in a different tense
   *  from the snapshot this report was filed under (e.g. employed -> between
   *  jobs). The report is NOT re-sliced; the page only asks them to describe
   *  the job again. The server always sends it in `complete`; optional here so
   *  fixtures written before it existed still type-check. */
  career_status_changed?: boolean;
}

export type SituationReport =
  | SituationNeedsCore
  | SituationNeedsEnvironmentReport
  | SituationComplete;

/** Narrowing helper -- `aligned` is the only bucket without guidance. */
export function isAlignedEntry(
  entry: SituationDimensionEntry,
): entry is AlignedDimensionEntry {
  return entry.bucket === "aligned";
}

/** `POST /me/environment-report`'s body. */
export interface EnvironmentReportSubmission {
  answers: Record<string, string>;
  stage_size: number;
  /** `null` is the deliberate "not sure" answer, never a missing one. */
  comp: number | null;
  /** A level key, or `null` for "not sure / rather not say". */
  industry: EnvIndustry | null;
  experienced: number;
  /** Which job this describes; the server defaults a missing one to current. */
  subject: EnvReportSubject;
}

/** `POST /me/environment-report`'s response -- an echo of the user's own
 *  description of their job, with no gap yet computed. */
export interface EnvironmentReportSubmitResponse {
  dimension_scores: Record<string, number>;
  stage_size: number;
  comp: number | null;
  industry: EnvIndustry | null;
  experienced: number;
  career_status: string;
  version: string;
  subject: EnvReportSubject;
}

export const situationReportKeys = {
  all: ["situationReport"] as const,
  report: () => ["situationReport", "report"] as const,
};

export function useSituationReport(options: { enabled?: boolean } = {}) {
  const { fetchWithAuth } = useAuth();

  return useQuery({
    queryKey: situationReportKeys.report(),
    queryFn: () => fetchWithAuth<SituationReport>("/me/situation-report", { method: "GET" }),
    enabled: options.enabled ?? true,
  });
}

/**
 * `POST /me/environment-report`.
 *
 * Invalidates the report on success rather than writing the submit response
 * into its cache: the submit response is the environment echo, and the report
 * is the gap -- two different shapes, and the second is not derivable from the
 * first without the person-side snapshot the client has never seen and must
 * not.
 */
export function useSubmitEnvironmentReport() {
  const { fetchWithAuth } = useAuth();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (body: EnvironmentReportSubmission) =>
      fetchWithAuth<EnvironmentReportSubmitResponse>("/me/environment-report", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: situationReportKeys.all });
    },
  });
}

/**
 * `POST /me/situation-report/recalibrate` -- ⚑5's explicit, logged re-pin.
 *
 * `recalibrated: false` is a success, not a failure: it means the report was
 * already pinned to the latest completed core sitting and nothing was written.
 */
export function useRecalibrateSituationReport() {
  const { fetchWithAuth } = useAuth();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () =>
      fetchWithAuth<{ recalibrated: boolean }>("/me/situation-report/recalibrate", {
        method: "POST",
      }),
    onSuccess: (result) => {
      if (result.recalibrated) {
        queryClient.invalidateQueries({ queryKey: situationReportKeys.all });
      }
    },
  });
}

/** True when `error` is the 409 a `first_job` caller gets from the environment
 *  form. Branch on this, never on the message text. */
export function isFirstJobRefusal(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    error.errorFor("career_status")?.code === "first_job_no_role"
  );
}

/** True when a past-job submit was refused because no current-job report
 *  exists yet. */
export function isCurrentReportRequiredRefusal(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    error.errorFor("subject")?.code === "current_report_required"
  );
}

/** True when a past-job submit was refused because the user's one past-job
 *  report is already filed. */
export function isPastReportLimitRefusal(error: unknown): boolean {
  return error instanceof ApiError && error.errorFor("subject")?.code === "past_report_limit";
}

/** True when `error` is the 409 recalibrate returns before any core sitting. */
export function isNoCoreSittingRefusal(error: unknown): boolean {
  return error instanceof ApiError && error.errorFor("core")?.code === "no_core_sitting";
}

/**
 * True when the submit was refused because the caller has no `career_status`
 * set, which the server needs in order to snapshot the row.
 *
 * Branched on the MESSAGE, unlike every other error in this file, and that is
 * the wire's fault rather than a shortcut: `submit_environment_report` returns
 * this one through the legacy `{"error": ...}` shape, which carries no
 * `errors[]` and therefore no code to read. `PathIntelligencePage` matches the
 * identical string for the identical condition. If that route is ever
 * converted to problem+json, this should follow it and stop matching prose.
 */
export function isCareerStatusNotSet(error: unknown): boolean {
  return error instanceof ApiError && error.message === "career_status_not_set";
}
