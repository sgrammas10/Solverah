/**
 * usePulse.ts -- the Pulse surface's queries and mutations (BUILD_PLAN B-3),
 * over B-2's API (`solverah/api/v1/me.py`, `solverah/schemas/pulse.py`).
 *
 * `GET /me/pulse/next-checkin` is the only source of which three dimensions
 * (plus `experienced`) the client renders next -- the round-robin lives in
 * `work_pulse.pulse_items.dimensions_for_checkin` server-side, and this file
 * has no client copy of it to keep in sync. Render `items` in the order the
 * server sent them; do not sort or re-derive the set.
 *
 * `useSituationReport.ts` is this file's direct precedent: same
 * `fetchWithAuth`-only dependency, same query-key-object shape, same
 * invalidate-the-read-on-write pattern rather than hand-writing the cache.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "../auth";

/** `work_pulse.pulse_items.DIMENSIONS`, client side. */
export type PulseDimension =
  | "fragmentation"
  | "sustainability"
  | "environmental_friction"
  | "recognition_friction"
  | "work_pace";

export interface PulseCheckinItem {
  item_id: string;
  dimension: PulseDimension;
  stem: string;
  low_anchor: string;
  high_anchor: string;
}

export interface PulseOutcomeItem {
  item_id: string;
  stem: string;
  low_anchor: string;
  high_anchor: string;
}

/** `GET /me/pulse/next-checkin`. */
export interface PulseNextCheckin {
  sequence: number;
  version: string;
  items: PulseCheckinItem[];
  experienced_item: PulseOutcomeItem;
}

/** `POST /me/pulse/checkins`'s body. Keys must be exactly the dimensions
 *  `PulseNextCheckin.items` served -- the server refuses (422) any other set. */
export interface PulseCheckinSubmission {
  item_scores: Record<string, number>;
  experienced: number;
}

export interface PulseCheckinRecord {
  id: number;
  taken_at: string | null;
  sequence: number;
  item_scores: Record<string, number>;
  experienced: number;
  version: string;
}

export type PulseEventType = "new_manager" | "reorg" | "remote_change" | "role_change" | "other";

export interface PulseEventRecord {
  id: number;
  at: string | null;
  event_type: PulseEventType;
  note: string | null;
}

export interface PulseHistory {
  checkins: PulseCheckinRecord[];
  events: PulseEventRecord[];
}

/** All four cadences, every one of them user-settable since G21 (2026-09-14)
 *  -- `monthly` is both a menu option and where the anti-nag auto-drop lands a
 *  quiet user (`pulse_settings.USER_SETTABLE_CADENCES`). `PulseSettableCadence`
 *  survives as the alias the settings UI and the PATCH mutation speak, now
 *  that the two sets have converged. */
export type PulseCadence = "weekly" | "biweekly" | "monthly" | "off";
export type PulseSettableCadence = PulseCadence;

/** `GET` and `PATCH /me/pulse/settings` -- one shape, which is load-bearing:
 *  `useUpdatePulseSettings` writes the PATCH echo into the GET's cache slot.
 *  `auto_slowed` distinguishes "the server slowed you down" from "you chose
 *  monthly", and only the first earns the slowdown note. */
export interface PulseSettings {
  cadence: PulseCadence;
  auto_slowed: boolean;
}

export const pulseKeys = {
  all: ["pulse"] as const,
  nextCheckin: () => ["pulse", "nextCheckin"] as const,
  history: (limit?: number) => ["pulse", "history", limit ?? "all"] as const,
  settings: () => ["pulse", "settings"] as const,
};

export function usePulseNextCheckin() {
  const { fetchWithAuth } = useAuth();
  return useQuery({
    queryKey: pulseKeys.nextCheckin(),
    queryFn: () => fetchWithAuth<PulseNextCheckin>("/me/pulse/next-checkin", { method: "GET" }),
  });
}

/**
 * `GET /me/pulse/history`. `limit` bounds check-ins only -- events are never
 * limited server-side (`pulse_service.get_history`'s own contract), which
 * matters here because a "log a change" annotation must stay visible on the
 * trend view even past a bounded check-in window.
 */
export function usePulseHistory(options: { limit?: number } = {}) {
  const { fetchWithAuth } = useAuth();
  const { limit } = options;
  return useQuery({
    queryKey: pulseKeys.history(limit),
    queryFn: () => {
      const query = limit ? `?limit=${limit}` : "";
      return fetchWithAuth<PulseHistory>("/me/pulse/history" + query, {
        method: "GET",
      });
    },
  });
}

/**
 * `POST /me/pulse/checkins`. Invalidates every Pulse read on success: a
 * completed check-in changes the next round-robin sequence (`nextCheckin`)
 * and adds a row (`history`), the same "write invalidates, never hand-writes
 * the cache" call `useSubmitEnvironmentReport` makes.
 */
export function useSubmitPulseCheckin() {
  const { fetchWithAuth } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: PulseCheckinSubmission) =>
      fetchWithAuth<PulseCheckinRecord>("/me/pulse/checkins", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: pulseKeys.all });
    },
  });
}

export interface PulseEventSubmission {
  event_type: PulseEventType;
  note?: string | null;
}

/** `POST /me/pulse/events`. Invalidates `history` -- the trend view's event
 *  annotations read straight from it. */
export function useSubmitPulseEvent() {
  const { fetchWithAuth } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: PulseEventSubmission) =>
      fetchWithAuth<PulseEventRecord>("/me/pulse/events", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: pulseKeys.all });
    },
  });
}

export function usePulseSettings() {
  const { fetchWithAuth } = useAuth();
  return useQuery({
    queryKey: pulseKeys.settings(),
    queryFn: () => fetchWithAuth<PulseSettings>("/me/pulse/settings", { method: "GET" }),
  });
}

/** `PATCH /me/pulse/settings`. `off` is always this one call -- no
 *  confirmation step belongs in front of it (PRODUCT_DECISIONS.md §2). */
export function useUpdatePulseSettings() {
  const { fetchWithAuth } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (cadence: PulseSettableCadence) =>
      fetchWithAuth<PulseSettings>("/me/pulse/settings", {
        method: "PATCH",
        body: JSON.stringify({ cadence }),
      }),
    onSuccess: (result) => {
      queryClient.setQueryData(pulseKeys.settings(), result);
    },
  });
}
