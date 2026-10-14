/**
 * ResumePrompt -- the shared "pick up where you left off / start over" card shown when
 * a user re-opens a quiz with a saved in-progress draft. Every quiz renders this same
 * component so the choice reads identically everywhere; the per-quiz part (which
 * question counts as "first unanswered", what clearing the draft means) stays with
 * the quiz. See `shared/lib/resumeDraft.ts` for the helpers.
 */

interface ResumePromptProps {
  /** The quiz's display name, e.g. "Work Pulse". */
  title: string;
  /** How many questions (or scenes) the draft already covers. */
  answeredCount: number;
  /** How many there are in total. */
  total: number;
  /** Singular noun for one step; defaults to "question". */
  unit?: string;
  onResume: () => void;
  onStartOver: () => void;
}

export default function ResumePrompt({
  title,
  answeredCount,
  total,
  unit = "question",
  onResume,
  onStartOver,
}: ResumePromptProps) {
  const noun = total === 1 ? unit : `${unit}s`;
  return (
    <section
      aria-labelledby="resume-prompt-heading"
      className="rounded-xl border border-cream-muted bg-white px-6 py-7 space-y-5 shadow-sm"
    >
      <div className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-widest text-forest-light">
          {title}
        </p>
        <h2
          id="resume-prompt-heading"
          className="font-display text-xl sm:text-2xl font-semibold text-ink-primary"
        >
          You have answers saved from last time
        </h2>
        <p className="text-sm text-ink-secondary leading-relaxed">
          You got through {answeredCount} of {total} {noun}. Pick up where you left off, or
          clear them and start again from the beginning.
        </p>
      </div>
      <div className="flex flex-col sm:flex-row gap-3">
        <button
          type="button"
          onClick={onResume}
          className="inline-flex items-center justify-center rounded-[4px] bg-forest-dark px-6 py-3 text-sm font-semibold text-white transition-colors hover:bg-forest-mid"
        >
          Pick up where you left off
        </button>
        <button
          type="button"
          onClick={onStartOver}
          className="inline-flex items-center justify-center rounded-[4px] border-2 border-forest-dark px-6 py-3 text-sm font-semibold text-forest-dark transition-colors hover:bg-forest-pale"
        >
          Start over
        </button>
      </div>
    </section>
  );
}
