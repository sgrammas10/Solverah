import { useState } from "react";

const LEVELS = ["beginner", "intermediate", "advanced"] as const;
type Level = (typeof LEVELS)[number];

const LEVEL_LABELS: Record<Level, string> = {
  beginner: "Beginner",
  intermediate: "Intermediate",
  advanced: "Advanced",
};

interface SkillProficiencyModalProps {
  skills: string[];
  initialLevels: Record<string, string>;
  saving: boolean;
  onSave: (levels: Record<string, string>) => void;
  onSkip: () => void;
}

export default function SkillProficiencyModal({
  skills,
  initialLevels,
  saving,
  onSave,
  onSkip,
}: SkillProficiencyModalProps) {
  const [levels, setLevels] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = {};
    for (const skill of skills) {
      init[skill] = initialLevels[skill] ?? "beginner";
    }
    return init;
  });

  const handleSave = () => {
    onSave(levels);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center px-4 py-8 overflow-y-auto">
      <div className="absolute inset-0 bg-ink-primary/40" />
      <div className="relative w-full max-w-2xl rounded-2xl border border-cream-subtle bg-cream-base shadow-2xl shadow-ink-primary/20">
        {/* Header */}
        <div className="px-6 pt-6 pb-4 border-b border-cream-muted">
          <h2 className="font-display text-xl font-semibold text-ink-primary">
            Rate your skills
          </h2>
          <p className="mt-1 text-sm text-ink-secondary leading-relaxed">
            Help us understand which skills you use most — it makes your career
            matches significantly more accurate.
          </p>
        </div>

        {/* Skill cards */}
        <div className="px-6 py-4 max-h-[60vh] overflow-y-auto">
          <div className="grid gap-3 sm:grid-cols-2">
            {skills.map((skill) => (
              <div
                key={skill}
                className="rounded-xl border border-cream-muted bg-white px-4 py-3"
              >
                <p className="text-sm font-semibold text-ink-primary mb-2 truncate">
                  {skill}
                </p>
                <div className="flex gap-1">
                  {LEVELS.map((lvl) => (
                    <button
                      key={lvl}
                      type="button"
                      onClick={() =>
                        setLevels((prev) => ({ ...prev, [skill]: lvl }))
                      }
                      className={
                        "flex-1 rounded-lg px-2 py-1 text-xs font-medium border transition-colors " +
                        (levels[skill] === lvl
                          ? "bg-forest-dark text-white border-forest-dark"
                          : "bg-white text-ink-secondary border-cream-muted hover:border-forest-light hover:text-forest-dark")
                      }
                    >
                      {LEVEL_LABELS[lvl]}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-cream-muted flex flex-col sm:flex-row gap-3 sm:justify-end">
          <button
            type="button"
            onClick={onSkip}
            disabled={saving}
            className="order-last sm:order-first px-4 py-2 text-sm text-ink-secondary hover:text-ink-primary transition-colors"
          >
            Skip for now
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="px-5 py-2 rounded-lg bg-forest-dark text-white text-sm font-semibold hover:bg-forest-mid transition-colors disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save & continue"}
          </button>
        </div>
      </div>
    </div>
  );
}
