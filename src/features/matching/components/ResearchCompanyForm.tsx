/**
 * "Research a company": name a company, we research it in the background.
 *
 * POST /companies/research answers 202 with a run (or a finished cached one); the
 * run is then polled (usePoll: 3 s, backing off) until done or failed, and every
 * CompanyLens query is refreshed when it finishes. Progress is announced in a
 * polite live region, so a screen reader hears "researching", then "done",
 * without focus moving.
 *
 * With `fixedName` the input is not shown, only a button: the company page uses
 * that to offer research on the company it is already showing.
 */
import { useId, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { useResearchCompany, type ResearchCompany } from "../useCompanyLens";
import type { PollTiming } from "../usePoll";
import {
  BODY_MUTED,
  INPUT,
  LABEL,
  PRIMARY_BUTTON,
  QUIET_BUTTON,
  TEXT_LINK,
} from "../lensStyles";

interface ResearchCompanyFormProps {
  /** Research this company by name; no input is shown. */
  fixedName?: string;
  /** Hide the "open the read" link on done (the page already shows the company). */
  hideOpenLink?: boolean;
  /** Override the polling schedule (tests). */
  pollTiming?: PollTiming;
}

const START_PROBLEMS: Record<NonNullable<ResearchCompany["problem"]>, string> = {
  daily_limit:
    "You've started research on five new companies today, which is the daily limit. Companies that are already researched are always free to look at, and you can start more tomorrow.",
  busy: "That was a lot of requests in a short time. Wait a minute, then try again.",
  unavailable: "Company research isn't available right now. Please try again a little later.",
  invalid: "Enter a company name to research.",
  other: "Something went wrong starting that research. Please try again.",
  lost: "We lost track of that research. Come back in a few minutes and refresh the page to see whether it finished.",
};

function progressText(research: ResearchCompany, name: string): string {
  switch (research.phase) {
    case "starting":
      return `Starting research on ${name}...`;
    case "queued":
      return `${name} is in the queue. Research usually takes a few minutes, and it keeps going if you leave this page.`;
    case "running":
      return `Researching ${name}: reading what's public about how work runs there. It keeps going if you leave this page.`;
    case "done":
      return research.cached
        ? `${name} was already researched, so there was nothing to wait for.`
        : `Research on ${name} is finished.`;
    case "failed":
      return `We couldn't finish researching ${name}. Please try again later.`;
    case "error":
      return research.problem ? START_PROBLEMS[research.problem] : START_PROBLEMS.other;
    default:
      return "";
  }
}

export default function ResearchCompanyForm({
  fixedName,
  hideOpenLink = false,
  pollTiming,
}: ResearchCompanyFormProps) {
  const research = useResearchCompany(pollTiming);
  const [name, setName] = useState(fixedName ?? "");
  const [submitted, setSubmitted] = useState("");
  const [emptyError, setEmptyError] = useState(false);
  const inputId = useId();
  const hintId = useId();

  const busy =
    research.phase === "starting" || research.phase === "queued" || research.phase === "running";

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = (fixedName ?? name).trim();
    if (!trimmed) {
      setEmptyError(true);
      return;
    }
    setEmptyError(false);
    setSubmitted(trimmed);
    research.start(trimmed);
  };

  const shownName = research.run?.company?.name ?? submitted;
  const message = emptyError ? START_PROBLEMS.invalid : progressText(research, shownName);
  const isProblem =
    emptyError || research.phase === "error" || research.phase === "failed";
  const companyId = research.run?.company_id;

  return (
    <form onSubmit={onSubmit} className="space-y-3" noValidate>
      {fixedName ? (
        <button type="submit" className={PRIMARY_BUTTON} disabled={busy}>
          {busy ? "Researching..." : `Research ${fixedName}`}
        </button>
      ) : (
        <div className="space-y-2">
          <label htmlFor={inputId} className={LABEL}>
            Research a company
          </label>
          <p id={hintId} className={BODY_MUTED}>
            Name any company. We read what's public about how work runs there and add it to your
            list.
          </p>
          <div className="flex flex-col gap-2 sm:flex-row">
            <input
              id={inputId}
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              aria-describedby={hintId}
              aria-invalid={emptyError || undefined}
              autoComplete="organization"
              placeholder="Company name"
              className={INPUT}
              disabled={busy}
            />
            <button type="submit" className={`${QUIET_BUTTON} shrink-0 justify-center`} disabled={busy}>
              {busy ? "Researching..." : "Research"}
            </button>
          </div>
        </div>
      )}

      <div role="status" aria-live="polite" className="space-y-1">
        {message && (
          <p className={isProblem ? "text-[0.93rem] leading-[1.55] text-red-800" : BODY_MUTED}>
            {message}
          </p>
        )}
        {research.phase === "done" && companyId != null && !hideOpenLink && (
          <p>
            <Link to={`/companies/${companyId}`} className={`${TEXT_LINK} text-[0.93rem]`}>
              Open the read on {shownName}
            </Link>
          </p>
        )}
      </div>
    </form>
  );
}
