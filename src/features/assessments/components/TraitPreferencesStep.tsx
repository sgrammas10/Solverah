/**
 * TraitPreferencesStep -- per-trait tolerance and must-have, the short step after
 * Work Pulse (six-trait match model, PRODUCT_DECISIONS.md §2, 2026-10-13).
 *
 * For each of the six traits the user says how much MORE and how much LESS of it than
 * they prefer a job could give and still be fine (not at all / a little / a lot ->
 * 0 / 1 / 2 steps), and may mark up to two as must-haves. Mounted on /work-pulse right
 * after a core sitting is saved, and on its own at /trait-preferences for a retake.
 *
 * SKIPPING WRITES NOTHING. A user who skips stays unanswered, which the server reads as
 * "behave exactly as before this step existed". Nothing here is pre-selected for the
 * same reason: a pre-filled "a little is fine" would be a default tolerance the user
 * never chose.
 *
 * WHY THE USER'S OWN POSITION IS NOT SHOWN. The brief asked for each trait's current
 * position in plain words. That is a person-side score on the wire, which D-15 rules
 * out (no person-side score, even as words, reaches the client: it gives a retaker
 * something to steer by). Each trait is described instead, and the questions are
 * framed against "what you prefer". Open question for Sebastian; see the C1 report.
 *
 * Copy is a best guess; Julie revises on the built product.
 */
import { useState } from "react";

import {
  MAX_MUST_HAVES,
  TRAIT_KEYS,
  useSaveTraitPreferences,
  useTraitPreferences,
} from "../useTraitPreferences";
import { TOLERANCE_OPTIONS, TRAIT_COPY } from "./traitPreferencesCopy";
import type {
  ToleranceSteps,
  TraitKey,
  TraitPreferenceInput,
  TraitPreferencesDocument,
} from "../useTraitPreferences";

export const SAVE_ERROR_MESSAGE =
  "We couldn't save these. Your choices are still here, so please try again.";

interface TraitDraft {
  over?: ToleranceSteps;
  under?: ToleranceSteps;
  mustHave: boolean;
}

type Draft = Record<TraitKey, TraitDraft>;

function draftFrom(doc: TraitPreferencesDocument | undefined): Draft {
  const draft = Object.fromEntries(
    TRAIT_KEYS.map((key) => [key, { mustHave: false }])
  ) as Draft;
  if (!doc?.answered) return draft;
  for (const entry of doc.traits) {
    draft[entry.dimension_key] = {
      over: (entry.over_steps ?? undefined) as ToleranceSteps | undefined,
      under: (entry.under_steps ?? undefined) as ToleranceSteps | undefined,
      mustHave: entry.must_have,
    };
  }
  return draft;
}

export interface TraitPreferencesStepProps {
  /** Called after a successful save, or when the user skips. */
  onFinished: (outcome: "saved" | "skipped") => void;
  /** The secondary button's label. "Skip for now" after Work Pulse; the retake page
   *  says "Cancel", since leaving there keeps whatever was saved before. */
  skipLabel?: string;
}

export default function TraitPreferencesStep({
  onFinished,
  skipLabel = "Skip for now",
}: TraitPreferencesStepProps) {
  const current = useTraitPreferences();

  if (current.isPending) {
    return <p className="text-sm text-ink-secondary">Loading…</p>;
  }
  // A failed read still lets the user answer from blank: the step must never stand
  // between them and the rest of the product.
  return (
    <TraitPreferencesForm
      initial={current.data}
      onFinished={onFinished}
      skipLabel={skipLabel}
    />
  );
}

interface TraitPreferencesFormProps {
  initial: TraitPreferencesDocument | undefined;
  onFinished: (outcome: "saved" | "skipped") => void;
  skipLabel: string;
}

function TraitPreferencesForm({ initial, onFinished, skipLabel }: TraitPreferencesFormProps) {
  const [draft, setDraft] = useState<Draft>(() => draftFrom(initial));
  const save = useSaveTraitPreferences();

  const mustHaveCount = TRAIT_KEYS.filter((key) => draft[key].mustHave).length;
  const complete = TRAIT_KEYS.every(
    (key) => draft[key].over !== undefined && draft[key].under !== undefined
  );

  function update(key: TraitKey, patch: Partial<TraitDraft>) {
    setDraft((prev) => ({ ...prev, [key]: { ...prev[key], ...patch } }));
  }

  function handleSave() {
    if (!complete) return;
    const traits: TraitPreferenceInput[] = TRAIT_KEYS.map((key) => ({
      dimension_key: key,
      under_steps: draft[key].under as ToleranceSteps,
      over_steps: draft[key].over as ToleranceSteps,
      must_have: draft[key].mustHave,
    }));
    save.mutate(traits, { onSuccess: () => onFinished("saved") });
  }

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h2 className="font-display text-xl sm:text-2xl font-semibold text-ink-primary">
          How much give is there?
        </h2>
        <p className="text-sm text-ink-secondary">
          No job matches what you prefer exactly. For each of the six areas Work Pulse
          covers, tell us how far a job could drift from what you prefer, in either
          direction, and still be fine. Then mark up to {MAX_MUST_HAVES} you won't bend on.
        </p>
        <p className="text-xs text-ink-secondary">
          Optional, and you can change it any time. Employers never see these answers.
        </p>
      </div>

      {TRAIT_KEYS.map((key) => {
        const copy = TRAIT_COPY[key];
        const value = draft[key];
        const mustHaveLocked = !value.mustHave && mustHaveCount >= MAX_MUST_HAVES;
        return (
          <section
            key={key}
            aria-labelledby={`trait-${key}-label`}
            className="rounded-lg border border-cream-muted bg-white/60 px-4 py-4 space-y-3"
          >
            <div>
              <h3 id={`trait-${key}-label`} className="font-semibold text-ink-primary">
                {copy.label}
              </h3>
              <p className="text-sm text-ink-secondary">{copy.description}</p>
            </div>
            <ToleranceQuestion
              name={`${key}-over`}
              legend="If your job had more of this than you prefer"
              value={value.over}
              onChange={(steps) => update(key, { over: steps })}
            />
            <ToleranceQuestion
              name={`${key}-under`}
              legend="If your job had less of this than you prefer"
              value={value.under}
              onChange={(steps) => update(key, { under: steps })}
            />
            <label
              className={`flex items-center gap-2 text-sm ${
                mustHaveLocked ? "text-ink-secondary opacity-60" : "text-ink-primary"
              }`}
            >
              <input
                type="checkbox"
                checked={value.mustHave}
                disabled={mustHaveLocked}
                onChange={(e) => update(key, { mustHave: e.target.checked })}
              />
              {copy.label} is a must-have for me
            </label>
          </section>
        );
      })}

      <p className="text-xs text-ink-secondary" aria-live="polite">
        {mustHaveCount >= MAX_MUST_HAVES
          ? `You've picked ${MAX_MUST_HAVES} must-haves, the most you can choose. Untick one to pick another.`
          : `Must-haves picked: ${mustHaveCount} of ${MAX_MUST_HAVES}.`}
      </p>

      {save.isError && (
        <p role="alert" className="text-sm text-red-700">
          {SAVE_ERROR_MESSAGE}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={handleSave}
          disabled={!complete || save.isPending}
          className="inline-flex items-center bg-forest-dark text-white text-sm font-semibold px-6 py-3 rounded hover:bg-forest-mid transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {save.isPending ? "Saving…" : "Save"}
        </button>
        <button
          type="button"
          onClick={() => onFinished("skipped")}
          disabled={save.isPending}
          className="inline-flex items-center border border-forest-dark text-forest-dark text-sm font-semibold px-6 py-3 rounded hover:bg-forest-pale transition-colors"
        >
          {skipLabel}
        </button>
        {!complete && (
          <span className="text-xs text-ink-secondary">
            Answer both questions for all six to save.
          </span>
        )}
      </div>
    </div>
  );
}

interface ToleranceQuestionProps {
  name: string;
  legend: string;
  value: ToleranceSteps | undefined;
  onChange: (steps: ToleranceSteps) => void;
}

function ToleranceQuestion({ name, legend, value, onChange }: ToleranceQuestionProps) {
  return (
    <fieldset>
      <legend className="text-sm text-ink-primary mb-1">{legend}</legend>
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {TOLERANCE_OPTIONS.map((option) => (
          <label key={option.steps} className="flex items-center gap-1.5 text-sm text-ink-secondary">
            <input
              type="radio"
              name={name}
              value={option.steps}
              checked={value === option.steps}
              onChange={() => onChange(option.steps)}
            />
            {option.label}
          </label>
        ))}
      </div>
    </fieldset>
  );
}
