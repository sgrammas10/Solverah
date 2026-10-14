/**
 * The older research profile (`profile_json` from `GET /companies/{id}`), kept as
 * background below the six-trait read and visually secondary to it.
 *
 * Shown only when the profile has something in it: a company first researched
 * through CompanyLens has no such profile, and an empty "Background" heading would
 * suggest something is missing.
 *
 * Two things the old page showed are deliberately gone. The bars for the retired
 * eight-dimension culture scores (empathy, harmony and the rest): those were the
 * interim scorer's company side, which this build deleted, and drawn under the
 * six-trait read they would look like a second, competing read. And the rating
 * grid (overall, work-life balance, ...): numbers out of five, which the
 * no-score rule for CompanyLens pages rules out. The written parts stay.
 */
import type { ReactNode } from "react";

import { text, type LegacyProfileDocument } from "../legacyProfile";

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="space-y-2 border-t border-cream-muted pt-4">
      <h3 className="text-[0.95rem] font-semibold text-ink-primary">{title}</h3>
      {children}
    </div>
  );
}

function Para({ label, value }: { label?: string; value: string }) {
  if (!value) return null;
  return (
    <p className="text-[0.93rem] leading-[1.6] text-ink-secondary">
      {label && <span className="font-semibold text-ink-primary">{label}: </span>}
      {value}
    </p>
  );
}

interface LegacyProfileProps {
  profile: LegacyProfileDocument;
}

export default function LegacyProfile({ profile }: LegacyProfileProps) {
  const cu = profile.culture;
  const rp = profile.remote_policy;
  const gd = profile.glassdoor;
  const iv = profile.interview;
  const co = profile.compensation;
  const ws = profile.workforce_signals;
  const values = (Array.isArray(cu?.core_values) ? cu.core_values : []).map(text).filter(Boolean);

  const culture =
    text(cu?.culture_narrative_company) ||
    text(cu?.culture_narrative_employees) ||
    text(cu?.work_environment) ||
    values.length > 0;
  const remote = text(rp?.policy) || text(rp?.remote_friendly) || text(rp?.details);
  const themes = text(gd?.key_positives) || text(gd?.key_negatives);
  const interview = text(iv?.difficulty) || text(iv?.process_overview) || text(iv?.timeline) || text(iv?.notes);
  const pay = text(co?.base_range) || text(co?.equity_notes) || text(co?.levels) || text(co?.notes);

  return (
    <section
      className="space-y-4 rounded-[6px] border border-dashed border-cream-muted px-5 py-5"
      aria-labelledby="legacy-heading"
    >
      <div className="space-y-1">
        <h2 id="legacy-heading" className="font-headline text-[1.05rem] font-bold text-ink-secondary">
          Background research
        </h2>
        <p className="text-[0.88rem] leading-[1.55] text-ink-tertiary">
          An older, general profile of this company. It isn't part of your read above.
        </p>
      </div>

      {culture && (
        <Section title="Culture">
          <Para label="What the company says" value={text(cu?.culture_narrative_company)} />
          <Para label="What employees say" value={text(cu?.culture_narrative_employees)} />
          {values.length > 0 && <Para label="Stated values" value={values.join(", ")} />}
          <Para label="Work environment" value={text(cu?.work_environment)} />
        </Section>
      )}

      {remote && (
        <Section title="Remote and office">
          <Para value={[text(rp?.policy), text(rp?.remote_friendly)].filter(Boolean).join(". ")} />
          <Para value={text(rp?.details)} />
        </Section>
      )}

      {themes && (
        <Section title="Themes from employees">
          <Para label="Positives" value={text(gd?.key_positives)} />
          <Para label="Concerns" value={text(gd?.key_negatives)} />
        </Section>
      )}

      {interview && (
        <Section title="Interview process">
          <Para label="Difficulty" value={text(iv?.difficulty)} />
          <Para value={text(iv?.process_overview)} />
          <Para label="Timeline" value={text(iv?.timeline)} />
          <Para value={text(iv?.notes)} />
        </Section>
      )}

      {pay && (
        <Section title="Compensation">
          <Para label="Base range" value={text(co?.base_range)} />
          <Para label="Equity" value={text(co?.equity_notes)} />
          <Para label="Levels" value={text(co?.levels)} />
          <Para value={text(co?.notes)} />
        </Section>
      )}

      {text(ws?.analyst_summary) && (
        <Section title="Workforce signals">
          <Para value={text(ws?.analyst_summary)} />
        </Section>
      )}
    </section>
  );
}
