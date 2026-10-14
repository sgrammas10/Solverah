/**
 * A read-side view of the legacy research profile (`profile_json`, served as the
 * open `profile` object of `GET /companies/{id}`). The contract types it as an open
 * object -- it is the stored research document -- so this names only the parts the
 * company page reads; it is not a copy of an API type.
 */

interface CompanyOverview {
  industry?: string;
  size?: string;
  headquarters?: string;
  website?: string;
}

interface CultureValues {
  culture_narrative_company?: string;
  culture_narrative_employees?: string;
  core_values?: string[];
  work_environment?: string;
}

interface RemotePolicy {
  policy?: string;
  remote_friendly?: string;
  details?: string;
}

interface EmployeeThemes {
  key_positives?: string;
  key_negatives?: string;
}

interface InterviewProcess {
  difficulty?: string;
  process_overview?: string;
  timeline?: string;
  notes?: string;
}

interface Compensation {
  base_range?: string;
  equity_notes?: string;
  levels?: string;
  notes?: string;
}

interface WorkforceSignals {
  analyst_summary?: string;
}

export interface LegacyProfileDocument {
  overview?: CompanyOverview;
  culture?: CultureValues;
  remote_policy?: RemotePolicy;
  glassdoor?: EmployeeThemes;
  interview?: InterviewProcess;
  compensation?: Compensation;
  workforce_signals?: WorkforceSignals;
}

/** A trimmed string, or "" for anything that is not a string. */
export function text(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

/** True when the document has at least one written part the page would show. */
export function hasLegacyContent(profile: LegacyProfileDocument | null | undefined): boolean {
  if (!profile || typeof profile !== "object") return false;
  const c = profile.culture;
  const parts = [
    c?.culture_narrative_company,
    c?.culture_narrative_employees,
    c?.work_environment,
    ...(Array.isArray(c?.core_values) ? c.core_values : []),
    profile.remote_policy?.policy,
    profile.remote_policy?.remote_friendly,
    profile.remote_policy?.details,
    profile.glassdoor?.key_positives,
    profile.glassdoor?.key_negatives,
    profile.interview?.difficulty,
    profile.interview?.process_overview,
    profile.interview?.timeline,
    profile.interview?.notes,
    profile.compensation?.base_range,
    profile.compensation?.equity_notes,
    profile.compensation?.levels,
    profile.compensation?.notes,
    profile.workforce_signals?.analyst_summary,
  ];
  return parts.some((part) => text(part) !== "");
}
