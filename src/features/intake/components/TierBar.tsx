/**
 * Pro is not built yet. It stays on the bar so the path reads true, but it is
 * labelled as coming soon the same way the results and Intelligence pages
 * label it, and nothing on the bar is clickable.
 */
const TIER_LABELS = ["Work Pulse Lite", "Work Pulse", "Work Pulse Pro · coming soon"] as const;

type TierState = "completed" | "next" | "future";

interface TierBarProps {
  nextTierIndex?: 0 | 1 | 2;
}

export default function TierBar({ nextTierIndex = 1 }: TierBarProps) {
  const tiers: { label: string; state: TierState }[] = TIER_LABELS.map((label, i) => ({
    label,
    state: i < nextTierIndex ? "completed" : i === nextTierIndex ? "next" : "future",
  }));

  return (
    <div>
      <p className="text-sm font-medium text-ink-secondary mb-3">
        Your Solverah journey
      </p>
      <div className="flex items-center">
        {tiers.map((tier, i) => (
          <div key={tier.label} className="flex items-center flex-1 last:flex-none">
            <div className="flex flex-col items-center">
              {tier.state === "completed" && (
                <div className="w-3 h-3 rounded-full bg-forest-dark" />
              )}
              {tier.state === "next" && (
                <div className="w-3 h-3 rounded-full bg-forest-light ring-2 ring-forest-pale animate-pulse" />
              )}
              {tier.state === "future" && (
                <div className="w-3 h-3 rounded-full border border-cream-muted bg-white" />
              )}
              <span
                className={[
                  "text-xs mt-1.5 text-center max-w-[9rem]",
                  tier.state === "future" ? "text-ink-tertiary" : "text-forest-dark font-semibold",
                ].join(" ")}
              >
                {tier.state === "completed" && "✓ "}
                {tier.state === "next" && "→ "}
                {tier.label}
              </span>
            </div>
            {i < tiers.length - 1 && (
              <div
                className={[
                  "flex-1 h-px mx-2 mb-4",
                  i < nextTierIndex ? "bg-forest-dark" : "bg-cream-muted",
                ].join(" ")}
              />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
