import { useState } from "react";

// ---------------------------------------------------------------------------
// Activity definitions — keys must match focus_type/score.py _S3_DIM_MAP
// ---------------------------------------------------------------------------

const ACTIVITIES = [
  { key: "deep_solo",  label: "Deep solo work",           hint: "Focused, uninterrupted output" },
  { key: "planning",   label: "Planning & organizing",    hint: "Thinking ahead, structuring" },
  { key: "social",     label: "Meetings & collaboration", hint: "Talking through ideas with others" },
  { key: "breaks",     label: "Breaks & recharging",      hint: "Stepping away, resetting" },
  { key: "exploring",  label: "Learning & exploring",     hint: "Reading, experimenting, discovering" },
] as const;

type ActivityKey = (typeof ACTIVITIES)[number]["key"];

type Values = Record<ActivityKey, number>;

const TOTAL_HOURS = 4;
const STEP = 0.5;

// ---------------------------------------------------------------------------
// Scene3Props
// ---------------------------------------------------------------------------

export interface Scene3Props {
  onComplete: (payload: {
    deep_solo: number;
    planning: number;
    social: number;
    breaks: number;
    exploring: number;
  }) => void;
}

// ---------------------------------------------------------------------------
// Scene 3
// ---------------------------------------------------------------------------

export default function Scene3({ onComplete }: Scene3Props) {
  const [values, setValues] = useState<Values>({
    deep_solo: 0,
    planning: 0,
    social: 0,
    breaks: 0,
    exploring: 0,
  });

  const total = Object.values(values).reduce((sum, v) => sum + v, 0);
  const remaining = +(TOTAL_HOURS - total).toFixed(1);
  const isExact = Math.abs(total - TOTAL_HOURS) < 0.001;
  const isOver = total > TOTAL_HOURS + 0.001;

  function handleChange(key: ActivityKey, raw: string) {
    setValues((prev) => ({ ...prev, [key]: parseFloat(raw) }));
  }

  return (
    <div className="space-y-6">
      {/* Scene header */}
      <div className="space-y-1.5">
        <p className="font-display text-lg font-semibold text-ink-primary">
          The Free Day
        </p>
        <p className="text-sm text-ink-secondary leading-relaxed">
          You have 4 uninterrupted hours — no meetings, no Slack. It's all yours.
          Allocate the time across five activities however feels natural to you.
        </p>
      </div>

      {/* Remaining counter */}
      <div
        className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold transition-colors ${
          isExact
            ? "bg-forest-pale text-forest-dark"
            : isOver
            ? "bg-red-100 text-red-600"
            : "bg-cream-subtle text-ink-secondary"
        }`}
      >
        <span
          className={`h-1.5 w-1.5 rounded-full ${
            isExact ? "bg-forest-dark" : isOver ? "bg-red-500" : "bg-ink-tertiary"
          }`}
        />
        {isExact
          ? "Perfect — exactly 4 hours"
          : isOver
          ? `${Math.abs(remaining).toFixed(1)} hrs over`
          : `${remaining.toFixed(1)} hrs remaining`}
      </div>

      {/* Sliders */}
      <div className="space-y-5">
        {ACTIVITIES.map(({ key, label, hint }) => (
          <div key={key} className="space-y-1.5">
            <div className="flex items-baseline justify-between gap-2">
              <div>
                <span className="text-sm font-medium text-ink-primary">{label}</span>
                <span className="ml-2 text-xs text-ink-tertiary">{hint}</span>
              </div>
              <span className="text-sm font-semibold text-ink-primary tabular-nums shrink-0">
                {values[key].toFixed(1)} hrs
              </span>
            </div>
            <input
              type="range"
              min={0}
              max={TOTAL_HOURS}
              step={STEP}
              value={values[key]}
              onChange={(e) => handleChange(key, e.target.value)}
              className="w-full h-1.5 rounded-full appearance-none cursor-pointer accent-forest-dark bg-cream-muted"
              aria-label={label}
            />
            <div className="flex justify-between text-[10px] text-ink-tertiary">
              <span>0 hrs</span>
              <span>4 hrs</span>
            </div>
          </div>
        ))}
      </div>

      {/* Submit */}
      <button
        type="button"
        onClick={() => onComplete({ ...values })}
        disabled={!isExact}
        className={`w-full font-semibold py-3.5 rounded transition-colors text-sm ${
          isExact
            ? "bg-forest-dark text-white hover:bg-forest-mid"
            : "bg-cream-muted text-ink-tertiary cursor-not-allowed"
        }`}
      >
        {isExact
          ? "That's my day →"
          : isOver
          ? "Reduce sliders to exactly 4 hours"
          : `Add ${remaining.toFixed(1)} more hours to continue`}
      </button>
    </div>
  );
}
