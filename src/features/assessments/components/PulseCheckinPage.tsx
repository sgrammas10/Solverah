/**
 * PulseCheckinPage -- the Pulse check-in (BUILD_PLAN B-3), at `/pulse`. This
 * exact path is B-2's email deep-link target (`send_pulse_prompt_email`), so
 * it must stay reachable signed-out-safe (RequireAuth bounces to /login and
 * back) and must not move.
 *
 * ONE SCREEN. Unlike `EnvironmentReportPage`'s one-question-per-screen
 * stepper, this instrument's own budget (60 seconds, `pulse_items.py`'s
 * header) is the reason NOT to page it -- a stepper adds a tap per question
 * to a flow trying to remove taps. All four items (the three the server's
 * round-robin served, plus `experienced`) render at once, in the order
 * `GET /me/pulse/next-checkin` sent them. Do not reorder: `experienced` is
 * last in that response on purpose (`pulse_items.py`'s anti-halo note), and
 * this page must not undo it by sorting or grouping.
 *
 * ONE THING BACK, NO UPSELL CHAIN. A successful submit swaps to a single
 * confirmation screen -- this week vs last, or an honest first-point note
 * with nothing to compare yet -- and then exactly one exit. No second screen
 * promoting another feature.
 *
 * THE COMPARISON POINT IS CAPTURED BEFORE SUBMIT, not read live after. The
 * submit mutation invalidates every Pulse query on success (`usePulse.ts`),
 * which refetches history in the background -- if the confirmation screen
 * read `usePulseHistory` reactively at that point, "last week" would flicker
 * from the real previous check-in to the one just submitted (now the newest
 * row) the moment that refetch resolves. `priorRef` snapshots the
 * pre-submission value once, at mount and whenever the query settles, and the
 * submit handler freezes that snapshot into local state before calling
 * `mutate` -- so the number on screen cannot move under the user.
 */
import { useEffect, useRef, useState } from "react";
import { useNavigate, Link } from "react-router-dom";

import { usePulseHistory, usePulseNextCheckin, useSubmitPulseCheckin } from "../usePulse";
import type { PulseCheckinItem, PulseCheckinRecord, PulseOutcomeItem } from "../usePulse";
import PulseSparkline from "./PulseSparkline";

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-cream-base">
      <div className="mx-auto max-w-lg px-6 pt-12 pb-16 space-y-6">{children}</div>
    </div>
  );
}

function Eyebrow({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-xs font-semibold uppercase tracking-widest text-forest-light">{children}</p>
  );
}

/** One item, one row of five taps. Anchors label the ends only -- the same
 *  "only the two endpoints worded" scale `pulse_items.py` defines. */
function LikertRow({
  stem,
  lowAnchor,
  highAnchor,
  value,
  onChange,
}: {
  stem: string;
  lowAnchor: string;
  highAnchor: string;
  value: number | undefined;
  onChange: (value: number) => void;
}) {
  return (
    <div className="space-y-2">
      <p className="text-sm font-medium text-ink-primary leading-snug">{stem}</p>
      <div role="radiogroup" aria-label={stem} className="flex items-center justify-between gap-2">
        {[1, 2, 3, 4, 5].map((n) => {
          const selected = value === n;
          return (
            <button
              key={n}
              type="button"
              role="radio"
              aria-checked={selected}
              aria-label={`${n}`}
              onClick={() => onChange(n)}
              className={[
                "h-11 w-11 shrink-0 rounded-full text-sm font-semibold transition-colors border",
                selected
                  ? "border-forest-dark bg-forest-dark text-white"
                  : "border-cream-muted bg-white text-ink-secondary hover:border-forest-light",
              ].join(" ")}
            >
              {n}
            </button>
          );
        })}
      </div>
      <div className="flex justify-between text-xs text-ink-tertiary">
        <span>{lowAnchor}</span>
        <span>{highAnchor}</span>
      </div>
    </div>
  );
}

/**
 * How many points the confirmation chart shows, the new check-in included. The
 * chart used to plot only [prior, current] -- after a third check-in the user
 * saw two dots and read it as lost data. A cap keeps the compact chart legible
 * and the request small; the full series lives at /pulse/trend.
 */
export const CONFIRMATION_CHART_POINTS = 12;

interface Confirmation {
  sequenceBefore: number;
  /** Check-ins before this one, newest first (the wire order), capped. */
  history: PulseCheckinRecord[];
  current: PulseCheckinRecord;
}

function directionWord(current: number, prior: number): string {
  if (current > prior) return "up";
  if (current < prior) return "down";
  return "about the same";
}

function Confirmation({ confirmation }: { confirmation: Confirmation }) {
  const navigate = useNavigate();
  const { sequenceBefore, history, current } = confirmation;
  const prior = history[0] ?? null;
  // Oldest first, left to right, then this check-in at the end.
  const points = [
    ...[...history].reverse().map((c) => ({ date: c.taken_at ?? "", value: c.experienced })),
    { date: current.taken_at ?? new Date().toISOString(), value: current.experienced },
  ];
  const tier = sequenceBefore === 0 || !prior ? "first" : sequenceBefore === 1 ? "second" : "later";

  return (
    <div className="space-y-5">
      <Eyebrow>Logged</Eyebrow>
      {tier === "first" ? (
        <>
          <h1 className="font-display text-2xl font-semibold text-ink-primary">That's your first pulse</h1>
          <p className="text-sm text-ink-secondary leading-relaxed">
            Nothing to compare it to yet. Check in again next week and you'll start seeing how it
            moves.
          </p>
        </>
      ) : (
        <>
          <h1 className="font-display text-2xl font-semibold text-ink-primary">
            {tier === "second" ? "Two points make a trend" : "This week vs. last week"}
          </h1>
          <div className="rounded-xl border border-cream-muted bg-white px-5 py-4">
            <PulseSparkline
              ariaLabel="How work's working for you, your recent check-ins up to this one"
              compact
              points={points}
            />
          </div>
          <p className="text-sm text-ink-secondary leading-relaxed">
            How work's working for you is {directionWord(current.experienced, prior!.experienced)}{" "}
            {tier === "second" ? "from last time." : "from last week."}
          </p>
        </>
      )}

      <div className="flex items-center justify-between pt-2">
        <Link to="/pulse/trend" className="text-sm font-semibold text-forest-dark hover:underline">
          See your trend →
        </Link>
        <button
          type="button"
          onClick={() => navigate("/job-seeker/dashboard")}
          className="bg-forest-dark text-white font-semibold px-8 py-3 rounded hover:bg-forest-mid transition-colors"
        >
          Done
        </button>
      </div>
    </div>
  );
}

export default function PulseCheckinPage() {
  const nextCheckinQuery = usePulseNextCheckin();
  const historyQuery = usePulseHistory({ limit: CONFIRMATION_CHART_POINTS - 1 });
  const submitMutation = useSubmitPulseCheckin();

  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);

  const priorRef = useRef<PulseCheckinRecord[]>([]);
  useEffect(() => {
    if (historyQuery.data) {
      priorRef.current = historyQuery.data.checkins;
    }
  }, [historyQuery.data]);

  if (confirmation) {
    return (
      <Shell>
        <Confirmation confirmation={confirmation} />
      </Shell>
    );
  }

  if (nextCheckinQuery.isLoading) {
    return (
      <div className="min-h-screen bg-cream-base flex flex-col items-center justify-center gap-4">
        <div className="w-8 h-8 rounded-full border-2 border-forest-light border-t-transparent animate-spin" />
        <p className="text-sm text-ink-secondary">Loading…</p>
      </div>
    );
  }

  if (nextCheckinQuery.isError || !nextCheckinQuery.data) {
    return (
      <div className="min-h-screen bg-cream-base flex items-center justify-center px-6">
        <div className="max-w-sm w-full rounded-lg border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-700">
          <p className="font-medium mb-1">We couldn't load this check-in right now.</p>
          <p className="text-xs">Please try again in a moment.</p>
          <button
            type="button"
            onClick={() => nextCheckinQuery.refetch()}
            className="mt-3 text-xs font-semibold text-red-700 underline"
          >
            Try again
          </button>
        </div>
      </div>
    );
  }

  const { sequence, items, experienced_item: experiencedItem } = nextCheckinQuery.data;
  const rows: Array<{ id: string; key: string; item: PulseCheckinItem | PulseOutcomeItem }> = [
    ...items.map((item) => ({ id: item.item_id, key: item.dimension, item })),
    { id: experiencedItem.item_id, key: "experienced", item: experiencedItem },
  ];
  const allAnswered = rows.every((row) => answers[row.id] !== undefined);

  function handleSubmit() {
    const itemScores: Record<string, number> = {};
    for (const item of items) {
      itemScores[item.dimension] = answers[item.item_id];
    }
    const experiencedValue = answers[experiencedItem.item_id];
    const priorSnapshot = priorRef.current;

    submitMutation.mutate(
      { item_scores: itemScores, experienced: experiencedValue },
      {
        onSuccess: (result) => {
          setConfirmation({ sequenceBefore: sequence, history: priorSnapshot, current: result });
        },
      },
    );
  }

  return (
    <Shell>
      <div className="space-y-2">
        <Eyebrow>Pulse check-in</Eyebrow>
        <h1 className="font-display text-2xl font-semibold text-ink-primary">
          Three questions about this week
        </h1>
        <p className="text-sm text-ink-secondary leading-relaxed">
          About a minute. Pick the number closest to true for you.
        </p>
      </div>

      <div className="space-y-6">
        {rows.map((row) => (
          <LikertRow
            key={row.id}
            stem={row.item.stem}
            lowAnchor={row.item.low_anchor}
            highAnchor={row.item.high_anchor}
            value={answers[row.id]}
            onChange={(value) => setAnswers((cur) => ({ ...cur, [row.id]: value }))}
          />
        ))}
      </div>

      {submitMutation.isError && (
        <p role="alert" className="text-sm text-red-700">
          We couldn't save that just now. Your answers are still here — try again.
        </p>
      )}

      <button
        type="button"
        onClick={handleSubmit}
        disabled={!allAnswered || submitMutation.isPending}
        className="w-full bg-forest-dark text-white font-semibold py-3.5 rounded hover:bg-forest-mid transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {submitMutation.isPending ? "Saving…" : "Done"}
      </button>
    </Shell>
  );
}
