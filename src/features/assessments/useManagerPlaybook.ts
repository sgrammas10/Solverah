/**
 * useManagerPlaybook.ts -- `GET /me/manager-playbook`, as one query.
 *
 * Mirrors `useManagerMatchResult`'s shape, but there is no profile-document
 * tier to check first: `manager_profiles` is its own store (BUILD_PLAN C-3,
 * ruling ⚑4), not folded into the profile document the way
 * `manager_match_result`/`focus_type_result` are. Every consumer reads
 * through this one query.
 *
 * The two 409 states -- no ManagerMatch sitting yet, and a ManagerMatch
 * sitting but no manager-profile sitting yet -- arrive as an `ApiError` with
 * `errors[0].code` set to `"no_manager_match"` or `"no_manager_profile"`
 * respectively (`solverah/services/manager_playbook_service.py`). Both are
 * client errors `shouldRetry` refuses to retry, so they surface immediately
 * rather than after two backoffs, and consumers branch on
 * `error.errorFor(...)?.code` -- never on the message text, which is prose
 * meant for a moment nothing else is checking it (CompanyLensPage.test.tsx's
 * note on why a bare `Error` is the wrong fixture applies here too).
 */
import { useQuery } from "@tanstack/react-query";

import { useAuth } from "../auth";
import { ApiError } from "../../shared/api/apiError";

/** One dimension of the diff (`manager_match.decoder.DimensionVerdict` + content). */
export interface ManagerPlaybookDimensionEntry {
  dimension: "autonomy" | "feedback_style" | "relationship" | "growth_focus";
  user_need: number;
  manager_style: number;
  gap: number;
  classification: "mesh" | "grind";
  direction: "over_supplied" | "under_supplied" | null;
  severity: "notable" | "acute" | null;
  band: "low" | "mid" | "high" | null;
  /** Present on a mesh entry only. */
  note?: string;
  /** Present on a grind entry only. */
  headline?: string;
  why?: string;
  ask?: string;
  agenda?: string[];
  scripts?: string[];
  constraint_note?: string | null;
}

/** `manager_match.decoder.build_playbook`'s output, verbatim. */
export interface ManagerPlaybook {
  privacy_notice: string;
  dimensions: ManagerPlaybookDimensionEntry[];
  priority: string[];
  grind_count: number;
  mesh_count: number;
}

/** The body shape shared by `POST /assessments/manager-profile` (when its
 *  `playbook` is non-null) and `GET /me/manager-playbook`. */
export interface ManagerPlaybookData {
  dimension_scores: Record<string, number>;
  scoring_key: string;
  version: string;
  created_at?: string;
  playbook: ManagerPlaybook;
}

export const managerPlaybookKeys = {
  all: ["managerPlaybook"] as const,
  result: () => ["managerPlaybook", "result"] as const,
};

export function useManagerPlaybook(options: { enabled?: boolean } = {}) {
  const { fetchWithAuth } = useAuth();

  return useQuery({
    queryKey: managerPlaybookKeys.result(),
    queryFn: () => fetchWithAuth<ManagerPlaybookData>("/me/manager-playbook", { method: "GET" }),
    enabled: options.enabled ?? true,
  });
}

/** True when `error` is the 409 this endpoint returns before any ManagerMatch sitting. */
export function isNoManagerMatch(error: unknown): boolean {
  return error instanceof ApiError && error.errorFor("manager_match")?.code === "no_manager_match";
}

/** True when `error` is the 409 this endpoint returns when ManagerMatch is
 *  done but no manager-profile is sitting yet. */
export function isNoManagerProfile(error: unknown): boolean {
  return error instanceof ApiError && error.errorFor("manager_profile")?.code === "no_manager_profile";
}
