/**
 * usePathWants.ts — the "what should change about your job" panel (W-5).
 *
 *   GET /me/path-wants   the panel for the user's own occupation, plus the
 *                        answers they have already given on it
 *   PUT /me/path-wants   the answers that changed; returns the whole panel
 *
 * ── THE PANEL NEVER STANDS BETWEEN THE USER AND A RESULT ────────────────────
 *
 * Design doc §8.3, and ⚑7's lesson applied a second time: a step before any
 * value is friction and most people skip it. So the GET is its own query, never
 * awaited by the page, and every failure it can have is silent — the page
 * renders exactly the suggestions it renders today whether this query is in
 * flight, refused or never asked. Nothing here reaches `stateForFailure`, which
 * is the mapping for failures that are allowed to take the screen.
 *
 * ── `retry: false`, DELIBERATELY ───────────────────────────────────────────
 *
 * The client default retries a 429 or a 5xx twice (`shouldRetry`). That is
 * wrong here for a reason that is not about latency: `GET` and `PUT
 * /me/path-wants` share one 20/min bucket, so a silent panel quietly spending
 * three of the user's twenty on a page load it does not block is spending them
 * on behalf of the save it will refuse later. A failed panel is simply not
 * offered this page load.
 *
 * ── EDITS ARE LOCAL UNTIL THE USER PRESSES THE BUTTON ──────────────────────
 *
 * A save re-scores (the write drops `path_cache`, so the next job re-ranks) and
 * the narrator takes 1.4–6.7 s. Writing per click would re-score a dozen times
 * while somebody works down one screen. So `draft` holds what changed and the
 * one `PUT` carries only that — partial bodies are the expected case on this
 * route, not an optimisation.
 *
 * `draft` is kept pruned to genuine differences from the server's answers: a
 * user who marks "more" and then puts it back to "fine" has changed nothing,
 * and the button must go back to disabled rather than send a no-op write.
 *
 * ── THE SAVE DOES NOT RE-RANK; IT ASKS THE PAGE TO ─────────────────────────
 *
 * `PUT /me/path-wants` deliberately returns the panel rather than a shortlist.
 * The re-score is the page's existing enqueue-and-poll flow, unchanged: the
 * mutation invalidates the suggestion-job cache and calls `onSaved`, and the
 * page answers it with the same `fetchSuggestions()` that a cache miss, a
 * preferences change and the retry button already call. There is no second job
 * flow here, and there must not be.
 */
import { useCallback, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "../auth";
import type { components } from "../../shared/api/schema";
import { pathWantsMessage, isStalePanel } from "./pathFailure";
import { pathSuggestionJobKeys } from "./usePathSuggestionJob";

/**
 * The wire types come from the generated schema rather than being re-declared,
 * the way `usePathFeedback` takes `PathFeedbackResponse` and `PathFitResponse`.
 * The two unions below are the narrower client-side reading of two fields the
 * generator types as bare `string`, exactly as `types.ts` narrows
 * `career_status`.
 */
export type PathWants = components["schemas"]["PathWantsResponse"];
export type PathWantAnchor = components["schemas"]["PathWantAnchor"];
export type PathWantTask = components["schemas"]["PathWantTask"];
export type PathWantCondition = components["schemas"]["PathWantCondition"];
export type PathWantAnswer = components["schemas"]["PathWantAnswer"];

/** A task row or a condition row. Both are answered the same way. */
export type WantKind = "task" | "condition";

/** The two things a user can say. "Fine" is the absence of an answer. */
export type WantVerdict = "more" | "less";

/**
 * `ok` the panel can be shown · `no_anchor` no current job, so there is no
 * panel at all · `unavailable` the task sidecar is missing, so the conditions
 * half still works and the task half is empty.
 */
export type PathWantsStatus = "ok" | "no_anchor" | "unavailable";

export const pathWantsKeys = {
  all: ["pathWants"] as const,
  panel: () => ["pathWants", "panel"] as const,
};

/** A draft is keyed by kind and key together: a task and a condition could in
 *  principle collide on a key, and the PUT needs both halves anyway. */
function itemId(kind: WantKind, key: string): string {
  return `${kind}:${key}`;
}

/** `GET /me/path-wants`. Silent on every failure — see the header. */
export function usePathWantsPanel(options: { enabled?: boolean } = {}) {
  const { user, fetchWithAuth } = useAuth();

  return useQuery({
    queryKey: pathWantsKeys.panel(),
    queryFn: () => fetchWithAuth<PathWants>("/me/path-wants", { method: "GET" }),
    enabled: (options.enabled ?? true) && Boolean(user),
    retry: false,
    // A failed panel is a panel that is not offered, not a screen. Routing it
    // to the route error boundary would be the exact friction ⚑7 forbids.
    throwOnError: false,
  });
}

/**
 * `PUT /me/path-wants` — store the named answers, get the whole panel back.
 *
 * The response goes straight into the panel query's cache rather than
 * triggering a refetch: it is the same shape a GET serves, which is why the
 * route returns it (`PathWantsResponse`'s docstring).
 */
export function useSavePathWants() {
  const { fetchWithAuth } = useAuth();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (answers: PathWantAnswer[]) =>
      fetchWithAuth<PathWants>("/me/path-wants", {
        method: "PUT",
        body: JSON.stringify({ answers }),
      }),
    onSuccess: (panel) => {
      queryClient.setQueryData(pathWantsKeys.panel(), panel);
      // The write dropped the server's cached shortlist; this drops the client's
      // memory of the job that produced it, so nothing stale can be shown while
      // the page enqueues the next one.
      queryClient.invalidateQueries({ queryKey: pathSuggestionJobKeys.all });
    },
  });
}

export interface UsePathWantsOptions {
  /** Whether to ask for the panel at all. */
  enabled?: boolean;
  /**
   * Called once a save has landed and the suggestion cache has been dropped.
   * The page answers it with its own `fetchSuggestions()` — the existing
   * enqueue-and-poll flow, not a second one.
   */
  onSaved?: () => void;
}

export interface UsePathWantsResult {
  /** Null while the panel is unknown: loading, or a failure we stay quiet about. */
  status: PathWantsStatus | null;
  anchor: PathWantAnchor | null;
  tasks: PathWantTask[];
  conditions: PathWantCondition[];
  loading: boolean;
  /** The GET failed. The panel renders nothing; the page is unaffected. */
  unavailable: boolean;
  /** The standing answer for one row — the draft if it has one, else the server's. */
  verdictFor: (kind: WantKind, key: string) => WantVerdict | null;
  setVerdict: (kind: WantKind, key: string, verdict: WantVerdict | null) => void;
  /** How many rows carry an answer right now, drafts included. */
  answeredCount: number;
  /** How many rows differ from what the server has stored. */
  changedCount: number;
  saving: boolean;
  /** Plain-words copy for a refused save, or null. */
  saveError: string | null;
  /** Send the difference. No-op when there is none. */
  save: () => void;
  /** Clear every answer, through the same one save. */
  clearAll: () => void;
}

/**
 * The panel's whole state: the server's copy, the user's unsaved edits, and the
 * one save that reconciles them.
 */
export function usePathWants(options: UsePathWantsOptions = {}): UsePathWantsResult {
  const { enabled = true, onSaved } = options;
  const queryClient = useQueryClient();
  const panel = usePathWantsPanel({ enabled });
  const savePanel = useSavePathWants();

  const [draft, setDraft] = useState<Record<string, WantVerdict | null>>({});
  const [saveError, setSaveError] = useState<string | null>(null);

  const data = panel.data ?? null;
  const tasks = useMemo(() => data?.tasks ?? [], [data]);
  const conditions = useMemo(() => data?.conditions ?? [], [data]);

  /** Every answerable row as `(kind, key, the server's verdict)`. */
  const rows = useMemo(
    () => [
      ...tasks.map((task) => ({
        kind: "task" as const,
        key: task.key,
        stored: (task.verdict ?? null) as WantVerdict | null,
      })),
      ...conditions.map((condition) => ({
        kind: "condition" as const,
        key: condition.axis,
        stored: (condition.verdict ?? null) as WantVerdict | null,
      })),
    ],
    [tasks, conditions],
  );

  const storedById = useMemo(() => {
    const out: Record<string, WantVerdict | null> = {};
    for (const row of rows) out[itemId(row.kind, row.key)] = row.stored;
    return out;
  }, [rows]);

  const verdictFor = useCallback(
    (kind: WantKind, key: string): WantVerdict | null => {
      const id = itemId(kind, key);
      return id in draft ? draft[id] : storedById[id] ?? null;
    },
    [draft, storedById],
  );

  const setVerdict = useCallback(
    (kind: WantKind, key: string, verdict: WantVerdict | null) => {
      const id = itemId(kind, key);
      setSaveError(null);
      setDraft((previous) => {
        const next = { ...previous };
        // Pruned, not recorded: a row put back to what the server already has
        // is not a change, and leaving it in would arm the save button over a
        // body that writes nothing.
        if ((storedById[id] ?? null) === verdict) delete next[id];
        else next[id] = verdict;
        return next;
      });
    },
    [storedById],
  );

  const answeredCount = useMemo(
    () => rows.filter((row) => verdictFor(row.kind, row.key) !== null).length,
    [rows, verdictFor],
  );

  const changedCount = Object.keys(draft).length;

  const send = useCallback(
    (answers: PathWantAnswer[]) => {
      if (answers.length === 0) return;
      setSaveError(null);
      savePanel.mutate(answers, {
        onSuccess: () => {
          setDraft({});
          onSaved?.();
        },
        onError: (error) => {
          setSaveError(pathWantsMessage(error).text);
          if (isStalePanel(error)) {
            // The panel on screen is about a job this user no longer holds, and
            // nothing was written. Throw the edits away and reload the panel:
            // re-sending them could only be refused again.
            setDraft({});
            queryClient.invalidateQueries({ queryKey: pathWantsKeys.all });
          }
        },
      });
    },
    [savePanel, onSaved, queryClient],
  );

  const save = useCallback(() => {
    const answers: PathWantAnswer[] = Object.entries(draft).map(([id, verdict]) => {
      const separator = id.indexOf(":");
      return {
        kind: id.slice(0, separator),
        key: id.slice(separator + 1),
        verdict,
      };
    });
    send(answers);
  }, [draft, send]);

  const clearAll = useCallback(() => {
    const answers: PathWantAnswer[] = rows
      .filter((row) => verdictFor(row.kind, row.key) !== null)
      .map((row) => ({ kind: row.kind, key: row.key, verdict: null }));
    send(answers);
  }, [rows, verdictFor, send]);

  return {
    status: (data?.status as PathWantsStatus | undefined) ?? null,
    anchor: data?.anchor ?? null,
    tasks,
    conditions,
    loading: panel.isLoading,
    unavailable: panel.isError,
    verdictFor,
    setVerdict,
    answeredCount,
    changedCount,
    saving: savePanel.isPending,
    saveError,
    save,
    clearAll,
  };
}
