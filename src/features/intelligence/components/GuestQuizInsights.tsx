import { useLocation, useNavigate } from "react-router-dom";
import { CONTAINER, LEAD, PAGE_H1, PRIMARY, SECONDARY } from "../../../shared/ui/publicStyles";

type InsightEntry = {
  title?: string;
  summary?: string;
  keyTakeaways?: string[];
  combinedMeaning?: string;
  nextSteps?: string[];
};

type InsightPayload = {
  overallSummary?: string | null;
  insights?: InsightEntry[];
};

const SUBHEAD = "text-[0.95rem] font-semibold text-ink-primary";
const ITEM = "flex gap-3 text-[0.97rem] leading-[1.6] text-ink-secondary";

function Bullets({ items }: { items: string[] }) {
  return (
    <ul className="mt-2.5 space-y-2">
      {items.map((item, idx) => (
        <li key={idx} className={ITEM}>
          <span className="mt-[0.8em] h-px w-4 shrink-0 bg-forest-dark" aria-hidden="true" />
          {item}
        </li>
      ))}
    </ul>
  );
}

function InsightRow({ title, entry }: { title: string; entry: InsightEntry }) {
  return (
    <article className="grid gap-4 border-b border-cream-muted py-8 md:grid-cols-[minmax(0,2fr)_minmax(0,5fr)] md:gap-10">
      <h2 className="font-headline text-[1.35rem] font-bold leading-tight text-balance">{title}</h2>
      <div className="space-y-6">
        {entry.summary ? (
          <p className="text-[1.02rem] leading-[1.65] text-ink-primary">{entry.summary}</p>
        ) : null}
        {entry.keyTakeaways?.length ? (
          <div>
            <h3 className={SUBHEAD}>Key takeaways</h3>
            <Bullets items={entry.keyTakeaways} />
          </div>
        ) : null}
        {entry.combinedMeaning ? (
          <div>
            <h3 className={SUBHEAD}>What it means together</h3>
            <p className="mt-2.5 text-[0.97rem] leading-[1.6] text-ink-secondary">{entry.combinedMeaning}</p>
          </div>
        ) : null}
        {entry.nextSteps?.length ? (
          <div>
            <h3 className={SUBHEAD}>Next steps</h3>
            <Bullets items={entry.nextSteps} />
          </div>
        ) : null}
      </div>
    </article>
  );
}

export default function GuestQuizInsights() {
  const location = useLocation();
  const navigate = useNavigate();
  const state = location.state as { insight?: InsightPayload } | null;
  const insight = state?.insight;

  return (
    <div className="landing min-h-screen bg-cream-base font-body text-ink-primary antialiased">
      <div className={`${CONTAINER} pb-20 pt-12 md:pb-28 md:pt-16`}>
        <button
          type="button"
          onClick={() => navigate("/quiz-preview")}
          className="text-[0.9rem] font-medium text-ink-secondary transition-colors hover:text-forest-mid"
        >
          Back to quizzes
        </button>

        <div className="mt-8 flex flex-col gap-8 md:flex-row md:items-end md:justify-between md:gap-12">
          <div className="max-w-[60ch]">
            <h1 className={PAGE_H1}>Your quiz insights</h1>
            <p className={`mt-5 ${LEAD}`}>
              What your answers point to, and what to try next. Create an account to keep them.
            </p>
          </div>
          <div className="flex shrink-0 flex-wrap gap-3">
            <button type="button" onClick={() => navigate("/register")} className={PRIMARY}>
              Create account
            </button>
            <button type="button" onClick={() => navigate("/login")} className={SECONDARY}>
              Sign in to save results
            </button>
          </div>
        </div>

        {!insight?.insights?.length ? (
          <div className="mt-12 border-t border-cream-muted pt-8">
            <p className="text-[1.02rem] leading-[1.6] text-ink-secondary">
              No insights found. Take a quiz to generate your insights.
            </p>
            <button type="button" onClick={() => navigate("/quiz-preview")} className={`mt-6 ${SECONDARY}`}>
              Choose a quiz
            </button>
          </div>
        ) : (
          <div className="mt-12">
            {insight.overallSummary ? (
              <section className="border-l-[3px] border-forest-dark bg-white px-6 py-5">
                <h2 className="text-[0.95rem] font-semibold text-ink-primary">Summary</h2>
                <p className="mt-2 max-w-[68ch] text-[1.05rem] leading-[1.7] text-ink-primary">
                  {insight.overallSummary}
                </p>
              </section>
            ) : null}
            <div className="mt-10 border-t border-cream-muted">
              {insight.insights.map((entry, idx) => {
                const title = entry.title || `Insight ${idx + 1}`;
                return <InsightRow key={title + idx} title={title} entry={entry} />;
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
