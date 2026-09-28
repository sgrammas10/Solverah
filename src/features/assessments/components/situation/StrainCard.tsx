/**
 * One straining or notable dimension, compact by default: the name, its
 * bucket word and direction phrase, and the diagnosis headline as the
 * one-line takeaway. The guidance itself (diagnosis text, the three
 * registers, the Decoder hand-offs) sits behind a disclosure button.
 *
 * The panel is always in the DOM and hidden with the `hidden` attribute, not
 * unmounted, for two reasons: `print:block` overrides it so a printed report
 * carries every piece of guidance whatever was open on screen, and the
 * experiment control inside keeps its hook state across open/close.
 *
 * Words only, never numbers -- see SituationReportPage.tsx's header (D-15).
 */
import { Link } from "react-router-dom";

import type {
  SituationManagerSection,
  StrainDimensionEntry,
} from "../../useSituationReport";
import type { Experiment } from "../../useExperiments";
import { ExperimentControl, type ExperimentsStatus } from "./Experiments";
import {
  BODY,
  BODY_MUTED,
  BUCKET_LABELS,
  TEXT_LINK,
  dimensionLabel,
  directionLabel,
} from "./format";

interface StrainCardProps {
  entry: StrainDimensionEntry;
  past: boolean;
  manager: SituationManagerSection;
  experiments: Experiment[];
  hasActiveElsewhere: boolean;
  experimentsStatus: ExperimentsStatus;
  open: boolean;
  onToggle: () => void;
}

function RegisterHeading({ children }: { children: React.ReactNode }) {
  return (
    <h4 className="font-headline text-[1.05rem] font-bold text-ink-primary">{children}</h4>
  );
}

/** A label/text pair, laid out as a two-column row from `sm` up. */
function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1 sm:grid-cols-[9.5rem_minmax(0,1fr)] sm:gap-5">
      <dt className="text-[0.9rem] font-semibold text-ink-secondary sm:pt-[0.1rem]">{label}</dt>
      <dd className={BODY}>{children}</dd>
    </div>
  );
}

function Register({ children }: { children: React.ReactNode }) {
  return (
    <section className="space-y-3 border-t border-cream-muted pt-5 print:break-inside-avoid">
      {children}
    </section>
  );
}

function DecoderNote({ text, href, cta }: { text: string; href: string; cta: string }) {
  return (
    <section className="space-y-2 rounded-[4px] bg-cream-base px-4 py-3.5 print:break-inside-avoid">
      <p className={BODY_MUTED}>{text}</p>
      <Link to={href} className={`${TEXT_LINK} text-[0.93rem]`}>
        {cta}
      </Link>
    </section>
  );
}

const FEEDBACK_DEFERRAL =
  "How feedback actually reaches you is enacted by one person rather than by the company, so the protocol for it lives in the Manager Decoder rather than here.";

export default function StrainCard({
  entry,
  past,
  manager,
  experiments,
  hasActiveElsewhere,
  experimentsStatus,
  open,
  onToggle,
}: StrainCardProps) {
  const { registers } = entry;
  const isStraining = entry.bucket === "straining";
  const name = dimensionLabel(entry.dimension);
  const panelId = `situation-guidance-${entry.dimension}`;
  const managerHref = manager.has_profile ? "/manager-profile/playbook" : "/manager-profile";
  const managerCta = manager.has_profile ? "Open your playbook" : "Profile your manager";

  return (
    <article
      className={[
        "rounded-[6px] border border-cream-muted bg-white border-l-[5px] print:break-inside-auto",
        isStraining ? "border-l-amber-600" : "border-l-forest-light/60",
      ].join(" ")}
    >
      <div className="flex flex-col gap-4 px-5 py-5 sm:flex-row sm:items-start sm:justify-between sm:px-6">
        <div className="min-w-0 space-y-1.5">
          <h3 className="font-headline text-[1.3rem] font-bold leading-tight tracking-[-0.01em] text-ink-primary">
            {name}
          </h3>
          <p className="flex flex-wrap items-baseline gap-x-3 text-[0.92rem]">
            <span
              className={
                isStraining ? "font-semibold text-amber-800" : "font-semibold text-forest-mid"
              }
            >
              {BUCKET_LABELS[entry.bucket]}
            </span>
            <span className="text-ink-secondary">{directionLabel(entry.direction, past)}</span>
          </p>
          <p className="pt-1 text-[1.02rem] leading-[1.5] text-ink-primary">
            {entry.diagnosis.headline}
          </p>
        </div>
        <button
          type="button"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={onToggle}
          className="inline-flex shrink-0 items-center gap-2 self-start rounded-[4px] border border-cream-muted px-3.5 py-2 text-[0.9rem] font-semibold text-forest-dark transition-colors hover:border-forest-light hover:bg-forest-pale/40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-light print:hidden"
        >
          {open ? "Hide guidance" : "Show guidance"}
          <span className="sr-only"> for {name}</span>
          <svg
            width="14"
            height="14"
            viewBox="0 0 14 14"
            fill="none"
            aria-hidden="true"
            className={`transition-transform duration-200 motion-reduce:transition-none ${open ? "rotate-180" : ""}`}
          >
            <path d="M3 5l4 4 4-4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>

      <div
        id={panelId}
        hidden={!open}
        className="space-y-5 px-5 pb-6 sm:px-6 print:block"
      >
        <p className={BODY}>{entry.diagnosis.text}</p>

        {registers.change_in_place && (
          <Register>
            <RegisterHeading>Change it in place</RegisterHeading>
            {registers.change_in_place.experiment_name && (
              <p className="font-semibold text-ink-primary">
                {registers.change_in_place.experiment_name}
              </p>
            )}
            {registers.change_in_place.experiment && (
              <p className={BODY}>{registers.change_in_place.experiment}</p>
            )}
            {registers.change_in_place.steps && registers.change_in_place.steps.length > 0 && (
              <ul className="list-disc space-y-1.5 pl-5 marker:text-forest-light">
                {registers.change_in_place.steps.map((stepText) => (
                  <li key={stepText.slice(0, 48)} className={BODY}>
                    {stepText}
                  </li>
                ))}
              </ul>
            )}
            <dl>
              <Row label={past ? "What to watch for next time" : "How you'll know it worked"}>
                {registers.change_in_place.signal}
              </Row>
            </dl>
            {/* Not shown in the needs-forward rendering: there is no live job
                to run a two-week change against, and the server never sends
                `experiment_name` for that slice. */}
            {!past && registers.change_in_place.experiment_name && (
              <ExperimentControl
                dimension={entry.dimension}
                direction={entry.direction}
                experiments={experiments}
                hasActiveElsewhere={hasActiveElsewhere}
                status={experimentsStatus}
              />
            )}
          </Register>
        )}

        {registers.negotiate && (
          <Register>
            <RegisterHeading>Negotiate it</RegisterHeading>
            <dl className="space-y-3">
              <Row label="Who, and where">{registers.negotiate.who_and_where}</Row>
              <Row label="How to open">{registers.negotiate.opening}</Row>
              {registers.negotiate.scripts.length > 0 && (
                <Row label="What to say">
                  <ul className="space-y-2">
                    {registers.negotiate.scripts.map((script) => (
                      <li
                        key={script.slice(0, 48)}
                        className="border-l-2 border-forest-light/50 pl-3 italic"
                      >
                        “{script}”
                      </li>
                    ))}
                  </ul>
                </Row>
              )}
              <Row label="If the answer is no">{registers.negotiate.if_no}</Row>
            </dl>
          </Register>
        )}

        {registers.rarely_moves && (
          <Register>
            <RegisterHeading>This one rarely moves</RegisterHeading>
            <dl className="space-y-3">
              <Row label="Why it's usually fixed">{registers.rarely_moves.why_fixed}</Row>
              <Row label="What staying costs">{registers.rarely_moves.cost_of_staying}</Row>
              <Row label="What that means">{registers.rarely_moves.what_it_implies}</Row>
            </dl>
          </Register>
        )}

        {/* The Decoder hand-off. `defers_to_decoder` is the whole-dimension
            deferral (feedback); `decoder_crossref` is the softer "some of this
            may be one person" paragraph (autonomy). A dimension can carry
            either, and neither duplicates protocol that lives in C-2. */}
        {entry.defers_to_decoder && (
          <DecoderNote text={FEEDBACK_DEFERRAL} href={managerHref} cta={managerCta} />
        )}
        {entry.decoder_crossref && (
          <DecoderNote text={entry.decoder_crossref} href={managerHref} cta={managerCta} />
        )}
      </div>
    </article>
  );
}
