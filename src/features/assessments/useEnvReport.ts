/**
 * useEnvReport -- in-progress state for the environment-side instrument.
 *
 * `useMP`'s shape, with one difference that matters: this instrument has two
 * kinds of answer. The twelve dimension items store an option KEY ("a".."e"),
 * because the server owns the key -> pole -> score mapping and the client must
 * never learn it. The four context items and the five optional outcome items
 * store a RAW value (1..5, or a level key for `industry`), which is itself the
 * answer
 * (`work_pulse.situation_items.context_value` / `context_level` are
 * pass-throughs with a guard, deliberately).
 *
 * `comp` can legitimately be answered `null` -- the "not sure" option, which
 * exists because a forced 1..5 guess at your own market rate is wrong in a
 * non-random direction (PRODUCT_DECISIONS §2, 2026-09-10). `industry` has the
 * same kind of option ("not sure, or I'd rather not say", 2026-10-01). So
 * "answered" is key PRESENCE in `context`, never a truthiness or null check:
 * an unanswered item is a missing key and an answered one may hold `null`.
 * A skipped optional outcome item is stored the same way, as `null`.
 *
 * sessionStorage, like `useMP`, so a mid-form reload does not throw
 * twenty-one answers away. Nothing here is a durable record -- the append-only row the
 * server writes on submit is.
 *
 * ONE DRAFT PER SUBJECT. The current-job form and the past-job form
 * (`/environment-report/past`, PRODUCT_DECISIONS §2, 2026-10-01) ask the same
 * questions about two different jobs, so they keep separate keys: a
 * half-finished description of one job must never resume as the other.
 */
import { useState } from "react";

export type EnvReportSubject = "current" | "past";

/** The current-job key predates the past form and is kept as-is, so a draft
 *  saved before this change still resumes. */
export const ENV_REPORT_DRAFT_KEYS: Record<EnvReportSubject, string> = {
  current: "env_report_answers",
  past: "env_report_answers_past",
};

export interface EnvReportDraft {
  /** dimension item id -> chosen option key. */
  answers: Record<string, string>;
  /** context or outcome item id -> raw 1..5 (or industry's level key), or
   *  null for comp's / industry's "not sure" or a skipped outcome item. */
  context: Record<string, number | string | null>;
}

const EMPTY: EnvReportDraft = { answers: {}, context: {} };

function readDraft(storageKey: string): EnvReportDraft {
  try {
    const raw = sessionStorage.getItem(storageKey);
    if (!raw) return EMPTY;
    const parsed = JSON.parse(raw) as Partial<EnvReportDraft>;
    return {
      answers: parsed.answers ?? {},
      context: parsed.context ?? {},
    };
  } catch {
    return EMPTY;
  }
}

function persist(storageKey: string, draft: EnvReportDraft) {
  try {
    sessionStorage.setItem(storageKey, JSON.stringify(draft));
  } catch {
    // A full or disabled sessionStorage costs the reload-resume convenience
    // and nothing else -- the draft still lives in React state.
  }
}

export function useEnvReport(subject: EnvReportSubject = "current") {
  const storageKey = ENV_REPORT_DRAFT_KEYS[subject];
  const [draft, setDraft] = useState<EnvReportDraft>(() => readDraft(storageKey));

  function setAnswer(itemId: string, optionKey: string) {
    setDraft((prev) => {
      const next = { ...prev, answers: { ...prev.answers, [itemId]: optionKey } };
      persist(storageKey, next);
      return next;
    });
  }

  function setContext(itemId: string, value: number | string | null) {
    setDraft((prev) => {
      const next = { ...prev, context: { ...prev.context, [itemId]: value } };
      persist(storageKey, next);
      return next;
    });
  }

  function reset() {
    setDraft(EMPTY);
    try {
      sessionStorage.removeItem(storageKey);
    } catch {
      // Same trade as `persist`.
    }
  }

  return { draft, setAnswer, setContext, reset };
}
