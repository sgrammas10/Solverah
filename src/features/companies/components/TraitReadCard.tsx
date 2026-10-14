/**
 * One trait of a company's read, as `GET /companies/{id}/read` sends it.
 *
 *   known    direction and tolerance in words, the must-have badge, how much evidence
 *            and from when and where, and up to three paraphrases with their source
 *   mixed    both ends side by side, each with its own paraphrases, never averaged,
 *            plus the scope-or-time explanation when there is one
 *   unknown  the plain explanation; no read, no penalty
 *
 * A must-have that is mixed or unknown carries the interview questions. With a
 * pasted posting, the role-level read sits under the company's and a disagreement
 * is called out.
 *
 * Evidence is always a paraphrase, never a quote (GAP-14), so it is not set in
 * quotation marks. No number on this card is a score.
 */
import {
  BODY,
  BODY_MUTED,
  CHIP,
  FlagBadge,
  MustHaveBadge,
  PANEL,
  SMALL_MUTED,
  STATUS_LINES,
  TEXT_LINK,
  dateRange,
  disagreementPhrase,
  formatMonth,
  joinNames,
  knownReadLine,
  sourceTypeLabel,
} from "../../matching";
import type { EvidenceItem, MixedEnd, PostingTraitRead, TraitRead } from "../useCompanyRead";

const KNOWN_PARAPHRASE_LIMIT = 3;

const STATUS_CHIPS: Record<TraitRead["status"], { label: string; className: string }> = {
  known: { label: "Clear read", className: "border-forest-light bg-forest-pale/60 text-forest-dark" },
  mixed: { label: "Evidence disagrees", className: "border-amber-200 bg-amber-50/60 text-amber-800" },
  unknown: { label: "Not enough evidence", className: "border-cream-muted bg-cream-base text-ink-secondary" },
};

interface EvidenceListProps {
  items: EvidenceItem[];
  limit?: number;
}

export function EvidenceList({ items, limit }: EvidenceListProps) {
  const shown = limit === undefined ? items : items.slice(0, limit);
  if (shown.length === 0) return null;
  return (
    <ul className="space-y-2.5">
      {shown.map((item, index) => {
        const meta = [
          sourceTypeLabel(item.source_type),
          item.scope !== "company" && item.scope_label ? item.scope_label : "",
          formatMonth(item.published_at),
        ].filter(Boolean);
        return (
          <li key={`${item.source_type}-${index}`} className="border-l-2 border-cream-muted pl-3">
            <p className={BODY}>{item.paraphrase}</p>
            <p className={SMALL_MUTED}>
              {meta.join(" · ")}
              {item.source_url && (
                <>
                  {meta.length > 0 && " · "}
                  <a
                    href={item.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={TEXT_LINK}
                  >
                    Source<span className="sr-only"> (opens in a new tab)</span>
                  </a>
                </>
              )}
            </p>
          </li>
        );
      })}
    </ul>
  );
}

function EvidenceSummaryLine({ trait }: { trait: TraitRead }) {
  const evidence = trait.evidence;
  if (!evidence || evidence.count === 0) return null;
  const range = dateRange(evidence.first_dated, evidence.last_dated);
  const sources = (evidence.source_types ?? []).map((s) => sourceTypeLabel(s).toLowerCase());
  const pieces = evidence.count === 1 ? "1 piece of evidence" : `${evidence.count} pieces of evidence`;
  return (
    <p className={SMALL_MUTED}>
      From {pieces}
      {range && <>, dated {range}</>}
      {sources.length > 0 && <>, from {joinNames(sources)}</>}.
    </p>
  );
}

interface MixedEndPanelProps {
  heading: string;
  end: MixedEnd;
  trait: TraitRead;
}

function MixedEndPanel({ heading, end, trait }: MixedEndPanelProps) {
  return (
    <div className="space-y-2 rounded-[4px] bg-cream-base px-4 py-3">
      <p className="text-[0.9rem] font-semibold text-ink-primary">{heading}</p>
      <p className={BODY_MUTED}>{knownReadLine({ ...end, low_pole: trait.low_pole, high_pole: trait.high_pole })}</p>
      <EvidenceList items={end.evidence ?? []} limit={KNOWN_PARAPHRASE_LIMIT} />
    </div>
  );
}

function PostingRow({ trait, posting }: { trait: TraitRead; posting: PostingTraitRead }) {
  let line: string;
  if (posting.status === "known") line = knownReadLine(posting);
  else if (posting.status === "mixed") line = "The posting itself is mixed on this.";
  else line = "The posting says nothing clear about this.";
  return (
    <div className="space-y-2 border-t border-cream-muted pt-3">
      <p className="text-[0.8rem] font-semibold uppercase tracking-[0.08em] text-ink-secondary">
        Your pasted posting (this role)
      </p>
      <p className={BODY}>{line}</p>
      {posting.disagrees && (
        <p className="rounded-[4px] border border-amber-200 bg-amber-50 px-3 py-2 text-[0.93rem] leading-[1.55] text-amber-900">
          {disagreementPhrase(trait.label, trait.direction, posting.direction, trait)}
        </p>
      )}
      <EvidenceList items={posting.paraphrases ?? []} limit={2} />
    </div>
  );
}

interface TraitReadCardProps {
  trait: TraitRead;
  /** The pasted posting's read of the same trait, when one is attached. */
  posting?: PostingTraitRead | null;
}

export default function TraitReadCard({ trait, posting }: TraitReadCardProps) {
  const chip = STATUS_CHIPS[trait.status];
  const questions = trait.questions ?? [];
  const headingId = `trait-${trait.dimension}`;
  return (
    <article className={`${PANEL} space-y-3 px-5 py-5`} aria-labelledby={headingId}>
      <div className="flex flex-wrap items-center gap-2">
        <h3 id={headingId} className="font-headline text-[1.1rem] font-bold text-ink-primary">
          {trait.label}
        </h3>
        <span className={`${CHIP} ${chip.className}`}>{chip.label}</span>
        {trait.must_have && <MustHaveBadge />}
        {trait.flag && <FlagBadge flag={trait.flag} />}
      </div>
      <p className={SMALL_MUTED}>
        From {trait.low_pole} to {trait.high_pole}
      </p>

      {trait.status === "known" && (
        <>
          <p className={BODY}>{knownReadLine(trait)}.</p>
          <EvidenceSummaryLine trait={trait} />
          {trait.scope_note && <p className={BODY_MUTED}>{trait.scope_note}</p>}
          <EvidenceList items={trait.paraphrases ?? []} limit={KNOWN_PARAPHRASE_LIMIT} />
        </>
      )}

      {trait.status === "mixed" && (
        <>
          <p className={BODY}>{trait.explanation ?? `${STATUS_LINES.mixed}.`}</p>
          {trait.mixed?.explanation && <p className={BODY_MUTED}>{trait.mixed.explanation}</p>}
          <EvidenceSummaryLine trait={trait} />
          {trait.mixed && (
            <div className="grid gap-3 sm:grid-cols-2">
              <MixedEndPanel
                heading={`Evidence on the ${trait.low_pole} side`}
                end={trait.mixed.low_end}
                trait={trait}
              />
              <MixedEndPanel
                heading={`Evidence on the ${trait.high_pole} side`}
                end={trait.mixed.high_end}
                trait={trait}
              />
            </div>
          )}
        </>
      )}

      {trait.status === "unknown" && (
        <p className={BODY_MUTED}>{trait.explanation ?? `${STATUS_LINES.unknown}.`}</p>
      )}

      {trait.must_have && questions.length > 0 && (
        <div className="space-y-2 rounded-[4px] bg-forest-pale/50 px-4 py-3">
          <p className="font-semibold text-forest-dark">Ask in your interview</p>
          <ul className="list-disc space-y-1.5 pl-5 marker:text-forest-light">
            {questions.map((question) => (
              <li key={question} className={BODY}>
                {question}
              </li>
            ))}
          </ul>
        </div>
      )}

      {posting && <PostingRow trait={trait} posting={posting} />}
    </article>
  );
}
