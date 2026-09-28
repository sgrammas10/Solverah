/**
 * The report in a few lines, above the per-dimension cards: which dimension
 * is under the most strain (the first strained row, since document order IS
 * the ranking), its diagnosis headline, then every dimension grouped under
 * its bucket as a plain list of names.
 *
 * Built only from what the server sent: no copy table of its own beyond the
 * row labels, no count, no number (D-15). Within each group the server's
 * order is kept, and a row the server dropped (the needs-forward aligned
 * set) is simply absent -- never backfilled.
 */
import { isAlignedEntry } from "../../useSituationReport";
import type { SituationDimensionEntry, StrainDimensionEntry } from "../../useSituationReport";
import { REPORT_H2, dimensionLabel, joinNames } from "./format";

interface ReportSummaryProps {
  dimensions: SituationDimensionEntry[];
  past: boolean;
}

export default function ReportSummary({ dimensions, past }: ReportSummaryProps) {
  const strained = dimensions.filter(
    (entry): entry is StrainDimensionEntry => !isAlignedEntry(entry),
  );
  const lead = strained[0];

  const names = (bucket: SituationDimensionEntry["bucket"]) =>
    dimensions.filter((entry) => entry.bucket === bucket).map((entry) => dimensionLabel(entry.dimension));

  const rows: { label: string; names: string[] }[] = [
    { label: past ? "Strained most" : "Under most strain", names: names("straining") },
    { label: "Worth watching", names: names("notable") },
    { label: "Working well", names: names("aligned") },
  ].filter((row) => row.names.length > 0);

  return (
    <section aria-labelledby="situation-summary" className="space-y-5">
      <h2 id="situation-summary" className={REPORT_H2}>
        In short
      </h2>
      <div className="rounded-[6px] border border-cream-muted bg-white px-5 py-5 sm:px-6">
        {lead ? (
          <div className="space-y-2">
            <p className="font-headline text-[1.2rem] font-bold leading-snug text-ink-primary">
              {dimensionLabel(lead.dimension)} {past ? "was" : "is"} under the most strain.
            </p>
            <p className="text-[1rem] leading-[1.6] text-ink-secondary">{lead.diagnosis.headline}</p>
          </div>
        ) : (
          <p className="font-headline text-[1.2rem] font-bold leading-snug text-ink-primary">
            Nothing is under strain.
          </p>
        )}
        <dl className="mt-5 divide-y divide-cream-muted border-t border-cream-muted">
          {rows.map((row) => (
            <div
              key={row.label}
              className="grid gap-0.5 py-2.5 sm:grid-cols-[11rem_minmax(0,1fr)] sm:gap-6"
            >
              <dt className="text-[0.92rem] font-semibold text-ink-secondary">{row.label}</dt>
              <dd className="text-[0.98rem] text-ink-primary">{joinNames(row.names)}</dd>
            </div>
          ))}
        </dl>
      </div>
    </section>
  );
}
