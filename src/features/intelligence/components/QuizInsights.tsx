import { useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useProfile } from "../../profile";
import { ALL_QUIZZES, CAREER_QUIZ_GROUP, storedInsightFor } from "../quizPayload";

type InsightEntry = {
  title?: string;
  summary?: string;
  keyTakeaways?: string[];
  combinedMeaning?: string;
  nextSteps?: string[];
};

type OverallInsight = {
  summary?: string;
  keyTakeaways?: string[];
  nextSteps?: string[];
};

type InsightGroup = {
  _overallInsight?: OverallInsight;
  _generatedAt?: string;
  _model?: string;
  [key: string]: any;
};

const groupTitles: Record<string, string> = {
  careerQuizzes: "Career Quizzes Insights",
  careerJobSearch: "Career & Job Search Insights",
  yourFutureYourWay: "Your Future, Your Way Insights",
};

/** A stored list field, or nothing: a non-array must not reach `.map`. */
const listOf = (value: unknown): string[] =>
  Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];

const CAREER_QUIZ_ORDER = ALL_QUIZZES.map((quiz) => quiz.key);

export default function QuizInsights() {
  // The insights live inside the profile document, which useProfile() already
  // caches — reading the cache replaces the fetchProfileData() round trip this
  // page used to make on every mount. A failed fetch throws to
  // RouteErrorBoundary with the document's other consumers (see useProfile).
  const { data: profile, isLoading: loading } = useProfile();
  const [activeFilter, setActiveFilter] = useState<string>("all");
  const navigate = useNavigate();
  const location = useLocation();
  const locationState = location.state as {
    insight?: {
      overallSummary?: string | null;
      overallInsight?: OverallInsight | null;
      insights?: InsightEntry[];
    };
  } | null;

  const group = useMemo(() => {
    const params = new URLSearchParams(location.search);
    return params.get("group") || CAREER_QUIZ_GROUP;
  }, [location.search]);

  const quizInsights = (profile as any)?.quizInsights;
  const insightsData: Record<string, any> | null =
    quizInsights && typeof quizInsights === "object"
      ? (quizInsights as Record<string, any>)
      : null;

  const renderInsightCard = (title: string, entry?: InsightEntry) => {
    if (!entry) return null;
    const keyTakeaways = listOf(entry.keyTakeaways);
    const nextSteps = listOf(entry.nextSteps);
    return (
      <div key={title} className="border border-cream-muted rounded-xl bg-white p-6">
        <h3 className="font-display text-lg font-semibold text-ink-primary mb-3">{title}</h3>

        {entry.summary && (
          <p className="text-sm text-ink-secondary leading-relaxed mb-4">{entry.summary}</p>
        )}

        {keyTakeaways.length ? (
          <div className="mb-4">
            <p className="text-xs font-semibold uppercase tracking-[0.08em] text-forest-light mb-2">
              Key takeaways
            </p>
            <ul className="space-y-1.5">
              {keyTakeaways.map((item, idx) => (
                <li key={idx} className="flex items-start gap-2 text-sm text-ink-secondary">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-forest-light" />
                  {item}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {entry.combinedMeaning && (
          <div className="mb-4">
            <p className="text-xs font-semibold uppercase tracking-[0.08em] text-forest-light mb-2">
              Combined meaning
            </p>
            <p className="text-sm text-ink-secondary leading-relaxed">{entry.combinedMeaning}</p>
          </div>
        )}

        {nextSteps.length ? (
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.08em] text-forest-light mb-2">
              Next steps
            </p>
            <ul className="space-y-1.5">
              {nextSteps.map((item, idx) => (
                <li key={idx} className="flex items-start gap-2 text-sm text-ink-secondary">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-forest-mid" />
                  {item}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    );
  };

  // What the quiz page just generated, handed over in router state. Shown only
  // when the profile document has nothing for this group yet -- e.g. the
  // refetch after the POST has not landed.
  const fromNavigation = (() => {
    const insight = locationState?.insight;
    if (!insight?.insights?.length) return null;
    const overallSummary = insight.overallInsight?.summary || insight.overallSummary;
    return (
      <div className="mt-6 grid gap-4">
        {overallSummary ? (
          <div className="rounded-xl border border-forest-pale bg-forest-pale px-5 py-4 text-sm text-forest-dark">
            <p className="text-xs font-semibold uppercase tracking-[0.08em] text-forest-mid mb-2">
              Overall summary
            </p>
            <p className="leading-relaxed">{overallSummary}</p>
          </div>
        ) : null}
        {insight.insights.map((entry, idx) =>
          renderInsightCard(entry.title || `Insight ${idx + 1}`, entry),
        )}
      </div>
    );
  })();

  const stored = (() => {
    if (!insightsData) return null;

    if (group === CAREER_QUIZ_GROUP) {
      const nested = (insightsData.careerQuizzes as InsightGroup | undefined) ?? {};
      // One entry per quiz: the nested careerQuizzes.<key> entry, else a
      // pre-2026-10-02 flat quizInsights.<key> document (audit #7 / G16 --
      // the guest replay used to write those, and this page never read them).
      const entries: Record<string, InsightEntry> = {};
      for (const key of Object.keys(nested).filter((k) => !k.startsWith("_"))) {
        if (nested[key] && typeof nested[key] === "object") entries[key] = nested[key];
      }
      for (const key of CAREER_QUIZ_ORDER) {
        if (entries[key]) continue;
        const legacy = storedInsightFor(insightsData, key);
        if (legacy) entries[key] = legacy;
      }
      const allKeys = Object.keys(entries);
      if (!allKeys.length) return null;
      const sortedKeys = [
        ...CAREER_QUIZ_ORDER.filter((k) => allKeys.includes(k)),
        ...allKeys.filter((k) => !CAREER_QUIZ_ORDER.includes(k)),
      ];
      const overall = nested._overallInsight;
      const overallTakeaways = listOf(overall?.keyTakeaways);
      const overallSteps = listOf(overall?.nextSteps);

      const filterOptions = [
        { value: "all", label: "All" },
        ...sortedKeys.map((key) => ({
          value: key,
          label: entries[key]?.title || key,
        })),
        ...(overall?.summary ? [{ value: "overall", label: "Overall Summary" }] : []),
      ];

      const showOverall = activeFilter === "all" || activeFilter === "overall";
      const visibleKeys = activeFilter === "all" || activeFilter === "overall"
        ? (activeFilter === "overall" ? [] : sortedKeys)
        : sortedKeys.filter((k) => k === activeFilter);

      const cards = visibleKeys
        .map((key) => {
          const entry = entries[key];
          return renderInsightCard(entry?.title || key, entry);
        })
        .filter(Boolean);

      return (
        <>
          {/* Filter pills */}
          <div className="mt-4 flex flex-wrap gap-2">
            {filterOptions.map((opt) => (
              <button
                key={opt.value}
                type="button"
                onClick={() => setActiveFilter(opt.value)}
                className={`px-3.5 py-1.5 rounded-full text-xs font-semibold transition-colors border ${
                  activeFilter === opt.value
                    ? "bg-forest-dark text-white border-forest-dark"
                    : "bg-white text-ink-secondary border-cream-muted hover:border-forest-pale hover:text-forest-mid"
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>

          {cards.length > 0 && <div className="mt-4 grid gap-4">{cards}</div>}

          {showOverall && overall?.summary ? (
            <div className="mt-6 rounded-2xl border-2 border-forest-mid bg-forest-dark p-6 text-cream-base">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-forest-pale mb-1">
                Combined Insight
              </p>
              <h3 className="font-display text-lg font-bold text-white mb-3">
                Across All Your Quizzes
              </h3>
              <p className="text-sm leading-relaxed text-cream-subtle mb-4">{overall.summary}</p>
              {overallTakeaways.length ? (
                <div className="mb-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.08em] text-forest-pale mb-2">
                    Key takeaways
                  </p>
                  <ul className="space-y-1.5">
                    {overallTakeaways.map((item, idx) => (
                      <li key={idx} className="flex items-start gap-2 text-sm text-cream-subtle">
                        <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-forest-pale" />
                        {item}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
              {overallSteps.length ? (
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.08em] text-forest-pale mb-2">
                    Next steps
                  </p>
                  <ul className="space-y-1.5">
                    {overallSteps.map((item, idx) => (
                      <li key={idx} className="flex items-start gap-2 text-sm text-cream-subtle">
                        <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-forest-light" />
                        {item}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          ) : null}
        </>
      );
    }

    // A single quiz (old links name one): its nested entry, else the flat one.
    const single = storedInsightFor(insightsData, group);
    if (!single) return null;
    const title = single.title || groupTitles[group] || "Insight";
    return <div className="grid gap-4">{renderInsightCard(title, single)}</div>;
  })();

  const content = stored ?? fromNavigation;

  return (
    <div className="min-h-screen bg-cream-base font-sans text-ink-primary">
      <div className="mx-auto max-w-4xl px-6 py-12">
        <div className="flex flex-wrap items-center justify-between gap-4 mb-8">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.08em] text-forest-light mb-2">
              Insights
            </p>
            <h1 className="font-display text-3xl font-bold text-ink-primary">
              {groupTitles[group] || "Quiz Insights"}
            </h1>
            <p className="mt-2 text-sm text-ink-secondary">
              Personalized takeaways based on your quiz responses.
            </p>
          </div>
          <button
            type="button"
            onClick={() => navigate("/intelligence")}
            className="border border-cream-muted bg-white text-ink-secondary text-sm font-semibold px-5 py-2.5 rounded hover:border-forest-pale hover:text-forest-mid transition-colors"
          >
            Back to assessments
          </button>
        </div>

        {loading ? (
          <p className="text-sm text-ink-tertiary">Loading insights…</p>
        ) : content ? (
          content
        ) : (
          <div className="rounded-xl border border-cream-muted bg-white px-5 py-6 text-sm text-ink-secondary">
            No insights found yet. Complete a quiz and generate insights to view them here.
          </div>
        )}
      </div>
    </div>
  );
}
