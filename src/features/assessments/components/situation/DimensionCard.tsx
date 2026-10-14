/**
 * One dimension of the report as one compact row: the name, its bucket word
 * and direction phrase, and a one-line takeaway. Straining, notable and
 * aligned rows share the shape so the page can render the server's list as
 * ONE list in the order it arrived -- splitting it into groups is how a
 * client ends up re-sorting without meaning to.
 *
 * The takeaway is the diagnosis headline on a strained row and the first
 * sentence of the note on an aligned one (the payload has no aligned
 * headline). Everything else sits behind the disclosure: the diagnosis text,
 * the registers as tabs (`RegisterTabs`), and the Decoder hand-offs. An
 * aligned note of one sentence has nothing more to show, so it gets no toggle.
 *
 * The panel is always in the DOM and hidden with the `hidden` attribute, not
 * unmounted: `print:block` puts every piece of guidance on paper whatever was
 * open on screen, and the experiment control inside keeps its hook state.
 *
 * Words only, never numbers -- see SituationReportPage.tsx's header (D-15).
 */
import { Link } from "react-router-dom";

import { isAlignedEntry } from "../../useSituationReport";
import type {
  SituationDimensionEntry,
  SituationManagerSection,
  StrainDimensionEntry,
} from "../../useSituationReport";
import type { Experiment } from "../../useExperiments";
import { ExperimentControl, type ExperimentsStatus } from "./Experiments";
import RegisterTabs, { type RegisterTab } from "./RegisterTabs";
import {
  BODY,
  BODY_MUTED,
  BUCKET_LABELS,
  TEXT_LINK,
  dimensionLabel,
  directionLabel,
  splitFirstSentence,
} from "./format";

interface DimensionCardProps {
  entry: SituationDimensionEntry;
  past: boolean;
  manager: SituationManagerSection;
  experiments: Experiment[];
  hasActiveElsewhere: boolean;
  experimentsStatus: ExperimentsStatus;
  open: boolean;
  onToggle: () => void;
}

const ACCENT: Record<SituationDimensionEntry["bucket"], { border: string; word: string }> = {
  straining: { border: "border-l-amber-600", word: "text-amber-800" },
  notable: { border: "border-l-forest-light/70", word: "text-forest-mid" },
  aligned: { border: "border-l-cream-muted", word: "text-forest-mid" },
};

/** A label/text pair, laid out as a two-column row from `sm` up. */
function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1 sm:grid-cols-[9rem_minmax(0,1fr)] sm:gap-5">
      <dt className="text-[0.9rem] font-semibold text-ink-secondary sm:pt-[0.1rem]">{label}</dt>
      <dd className={BODY}>{children}</dd>
    </div>
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
  "How feedback reaches you is set by one person more than by the company, so the playbook for it lives in the Manager Decoder.";

interface RegisterProps {
  entry: StrainDimensionEntry;
  past: boolean;
  experiments: Experiment[];
  hasActiveElsewhere: boolean;
  experimentsStatus: ExperimentsStatus;
}

/** The registers the server sent, as tabs, in the server's register order. */
function registerTabs({
  entry,
  past,
  experiments,
  hasActiveElsewhere,
  experimentsStatus,
}: RegisterProps): RegisterTab[] {
  const { change_in_place: change, negotiate, rarely_moves: rarely } = entry.registers;
  const tabs: RegisterTab[] = [];

  if (change) {
    tabs.push({
      key: "change",
      label: past ? "What to look for" : "Try a change",
      content: (
        <>
          {change.experiment_name && (
            <p className="font-semibold text-ink-primary">{change.experiment_name}</p>
          )}
          {change.experiment && <p className={BODY}>{change.experiment}</p>}
          {change.steps && change.steps.length > 0 && (
            <ul className="list-disc space-y-1.5 pl-5 marker:text-forest-light">
              {change.steps.map((stepText) => (
                <li key={stepText.slice(0, 48)} className={BODY}>
                  {stepText}
                </li>
              ))}
            </ul>
          )}
          <dl>
            <Row label={past ? "What to watch for next time" : "How you'll know it worked"}>
              {change.signal}
            </Row>
          </dl>
          {/* Not in the needs-forward rendering: there is no live job to run a
              two-week change against, and the server never sends
              `experiment_name` for that slice. */}
          {!past && change.experiment_name && (
            <ExperimentControl
              dimension={entry.dimension}
              direction={entry.direction}
              experiments={experiments}
              hasActiveElsewhere={hasActiveElsewhere}
              status={experimentsStatus}
            />
          )}
        </>
      ),
    });
  }

  if (negotiate) {
    tabs.push({
      key: "negotiate",
      label: "Negotiate it",
      content: (
        <dl className="space-y-3">
          <Row label="Who, and where">{negotiate.who_and_where}</Row>
          <Row label="How to open">{negotiate.opening}</Row>
          {negotiate.scripts.length > 0 && (
            <Row label="What to say">
              <ul className="space-y-2">
                {negotiate.scripts.map((script) => (
                  <li key={script.slice(0, 48)} className="border-l-2 border-forest-light/50 pl-3 italic">
                    “{script}”
                  </li>
                ))}
              </ul>
            </Row>
          )}
          <Row label="If the answer is no">{negotiate.if_no}</Row>
        </dl>
      ),
    });
  }

  if (rarely) {
    tabs.push({
      key: "rarely",
      label: past ? "Why it rarely moves" : "If it won't move",
      content: (
        <dl className="space-y-3">
          <Row label="Why it's usually fixed">{rarely.why_fixed}</Row>
          <Row label="What staying costs">{rarely.cost_of_staying}</Row>
          <Row label="What that means">{rarely.what_it_implies}</Row>
        </dl>
      ),
    });
  }

  return tabs;
}

export default function DimensionCard({
  entry,
  past,
  manager,
  experiments,
  hasActiveElsewhere,
  experimentsStatus,
  open,
  onToggle,
}: DimensionCardProps) {
  const name = dimensionLabel(entry.dimension);
  const panelId = `situation-guidance-${entry.dimension}`;
  const accent = ACCENT[entry.bucket];
  const aligned = isAlignedEntry(entry);

  const [alignedLead, alignedRest] = aligned ? splitFirstSentence(entry.aligned_note) : ["", ""];
  const takeaway = aligned ? alignedLead : entry.diagnosis.headline;
  const hasMore = aligned ? alignedRest.length > 0 : true;

  const managerHref = manager.has_profile ? "/manager-profile/playbook" : "/manager-profile";
  const managerCta = manager.has_profile ? "Open your playbook" : "Profile your manager";

  return (
    <article
      className={`overflow-hidden rounded-[6px] border border-l-[4px] border-cream-muted bg-white ${accent.border} print:break-inside-auto`}
    >
      {/* The whole header is the disclosure: the button is stretched over it
          (not wrapped around it, so the h3 keeps the dimension's name as its
          accessible name) and the row lights up on hover. */}
      <div
        className={`relative px-4 py-4 sm:px-5 ${
          hasMore ? "pr-11 transition-colors hover:bg-cream-base/60 motion-reduce:transition-none sm:pr-12 print:pr-5" : ""
        }`}
      >
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
            <h3 className="font-headline text-[1.15rem] font-bold leading-tight text-ink-primary">
              {name}
            </h3>
            <p className="text-[0.88rem]">
              <span className={`font-semibold ${accent.word}`}>{BUCKET_LABELS[entry.bucket]}</span>
              {!aligned && (
                <>
                  <span aria-hidden className="text-ink-tertiary">
                    {" · "}
                  </span>
                  <span className="text-ink-secondary">{directionLabel(entry.direction, past)}</span>
                </>
              )}
            </p>
          </div>
          <p className="text-[0.98rem] leading-[1.5] text-ink-primary">{takeaway}</p>
        </div>
        {hasMore && (
          <button
            type="button"
            aria-expanded={open}
            aria-controls={panelId}
            onClick={onToggle}
            className="absolute inset-0 w-full cursor-pointer text-ink-tertiary transition-colors hover:text-forest-dark focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-forest-light print:hidden"
          >
            <span className="sr-only">
              {aligned ? (open ? "Show less" : "Read more") : open ? "Hide guidance" : "Show guidance"} for {name}
            </span>
            <svg
              width="14"
              height="14"
              viewBox="0 0 14 14"
              fill="none"
              aria-hidden="true"
              className={`absolute right-4 top-5 transition-transform duration-200 motion-reduce:transition-none sm:right-5 ${open ? "rotate-180" : ""}`}
            >
              <path d="M3 5l4 4 4-4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        )}
      </div>

      {hasMore && (
        <div id={panelId} hidden={!open} className="space-y-4 px-4 pb-5 sm:px-5 print:block">
          {aligned ? (
            <p className={BODY}>{alignedRest}</p>
          ) : (
            <>
              <p className={BODY}>{entry.diagnosis.text}</p>
              <RegisterTabs
                idBase={`situation-${entry.dimension}`}
                tabs={registerTabs({ entry, past, experiments, hasActiveElsewhere, experimentsStatus })}
              />
              {/* The Decoder hand-off. `defers_to_decoder` is the whole-dimension
                  deferral (feedback); `decoder_crossref` is the softer "some of
                  this may be one person" paragraph (autonomy). */}
              {entry.defers_to_decoder && (
                <DecoderNote text={FEEDBACK_DEFERRAL} href={managerHref} cta={managerCta} />
              )}
              {entry.decoder_crossref && (
                <DecoderNote text={entry.decoder_crossref} href={managerHref} cta={managerCta} />
              )}
            </>
          )}
        </div>
      )}
    </article>
  );
}
