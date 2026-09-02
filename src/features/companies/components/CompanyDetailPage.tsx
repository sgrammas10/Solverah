import { type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { useParams, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../../auth";

interface CompanyOverview {
  name: string;
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
  pace?: string;
  empathy?: number;
  creative_drive?: number;
  adaptability?: number;
  futuristic?: number;
  harmony?: number;
  data_orientation?: number;
}

interface RemotePolicy {
  policy?: string;
  remote_friendly?: string;
  details?: string;
}

interface GlassdoorRatings {
  overall_rating?: number;
  work_life_balance?: number;
  compensation_score?: number;
  culture_score?: number;
  key_positives?: string;
  key_negatives?: string;
  source?: string;
}

interface InterviewProcess {
  difficulty?: string;
  process_overview?: string;
  coding_focus?: string;
  system_design?: boolean;
  behavioral?: string;
  avg_rounds?: number;
  timeline?: string;
  notes?: string;
}

interface Compensation {
  new_grad_swe_total?: string;
  mid_level_total?: string;
  senior_total?: string;
  base_range?: string;
  equity_notes?: string;
  levels?: string;
  notes?: string;
}

interface WorkforceSignals {
  warn_risk_level?: string;
  analyst_summary?: string;
  reddit_glassdoor_themes?: string;
}

interface TechStack {
  frontend?: string;
  backend?: string;
  infrastructure?: string;
  primary_languages?: string;
  notes?: string;
}

interface CompanyProfile {
  overview: CompanyOverview;
  culture?: CultureValues;
  remote_policy?: RemotePolicy;
  glassdoor?: GlassdoorRatings;
  interview?: InterviewProcess;
  compensation?: Compensation;
  workforce_signals?: WorkforceSignals;
  tech_stack?: TechStack;
}

interface CompanyDetailResponse {
  id: number;
  name: string;
  slug: string;
  profile: CompanyProfile;
}

interface FitState {
  fit_score: number;
  top_matching_dimensions: string[];
  top_mismatching_dimensions: string[];
}

const DIM_LABELS: Record<string, string> = {
  empathy: "Empathy",
  creative_drive: "Creative Drive",
  adaptability: "Adaptability",
  futuristic: "Future Orientation",
  harmony: "Harmony",
  data_orientation: "Data Orientation",
  pace: "Work Pace",
  work_environment: "Work Environment",
};

const NUMERIC_DIMS: { key: keyof CultureValues; label: string }[] = [
  { key: "empathy", label: "Empathy" },
  { key: "creative_drive", label: "Creative Drive" },
  { key: "adaptability", label: "Adaptability" },
  { key: "futuristic", label: "Future Orientation" },
  { key: "harmony", label: "Harmony" },
  { key: "data_orientation", label: "Data Orientation" },
];

function Eyebrow({ children }: { children: ReactNode }) {
  return (
    <p className="text-xs font-semibold uppercase tracking-widest text-forest-light mb-3">
      {children}
    </p>
  );
}

function Card({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-xl border border-cream-muted bg-white px-6 py-5">
      {children}
    </div>
  );
}

function LabelRow({ label, value }: { label: string; value?: string | number | boolean }) {
  if (value == null || value === "") return null;
  return (
    <div className="flex gap-2 text-sm">
      <span className="text-ink-tertiary shrink-0 w-36">{label}</span>
      <span className="text-ink-primary">{String(value)}</span>
    </div>
  );
}

function Badge({ label }: { label: string }) {
  return (
    <span className="inline-block text-xs px-2.5 py-1 rounded-full border border-cream-muted bg-cream-subtle text-ink-secondary">
      {label}
    </span>
  );
}

function DimBar({ value }: { value: number }) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  return (
    <div className="flex-1 rounded-full bg-cream-subtle h-1.5 overflow-hidden">
      <div
        className="h-full rounded-full bg-forest-light"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

function warnBadgeClass(level?: string): string {
  const l = (level ?? "").toLowerCase();
  if (l === "high") return "bg-red-50 text-red-700 border-red-200";
  if (l === "medium") return "bg-amber-50 text-amber-700 border-amber-200";
  return "bg-green-50 text-green-700 border-green-200";
}

/** Query keys for company documents. `all` is the invalidation handle. */
export const companyKeys = {
  all: ["companies"] as const,
  detail: (id: string) => ["companies", "detail", id] as const,
};

export default function CompanyDetailPage() {
  const { id } = useParams<{ id: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const { fetchWithAuth } = useAuth();

  const fitState = (location.state as FitState | null) ?? null;
  const hasFit =
    fitState !== null &&
    typeof fitState.fit_score === "number" &&
    Array.isArray(fitState.top_matching_dimensions);

  // A 5xx now gets queryClient.ts's bounded retries before the error card
  // (safe: Phase 3a removed every commit from GET handlers). The retry button
  // is refetch() — the duplicated hand-written fetch it replaced is gone.
  const companyQuery = useQuery({
    queryKey: companyKeys.detail(id ?? ""),
    queryFn: () => fetchWithAuth<CompanyDetailResponse>(`/companies/${id}`),
  });
  const data = companyQuery.data;

  if (companyQuery.isLoading) {
    return (
      <div className="min-h-screen bg-cream-base flex flex-col items-center justify-center gap-4">
        <div className="w-8 h-8 rounded-full border-2 border-forest-light border-t-transparent animate-spin" />
        <p className="text-sm text-ink-secondary">Loading company profile…</p>
      </div>
    );
  }

  if (companyQuery.isError || !data) {
    return (
      <div className="min-h-screen bg-cream-base flex items-center justify-center px-6">
        <div className="max-w-sm w-full rounded-lg border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-700">
          <p className="font-medium mb-1">Couldn't load this company profile.</p>
          <p className="text-xs">Please try again in a moment.</p>
          <button
            type="button"
            onClick={() => companyQuery.refetch()}
            className="mt-3 text-xs font-semibold text-red-700 underline"
          >
            Try again
          </button>
        </div>
      </div>
    );
  }

  const { profile } = data;
  const ov = profile.overview;
  const cu = profile.culture;
  const rp = profile.remote_policy;
  const gd = profile.glassdoor;
  const iv = profile.interview;
  const co = profile.compensation;
  const ws = profile.workforce_signals;
  const ts = profile.tech_stack;

  const hasCulture =
    cu &&
    (cu.culture_narrative_company ||
      cu.culture_narrative_employees ||
      (cu.core_values && cu.core_values.length > 0));

  const hasWorkEnv =
    cu &&
    (cu.work_environment ||
      cu.pace ||
      NUMERIC_DIMS.some((d) => cu[d.key] != null));

  const hasRemote = rp && (rp.policy || rp.remote_friendly || rp.details);

  const hasGlassdoor =
    gd &&
    (gd.overall_rating != null ||
      gd.work_life_balance != null ||
      gd.compensation_score != null ||
      gd.culture_score != null ||
      gd.key_positives ||
      gd.key_negatives);

  const hasInterview =
    iv &&
    (iv.difficulty ||
      iv.process_overview ||
      iv.coding_focus ||
      iv.system_design != null ||
      iv.behavioral ||
      iv.avg_rounds != null ||
      iv.timeline ||
      iv.notes);

  const hasComp =
    co &&
    (co.new_grad_swe_total ||
      co.mid_level_total ||
      co.senior_total ||
      co.base_range ||
      co.equity_notes ||
      co.levels ||
      co.notes);

  const hasWorkforce =
    ws && (ws.warn_risk_level || ws.analyst_summary || ws.reddit_glassdoor_themes);

  const hasTechStack =
    ts &&
    (ts.frontend ||
      ts.backend ||
      ts.infrastructure ||
      ts.primary_languages ||
      ts.notes);

  const envTags = cu?.work_environment
    ? cu.work_environment.split(",").map((t) => t.trim()).filter(Boolean)
    : [];

  return (
    <div className="min-h-screen bg-cream-base">
      <div className="mx-auto max-w-3xl px-6 pt-12 pb-20 space-y-6">

        {/* Back link */}
        <button
          type="button"
          onClick={() => navigate(-1)}
          className="text-sm font-semibold text-forest-mid hover:underline"
        >
          ← Back to companies
        </button>

        {/* 1. Page header */}
        <div className="space-y-1">
          <h1 className="font-display text-3xl font-semibold text-ink-primary">{data.name}</h1>
          {(ov.industry || ov.size || ov.headquarters) && (
            <p className="text-sm text-ink-secondary">
              {[ov.industry, ov.size, ov.headquarters].filter(Boolean).join(" · ")}
            </p>
          )}
          {ov.website && (
            <a
              href={ov.website}
              target="_blank"
              rel="noreferrer"
              className="text-sm text-forest-mid hover:underline"
            >
              {ov.website}
            </a>
          )}
        </div>

        {/* 2. Fit score banner */}
        {hasFit && (
          <div className="rounded-xl border border-forest-light bg-forest-pale px-6 py-4 space-y-3">
            <Eyebrow>Your CompanyLens™ fit score</Eyebrow>
            <p className="font-display text-2xl font-semibold text-forest-dark">
              {Math.round(fitState!.fit_score * 100)}%
            </p>
            {fitState!.top_matching_dimensions.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {fitState!.top_matching_dimensions.map((d) => (
                  <span
                    key={d}
                    className="bg-white border border-forest-light text-forest-mid text-xs px-2.5 py-1 rounded-full"
                  >
                    {DIM_LABELS[d] ?? d}
                  </span>
                ))}
              </div>
            )}
            {fitState!.top_mismatching_dimensions.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {fitState!.top_mismatching_dimensions.map((d) => (
                  <span
                    key={d}
                    className="bg-amber-50 border border-amber-200 text-amber-700 text-xs px-2.5 py-1 rounded-full"
                  >
                    {DIM_LABELS[d] ?? d}
                  </span>
                ))}
              </div>
            )}
          </div>
        )}

        {/* 3. Culture */}
        {hasCulture && (
          <Card>
            <Eyebrow>Culture</Eyebrow>
            <div className="space-y-4">
              {cu!.culture_narrative_company && (
                <div>
                  <p className="text-xs font-semibold text-ink-secondary mb-1">What the company says</p>
                  <p className="text-sm text-ink-primary leading-relaxed">{cu!.culture_narrative_company}</p>
                </div>
              )}
              {cu!.culture_narrative_employees && (
                <div>
                  <p className="text-xs font-semibold text-ink-secondary mb-1">What employees say</p>
                  <p className="text-sm text-ink-primary leading-relaxed">{cu!.culture_narrative_employees}</p>
                </div>
              )}
              {cu!.core_values && cu!.core_values.length > 0 && (
                <div className="flex flex-wrap gap-1.5 pt-1">
                  {cu!.core_values.map((v) => (
                    <span
                      key={v}
                      className="bg-cream-subtle text-ink-secondary text-xs px-2.5 py-1 rounded-full border border-cream-muted"
                    >
                      {v}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </Card>
        )}

        {/* 4. Work environment */}
        {hasWorkEnv && (
          <Card>
            <Eyebrow>Work Environment</Eyebrow>
            <div className="space-y-4">
              {envTags.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {envTags.map((tag) => <Badge key={tag} label={tag} />)}
                </div>
              )}
              {cu!.pace && (
                <span className="inline-block text-xs px-2.5 py-1 rounded-full border border-forest-light text-forest-mid">
                  Pace: {cu!.pace.charAt(0).toUpperCase() + cu!.pace.slice(1).replace("-", " ")}
                </span>
              )}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2 pt-1">
                {NUMERIC_DIMS.map(({ key, label }) => {
                  const val = cu![key] as number | undefined;
                  if (val == null) return null;
                  return (
                    <div key={key} className="flex items-center gap-3">
                      <span className="text-xs text-ink-secondary w-32 shrink-0">{label}</span>
                      <DimBar value={val} />
                    </div>
                  );
                })}
              </div>
            </div>
          </Card>
        )}

        {/* 5. Remote & office policy */}
        {hasRemote && (
          <Card>
            <Eyebrow>Remote &amp; Office</Eyebrow>
            <div className="space-y-2">
              {rp!.policy && <Badge label={rp!.policy} />}
              {rp!.remote_friendly && (
                <p className="text-sm text-ink-secondary">Remote-friendly: {rp!.remote_friendly}</p>
              )}
              {rp!.details && (
                <p className="text-sm text-ink-primary leading-relaxed">{rp!.details}</p>
              )}
            </div>
          </Card>
        )}

        {/* 6. Employee ratings */}
        {hasGlassdoor && (
          <Card>
            <Eyebrow>Employee Ratings</Eyebrow>
            <div className="space-y-4">
              {gd!.source && (
                <p className="text-xs text-ink-tertiary">{gd!.source}</p>
              )}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                {[
                  { label: "Overall", val: gd!.overall_rating },
                  { label: "Work-Life Balance", val: gd!.work_life_balance },
                  { label: "Compensation", val: gd!.compensation_score },
                  { label: "Culture", val: gd!.culture_score },
                ].map(({ label, val }) =>
                  val != null ? (
                    <div key={label} className="text-center">
                      <p className="font-display text-2xl font-semibold text-ink-primary">{val.toFixed(1)}</p>
                      <p className="text-xs text-ink-tertiary mt-0.5">{label}</p>
                    </div>
                  ) : null
                )}
              </div>
              {gd!.key_positives && (
                <div>
                  <p className="text-xs font-semibold text-ink-secondary mb-1">Key positives</p>
                  <p className="text-sm text-ink-primary leading-relaxed">{gd!.key_positives}</p>
                </div>
              )}
              {gd!.key_negatives && (
                <div>
                  <p className="text-xs font-semibold text-ink-secondary mb-1">Key concerns</p>
                  <p className="text-sm text-ink-primary leading-relaxed">{gd!.key_negatives}</p>
                </div>
              )}
            </div>
          </Card>
        )}

        {/* 7. Interview process */}
        {hasInterview && (
          <Card>
            <Eyebrow>Interview Process</Eyebrow>
            <div className="space-y-3">
              {iv!.difficulty && <Badge label={iv!.difficulty} />}
              {iv!.process_overview && (
                <p className="text-sm text-ink-primary leading-relaxed">{iv!.process_overview}</p>
              )}
              <div className="space-y-1.5">
                <LabelRow label="Coding focus" value={iv!.coding_focus} />
                {iv!.system_design != null && (
                  <LabelRow label="System design" value={iv!.system_design ? "Yes" : "No"} />
                )}
                <LabelRow label="Behavioral" value={iv!.behavioral} />
                <LabelRow label="Avg rounds" value={iv!.avg_rounds} />
                <LabelRow label="Timeline" value={iv!.timeline} />
              </div>
              {iv!.notes && (
                <p className="text-sm text-ink-secondary leading-relaxed">{iv!.notes}</p>
              )}
            </div>
          </Card>
        )}

        {/* 8. Compensation */}
        {hasComp && (
          <Card>
            <Eyebrow>Compensation</Eyebrow>
            <div className="space-y-4">
              {(co!.new_grad_swe_total || co!.mid_level_total || co!.senior_total) && (
                <div className="grid grid-cols-3 gap-4">
                  {[
                    { label: "New Grad", val: co!.new_grad_swe_total },
                    { label: "Mid-Level", val: co!.mid_level_total },
                    { label: "Senior", val: co!.senior_total },
                  ].map(({ label, val }) =>
                    val ? (
                      <div key={label} className="text-center">
                        <p className="text-sm font-semibold text-ink-primary">{val}</p>
                        <p className="text-xs text-ink-tertiary mt-0.5">{label}</p>
                      </div>
                    ) : null
                  )}
                </div>
              )}
              <div className="space-y-1.5">
                <LabelRow label="Base range" value={co!.base_range} />
                <LabelRow label="Equity" value={co!.equity_notes} />
                <LabelRow label="Levels" value={co!.levels} />
              </div>
              {co!.notes && (
                <p className="text-sm text-ink-secondary leading-relaxed">{co!.notes}</p>
              )}
            </div>
          </Card>
        )}

        {/* 9. Workforce signals */}
        {hasWorkforce && (
          <Card>
            <Eyebrow>Workforce Signals</Eyebrow>
            <div className="space-y-3">
              {ws!.warn_risk_level && (
                <span
                  className={`inline-block text-xs px-2.5 py-1 rounded-full border font-medium ${warnBadgeClass(ws!.warn_risk_level)}`}
                >
                  WARN risk: {ws!.warn_risk_level}
                </span>
              )}
              {ws!.analyst_summary && (
                <p className="text-sm text-ink-primary leading-relaxed">{ws!.analyst_summary}</p>
              )}
              {ws!.reddit_glassdoor_themes && (
                <div>
                  <p className="text-xs font-semibold text-ink-secondary mb-1">Reddit / Glassdoor themes</p>
                  <p className="text-sm text-ink-primary leading-relaxed">{ws!.reddit_glassdoor_themes}</p>
                </div>
              )}
            </div>
          </Card>
        )}

        {/* 10. Tech stack */}
        {hasTechStack && (
          <Card>
            <Eyebrow>Tech Stack</Eyebrow>
            <div className="space-y-1.5">
              <LabelRow label="Frontend" value={ts!.frontend} />
              <LabelRow label="Backend" value={ts!.backend} />
              <LabelRow label="Infrastructure" value={ts!.infrastructure} />
              <LabelRow label="Languages" value={ts!.primary_languages} />
              {ts!.notes && (
                <p className="text-sm text-ink-secondary leading-relaxed pt-1">{ts!.notes}</p>
              )}
            </div>
          </Card>
        )}

      </div>
    </div>
  );
}
