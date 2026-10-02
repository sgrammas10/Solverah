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
 * turns off hover, axes and event annotations -- those call sites already say
 * everything the chart could add in a sentence beside it, and a hit-target
 * layer on a 60px-wide sparkline has no room to be useful.
 *
 * RESPONSIVE (2026-10-02, F2). The SVG carries a `viewBox` and is `width:
 * 100%` of its container, so it never forces a horizontal scroll at phone
 * width. `width`/`height` are the viewBox's logical size. Where
 * `ResizeObserver` exists the logical width follows the container's measured
 * width, so text and hit targets render 1:1 rather than shrinking with the
 * viewBox on a narrow screen; where it does not (jsdom), the `width` prop is
 * the logical width and the viewBox scales. Tooltips are positioned in
 * percentages of the logical size so they land on the mark either way, and
 * they wrap rather than run off the edge.
 */
import { useEffect, useId, useRef, useState } from "react";

const DEFAULT_COLOR = "#2D6A4F"; // forest-mid
const EVENT_TICK_COLOR = "#888888"; // ink-tertiary
const AXIS_COLOR = "#888888"; // ink-tertiary
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
  /** Logical (viewBox) width; the rendered width is always the container's. */
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

/** The container's measured width, or null where nothing can measure it. */
function useMeasuredWidth(ref: React.RefObject<HTMLDivElement | null>): number | null {
  const [measured, setMeasured] = useState<number | null>(null);
  useEffect(() => {
    const element = ref.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver((entries) => {
      const next = entries[0]?.contentRect.width;
      if (next && next > 0) setMeasured(Math.round(next));
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [ref]);
  return measured;
}

export default function PulseSparkline({
  points,
  events = [],
  min = 1,
  max = 5,
  width: widthProp = 240,
  height = 56,
  color = DEFAULT_COLOR,
  compact = false,
  ariaLabel,
}: Props) {
  const uid = useId();
  const containerRef = useRef<HTMLDivElement>(null);
  const measuredWidth = useMeasuredWidth(containerRef);
  const [activePoint, setActivePoint] = useState<number | null>(null);
  const [activeEvent, setActiveEvent] = useState<number | null>(null);

  const width = measuredWidth ?? widthProp;
  const axes = !compact;
  const padLeft = axes ? 22 : 10;
  const padRight = 10;
  const padTop = 10;
  const padBottom = axes ? 20 : 10;
  const plotW = width - padLeft - padRight;
  const plotH = height - padTop - padBottom;

  const yFor = (value: number) => padTop + plotH * (1 - (value - min) / (max - min || 1));

  if (points.length === 0) return null;

  // Every whole value from min to max when there is room for them; the two
  // ends otherwise (a 72px dimension card cannot space five labels).
  const yTicks =
    plotH >= 60
      ? Array.from({ length: max - min + 1 }, (_, i) => min + i)
      : [min, max];

  const svgProps = {
    viewBox: `0 0 ${width} ${height}`,
    width: "100%" as const,
    role: "img" as const,
    "aria-label": ariaLabel,
    style: { display: "block", height: "auto", overflow: "visible" as const },
  };

  const yAxis = axes && (
    <g aria-hidden="true">
      {yTicks.map((tick) => (
        <g key={`${uid}-y-${tick}`}>
          <line
            x1={padLeft}
            x2={width - padRight}
            y1={yFor(tick)}
            y2={yFor(tick)}
            stroke={AXIS_COLOR}
            strokeOpacity={0.15}
            strokeWidth={1}
          />
          <text
            x={padLeft - 6}
            y={yFor(tick)}
            textAnchor="end"
            dominantBaseline="middle"
            fontSize={10}
            fill={AXIS_COLOR}
          >
            {tick}
          </text>
        </g>
      ))}
    </g>
  );

  if (points.length === 1) {
    const cy = yFor(points[0].value);
    const cx = padLeft + plotW / 2;
    return (
      <div ref={containerRef} style={{ position: "relative", width: "100%" }}>
        <svg {...svgProps}>
          {yAxis}
          <circle cx={cx} cy={cy} r={4} fill={color} stroke={SURFACE} strokeWidth={2} />
          {axes && (
            <text
              x={cx}
              y={height - 4}
              textAnchor="middle"
              fontSize={10}
              fill={AXIS_COLOR}
              aria-hidden="true"
            >
              {formatDate(points[0].date)}
            </text>
          )}
        </svg>
      </div>
    );
  }

  const times = points.map((p) => new Date(p.date).getTime());
  const eventTimes = !compact ? events.map((e) => new Date(e.date).getTime()) : [];
  const allTimes = [...times, ...eventTimes];
  const minT = Math.min(...allTimes);
  const maxT = Math.max(...allTimes);
  const span = maxT - minT || 1;

  const xFor = (t: number) => padLeft + plotW * ((t - minT) / span);

  const coords = points.map((p, i) => ({ x: xFor(times[i]), y: yFor(p.value), p }));
  const path = coords.map((c, i) => `${i === 0 ? "M" : "L"}${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(" ");

  const activeTooltip =
    activePoint !== null
      ? { x: coords[activePoint].x, y: coords[activePoint].y, text: `${formatDate(coords[activePoint].p.date)}: ${coords[activePoint].p.value}` }
      : activeEvent !== null && !compact
        ? (() => {
            const e = events[activeEvent];
            const x = xFor(new Date(e.date).getTime());
            return { x, y: padTop + plotH, text: e.note ? `${e.label} — ${formatDate(e.date)}: ${e.note}` : `${e.label} — ${formatDate(e.date)}` };
          })()
        : null;

  // Anchor the tooltip so it never runs past either edge: hugging the left
  // edge near the start, the right edge near the end, centred otherwise.
  const tooltipShift =
    activeTooltip === null
      ? ""
      : activeTooltip.x < width * 0.25
        ? "translate-x-0"
        : activeTooltip.x > width * 0.75
          ? "-translate-x-full"
          : "-translate-x-1/2";

  // The leftmost and rightmost dates label the time axis; between them the
  // marks (and their tooltips) carry the dates.
  const xLabels = axes
    ? [
        { x: padLeft, anchor: "start" as const, text: formatDate(new Date(minT).toISOString()) },
        { x: width - padRight, anchor: "end" as const, text: formatDate(new Date(maxT).toISOString()) },
      ]
    : [];

  return (
    <div ref={containerRef} style={{ position: "relative", width: "100%" }}>
      <svg {...svgProps}>
        {yAxis}
        {xLabels.map((label) => (
          <text
            key={`${uid}-x-${label.anchor}`}
            x={label.x}
            y={height - 4}
            textAnchor={label.anchor}
            fontSize={10}
            fill={AXIS_COLOR}
            aria-hidden="true"
          >
            {label.text}
          </text>
        ))}

        {!compact &&
          events.map((e, i) => {
            const x = xFor(new Date(e.date).getTime());
            return (
              <g key={`${uid}-event-${i}`}>
                <line
                  x1={x}
                  x2={x}
                  y1={padTop}
                  y2={padTop + plotH}
                  stroke={EVENT_TICK_COLOR}
                  strokeOpacity={0.4}
                  strokeWidth={1}
                  strokeDasharray="2,2"
                />
                <circle cx={x} cy={padTop + plotH} r={3} fill={EVENT_TICK_COLOR} fillOpacity={0.7} />
                {/* Hit target, bigger than the mark -- 24px, keyboard-reachable. */}
                <circle
                  cx={x}
                  cy={padTop + plotH}
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
          className={`pointer-events-none absolute z-10 w-max max-w-[14rem] ${tooltipShift} -translate-y-full whitespace-normal break-words rounded border border-cream-muted bg-white px-2 py-1 text-xs font-medium text-ink-primary shadow-sm`}
          style={{
            left: `${(activeTooltip.x / width) * 100}%`,
            top: `${(Math.max(activeTooltip.y - 6, 0) / height) * 100}%`,
          }}
        >
          {activeTooltip.text}
        </div>
      )}
    </div>
  );
}
