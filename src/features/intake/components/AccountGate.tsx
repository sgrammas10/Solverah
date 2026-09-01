import { Link } from "react-router-dom";

const UNLOCK_ITEMS = [
  "Your full 12-question Work Pulse assessment",
  "A complete snapshot narrative of how you work",
  "Emerging signals about your friction and flow",
  "A partial Solverah profile you can build over time",
];

export default function AccountGate() {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-widest text-forest-light mb-2">
        Your Work Pulse report is ready
      </p>
      <h1 className="font-display text-2xl sm:text-3xl font-semibold text-ink-primary">
        Unlock your full results
      </h1>
      <p className="text-sm text-ink-secondary mt-2 mb-5">
        Create a free account to access:
      </p>

      <ul className="space-y-2">
        {UNLOCK_ITEMS.map((item) => (
          <li key={item} className="flex items-start gap-2 text-sm text-ink-primary">
            <span className="text-forest-dark font-semibold shrink-0">✓</span>
            {item}
          </li>
        ))}
      </ul>

      <Link
        to="/register?from=wpll"
        className="w-full block text-center bg-forest-dark text-white font-semibold py-3.5 rounded hover:bg-forest-mid transition-colors mt-6"
      >
        Create my free account →
      </Link>

      <Link
        to="/login?from=wpll"
        className="text-sm text-ink-secondary hover:text-forest-mid transition-colors text-center block mt-3"
      >
        Already have an account? Sign in
      </Link>

      <p className="text-xs text-ink-tertiary text-center mt-2">
        No credit card required. Takes 60 seconds.
      </p>
    </div>
  );
}
