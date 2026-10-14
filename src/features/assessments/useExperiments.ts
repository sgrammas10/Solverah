/**
 * useExperiments.ts -- condition experiments (BUILD_PLAN B-5), over
 * `GET|POST /me/experiments` and `POST /me/experiments/{id}/abandon`
 * (`solverah/api/v1/me.py`, `solverah/schemas/experiments.py`).
 *
 * Same conventions as `useSituationReport.ts`/`usePulse.ts`: `fetchWithAuth`
 * only, a query-key-object, invalidate-on-write rather than hand-writing the
 * cache.
 *
 * `dimension`/`direction` here are `work_pulse.situation`'s short vocabulary
 * -- the same one a `StrainDimensionEntry` already carries -- so starting an
 * experiment from the report page needs no re-encoding of the pair a cell is
 * already keyed on.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "../auth";
import { ApiError } from "../../shared/api/apiError";
import type { SituationDimension, SituationDirection } from "./useSituationReport";

/** `work_pulse.experiments.compute_readout`'s output. Never a delta or a
 *  mean -- see that module's docstring. */
export interface ExperimentReadout {
  verdict: "not_enough_data" | "moved_up" | "moved_down" | "about_the_same";
  before_count: number;
  after_count: number;
}

/** One experiment, as every one of the three routes below returns it. */
export interface Experiment {
  id: number;
  dimension: SituationDimension;
  direction: SituationDirection;
  started_at: string;
  ends_at: string;
  /** The stored fact. `completed` is written once `ends_at` has passed
   *  (2026-10-02), so an ended experiment never blocks the next start. */
  status: "active" | "completed" | "abandoned";
  abandoned_at: string | null;
  /** Derived server-side on every read -- never stored. */
  phase: "running" | "ended" | "abandoned";
  /** The cell's own name, resolved from `work_pulse.situation_content`. */
  experiment_name: string;
  readout: ExperimentReadout;
}

export interface ExperimentStartBody {
  dimension: SituationDimension;
  direction: SituationDirection;
}

export const experimentKeys = {
  all: ["experiments"] as const,
  list: () => ["experiments", "list"] as const,
};

export function useExperiments() {
  const { fetchWithAuth } = useAuth();
  return useQuery({
    queryKey: experimentKeys.list(),
    queryFn: () =>
      fetchWithAuth<{ experiments: Experiment[] }>("/me/experiments", { method: "GET" }),
  });
}

/** `POST /me/experiments`. Refuses 409 when one is already running -- see
 *  {@link isExperimentAlreadyActive}. */
export function useStartExperiment() {
  const { fetchWithAuth } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ExperimentStartBody) =>
      fetchWithAuth<Experiment>("/me/experiments", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: experimentKeys.all });
    },
    onError: (error) => {
      // A 409 means the server knows of a running experiment this page's
      // list does not (started in another tab, say). Refetch so the cells
      // show that experiment instead of a button that can only fail again.
      if (isExperimentAlreadyActive(error)) {
        queryClient.invalidateQueries({ queryKey: experimentKeys.all });
      }
    },
  });
}

/** `POST /me/experiments/{id}/abandon`. Idempotent -- a second click is a
 *  200 with the row unchanged, never an error. */
export function useAbandonExperiment() {
  const { fetchWithAuth } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (experimentId: number) =>
      fetchWithAuth<Experiment>(`/me/experiments/${experimentId}/abandon`, {
        method: "POST",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: experimentKeys.all });
    },
  });
}

/** True when `error` is the 409 `useStartExperiment` gets while one is
 *  already running. Branch on this, never on the message text. */
export function isExperimentAlreadyActive(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    error.errorFor("experiment")?.code === "experiment_already_active"
  );
}
