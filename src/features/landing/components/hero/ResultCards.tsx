import { ReactNode } from "react";
import { BookOpenText, Check, ClipboardList, ScanText } from "lucide-react";

/**
 * Example result cards: a Work Pulse reading, a Situation Report and a
 * manager playbook. Demonstration content, always shown with an "Example"
 * note nearby. Used by the scroll story. Styles live in cards.css.
 */

function ResultCard({
  icon,
  kicker,
  title,
  children,
  className = "",
}: {
  icon: ReactNode;
  kicker: string;
  title: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`ht-result ${className}`.trim()} aria-hidden="true">
      <div className="ht-result-head">
        <span className="ht-result-icon">{icon}</span>
        <span>{kicker}</span>
      </div>
      <p className="ht-result-title">{title}</p>
      {children}
    </div>
  );
}

export function SituationCard({ className }: { className?: string }) {
  return (
    <ResultCard
      className={className}
      icon={<ClipboardList aria-hidden />}
      kicker="Situation Report"
      title="Where your job fits you"
    >
      <ul className="ht-rows">
        <li>
          <span>Autonomy</span>
          <b className="ht-ok">Aligned</b>
        </li>
        <li>
          <span>Pace</span>
          <b className="ht-warn">Costing you</b>
        </li>
        <li>
          <span>Feedback</span>
          <b className="ht-ok">Aligned</b>
        </li>
      </ul>
    </ResultCard>
  );
}

export function PulseCard({ className }: { className?: string }) {
  return (
    <ResultCard
      className={className}
      icon={<ScanText aria-hidden />}
      kicker="Work Pulse™ reading"
      title="The Autonomist"
    >
      <p className="ht-result-text">
        You do your best work with a clear goal and room to decide how to reach it. Close oversight
        drains you faster than hard problems do.
      </p>
      <ul className="ht-rows">
        <li>
          <span>Autonomy need</span>
          <b>High</b>
        </li>
        <li>
          <span>Structure need</span>
          <b>Low</b>
        </li>
        <li>
          <span>Pace preference</span>
          <b>Fast, with one clear owner</b>
        </li>
      </ul>
      <p className="ht-result-check">
        <Check aria-hidden /> Checked by a person
      </p>
    </ResultCard>
  );
}

export function PlaybookCard({ className }: { className?: string }) {
  return (
    <ResultCard
      className={className}
      icon={<BookOpenText aria-hidden />}
      kicker="Manager playbook"
      title="Working with a hands-on manager"
    >
      <ul className="ht-bullets">
        <li>Agree on the goal, then ask for room on the how.</li>
        <li>Send a short update before they have to ask.</li>
      </ul>
    </ResultCard>
  );
}
