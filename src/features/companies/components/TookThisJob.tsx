/**
 * "I took this job": link the user to this company from a start date.
 *
 * The link is how later Pulse check-ins are tied back to this read (PRODUCT_DECISIONS
 * §2, what changes the weights, item 4): directional evidence on whether the read
 * was right. "I left this job" closes it with a last day (PATCH ended_on); an ended
 * link reads as past and the form shows again. It can be removed at any time.
 */
import { useId, useState, type FormEvent } from "react";

import { BODY_MUTED, LABEL, PANEL, QUIET_BUTTON, REPORT_H2, formatDay } from "../../matching";
import { ApiError } from "../../../shared/api/apiError";
import {
  useCompanyLinks,
  useCreateCompanyLink,
  useDeleteCompanyLink,
  useEndCompanyLink,
} from "../useCompanyRead";

const DATE_INPUT =
  "rounded-[4px] border border-cream-muted bg-white px-3 py-2 text-[0.95rem] text-ink-primary focus:border-forest-light focus:outline-none";

function todayIso(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

interface TookThisJobProps {
  companyId: number;
  companyName: string;
}

export default function TookThisJob({ companyId, companyName }: TookThisJobProps) {
  const links = useCompanyLinks();
  const create = useCreateCompanyLink();
  const remove = useDeleteCompanyLink();
  const end = useEndCompanyLink();
  const [startedOn, setStartedOn] = useState(todayIso);
  const [leaving, setLeaving] = useState(false);
  const [endedOn, setEndedOn] = useState(todayIso);
  const dateId = useId();
  const endId = useId();

  // The open link (no end date) is "you work here". A user has at most one open link
  // (a new one closes the previous, server-side), so an ended link to this company
  // is history: the form shows again under it.
  const here = (links.data?.data ?? []).filter((entry) => entry.company_id === companyId);
  const link = here.find((entry) => entry.ended_on == null) ?? null;
  const past = link === null ? (here.find((entry) => entry.ended_on != null) ?? null) : null;
  const elsewhere =
    (links.data?.data ?? []).find((entry) => entry.company_id !== companyId && entry.ended_on == null) ??
    null;

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (!startedOn) return;
    create.mutate({ company_id: companyId, started_on: startedOn });
  };

  const onLeave = (event: FormEvent, linkId: number) => {
    event.preventDefault();
    if (!endedOn) return;
    end.mutate({ linkId, endedOn }, { onSuccess: () => setLeaving(false) });
  };

  const endProblem =
    end.error instanceof ApiError && end.error.status === 422
      ? "We couldn't use that date. Your last day needs to be on or after your start date."
      : "We couldn't save that. Please try again.";

  return (
    <section className={`${PANEL} space-y-3 px-5 py-5`} aria-labelledby="took-job-heading">
      <h2 id="took-job-heading" className={REPORT_H2}>
        Did you take a job here?
      </h2>

      {links.isLoading ? (
        <p className={BODY_MUTED}>Checking...</p>
      ) : link ? (
        <div className="space-y-3">
          <p className={BODY_MUTED}>
            You took a job at {companyName}, starting {formatDay(link.started_on)}. Your Pulse
            check-ins from here on help us learn whether this read was right.
          </p>
          {leaving ? (
            <form onSubmit={(event) => onLeave(event, link.id)} className="space-y-3">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
                <div className="space-y-1.5">
                  <label htmlFor={endId} className={LABEL}>
                    Last day
                  </label>
                  <input
                    id={endId}
                    type="date"
                    value={endedOn}
                    min={link.started_on}
                    onChange={(e) => setEndedOn(e.target.value)}
                    required
                    className={DATE_INPUT}
                  />
                </div>
                <button type="submit" className={QUIET_BUTTON} disabled={end.isPending || !endedOn}>
                  {end.isPending ? "Saving..." : "Save"}
                </button>
                <button
                  type="button"
                  className={QUIET_BUTTON}
                  onClick={() => {
                    setLeaving(false);
                    end.reset();
                  }}
                >
                  Cancel
                </button>
              </div>
            </form>
          ) : (
            <div className="flex flex-wrap gap-2">
              <button type="button" className={QUIET_BUTTON} onClick={() => setLeaving(true)}>
                I left this job
              </button>
              <button
                type="button"
                className={QUIET_BUTTON}
                onClick={() => remove.mutate(link.id)}
                disabled={remove.isPending}
              >
                {remove.isPending ? "Removing..." : "Remove this"}
              </button>
            </div>
          )}
        </div>
      ) : (
        <form onSubmit={onSubmit} className="space-y-3">
          {past?.ended_on && (
            <p className={BODY_MUTED}>
              You worked at {companyName} from {formatDay(past.started_on)} to{" "}
              {formatDay(past.ended_on)}.
            </p>
          )}
          <p className={BODY_MUTED}>
            Tell us and we'll tie your Pulse check-ins to this read, so we can learn whether it
            was right. You can remove it any time.
            {elsewhere && (
              <>
                {" "}
                This replaces the job you recorded at{" "}
                {elsewhere.company?.name ?? "another company"}.
              </>
            )}
          </p>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
            <div className="space-y-1.5">
              <label htmlFor={dateId} className={LABEL}>
                Start date
              </label>
              <input
                id={dateId}
                type="date"
                value={startedOn}
                onChange={(e) => setStartedOn(e.target.value)}
                required
                className={DATE_INPUT}
              />
            </div>
            <button type="submit" className={QUIET_BUTTON} disabled={create.isPending || !startedOn}>
              {create.isPending ? "Saving..." : "I took this job"}
            </button>
          </div>
        </form>
      )}

      <div role="status" aria-live="polite">
        {create.isError && (
          <p className="text-[0.93rem] text-red-800">We couldn't save that. Please try again.</p>
        )}
        {end.isError && <p className="text-[0.93rem] text-red-800">{endProblem}</p>}
        {remove.isError && (
          <p className="text-[0.93rem] text-red-800">We couldn't remove that. Please try again.</p>
        )}
      </div>
    </section>
  );
}
