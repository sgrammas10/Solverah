import { CSSProperties, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  Activity,
  BookOpenText,
  CalendarCheck,
  ClipboardList,
  FileText,
  Focus,
  Route,
  ScanText,
  UsersRound,
  type LucideIcon,
} from "lucide-react";
import "./ecosystem.css";

/**
 * The Solverah ecosystem on the landing page: one profile at the centre, the
 * instruments and readings around it.
 *
 * Adapted from a 21st.dev "integration card". The hub keeps that card's
 * geometry (564x410 canvas, orthogonal wires, a light travelling each wire)
 * but drops its dependencies: `motion` and `@base-ui/react` would have gone
 * into the entry bundle, which sits right under its CI budget, so the
 * animation is CSS (packets of light travel each edge and light the nodes at
 * each end, every edge on its own interval) and the button is the page's own. This module is
 * lazy-loaded, with its own stylesheet, so it adds nothing to first paint.
 *
 * Split is the chosen layout (2026-09-28, "for now"). The card and flow
 * layouts stay reachable with `?eco=card|split|flow|off`, and in development a
 * switcher in the corner flips between them.
 */

type Icon = LucideIcon;

export const VARIANTS = ["card", "split", "flow", "off"] as const;
export type EcoVariant = (typeof VARIANTS)[number];
const DEFAULT_VARIANT: EcoVariant = "split";

type HubNode = {
  id: string;
  name: string;
  line: string;
  icon: Icon;
  x: number;
  y: number;
  path: string;
};

// Canvas is 564 x 410, centre (282, 205). Positions and wires are the
// source card's, so the composition it was chosen for survives.
export const HUB_NODES: HubNode[] = [
  {
    id: "work-pulse",
    name: "Work Pulse™",
    line: "Twelve questions on how you work: pace, structure, autonomy, feedback.",
    icon: Activity,
    x: 110,
    y: 90,
    path: "M 270 205 V 105 Q 270 90 255 90 H 110",
  },
  {
    id: "focus-type",
    name: "FocusType",
    line: "How you actually focus, and what breaks it.",
    icon: Focus,
    x: 360,
    y: 70,
    path: "M 294 205 V 85 Q 294 70 309 70 H 360",
  },
  {
    id: "manager-match",
    name: "ManagerMatch™",
    line: "The kind of manager you do your best work under.",
    icon: UsersRound,
    x: 160,
    y: 205,
    path: "M 250 205 H 160",
  },
  {
    id: "situation-report",
    name: "Situation Report",
    line: "Your current job, read against what you need from one.",
    icon: ClipboardList,
    x: 480,
    y: 205,
    path: "M 314 205 H 480",
  },
  {
    id: "manager-decoder",
    name: "Manager Decoder",
    line: "Profile the manager you have, and get a playbook for working with them.",
    icon: BookOpenText,
    x: 282,
    y: 360,
    path: "M 282 205 V 360",
  },
  {
    id: "path-intelligence",
    name: "Path Intelligence",
    line: "Roles that would give you more, or less, of the work you do now.",
    icon: Route,
    x: 460,
    y: 340,
    path: "M 314 215 V 325 Q 314 340 329 340 H 460",
  },
];

type FlowItem = { name: string; icon: Icon };

const FLOW_IN: FlowItem[] = [
  { name: "Your resume", icon: FileText },
  { name: "Work Pulse™", icon: Activity },
  { name: "FocusType", icon: Focus },
  { name: "ManagerMatch™", icon: UsersRound },
  { name: "Weekly pulse check-ins", icon: CalendarCheck },
];

const FLOW_OUT: FlowItem[] = [
  { name: "Your reading", icon: ScanText },
  { name: "Situation Report", icon: ClipboardList },
  { name: "Manager playbook", icon: BookOpenText },
  { name: "Path Intelligence", icon: Route },
];

/**
 * Each edge's cycle, in seconds: [length, start]. Uneven on purpose, so the
 * packets never line up into a single beat. The node, its edge's glow and its
 * packet all read the same pair, which is what keeps a node lighting exactly
 * as its packet leaves and comes home.
 */
const HUB_TIMING: [number, number][] = [
  [4.6, 0],
  [5.8, 1.4],
  [4.0, 2.6],
  [6.2, 0.6],
  [5.0, 3.4],
  [5.4, 2.0],
];
const IN_TIMING: [number, number][] = [
  [5.2, 0],
  [4.4, 1.1],
  [6.0, 2.3],
  [4.8, 0.5],
  [5.6, 3.0],
];
const OUT_TIMING: [number, number][] = [
  [5.0, 1.8],
  [5.8, 3.2],
  [4.6, 2.4],
  [6.4, 0.9],
];

function cycle([dur, d]: [number, number]) {
  return { "--dur": `${dur}s`, "--d": `${d}s` } as CSSProperties;
}

const HUB_LABEL = `Solverah at the centre, connected to ${HUB_NODES.map((n) => n.name).join(", ")}.`;

const CONTAINER = "mx-auto w-full max-w-[1180px] px-6";
const H2 =
  "font-headline text-[clamp(2rem,4.2vw,3.1rem)] font-extrabold leading-[1.02] tracking-[-0.02em] text-balance";
const PRIMARY =
  "inline-flex items-center justify-center rounded-[4px] bg-forest-dark px-7 py-3.5 font-headline text-[0.98rem] font-bold text-white transition-colors hover:bg-forest-mid";

/** Adds `is-in` once the element scrolls into view, so the nodes arrive then. */
function useInView<T extends Element>() {
  const ref = useRef<T | null>(null);
  const [inView, setInView] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (typeof IntersectionObserver === "undefined") {
      setInView(true);
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setInView(true);
          io.disconnect();
        }
      },
      { threshold: 0.25 }
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  return { ref, inView };
}

function Mark({ static: isStatic = false }: { static?: boolean }) {
  return (
    <div className={`eco-center${isStatic ? " eco-center--static" : ""}`} aria-hidden="true">
      <div className="eco-mark">S</div>
      <div className="eco-ring" />
    </div>
  );
}

function Hub({ active }: { active?: string | null }) {
  const { ref, inView } = useInView<HTMLDivElement>();

  return (
    <div ref={ref} className={`eco-hub${inView ? " is-in" : ""}`} role="img" aria-label={HUB_LABEL}>
      <svg viewBox="0 0 564 410" fill="none" aria-hidden="true">
        {HUB_NODES.map((n, i) => (
          <g key={n.id} style={cycle(HUB_TIMING[i])}>
            <path className="eco-line-base" d={n.path} />
            <path className="eco-edge-glow" d={n.path} />
            <path className="eco-packet" d={n.path} pathLength={200} />
            <path className="eco-line-active" d={n.path} data-active={active === n.id} />
          </g>
        ))}
      </svg>

      <Mark />

      {HUB_NODES.map((n, i) => {
        const Glyph = n.icon;
        return (
          <div
            key={n.id}
            aria-hidden="true"
            data-node={n.id}
            data-active={active === n.id}
            className="eco-node"
            style={
              {
                left: `${(n.x / 564) * 100}%`,
                top: `${(n.y / 410) * 100}%`,
                "--in": `${0.1 + i * 0.1}s`,
                ...cycle(HUB_TIMING[i]),
              } as CSSProperties
            }
          >
            <Glyph aria-hidden />
          </div>
        );
      })}
    </div>
  );
}

function CardVariant() {
  return (
    <div className="eco-card">
      <div className="eco-visual">
        <Hub />
      </div>
      <div className="eco-card-body">
        <div>
          <h2 className="eco-card-title">One profile, read six ways.</h2>
          <p className="eco-body" style={{ marginTop: "0.5rem" }}>
            Every instrument in Solverah adds to the same profile, so each new reading starts from
            what you've already told us.
          </p>
        </div>
        <a href="#how-it-reads" className={`${PRIMARY} self-start`}>
          See how a reading is made
        </a>
      </div>
    </div>
  );
}

function SplitVariant() {
  const [active, setActive] = useState<string | null>(null);

  return (
    <div className="eco-split">
      <div>
        <h2 className={H2}>Six instruments, one profile.</h2>
        <p className="eco-body" style={{ marginTop: "1.25rem" }}>
          Each one adds to the same profile, so every new reading starts from what you've already
          told us.
        </p>
        <ul className="eco-list">
          {HUB_NODES.map((n) => {
            const Glyph = n.icon;
            return (
              <li
                key={n.id}
                data-active={active === n.id}
                onMouseEnter={() => setActive(n.id)}
                onMouseLeave={() => setActive(null)}
              >
                <span className="eco-list-icon" aria-hidden="true">
                  <Glyph aria-hidden />
                </span>
                <div>
                  <p className="eco-list-name">{n.name}</p>
                  <p className="eco-list-line">{n.line}</p>
                </div>
              </li>
            );
          })}
        </ul>
      </div>
      <div className="eco-visual">
        <Hub active={active} />
      </div>
    </div>
  );
}

/** Curves from each row's centre to the middle of the far edge (or back). */
function Wires({ timing, direction }: { timing: [number, number][]; direction: "in" | "out" }) {
  const rows = timing.length;
  return (
    <svg className="eco-wire" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
      {Array.from({ length: rows }, (_, i) => {
        const y = ((i + 0.5) / rows) * 100;
        const d =
          direction === "in" ? `M 0 ${y} C 55 ${y}, 45 50, 100 50` : `M 0 50 C 55 50, 45 ${y}, 100 ${y}`;
        return (
          <g key={i} style={cycle(timing[i])}>
            <path className="eco-line-base" d={d} vectorEffect="non-scaling-stroke" />
            <path className="eco-edge-glow" d={d} vectorEffect="non-scaling-stroke" />
            <path className="eco-packet" d={d} pathLength={200} vectorEffect="non-scaling-stroke" />
          </g>
        );
      })}
    </svg>
  );
}

function FlowColumn({
  label,
  items,
  timing,
  out = false,
}: {
  label: string;
  items: FlowItem[];
  timing: [number, number][];
  out?: boolean;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      <p className="eco-col-label">{label}</p>
      <ul className="eco-col" style={{ flex: 1 }}>
        {items.map(({ name, icon: Glyph }, i) => (
          <li key={name} className={`eco-item${out ? " eco-item--out" : ""}`} style={cycle(timing[i])}>
            <Glyph aria-hidden />
            {name}
          </li>
        ))}
      </ul>
    </div>
  );
}

function FlowVariant() {
  return (
    <>
      <div className="grid gap-5 md:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] md:items-end md:gap-20">
        <h2 className={H2}>What goes in, what comes back.</h2>
        <p className="eco-body">
          Everything you tell Solverah lands in one profile. Every reading draws on all of it, and a
          person checks it before it reaches you.
        </p>
      </div>
      <FlowDiagram />
    </>
  );
}

/** Inputs, the hub, and outputs, wired together. */
function FlowDiagram({ className = "" }: { className?: string }) {
  return (
    <div className={`eco-field ${className}`.trim()}>
        <div className="eco-flow">
          <FlowColumn label="What you give" items={FLOW_IN} timing={IN_TIMING} />
          <div className="eco-wire-cell">
            <Wires timing={IN_TIMING} direction="in" />
          </div>
          <div className="eco-flow-center">
            <div className="eco-flow-hub">
              <Mark static />
              <p className="eco-flow-caption">One profile, checked by a person</p>
            </div>
          </div>
          <div className="eco-wire-cell">
            <Wires timing={OUT_TIMING} direction="out" />
          </div>
          <FlowColumn label="What comes back" items={FLOW_OUT} timing={OUT_TIMING} out />
        </div>
    </div>
  );
}

function DevSwitcher({ current, onPick }: { current: EcoVariant; onPick: (v: EcoVariant) => void }) {
  return (
    <div className="eco-switch" role="group" aria-label="Ecosystem layout (development only)">
      <span>Ecosystem</span>
      {VARIANTS.map((v) => (
        <button key={v} type="button" aria-pressed={current === v} onClick={() => onPick(v)}>
          {v}
        </button>
      ))}
    </div>
  );
}

export default function EcosystemSection() {
  const [params, setParams] = useSearchParams();
  const raw = params.get("eco");
  const variant: EcoVariant = (VARIANTS as readonly string[]).includes(raw ?? "")
    ? (raw as EcoVariant)
    : DEFAULT_VARIANT;

  const pick = (v: EcoVariant) => {
    const next = new URLSearchParams(params);
    next.set("eco", v);
    setParams(next, { replace: true, preventScrollReset: true });
  };

  return (
    <div className="eco">
      {variant !== "off" && (
        <section id="ecosystem" className="scroll-mt-16 border-t border-cream-muted">
          <div className={`${CONTAINER} py-20 md:py-28`}>
            {variant === "card" && <CardVariant />}
            {variant === "split" && <SplitVariant />}
            {variant === "flow" && <FlowVariant />}
          </div>
        </section>
      )}
      {import.meta.env.DEV && <DevSwitcher current={variant} onPick={pick} />}
    </div>
  );
}
