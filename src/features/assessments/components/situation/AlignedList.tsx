/**
 * The aligned dimensions, grouped after the strained ones in one quiet
 * panel. An aligned row carries a single note and no registers, so there is
 * nothing to disclose: the note is the whole of it.
 */
import type { AlignedDimensionEntry } from "../../useSituationReport";
import { BODY, BUCKET_LABELS, dimensionLabel } from "./format";

interface AlignedListProps {
  entries: AlignedDimensionEntry[];
}

export default function AlignedList({ entries }: AlignedListProps) {
  return (
    <ul className="divide-y divide-cream-muted rounded-[6px] border border-cream-muted bg-white print:break-inside-avoid">
      {entries.map((entry) => (
        <li
          key={entry.dimension}
          className="grid gap-1.5 px-5 py-4 sm:grid-cols-[11rem_minmax(0,1fr)] sm:gap-6 sm:px-6"
        >
          <div className="space-y-0.5">
            <h3 className="font-headline text-[1.1rem] font-bold leading-tight text-ink-primary">
              {dimensionLabel(entry.dimension)}
            </h3>
            <p className="text-[0.9rem] font-semibold text-forest-mid">{BUCKET_LABELS.aligned}</p>
          </div>
          <p className={BODY}>{entry.aligned_note}</p>
        </li>
      ))}
    </ul>
  );
}
