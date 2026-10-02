/**
 * PulseTrendPage -- the trend view, event log, and cadence settings
 * (BUILD_PLAN B-3), at `/pulse/trend`. Three of B-3's four surfaces live here
 * rather than as separate routes: none of them is a full instrument the way
 * the check-in itself is, and splitting them would cost a page load per
 * section for a feature whose own product decision is to ship thin
 * (PRODUCT_DECISIONS.md §2).
 *
 * DEGRADE GRACEFULLY, PER SECTION, NOT AS ONE GATE. A brand-new account has
 * zero check-ins and zero events but a real cadence setting -- so this page
 * never blocks the whole screen on "not enough data" the way a full-page
 * empty state would. The experienced line and each per-dimension sparkline
 * degrade on their own point count (see `PulseSparkline`); only the settings
 * section is unconditional.
 *
 * PER-DIMENSION COVERAGE IS SPARSE BY DESIGN, NOT A BUG TO PAPER OVER.
 * `pulse_items.dimensions_for_checkin` serves 3 of 5 dimensions each
 * check-in, round-robin, so any one dimension's own series is built by
 * filtering `item_scores` for that key across check-ins -- it will always
 * have fewer points than the experienced line, and that gap is real, not a
 * rendering bug.
 *
 * EVENT ANNOTATIONS RIDE THE EXPERIENCED LINE ONLY. Five more copies of the
 * same tick marks across the per-dimension grid would repeat the same dates
 * five times over for no added information -- the experienced line is
 * already "the time axis" B-3 asks annotations to sit on.
 */
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import {
  usePulseHistory,
  usePulseSettings,
  useSubmitPulseEvent,
  useUpdatePulseSettings,
} from "../usePulse";
import type { PulseCheckinRecord, PulseDimension, PulseEventType, PulseSettableCadence } from "../usePulse";
import PulseSparkline from "./PulseSparkline";

const DIMENSION_ORDER: PulseDimension[] = [
  "fragmentation",
  "sustainability",
  "environmental_friction",
  "recognition_friction",
  "work_pace",
];

const DIMENSION_LABELS: Record<PulseDimension, string> = {
  fragmentation: "Focus",
  sustainability: "Workload",
  environmental_friction: "Surroundings",
  recognition_friction: "Recognition",
  work_pace: "Pace",
};

const EVENT_TYPES: PulseEventType[] = ["new_manager", "reorg", "remote_change", "role_change", "other"];

const EVENT_LABELS: Record<PulseEventType, string> = {
  new_manager: "New manager",
  reorg: "Reorg",
  remote_change: "Remote / office change",
  role_change: "Role change",
  other: "Something else",
};

const EVENT_NOTE_MAX = 280;

function formatDateLong(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-cream-base">
      <div className="mx-auto max-w-2xl px-6 pt-12 pb-20 space-y-8">{children}</div>
    </div>
  );
}

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="font-display text-lg font-semibold text-ink-primary">{children}</h2>
  );
}

// ---------------------------------------------------------------------------
// Experienced line
// ---------------------------------------------------------------------------

function ExperiencedSection({
  checkins,
  events,
}: {
  checkins: PulseCheckinRecord[];
  events: Array<{ date: string; label: string; note?: string | null }>;
}) {
  const points = checkins.map((c) => ({ date: c.taken_at ?? "", value: c.experienced }));

  return (
    <section className="space-y-3">
      <SectionHeading>How work's been working for you</SectionHeading>
      <div className="rounded-xl border border-cream-muted bg-white px-5 py-5">
        {points.length === 1 ? (
          <div className="space-y-3">
            <PulseSparkline ariaLabel="How work's working for you" points={points} width={520} height={120} />
            <p className="text-xs text-ink-tertiary">
              One check-in so far — the line fills in as you add more.
            </p>
          </div>
        ) : (
          <PulseSparkline
            ariaLabel="How work's working for you, over time"
            points={points}
            events={events}
            width={520}
            height={140}
          />
        )}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Per-dimension small multiples
// ---------------------------------------------------------------------------

function DimensionCard({ dimension, checkins }: { dimension: PulseDimension; checkins: PulseCheckinRecord[] }) {
  const points = checkins
    .filter((c) => c.item_scores[dimension] !== undefined)
    .map((c) => ({ date: c.taken_at ?? "", value: c.item_scores[dimension] }));

  return (
    <div className="rounded-xl border border-cream-muted bg-white px-4 py-4 space-y-2">
      <p className="text-sm font-semibold text-ink-primary">{DIMENSION_LABELS[dimension]}</p>
      {points.length === 0 && <p className="text-xs text-ink-tertiary">Not answered yet.</p>}
      {points.length === 1 && (
        <div className="space-y-1">
          <PulseSparkline ariaLabel={`${DIMENSION_LABELS[dimension]} trend`} points={points} width={240} height={72} />
          <p className="text-xs text-ink-tertiary">One answer so far.</p>
        </div>
      )}
      {points.length >= 2 && (
        <PulseSparkline ariaLabel={`${DIMENSION_LABELS[dimension]} trend`} points={points} width={240} height={72} />
      )}
    </div>
  );
}

function DimensionsGrid({ checkins }: { checkins: PulseCheckinRecord[] }) {
  return (
    <section className="space-y-3">
      <SectionHeading>By dimension</SectionHeading>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {DIMENSION_ORDER.map((dim) => (
          <DimensionCard key={dim} dimension={dim} checkins={checkins} />
        ))}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Log a change
// ---------------------------------------------------------------------------

function LogChangeSection({
  events,
}: {
  events: Array<{ id: number; at: string | null; event_type: PulseEventType; note: string | null }>;
}) {
  const [open, setOpen] = useState(false);
  const [selectedType, setSelectedType] = useState<PulseEventType | null>(null);
  const [note, setNote] = useState("");
  const submitEvent = useSubmitPulseEvent();

  function close() {
    setOpen(false);
    setSelectedType(null);
    setNote("");
  }

  function handleSave() {
    if (!selectedType) return;
    submitEvent.mutate(
      { event_type: selectedType, note: note.trim() ? note.trim() : null },
      { onSuccess: close },
    );
  }

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <SectionHeading>Changes you've logged</SectionHeading>
        {!open && (
          <button
            type="button"
            onClick={() => setOpen(true)}
            className="text-sm font-semibold text-forest-dark hover:underline"
          >
            + Log a change
          </button>
        )}
      </div>

      {open && (
        <div className="rounded-xl border border-cream-muted bg-white px-5 py-4 space-y-3">
          <div role="radiogroup" aria-label="What changed" className="flex flex-wrap gap-2">
            {EVENT_TYPES.map((type) => {
              const selected = selectedType === type;
              return (
                <button
                  key={type}
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  onClick={() => setSelectedType(type)}
                  className={[
                    "rounded-full border px-3 py-1.5 text-sm font-medium transition-colors",
                    selected
                      ? "border-forest-dark bg-forest-pale text-forest-dark"
                      : "border-cream-muted bg-white text-ink-secondary hover:border-forest-light",
                  ].join(" ")}
                >
                  {EVENT_LABELS[type]}
                </button>
              );
            })}
          </div>
          <div className="space-y-1">
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value.slice(0, EVENT_NOTE_MAX))}
              placeholder="Add a short note (optional)"
              rows={2}
              className="w-full rounded border border-cream-muted bg-cream-base px-3 py-2 text-sm text-ink-primary placeholder:text-ink-tertiary focus:border-forest-light focus:outline-none"
            />
            <p className="text-xs text-ink-tertiary text-right">
              {note.length}/{EVENT_NOTE_MAX}
            </p>
          </div>
          {submitEvent.isError && (
            <p role="alert" className="text-sm text-red-700">
              We couldn't save that just now. Try again.
            </p>
          )}
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={handleSave}
              disabled={!selectedType || submitEvent.isPending}
              className="bg-forest-dark text-white font-semibold px-5 py-2 rounded hover:bg-forest-mid transition-colors disabled:opacity-50 disabled:cursor-not-allowed text-sm"
            >
              {submitEvent.isPending ? "Saving…" : "Save"}
            </button>
            <button
              type="button"
              onClick={close}
              className="text-sm font-semibold text-ink-secondary hover:text-ink-primary"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {events.length === 0 ? (
        !open && <p className="text-sm text-ink-tertiary">No changes logged yet.</p>
      ) : (
        <ul className="space-y-2">
          {events.map((e) => (
            <li
              key={e.id}
              className="flex items-baseline gap-3 rounded-lg border border-cream-muted bg-white px-4 py-2.5 text-sm"
            >
              <span className="text-xs text-ink-tertiary shrink-0">{formatDateLong(e.at)}</span>
              <span className="font-medium text-ink-primary">{EVENT_LABELS[e.event_type]}</span>
              {e.note && <span className="text-ink-secondary italic">"{e.note}"</span>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Cadence settings
// ---------------------------------------------------------------------------

const CADENCE_OPTIONS: Array<{ value: PulseSettableCadence; label: string }> = [
  { value: "weekly", label: "Weekly" },
  { value: "biweekly", label: "Every two weeks" },
  { value: "monthly", label: "Monthly" },
  { value: "off", label: "Off" },
];

function CadenceSection() {
  const settingsQuery = usePulseSettings();
  const updateSettings = useUpdatePulseSettings();
  const cadence = settingsQuery.data?.cadence;

  // Four unpressed buttons is not a loading state and not an error state --
  // it reads as "no cadence set", which is never true. Each gets its own
  // rendering (2026-10-02, F10).
  if (settingsQuery.isLoading) {
    return (
      <section className="space-y-3">
        <SectionHeading>Check-in cadence</SectionHeading>
        <div className="rounded-xl border border-cream-muted bg-white px-5 py-4">
          <p className="text-sm text-ink-tertiary">Loading your cadence…</p>
        </div>
      </section>
    );
  }

  if (settingsQuery.isError || !settingsQuery.data) {
    return (
      <section className="space-y-3">
        <SectionHeading>Check-in cadence</SectionHeading>
        <div className="rounded-xl border border-cream-muted bg-white px-5 py-4 space-y-2">
          <p role="alert" className="text-sm text-ink-secondary">
            We couldn't load your cadence right now.
          </p>
          <button
            type="button"
            onClick={() => settingsQuery.refetch()}
            className="text-sm font-semibold text-forest-dark hover:underline"
          >
            Try again
          </button>
        </div>
      </section>
    );
  }

  return (
    <section className="space-y-3">
      <SectionHeading>Check-in cadence</SectionHeading>
      <div className="rounded-xl border border-cream-muted bg-white px-5 py-4 space-y-3">
        {/* `auto_slowed`, not `cadence === "monthly"`: since G21 a user can
            choose monthly themselves, and telling them we slowed it down
            because it's been quiet would be a story about a decision they
            made. The note belongs only to the drop the server performed. */}
        {settingsQuery.data.auto_slowed && (
          <p className="text-sm text-ink-secondary leading-relaxed">
            We've slowed these down to once a month since it's been quiet — no rush, and you can
            check in any time.
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          {CADENCE_OPTIONS.map((opt) => {
            const selected = cadence === opt.value;
            return (
              <button
                key={opt.value}
                type="button"
                aria-pressed={selected}
                onClick={() => updateSettings.mutate(opt.value)}
                disabled={updateSettings.isPending}
                className={[
                  "rounded-full border px-4 py-1.5 text-sm font-medium transition-colors disabled:opacity-50",
                  selected
                    ? "border-forest-dark bg-forest-dark text-white"
                    : "border-cream-muted bg-white text-ink-secondary hover:border-forest-light",
                ].join(" ")}
              >
                {opt.label}
              </button>
            );
          })}
        </div>
        {updateSettings.isError && (
          <p role="alert" className="text-xs text-red-700">
            We couldn't save that just now. Try again.
          </p>
        )}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function PulseTrendPage() {
  const navigate = useNavigate();
  const historyQuery = usePulseHistory();

  if (historyQuery.isLoading) {
    return (
      <div className="min-h-screen bg-cream-base flex flex-col items-center justify-center gap-4">
        <div className="w-8 h-8 rounded-full border-2 border-forest-light border-t-transparent animate-spin" />
        <p className="text-sm text-ink-secondary">Loading your pulse…</p>
      </div>
    );
  }

  if (historyQuery.isError || !historyQuery.data) {
    return (
      <div className="min-h-screen bg-cream-base flex items-center justify-center px-6">
        <div className="max-w-sm w-full rounded-lg border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-700">
          <p className="font-medium mb-1">We couldn't load your pulse right now.</p>
          <p className="text-xs">Please try again in a moment.</p>
          <button
            type="button"
            onClick={() => historyQuery.refetch()}
            className="mt-3 text-xs font-semibold text-red-700 underline"
          >
            Try again
          </button>
        </div>
      </div>
    );
  }

  // Newest first off the wire; the chart wants ascending (oldest first, left to right).
  const checkins = [...historyQuery.data.checkins].reverse();
  const events = historyQuery.data.events;
  const chartEvents = events.map((e) => ({
    date: e.at ?? "",
    label: EVENT_LABELS[e.event_type],
    note: e.note,
  }));

  return (
    <Shell>
      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={() => navigate("/job-seeker/dashboard")}
          className="flex items-center gap-1.5 text-sm font-semibold text-forest-dark hover:underline"
        >
          <span aria-hidden>←</span> Dashboard
        </button>
        <Link to="/pulse" className="text-sm font-semibold text-forest-dark hover:underline">
          Check in →
        </Link>
      </div>

      <div className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-widest text-forest-light">Pulse</p>
        <h1 className="font-display text-2xl sm:text-3xl font-semibold text-ink-primary">Your pulse</h1>
        {checkins.length > 0 && (
          <p className="text-sm text-ink-secondary">
            {checkins.length} check-in{checkins.length === 1 ? "" : "s"} logged.
          </p>
        )}
      </div>

      {checkins.length === 0 ? (
        <section className="rounded-xl border border-forest-light bg-forest-pale px-6 py-5 space-y-3">
          <p className="text-sm text-forest-dark font-medium leading-relaxed">
            Nothing to show yet. Your trend builds from check-ins — it takes about a minute.
          </p>
          <Link
            to="/pulse"
            className="inline-flex items-center bg-forest-dark text-white text-sm font-semibold px-6 py-3 rounded hover:bg-forest-mid transition-colors"
          >
            Check in now →
          </Link>
        </section>
      ) : (
        <>
          <ExperiencedSection checkins={checkins} events={chartEvents} />
          <DimensionsGrid checkins={checkins} />
        </>
      )}

      <LogChangeSection events={events} />
      <CadenceSection />
    </Shell>
  );
}
