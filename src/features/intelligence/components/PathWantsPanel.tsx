/**
 * PathWantsPanel — "what should change about your job" (W-5, design doc §8.3).
 *
 * The user's own occupation, in their own O*NET tasks and four measured work
 * conditions, each answerable *less · fine · more*. The answers steer all three
 * paths; the panel itself renders no ranking and no score.
 *
 * ── IT NEVER STANDS BETWEEN THE USER AND A RESULT ──────────────────────────
 *
 * ⚑7's lesson, applied a second time: a step before any value is friction and
 * most people skip it. So:
 *
 *   · the page above renders its suggestions whether this panel has loaded,
 *     failed, or been ignored — nothing here is awaited by anything;
 *   · a failed `GET /me/path-wants` renders NOTHING. Not an error, not a retry
 *     link, not an empty box. A panel nobody asked for does not get to report
 *     its own outage on a page that is working;
 *   · `no_anchor` (no current job) renders nothing at all, by design — taps
 *     alone steer that user's page;
 *   · collapsed by default, one row, and answering none of it is a valid
 *     answer. No progress meter, no required field, no wizard.
 *
 * ── ONE SAVE, NOT ONE PER CLICK ────────────────────────────────────────────
 *
 * Every answer is local until "Update my suggestions". A write drops the
 * server's cached shortlist and the re-score takes seconds (the narrator runs
 * 1.4–6.7 s), so saving per radio would re-score a dozen times while somebody
 * works down one screen. The button is disabled until something has actually
 * changed, and "Clear my answers" goes through the same single save.
 *
 * ── COPY ───────────────────────────────────────────────────────────────────
 *
 * Every string here is a best guess. Julie owns the wording and revises it on
 * the built product; the tests select controls by role and by `data-want`,
 * never by their prose, so a copy edit cannot redden the suite.
 */
import { useEffect, useId, useState } from "react";

import {
  usePathWants,
  type WantKind,
  type WantVerdict,
} from "../usePathWants";

export interface PathWantsPanelProps {
  /**
   * A save landed and the suggestion cache has been dropped. The page answers
   * this with its own `fetchSuggestions()` — the existing enqueue-and-poll
   * flow, the same one a cache miss uses. This panel starts no job of its own.
   */
  onSaved: () => void;
  /** True while the page's scoring job is in flight. */
  rescoring?: boolean;
}

/** The three-way choice. `null` is "fine", and is stored as no answer at all. */
const CHOICES: ReadonlyArray<{ value: WantVerdict | null; label: string }> = [
  { value: "less", label: "Less of this" },
  { value: null, label: "Fine as it is" },
  { value: "more", label: "More of this" },
];

function choiceId(verdict: WantVerdict | null): string {
  return verdict ?? "fine";
}

interface WantRowProps {
  kind: WantKind;
  itemKey: string;
  label: string;
  verdict: WantVerdict | null;
  disabled: boolean;
  onChange: (kind: WantKind, key: string, verdict: WantVerdict | null) => void;
}

/**
 * One row: a real radio group, so the browser gives it arrow-key navigation,
 * one tab stop and a group name, and we give it none of those by hand.
 *
 * The inputs are `sr-only` and the pill is styled off `peer-checked`, which
 * keeps the look of the card's verdict controls without replacing the control:
 * an `sr-only` input is focusable, announced, and reachable by keyboard.
 */
function WantRow({ kind, itemKey, label, verdict, disabled, onChange }: WantRowProps) {
  const group = `want-${kind}-${itemKey}`;

  return (
    <fieldset className="border-0 p-0 m-0" data-want={group}>
      <legend className="text-sm text-ink-primary leading-relaxed mb-2 p-0">{label}</legend>
      {/* Wraps rather than scrolls: at 360 px the three options stack under the
          label instead of running off the side of the screen. */}
      <div className="flex flex-wrap gap-2">
        {CHOICES.map((choice) => {
          const active = verdict === choice.value;
          return (
            <label key={choiceId(choice.value)} className="cursor-pointer">
              <input
                type="radio"
                name={group}
                value={choiceId(choice.value)}
                checked={active}
                disabled={disabled}
                onChange={() => onChange(kind, itemKey, choice.value)}
                className="sr-only peer"
              />
              <span
                className={[
                  "block rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors",
                  "border-cream-muted text-ink-secondary hover:bg-cream-base",
                  "peer-checked:border-forest-mid peer-checked:bg-forest-pale peer-checked:text-forest-mid",
                  "peer-focus-visible:ring-2 peer-focus-visible:ring-forest-light",
                  disabled ? "opacity-60 cursor-not-allowed" : "",
                ].join(" ")}
              >
                {choice.label}
              </span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

export default function PathWantsPanel({ onSaved, rescoring = false }: PathWantsPanelProps) {
  const bodyId = useId();
  const [expanded, setExpanded] = useState(false);
  // True between a landed save and the re-score finishing, so the button can
  // keep saying what is happening. Kept here rather than read off `rescoring`
  // alone: the page is also "loading" on a first visit, and the button must not
  // claim to be re-sorting something the user never asked it to.
  const [awaitingRescore, setAwaitingRescore] = useState(false);

  const wants = usePathWants({
    onSaved: () => {
      setAwaitingRescore(true);
      onSaved();
    },
  });

  useEffect(() => {
    if (!rescoring && awaitingRescore) setAwaitingRescore(false);
  }, [rescoring, awaitingRescore]);

  const { status, anchor, tasks, conditions, answeredCount, changedCount } = wants;

  // Quiet in every one of these: loading, a refused GET, no current job. The
  // page has already rendered the suggestions and owes the user nothing here.
  if (wants.loading || wants.unavailable) return null;
  if (status === null || status === "no_anchor") return null;

  // `unavailable` is the task sidecar missing. The four conditions are names in
  // code and stay answerable, so the panel asks them — and says nothing about
  // the tasks it cannot offer. An apology would be a worse row than no row.
  const showTasks = status === "ok" && tasks.length > 0;
  if (!showTasks && conditions.length === 0) return null;

  const busy = wants.saving || awaitingRescore;
  // "About your work: Software Developers", not "...as a Software Developers":
  // `anchor.title` is the O*NET title and O*NET titles are plural ("Chefs and
  // Head Cooks"), so no article reads correctly in front of one.
  const heading = anchor ? `About your work: ${anchor.title}` : "About your work";
  const summary =
    answeredCount === 1 ? "1 thing you want to change" : `${answeredCount} things you want to change`;

  return (
    <section className="rounded-xl border border-cream-muted bg-white">
      <h2 className="sr-only">What should change about your job</h2>

      <button
        type="button"
        aria-expanded={expanded}
        aria-controls={bodyId}
        onClick={() => setExpanded((open) => !open)}
        className="w-full flex items-center justify-between gap-4 px-5 py-4 text-left rounded-xl focus:outline-none focus-visible:ring-2 focus-visible:ring-forest-light"
      >
        <span className="block space-y-0.5">
          <span className="block text-sm font-semibold text-ink-primary">
            Tell us what should change about your job, and we'll re-sort these
          </span>
          {answeredCount > 0 && (
            <span className="block text-xs text-ink-secondary">{summary}</span>
          )}
        </span>
        <span aria-hidden="true" className="shrink-0 text-xs font-semibold text-forest-mid">
          {expanded ? "Hide" : "Open"}
        </span>
      </button>

      {/* Rendered always and hidden when collapsed, so `aria-controls` points at
          something real. `hidden` keeps it out of the accessibility tree and out
          of the tab order — it is not merely invisible. */}
      <div id={bodyId} hidden={!expanded} className="border-t border-cream-muted px-5 py-5 space-y-6">
        <div className="space-y-1">
          {/* Not `font-display text-lg`: that pair is the suggestion card's
              title, and the page's test helper reads the cards off it. */}
          <p className="font-display text-base font-semibold text-ink-primary">{heading}</p>
          <p className="text-xs text-ink-secondary leading-relaxed">
            Mark anything you'd like more or less of. Answer as many or as few as you like —
            leaving something as it is tells us nothing is wrong with it.
          </p>
        </div>

        {showTasks && (
          <div className="space-y-5">
            <h3 className="text-xs font-semibold uppercase tracking-widest text-forest-light">
              What you spend your time on
            </h3>
            {tasks.map((task) => (
              <WantRow
                key={task.key}
                kind="task"
                itemKey={task.key}
                label={task.label}
                verdict={wants.verdictFor("task", task.key)}
                disabled={busy}
                onChange={wants.setVerdict}
              />
            ))}
          </div>
        )}

        {conditions.length > 0 && (
          <div className="space-y-5">
            <h3 className="text-xs font-semibold uppercase tracking-widest text-forest-light">
              How you work
            </h3>
            {conditions.map((condition) => (
              <WantRow
                key={condition.axis}
                kind="condition"
                itemKey={condition.axis}
                label={condition.label}
                verdict={wants.verdictFor("condition", condition.axis)}
                disabled={busy}
                onChange={wants.setVerdict}
              />
            ))}
          </div>
        )}

        {wants.saveError && (
          <div
            role="alert"
            className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-xs text-red-700"
          >
            {wants.saveError}
          </div>
        )}

        <div className="flex flex-wrap items-center gap-3 border-t border-cream-muted pt-4">
          <button
            type="button"
            data-wants-save
            aria-busy={busy}
            disabled={changedCount === 0 || busy || rescoring}
            onClick={wants.save}
            className="bg-forest-dark text-white font-semibold px-4 py-2 rounded text-sm hover:bg-forest-mid transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {busy ? "Re-sorting your paths…" : "Update my suggestions"}
          </button>

          {answeredCount > 0 && (
            <button
              type="button"
              data-wants-clear
              disabled={busy}
              onClick={wants.clearAll}
              className="text-xs font-semibold text-forest-mid underline hover:text-forest-dark transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
            >
              Clear my answers
            </button>
          )}
        </div>
      </div>
    </section>
  );
}
