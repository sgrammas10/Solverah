import { useState, useEffect, useRef, useCallback } from "react";

// ---------------------------------------------------------------------------
// Card data — IDs must match focus_type/score.py Scene 4 card sets
// ---------------------------------------------------------------------------

interface TaskCard {
  id: string;
  icon: string;
  label: string;
}

const TASK_CARDS: TaskCard[] = [
  { id: "reply_teammate",     icon: "💬", label: "Reply to a teammate's question" },
  { id: "write_report_draft", icon: "📄", label: "Write the first draft of the weekly report" },
  { id: "update_task_tracker",icon: "✅", label: "Update the team task tracker" },
  { id: "quick_call_unblock", icon: "📞", label: "Quick call to unblock a colleague" },
  { id: "sketch_tomorrow_plan",icon: "🗓️", label: "Sketch out tomorrow's plan" },
  { id: "deep_research",      icon: "🔍", label: "Start the deep research you've been putting off" },
  { id: "send_followup_email",icon: "📧", label: "Send a follow-up email to a client" },
  { id: "review_others_work", icon: "👀", label: "Review someone's work and leave feedback" },
];

const TIMER_MS = 3000;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Decision {
  id: string;
  dest: "now" | "tomorrow";
  clickTime?: number; // ms since card appeared; undefined = timeout
}

export interface Scene4Props {
  onComplete: (payload: {
    now: string[];
    tomorrow: string[];
    /** Mean over the cards the user clicked. Timed-out cards are not decisions
     *  and are left out; null when every card timed out, which the scorer reads
     *  as no timing signal (it used to be 0, which read as the fastest possible). */
    avg_decision_time_ms: number | null;
  }) => void;
}

// ---------------------------------------------------------------------------
// Scene 4
// ---------------------------------------------------------------------------

export default function Scene4({ onComplete }: Scene4Props) {
  const [phase, setPhase] = useState<"brief" | "active">("brief");
  const [cardIndex, setCardIndex] = useState(0);
  const [progress, setProgress] = useState(100); // 100 → 0 over TIMER_MS
  const [cardVisible, setCardVisible] = useState(true);

  const decisionsRef = useRef<Decision[]>([]);
  const cardStartRef = useRef<number>(Date.now());
  const decidedRef = useRef(false);
  const rafRef = useRef<number | null>(null);
  const onCompleteRef = useRef(onComplete);
  onCompleteRef.current = onComplete;

  // Compute and fire onComplete from the accumulated decisions
  const finalize = useCallback((decisions: Decision[]) => {
    const nowIds = decisions.filter((d) => d.dest === "now").map((d) => d.id);
    const tomorrowIds = decisions.filter((d) => d.dest === "tomorrow").map((d) => d.id);
    const clickedTimes = decisions
      .filter((d) => d.clickTime !== undefined)
      .map((d) => d.clickTime!);
    const avg =
      clickedTimes.length > 0
        ? Math.round(clickedTimes.reduce((a, b) => a + b, 0) / clickedTimes.length)
        : null;
    onCompleteRef.current({ now: nowIds, tomorrow: tomorrowIds, avg_decision_time_ms: avg });
  }, []);

  const advanceCard = useCallback(
    (dest: "now" | "tomorrow", clickTime?: number) => {
      if (decidedRef.current) return;
      decidedRef.current = true;

      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }

      const card = TASK_CARDS[cardIndex];
      const updated: Decision[] = [...decisionsRef.current, { id: card.id, dest, clickTime }];
      decisionsRef.current = updated;

      const isLast = cardIndex === TASK_CARDS.length - 1;

      // Exit animation — slide card away
      setCardVisible(false);

      setTimeout(() => {
        if (isLast) {
          finalize(updated);
        } else {
          decidedRef.current = false;
          setCardIndex((i) => i + 1);
          setProgress(100);
          setCardVisible(true);
          cardStartRef.current = Date.now();
        }
      }, 320);
    },
    [cardIndex, finalize]
  );

  // Smooth progress bar + auto-timeout via rAF
  useEffect(() => {
    if (phase !== "active") return;
    cardStartRef.current = Date.now();
    decidedRef.current = false;
    setProgress(100);

    const tick = () => {
      const elapsed = Date.now() - cardStartRef.current;
      const pct = Math.max(0, ((TIMER_MS - elapsed) / TIMER_MS) * 100);
      setProgress(pct);

      if (elapsed >= TIMER_MS) {
        advanceCard("tomorrow", undefined);
      } else {
        rafRef.current = requestAnimationFrame(tick);
      }
    };

    rafRef.current = requestAnimationFrame(tick);

    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    };
  }, [phase, cardIndex, advanceCard]);

  function handleClick(dest: "now" | "tomorrow") {
    const clickTime = Date.now() - cardStartRef.current;
    advanceCard(dest, clickTime);
  }

  const card = TASK_CARDS[cardIndex];
  const total = TASK_CARDS.length;

  // ---------------------------------------------------------------------------
  // Briefing screen — shown once before the timed cards start
  // ---------------------------------------------------------------------------

  if (phase === "brief") {
    return (
      <div className="space-y-6">
        <div className="space-y-1.5">
          <p className="font-display text-lg font-semibold text-ink-primary">
            The 2:30 Crash
          </p>
          <p className="text-sm text-ink-secondary leading-relaxed">
            Your energy is dipping. Eight tasks are stacked up — and you need to
            decide each one <strong className="text-ink-primary">fast</strong>.
          </p>
        </div>

        {/* How it works */}
        <div className="rounded-xl border border-cream-muted bg-cream-subtle/40 px-5 py-4 space-y-3">
          <p className="text-xs font-semibold uppercase tracking-wider text-ink-tertiary">
            How it works
          </p>
          <ul className="space-y-2 text-sm text-ink-secondary">
            <li className="flex items-start gap-2">
              <span className="text-forest-dark font-bold mt-0.5">1.</span>
              A task card appears. You have <strong className="text-ink-primary">3 seconds</strong> to decide.
            </li>
            <li className="flex items-start gap-2">
              <span className="text-forest-dark font-bold mt-0.5">2.</span>
              Tap <strong className="text-ink-primary">Do it now</strong> or{" "}
              <strong className="text-ink-primary">Push to tomorrow</strong> — go with your gut.
            </li>
            <li className="flex items-start gap-2">
              <span className="text-forest-dark font-bold mt-0.5">3.</span>
              No tap in 3 seconds? It automatically goes to tomorrow.
            </li>
          </ul>
        </div>

        {/* Example card */}
        <div className="space-y-3">
          <p className="text-xs font-semibold uppercase tracking-wider text-ink-tertiary">
            Example
          </p>

          <div className="rounded-xl border border-cream-muted bg-white px-6 py-8 flex flex-col items-center gap-3 shadow-sm">
            <span className="text-5xl select-none" role="img" aria-hidden>📞</span>
            <p className="text-base font-medium text-ink-primary text-center leading-snug max-w-xs">
              Quick call to unblock a colleague
            </p>
          </div>

          {/* Static timer bar */}
          <div className="h-0.5 w-full rounded-full bg-cream-muted overflow-hidden">
            <div className="h-full rounded-full bg-forest-light" style={{ width: "60%" }} />
          </div>

          <div className="grid grid-cols-2 gap-3 pointer-events-none select-none opacity-70">
            <div className="font-semibold py-4 rounded border-2 border-forest-dark text-forest-dark text-sm text-center">
              Do it now
            </div>
            <div className="font-semibold py-4 rounded bg-cream-subtle text-ink-secondary text-sm text-center">
              Push to tomorrow
            </div>
          </div>

          <p className="text-center text-xs text-ink-tertiary">
            ↑ this is what you'll see — the bar drains over 3 seconds
          </p>
        </div>

        <button
          type="button"
          onClick={() => setPhase("active")}
          className="w-full bg-forest-dark text-white font-semibold py-3.5 rounded hover:bg-forest-mid transition-colors text-sm"
        >
          I'm ready — start the 2:30 Crash →
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Scene header */}
      <div className="space-y-1.5">
        <p className="font-display text-lg font-semibold text-ink-primary">
          The 2:30 Crash
        </p>
        <p className="text-sm text-ink-secondary leading-relaxed">
          It's 2:30pm and your energy is dipping. Eight tasks are stacked up.
          Decide fast — do it <strong className="text-ink-primary">now</strong> or{" "}
          <strong className="text-ink-primary">push to tomorrow</strong>. You have
          3 seconds per card.
        </p>
      </div>

      {/* Card counter */}
      <div className="flex items-center gap-2">
        <p className="text-xs text-ink-tertiary">
          {cardIndex + 1} of {total}
        </p>
        <div className="flex gap-1">
          {TASK_CARDS.map((_, i) => (
            <div
              key={i}
              className={`h-1 w-4 rounded-full transition-colors duration-200 ${
                i < cardIndex
                  ? decisionsRef.current[i]?.dest === "now"
                    ? "bg-forest-dark"
                    : "bg-cream-muted"
                  : i === cardIndex
                  ? "bg-ink-tertiary"
                  : "bg-cream-muted"
              }`}
            />
          ))}
        </div>
      </div>

      {/* Task card */}
      <div
        className={`rounded-xl border border-cream-muted bg-white px-6 py-10 flex flex-col items-center gap-4 shadow-sm transition-all duration-300 ${
          cardVisible
            ? "opacity-100 translate-y-0"
            : "opacity-0 translate-y-3"
        }`}
      >
        <span className="text-5xl select-none" role="img" aria-hidden>
          {card.icon}
        </span>
        <p className="text-base font-medium text-ink-primary text-center leading-snug max-w-xs">
          {card.label}
        </p>
      </div>

      {/* Progress bar — depletes over 3 seconds */}
      <div className="h-0.5 w-full rounded-full bg-cream-muted overflow-hidden">
        <div
          className="h-full rounded-full bg-forest-light"
          style={{ width: `${progress}%`, transition: "none" }}
        />
      </div>

      {/* Decision buttons */}
      <div className="grid grid-cols-2 gap-3">
        <button
          type="button"
          onClick={() => handleClick("now")}
          disabled={!cardVisible}
          className="font-semibold py-4 rounded border-2 border-forest-dark text-forest-dark hover:bg-forest-pale active:bg-forest-pale transition-colors text-sm disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Do it now
        </button>
        <button
          type="button"
          onClick={() => handleClick("tomorrow")}
          disabled={!cardVisible}
          className="font-semibold py-4 rounded bg-cream-subtle text-ink-secondary hover:bg-cream-muted active:bg-cream-muted transition-colors text-sm disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Push to tomorrow
        </button>
      </div>

      {/* Timeout hint */}
      <p className="text-center text-xs text-ink-tertiary">
        No click in 3 seconds → goes to tomorrow automatically
      </p>
    </div>
  );
}
