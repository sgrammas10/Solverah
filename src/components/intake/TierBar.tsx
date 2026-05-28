interface TierSegment {
  label: string;
  state: "completed" | "next" | "future";
}

const TIERS: TierSegment[] = [
  { label: "Lite Lite", state: "completed" },
  { label: "Work Pulse Lite", state: "next" },
  { label: "Work Pulse", state: "future" },
];

export default function TierBar() {
  return (
    <div>
      <p className="text-xs text-ink-tertiary uppercase tracking-widest mb-3">
        Your Solverah journey
      </p>
      <div className="flex items-center">
        {TIERS.map((tier, i) => (
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
                  "text-xs mt-1.5 whitespace-nowrap",
                  tier.state === "future" ? "text-ink-tertiary" : "text-forest-dark font-semibold",
                ].join(" ")}
              >
                {tier.state === "completed" && "✓ "}
                {tier.state === "next" && "→ "}
                {tier.label}
              </span>
            </div>
            {i < TIERS.length - 1 && (
              <div
                className={[
                  "flex-1 h-px mx-2 mb-4",
                  i === 0 ? "bg-forest-dark" : "bg-cream-muted",
                ].join(" ")}
              />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
