import { CSSProperties, ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { Check } from "lucide-react";
import { Actions } from "./HeroActions";
import { PlaybookCard, PulseCard, SituationCard } from "./ResultCards";
import "./cards.css";
import "./scroll-story.css";

/**
 * A scroll-driven hero. The stage pins under the nav while the visitor
 * scrolls through five steps; each step swaps the words, rearranges the
 * example cards and shifts the background, so scrolling changes the page
 * rather than moving down it. After the last step the page scrolls on.
 *
 * Steps are driven by scroll position, not by timers, so the visitor stays in
 * control and can go back up. Dots on the right show the step and jump to it.
 * Every step's words are in the DOM; inactive ones are hidden with
 * `visibility`, so they cannot take keyboard focus while invisible.
 */

type CardId = "situation" | "pulse" | "playbook";
type Place = { x: number; y: number; s: number; o: number; z: number; r?: number };

type Step = {
  id: string;
  dot: string;
  tone: "cream" | "subtle" | "pale" | "dark";
  focus: CardId;
  body: ReactNode;
};

const STEPS: Step[] = [
  {
    id: "intro",
    dot: "Start",
    tone: "cream",
    focus: "pulse",
    body: (
      <>
        <h1 className="ss-h1">See how you actually work.</h1>
        <p className="ss-lead">
          Short assessments turn into a reading you can use: how you work, what your job costs you,
          and how to work with your manager.
        </p>
        <Actions center />
      </>
    ),
  },
  {
    id: "pulse",
    dot: "Work Pulse",
    tone: "subtle",
    focus: "pulse",
    body: (
      <>
        <h2 className="ss-h2">Answer twelve questions.</h2>
        <p className="ss-lead">
          Work Pulse™ asks how you actually work: your pace, how much structure you need, how you
          like feedback. You get a reading of your work style, not a score.
        </p>
      </>
    ),
  },
  {
    id: "situation",
    dot: "Situation Report",
    tone: "pale",
    focus: "situation",
    body: (
      <>
        <h2 className="ss-h2">See what your job is costing you.</h2>
        <p className="ss-lead">
          The Situation Report sets your current job against what you need from one, so you can see
          what's working and what's wearing you down.
        </p>
      </>
    ),
  },
  {
    id: "playbook",
    dot: "Manager Decoder",
    tone: "subtle",
    focus: "playbook",
    body: (
      <>
        <h2 className="ss-h2">Work with the manager you have.</h2>
        <p className="ss-lead">
          Manager Decoder turns a short profile of your manager into a playbook for working with
          them.
        </p>
      </>
    ),
  },
  {
    id: "checked",
    dot: "Checked by a person",
    tone: "dark",
    focus: "pulse",
    body: (
      <>
        <h2 className="ss-h2">Checked by a person. Kept from employers.</h2>
        <p className="ss-lead">
          Every reading is reviewed by someone before it reaches you. Your data is never sold, and
          never shown to an employer.
        </p>
        <Actions onDark />
      </>
    ),
  },
];

/*
 * Where each card sits at each step: centre x/y as % of the stage, scale,
 * opacity, stacking, and an optional tilt. Desktop and phone differ because
 * a phone has room for one card at a time.
 */
const WIDE: Record<CardId, Place>[] = [
  {
    situation: { x: 21, y: 76, s: 0.92, o: 1, z: 1 },
    pulse: { x: 50, y: 73, s: 0.96, o: 1, z: 3 },
    playbook: { x: 79, y: 78, s: 0.92, o: 1, z: 1 },
  },
  {
    situation: { x: 88, y: 26, s: 0.78, o: 0.35, z: 1 },
    pulse: { x: 68, y: 52, s: 1.08, o: 1, z: 3 },
    playbook: { x: 90, y: 80, s: 0.78, o: 0.35, z: 1 },
  },
  {
    situation: { x: 68, y: 50, s: 1.28, o: 1, z: 3 },
    pulse: { x: 88, y: 22, s: 0.72, o: 0.35, z: 1 },
    playbook: { x: 90, y: 82, s: 0.78, o: 0.35, z: 1 },
  },
  {
    situation: { x: 90, y: 80, s: 0.78, o: 0.35, z: 1 },
    pulse: { x: 88, y: 22, s: 0.72, o: 0.35, z: 1 },
    playbook: { x: 68, y: 50, s: 1.28, o: 1, z: 3 },
  },
  {
    situation: { x: 60, y: 55, s: 0.85, o: 1, z: 1, r: -5 },
    pulse: { x: 71, y: 50, s: 0.92, o: 1, z: 3 },
    playbook: { x: 82, y: 56, s: 0.85, o: 1, z: 2, r: 5 },
  },
];

function narrow(step: number): Record<CardId, Place> {
  const focus = STEPS[step].focus;
  const place = (id: CardId): Place =>
    id === focus ? { x: 50, y: 69, s: 0.9, o: 1, z: 3 } : { x: 50, y: 73, s: 0.82, o: 0, z: 1 };
  return { situation: place("situation"), pulse: place("pulse"), playbook: place("playbook") };
}

function placeStyle(p: Place): CSSProperties {
  return {
    left: `${p.x}%`,
    top: `${p.y}%`,
    opacity: p.o,
    zIndex: p.z,
    transform: `translate(-50%, -50%) scale(${p.s}) rotate(${p.r ?? 0}deg)`,
  };
}

function useWide() {
  const query = "(min-width: 900px)";
  const [wide, setWide] = useState(
    () => typeof window !== "undefined" && !!window.matchMedia?.(query).matches
  );
  useEffect(() => {
    const mq = window.matchMedia?.(query);
    if (!mq) return;
    const on = () => setWide(mq.matches);
    on();
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return wide;
}

export default function ScrollStory() {
  const ref = useRef<HTMLElement | null>(null);
  const [step, setStep] = useState(0);
  const wide = useWide();

  useEffect(() => {
    let frame = 0;
    const measure = () => {
      frame = 0;
      const el = ref.current;
      if (!el) return;
      const travel = el.offsetHeight - window.innerHeight;
      if (travel <= 0) return;
      const progress = Math.min(1, Math.max(0, -el.getBoundingClientRect().top / travel));
      setStep(Math.min(STEPS.length - 1, Math.floor(progress * STEPS.length)));
    };
    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(measure);
    };
    measure();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      if (frame) cancelAnimationFrame(frame);
    };
  }, []);

  const goTo = useCallback((i: number) => {
    const el = ref.current;
    if (!el) return;
    const travel = el.offsetHeight - window.innerHeight;
    const top = el.getBoundingClientRect().top + window.scrollY;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    window.scrollTo({ top: top + ((i + 0.5) / STEPS.length) * travel, behavior: reduce ? "auto" : "smooth" });
  }, []);

  const places = wide ? WIDE[step] : narrow(step);
  const tone = STEPS[step].tone;

  return (
    <section
      ref={ref}
      className="ss"
      style={{ "--steps": STEPS.length } as CSSProperties}
      aria-label="How Solverah works"
    >
      <div className={`ss-stage ss-tone-${tone}`} data-step={step}>
        <div className="ss-inner">
          {STEPS.map((s, i) => (
            <div
              key={s.id}
              className={`ss-text${i === 0 ? " ss-text--intro" : ""}`}
              data-active={i === step}
            >
              {s.body}
              {i === 4 && (
                <ul className="ss-promise">
                  {["Read by a person", "Never sold", "Never shown to employers"].map((t) => (
                    <li key={t}>
                      <Check aria-hidden />
                      {t}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}

          <div className="ss-cards" role="img" aria-label="Example Solverah results: a Work Pulse reading, a Situation Report and a manager playbook.">
            <div className="ss-card ss-card--wide" style={placeStyle(places.pulse)}>
              <PulseCard />
            </div>
            <div className="ss-card" style={placeStyle(places.situation)}>
              <SituationCard />
            </div>
            <div className="ss-card" style={placeStyle(places.playbook)}>
              <PlaybookCard />
            </div>
          </div>

          <p className="ss-note">Example results. Yours come from your own answers.</p>

        </div>
        <nav className="ss-dots" aria-label="Story steps">
          {STEPS.map((s, i) => (
            <button
              key={s.id}
              type="button"
              aria-label={s.dot}
              aria-current={i === step ? "step" : undefined}
              onClick={() => goTo(i)}
            />
          ))}
        </nav>
      </div>
    </section>
  );
}
