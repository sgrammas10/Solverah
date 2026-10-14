/**
 * One company in the CompanyLens list.
 *
 * A ranked company shows how much of it we could read ("Based on 4 of 6 traits"),
 * the next step with its reason, the reads on the user's must-have traits, the
 * flag counts and the size note. A `not_enough_evidence` company shows only what
 * is missing: it has no rank, and it is not a match either way.
 *
 * No number here is a score. The server's order is the ranking; nothing on the
 * card says how far apart two companies are.
 */
import { Link } from "react-router-dom";

import type { MatchEntry, TraitReadSummary } from "../useCompanyLens";
import {
  STATUS_LINES,
  coverageDetail,
  coverageLine,
  flagCountLines,
  joinNames,
  knownReadLine,
  traitName,
} from "../companyLensCopy";
import { BODY, BODY_MUTED, CARD_H3, PANEL, SMALL_MUTED, TEXT_LINK } from "../lensStyles";
import { FlagBadge, NextStepChip } from "./LensBits";

function mustHaveLine(read: TraitReadSummary): string {
  if (read.status === "known") return knownReadLine(read);
  return STATUS_LINES[read.status];
}

interface MustHaveReadsProps {
  reads: TraitReadSummary[];
}

function MustHaveReads({ reads }: MustHaveReadsProps) {
  if (reads.length === 0) return null;
  return (
    <div className="space-y-1.5">
      <p className="text-[0.8rem] font-semibold uppercase tracking-[0.08em] text-ink-secondary">
        Your must-haves
      </p>
      <ul className="space-y-1.5">
        {reads.map((read) => (
          <li key={read.dimension} className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className={BODY}>
              <span className="font-semibold">{read.label}:</span> {mustHaveLine(read)}
            </span>
            {read.flag && <FlagBadge flag={read.flag} />}
          </li>
        ))}
      </ul>
    </div>
  );
}

function ResearchNote({ entry }: { entry: MatchEntry }) {
  const status = entry.research?.status;
  if (status !== "queued" && status !== "running") return null;
  return <p className={SMALL_MUTED}>We're updating the research on this company now.</p>;
}

interface CompanyMatchCardProps {
  entry: MatchEntry;
}

export default function CompanyMatchCard({ entry }: CompanyMatchCardProps) {
  const name = entry.name ?? "This company";
  const flags = flagCountLines(entry.flags);
  return (
    <article className={`${PANEL} space-y-4 px-5 py-5`} aria-label={name}>
      <div className="space-y-1">
        <h3 className={CARD_H3}>
          <Link to={`/companies/${entry.id}`} className="hover:underline focus-visible:underline">
            {name}
          </Link>
        </h3>
        <p className={BODY_MUTED}>
          {coverageLine(entry.coverage)}
          <span className="text-ink-tertiary"> ({coverageDetail(entry.coverage)})</span>
        </p>
      </div>

      <NextStepChip step={entry.next_step} />

      <MustHaveReads reads={entry.must_have_reads ?? []} />

      {flags.length > 0 && (
        <ul className="flex flex-wrap gap-x-4 gap-y-1">
          {flags.map((line) => (
            <li key={line} className="text-[0.88rem] font-semibold text-amber-800">
              {line}
            </li>
          ))}
        </ul>
      )}

      {entry.size_note && <p className={SMALL_MUTED}>{entry.size_note}</p>}
      <ResearchNote entry={entry} />

      <p>
        <Link to={`/companies/${entry.id}`} className={`${TEXT_LINK} text-[0.93rem]`}>
          See the full read<span className="sr-only"> on {name}</span>
        </Link>
      </p>
    </article>
  );
}

interface NotEnoughEvidenceRowProps {
  entry: MatchEntry;
}

export function NotEnoughEvidenceRow({ entry }: NotEnoughEvidenceRowProps) {
  const name = entry.name ?? "This company";
  const missing = (entry.missing ?? []).map(traitName);
  return (
    <li className={`${PANEL} space-y-2 px-5 py-4`}>
      <p className="font-semibold text-ink-primary">
        <Link to={`/companies/${entry.id}`} className="hover:underline focus-visible:underline">
          {name}
        </Link>
      </p>
      <p className={BODY_MUTED}>
        Clear reads on {entry.coverage.known} of {entry.coverage.total} traits so far, which is
        not enough to say how it compares.
        {missing.length > 0 && <> Too little evidence on {joinNames(missing)}.</>}
      </p>
      <NextStepChip step={entry.next_step} />
      <ResearchNote entry={entry} />
    </li>
  );
}
