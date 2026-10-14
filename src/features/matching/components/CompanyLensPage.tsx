/**
 * /company-lens -- companies read against how you like to work, on six traits.
 *
 * PRODUCT_DECISIONS.md §2, "The six-trait match model" (2026-10-13). One call,
 * `GET /me/matches`, in one of three states:
 *
 *   core_required  no current core sitting: a friendly prompt to /work-pulse
 *   no_companies   nothing researched yet: an invitation to research one
 *   ranked         ranked cards in the server's order, then "Not enough evidence yet"
 *
 * The server's order IS the ranking. There is no probability, score or
 * percentage on the wire and none is made here -- see companyLensCopy.ts. A
 * company with a broken must-have is flagged and listed last by the server; it
 * is never hidden, and neither is a company we could not read well enough.
 */
import type { ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";

import { useMatches, type MatchEntry } from "../useCompanyLens";
import type { PollTiming } from "../usePoll";
import { LEAD, PAGE_H1, PRIMARY } from "../../../shared/ui/publicStyles";
import { BODY_MUTED, PANEL, QUIET_BUTTON, REPORT_H2, TEXT_LINK } from "../lensStyles";
import CompanyMatchCard, { NotEnoughEvidenceRow } from "./CompanyMatchCard";
import ResearchCompanyForm from "./ResearchCompanyForm";

function Shell({ children }: { children: ReactNode }) {
  return (
    <main className="min-h-screen bg-cream-base font-body text-ink-primary antialiased">
      <div className="mx-auto w-full max-w-3xl space-y-10 px-4 pb-24 pt-8 sm:px-6 md:pt-14">
        {children}
      </div>
    </main>
  );
}

function BackLink() {
  const navigate = useNavigate();
  return (
    <button
      type="button"
      onClick={() => navigate("/intelligence")}
      className="text-[0.9rem] font-medium text-ink-secondary transition-colors hover:text-forest-mid"
    >
      <span aria-hidden>←</span> Back to Intelligence
    </button>
  );
}

function Header({ children }: { children?: ReactNode }) {
  return (
    <header className="max-w-[62ch] space-y-4">
      <p className="text-[0.8rem] font-semibold uppercase tracking-[0.12em] text-forest-light">
        CompanyLens™
      </p>
      <h1 className={PAGE_H1}>Companies, read against how you like to work</h1>
      <p className={LEAD}>
        We read what's public about each company on six traits (autonomy, pace, collaboration,
        feedback, innovation and how decisions get made) and set it beside what you told us you
        prefer. Where the evidence is thin or disagrees, we say so.
      </p>
      {children}
    </header>
  );
}

function PreferencesNudge() {
  return (
    <p className={`${BODY_MUTED} rounded-[6px] bg-forest-pale/50 px-4 py-3`}>
      These reads use a narrow range around each of your answers.{" "}
      <Link to="/trait-preferences" className={TEXT_LINK}>
        Tell us how much give you have
      </Link>{" "}
      on each trait, and which ones are must-haves.
    </p>
  );
}

interface CompanyLensPageProps {
  /** Override the research polling schedule (tests). */
  researchPollTiming?: PollTiming;
}

export default function CompanyLensPage({ researchPollTiming }: CompanyLensPageProps = {}) {
  const navigate = useNavigate();
  const matches = useMatches();

  if (matches.isLoading) {
    return (
      <Shell>
        <div className="flex flex-col items-center gap-4 pt-16" role="status">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-forest-light border-t-transparent motion-reduce:animate-none" />
          <p className={BODY_MUTED}>Reading companies against your answers...</p>
        </div>
      </Shell>
    );
  }

  if (matches.isError || !matches.data) {
    return (
      <Shell>
        <div className="mx-auto max-w-sm rounded-[6px] border border-red-200 bg-red-50 px-5 py-4 text-red-800" role="alert">
          <p className="mb-1 font-semibold">We couldn't load CompanyLens right now.</p>
          <p className="text-[0.88rem]">Please try again in a moment.</p>
          <button
            type="button"
            onClick={() => void matches.refetch()}
            className="mt-3 text-[0.88rem] font-semibold text-red-800 underline underline-offset-4"
          >
            Try again
          </button>
        </div>
      </Shell>
    );
  }

  const pages = matches.data.pages;
  const first = pages[0];

  if (first.state === "core_required") {
    return (
      <Shell>
        <BackLink />
        <Header>
          <section className={`${PANEL} space-y-4 px-5 py-5`}>
            <h2 className={REPORT_H2}>Start with how you like to work</h2>
            <p className={BODY_MUTED}>
              CompanyLens compares companies with your own preferences, so it needs your Work
              Pulse answers first. It's a short set of questions, and every read here builds on
              it.
            </p>
            <button type="button" onClick={() => navigate("/work-pulse")} className={PRIMARY}>
              Take Work Pulse
            </button>
          </section>
        </Header>
      </Shell>
    );
  }

  const entries: MatchEntry[] = pages.flatMap((page) => page.data ?? []);
  const ranked = entries.filter((entry) => entry.state === "ranked");
  const thin = entries.filter((entry) => entry.state === "not_enough_evidence");

  return (
    <Shell>
      <BackLink />
      <Header>{!first.preferences_answered && <PreferencesNudge />}</Header>

      <section className={`${PANEL} px-5 py-5`}>
        <ResearchCompanyForm pollTiming={researchPollTiming} />
      </section>

      {first.state === "no_companies" ? (
        <section className="space-y-2">
          <h2 className={REPORT_H2}>No companies yet</h2>
          <p className={BODY_MUTED}>
            Name a company you're curious about above, whether it's one you're interviewing
            with or one you've always wondered about. Once it's researched, its read shows up
            here.
          </p>
        </section>
      ) : (
        <>
          {ranked.length > 0 && (
            <section className="space-y-4" aria-labelledby="lens-ranked">
              <div className="space-y-1">
                <h2 id="lens-ranked" className={REPORT_H2}>
                  Your companies
                </h2>
                <p className={BODY_MUTED}>
                  Closest to how you like to work first. A company that breaks one of your
                  must-haves is flagged and listed last, never hidden.
                </p>
              </div>
              <ol className="space-y-3">
                {ranked.map((entry) => (
                  <li key={entry.id}>
                    <CompanyMatchCard entry={entry} />
                  </li>
                ))}
              </ol>
            </section>
          )}

          {thin.length > 0 && (
            <section className="space-y-4" aria-labelledby="lens-thin">
              <div className="space-y-1">
                <h2 id="lens-thin" className={REPORT_H2}>
                  Not enough evidence yet
                </h2>
                <p className={BODY_MUTED}>
                  We found too little to read these companies on at least three traits, so we
                  don't place them. Here's what's missing.
                </p>
              </div>
              <ul className="space-y-3">
                {thin.map((entry) => (
                  <NotEnoughEvidenceRow key={entry.id} entry={entry} />
                ))}
              </ul>
            </section>
          )}

          {matches.hasNextPage && (
            <div className="flex justify-center">
              <button
                type="button"
                onClick={() => void matches.fetchNextPage()}
                disabled={matches.isFetchingNextPage}
                className={QUIET_BUTTON}
              >
                {matches.isFetchingNextPage ? "Loading..." : "Show more companies"}
              </button>
            </div>
          )}
        </>
      )}
    </Shell>
  );
}
