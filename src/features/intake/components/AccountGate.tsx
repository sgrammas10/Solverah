import { Link } from "react-router-dom";
import { PRIMARY } from "../../../shared/ui/publicStyles";

const UNLOCK_ITEMS = [
  "Your full 12-question Work Pulse assessment",
  "A complete snapshot narrative of how you work",
  "Emerging signals about your friction and flow",
  "A partial Solverah profile you can build over time",
];

export default function AccountGate() {
  return (
    <div>
      <p className="text-[0.95rem] font-medium text-forest-mid mb-2">
        Your Work Pulse report is ready
      </p>
      <h1 className="font-headline text-[clamp(1.6rem,3.4vw,2.2rem)] font-extrabold leading-[1.1] tracking-[-0.02em] text-ink-primary">
        Unlock your full results
      </h1>
      <p className="text-[1.02rem] leading-[1.6] text-ink-secondary mt-3 mb-5">
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
        className={`${PRIMARY} w-full mt-6`}
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
