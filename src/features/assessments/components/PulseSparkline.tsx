/**
 * PulseSparkline -- the one chart type B-3 needs: a small multiple over time,
 * one series, sometimes with dated annotations. Built to the dataviz skill's
 * mark specs (2px line, >=8px / r>=4 markers with a 2px surface ring, a 24px
 * hit target per point, hover+focus parity) rather than a chart dependency,
 * per BUILD_PLAN B-3's brief.
 *
 * ONE SERIES, SO NO LEGEND. Every call site plots exactly one line -- the
 * per-dimension trend, the experienced line, or the two-point "this week vs
 * last" comparison -- so the chart's own heading names what's plotted and a
 * legend box would restate it (marks-and-anatomy.md: "a single series needs
 * no legend box").
 *
 * DEGRADES ON POINT COUNT, NOT A SEPARATE COMPONENT. Zero points renders
 * nothing (the caller writes the empty-state copy, which varies by context).
 * One point renders a single dot with no line -- there is nothing to connect.
 * Two or more draws the line. This mirrors BUILD_PLAN B-3's "degrade
 * gracefully at 1-2 points" for both the compact dashboard/confirmation use
 * and the full trend view.
 *
 * `compact` (the dashboard card, the post-check-in "one thing back" screen)
 * turns off hover and event annotations -- those call sites already say
 * everything the chart could add in a sentence beside it, and a hit-target
 * layer on a 60px-wide sparkline has no room to be useful.
 */
import { useId, useState } from "react";

const DEFAULT_COLOR = "#2D6A4F"; // forest-mid
const EVENT_TICK_COLOR = "#888888"; // ink-tertiary
const SURFACE = "#FFFFFF";

export interface PulseSparklinePoint {
  /** ISO-8601 date/datetime. */
  date: string;
  value: number;
}

export interface PulseSparklineEvent {
  date: string;
  label: string;
  note?: string | null;
}

interface Props {
  points: PulseSparklinePoint[];
  events?: PulseSparklineEvent[];
  min?: number;
  max?: number;
  width?: number;
  height?: number;
  color?: string;
  compact?: boolean;
  ariaLabel: string;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export default function PulseSparkline({
  points,
  events = [],
  min = 1,
  max = 5,
  width = 240,
  height = 56,
  color = DEFAULT_COLOR,
  compact = false,
  ariaLabel,
}: Props) {
  const uid = useId();
  const [activePoint, setActivePoint] = useState<number | null>(null);
  const [activeEvent, setActiveEvent] = useState<number | null>(null);

  const padX = 10;
  const padY = 10;
  const plotW = width - padX * 2;
  const plotH = height - padY * 2;

  const yFor = (value: number) => padY + plotH * (1 - (value - min) / (max - min || 1));

  if (points.length === 0) return null;

  if (points.length === 1) {
    const cy = yFor(points[0].value);
    return (
      <svg width={width} height={height} role="img" aria-label={ariaLabel}>
        <circle cx={width / 2} cy={cy} r={4} fill={color} stroke={SURFACE} strokeWidth={2} />
      </svg>
    );
  }

  const times = points.map((p) => new Date(p.date).getTime());
  const eventTimes = !compact ? events.map((e) => new Date(e.date).getTime()) : [];
  const allTimes = [...times, ...eventTimes];
  const minT = Math.min(...allTimes);
  const maxT = Math.max(...allTimes);
  const span = maxT - minT || 1;

  const xFor = (t: number) => padX + plotW * ((t - minT) / span);

  const coords = points.map((p, i) => ({ x: xFor(times[i]), y: yFor(p.value), p }));
  const path = coords.map((c, i) => `${i === 0 ? "M" : "L"}${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(" ");

  const activeTooltip =
    activePoint !== null
      ? { x: coords[activePoint].x, y: coords[activePoint].y, text: `${formatDate(coords[activePoint].p.date)}: ${coords[activePoint].p.value}` }
      : activeEvent !== null && !compact
        ? (() => {
            const e = events[activeEvent];
            const x = xFor(new Date(e.date).getTime());
            return { x, y: height - padY, text: e.note ? `${e.label} — ${formatDate(e.date)}: ${e.note}` : `${e.label} — ${formatDate(e.date)}` };
          })()
        : null;

  return (
    <div style={{ position: "relative", width, height }}>
      <svg width={width} height={height} role="img" aria-label={ariaLabel}>
        {!compact &&
          events.map((e, i) => {
            const x = xFor(new Date(e.date).getTime());
            return (
              <g key={`${uid}-event-${i}`}>
                <line
                  x1={x}
                  x2={x}
                  y1={padY}
                  y2={height - padY}
                  stroke={EVENT_TICK_COLOR}
                  strokeOpacity={0.4}
                  strokeWidth={1}
                  strokeDasharray="2,2"
                />
                <circle cx={x} cy={height - padY} r={3} fill={EVENT_TICK_COLOR} fillOpacity={0.7} />
                {/* Hit target, bigger than the mark -- 24px, keyboard-reachable. */}
                <circle
                  cx={x}
                  cy={height - padY}
                  r={12}
                  fill="transparent"
                  tabIndex={0}
                  role="button"
                  aria-label={e.note ? `${e.label} on ${formatDate(e.date)}: ${e.note}` : `${e.label} on ${formatDate(e.date)}`}
                  onMouseEnter={() => setActiveEvent(i)}
                  onMouseLeave={() => setActiveEvent((cur) => (cur === i ? null : cur))}
                  onFocus={() => setActiveEvent(i)}
                  onBlur={() => setActiveEvent((cur) => (cur === i ? null : cur))}
                />
              </g>
            );
          })}

        <path d={path} fill="none" stroke={color} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />

        {coords.map((c, i) => (
          <g key={`${uid}-point-${i}`}>
            <circle cx={c.x} cy={c.y} r={4} fill={color} stroke={SURFACE} strokeWidth={2} />
            {!compact && (
              <circle
                cx={c.x}
                cy={c.y}
                r={12}
                fill="transparent"
                tabIndex={0}
                role="button"
                aria-label={`${formatDate(c.p.date)}: ${c.p.value}`}
                onMouseEnter={() => setActivePoint(i)}
                onMouseLeave={() => setActivePoint((cur) => (cur === i ? null : cur))}
                onFocus={() => setActivePoint(i)}
                onBlur={() => setActivePoint((cur) => (cur === i ? null : cur))}
              />
            )}
          </g>
        ))}
      </svg>

      {activeTooltip && (
        <div
          role="status"
          className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full whitespace-nowrap rounded border border-cream-muted bg-white px-2 py-1 text-xs font-medium text-ink-primary shadow-sm"
          style={{ left: activeTooltip.x, top: Math.max(activeTooltip.y - 6, 0) }}
        >
          {activeTooltip.text}
        </div>
      )}
    </div>
  );
}
