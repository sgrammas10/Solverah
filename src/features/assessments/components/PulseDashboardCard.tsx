/**
 * PulseDashboardCard -- "Your pulse this week" (BUILD_PLAN B-3), a compact
 * card on the existing dashboard. Feeds D-6 later; this only adds the card,
 * it does not reframe the dashboard around it.
 *
 * Degrades to an invitation for a user with no check-ins yet, same shape as
 * `WorkPulseBanner`'s not-started state beside it. `limit: 2` is exactly
 * enough to say "up / down / about the same from before" without pulling a
 * history this card never renders as a chart -- the full trend lives at
 * `/pulse/trend`, one tap away.
 */
import { Link } from "react-router-dom";

import { usePulseHistory } from "../usePulse";

function formatDate(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function directionSentence(current: number, previous: number): string {
  const word = current > previous ? "up" : current < previous ? "down" : "about the same";
  return `How work's working for you is ${word} from before.`;
}

const WEEK_MS = 7 * 24 * 60 * 60 * 1000;

/** Whether `iso` is within the last seven days -- the only case in which
 *  "this week" is a true word for the heading. */
function isThisWeek(iso: string | null, now = Date.now()): boolean {
  if (!iso) return false;
  const t = new Date(iso).getTime();
  return !Number.isNaN(t) && now - t <= WEEK_MS;
}

export default function PulseDashboardCard() {
  const { data, isLoading, isError, refetch } = usePulseHistory({ limit: 2 });

  if (isLoading) return null;

  // A failed fetch is not "no check-ins yet": inviting a user with months of
  // history to "take your first check-in" would be the card lying to them.
  if (isError || !data) {
    return (
      <div className="rounded-xl border border-cream-muted bg-white p-6">
        <p className="text-xs font-semibold uppercase tracking-widest text-forest-light mb-2">Pulse</p>
        <h2 className="font-display text-lg font-semibold text-ink-primary mb-1">Your pulse</h2>
        <p role="alert" className="text-sm text-ink-secondary mb-4">
          We couldn't load your pulse right now.
        </p>
        <div className="flex items-center gap-4">
          <button
            type="button"
            onClick={() => refetch()}
            className="text-sm font-semibold text-forest-dark hover:underline"
          >
            Try again
          </button>
          <Link to="/pulse" className="text-sm text-ink-secondary hover:text-ink-primary">
            Check in →
          </Link>
        </div>
      </div>
    );
  }

  const checkins = data.checkins;

  if (checkins.length === 0) {
    return (
      <div className="rounded-xl border border-cream-muted bg-white p-6">
        <p className="text-xs font-semibold uppercase tracking-widest text-forest-light mb-2">Pulse</p>
        <h2 className="font-display text-lg font-semibold text-ink-primary mb-1">Keep a pulse on work</h2>
        <p className="text-sm text-ink-secondary mb-4">
          A short weekly check-in — three questions, about a minute. It gets more useful the more
          you do it.
        </p>
        <Link to="/pulse" className="text-sm font-semibold text-forest-dark hover:underline">
          Take your first check-in →
        </Link>
      </div>
    );
  }

  const [latest, previous] = checkins;

  return (
    <div className="rounded-xl border border-cream-muted bg-white p-6">
      <p className="text-xs font-semibold uppercase tracking-widest text-forest-light mb-2">Pulse</p>
      <h2 className="font-display text-lg font-semibold text-ink-primary mb-1">
        {isThisWeek(latest.taken_at) ? "Your pulse this week" : "Your pulse"}
      </h2>
      <p className="text-sm text-ink-secondary mb-4">
        Last check-in {formatDate(latest.taken_at)}.{" "}
        {previous
          ? directionSentence(latest.experienced, previous.experienced)
          : "One check-in so far — a trend builds after the next one."}
      </p>
      <div className="flex items-center gap-4">
        <Link to="/pulse/trend" className="text-sm font-semibold text-forest-dark hover:underline">
          See your trend →
        </Link>
        <Link to="/pulse" className="text-sm text-ink-secondary hover:text-ink-primary">
          Check in →
        </Link>
      </div>
    </div>
  );
}
