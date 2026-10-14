/**
 * /companies/:id -- one company, read against how you like to work.
 *
 * "Your read" (`GET /companies/{id}/read`) is the page: coverage, the next step,
 * the size note, then one card per trait (TraitReadCard). Below it, the two things
 * a user can do with a read -- paste a job posting for a role-level read beside the
 * company's, and say "I took this job" -- and last, only if the company has one,
 * the older research profile, visually secondary.
 *
 * States of the read: `ranked` and `not_enough_evidence` carry traits;
 * `core_required` asks for Work Pulse; `not_researched` offers to research it.
 *
 * The pasted posting's id lives in the URL (`?posting=`), so a reload keeps it. It
 * is polled until it has a read, and only then is the read refetched with
 * `?posting_id=` -- before that the server has nothing role-level to add.
 *
 * Never a probability, score or percentage (PRODUCT_DECISIONS §2): see
 * matching/companyLensCopy.ts.
 */
import type { ReactNode } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import {
  BODY_MUTED,
  NextStepChip,
  PANEL,
  QUIET_BUTTON,
  REPORT_H2,
  ResearchCompanyForm,
  SMALL_MUTED,
  TEXT_LINK,
  coverageDetail,
  coverageLine,
  flagCountLines,
  type PollTiming,
} from "../../matching";
import { PAGE_H1, PRIMARY } from "../../../shared/ui/publicStyles";
import {
  useCompanyProfile,
  useCompanyRead,
  usePostingStatus,
  type CompanyReadResponse,
} from "../useCompanyRead";
import { hasLegacyContent, text, type LegacyProfileDocument } from "../legacyProfile";
import LegacyProfile from "./LegacyProfile";
import PostingPanel from "./PostingPanel";
import TookThisJob from "./TookThisJob";
import TraitReadCard from "./TraitReadCard";

function Shell({ children }: { children: ReactNode }) {
  return (
    <main className="min-h-screen bg-cream-base font-body text-ink-primary antialiased">
      <div className="mx-auto w-full max-w-3xl space-y-8 px-4 pb-24 pt-8 sm:px-6 md:pt-14">
        {children}
      </div>
    </main>
  );
}

function BackLink() {
  return (
    <Link
      to="/company-lens"
      className="text-[0.9rem] font-medium text-ink-secondary transition-colors hover:text-forest-mid"
    >
      <span aria-hidden>←</span> Back to CompanyLens
    </Link>
  );
}

interface ReadSummaryProps {
  read: CompanyReadResponse;
}

function ReadSummary({ read }: ReadSummaryProps) {
  const flags = read.flags ? flagCountLines(read.flags) : [];
  return (
    <section className={`${PANEL} space-y-4 px-5 py-5`} aria-labelledby="read-heading">
      <div className="space-y-1">
        <h2 id="read-heading" className={REPORT_H2}>
          Your read
        </h2>
        {read.coverage && (
          <p className={BODY_MUTED}>
            {coverageLine(read.coverage)}
            <span className="text-ink-tertiary"> ({coverageDetail(read.coverage)})</span>
          </p>
        )}
      </div>
      {read.state === "not_enough_evidence" && (
        <p className={BODY_MUTED}>
          That's too few clear reads to say how this company compares with the others, so we
          don't place it. What we did find is below.
        </p>
      )}
      {read.next_step && <NextStepChip step={read.next_step} />}
      {flags.length > 0 && (
        <ul className="flex flex-wrap gap-x-4 gap-y-1">
          {flags.map((line) => (
            <li key={line} className="text-[0.88rem] font-semibold text-amber-800">
              {line}
            </li>
          ))}
        </ul>
      )}
      {read.company.size_note && <p className={SMALL_MUTED}>{read.company.size_note}</p>}
      {!read.preferences_answered && (
        <p className={SMALL_MUTED}>
          These reads use a narrow range around each of your answers.{" "}
          <Link to="/trait-preferences" className={TEXT_LINK}>
            Tell us how much give you have
          </Link>
          .
        </p>
      )}
    </section>
  );
}

interface CompanyDetailPageProps {
  /** Override the posting and research polling schedule (tests). */
  pollTiming?: PollTiming;
}

export default function CompanyDetailPage({ pollTiming }: CompanyDetailPageProps = {}) {
  const { id = "" } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const rawPosting = searchParams.get("posting");
  const postingId = rawPosting && /^\d+$/.test(rawPosting) ? Number(rawPosting) : null;
  const postingPoll = usePostingStatus(postingId, pollTiming);
  const postingStatus = postingPoll.data?.posting ?? null;
  const readPostingId = postingStatus?.has_read ? postingId : null;

  const readQuery = useCompanyRead(id, readPostingId);
  const profileQuery = useCompanyProfile(id);

  const setPosting = (next: number | null) => {
    const params = new URLSearchParams(searchParams);
    if (next === null) params.delete("posting");
    else params.set("posting", String(next));
    setSearchParams(params, { replace: true });
  };

  if (readQuery.isLoading) {
    return (
      <Shell>
        <div className="flex flex-col items-center gap-4 pt-16" role="status">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-forest-light border-t-transparent motion-reduce:animate-none" />
          <p className={BODY_MUTED}>Loading your read...</p>
        </div>
      </Shell>
    );
  }

  if (readQuery.isError || !readQuery.data) {
    return (
      <Shell>
        <div className="mx-auto max-w-sm rounded-[6px] border border-red-200 bg-red-50 px-5 py-4 text-red-800" role="alert">
          <p className="mb-1 font-semibold">We couldn't load this company.</p>
          <p className="text-[0.88rem]">Please try again in a moment.</p>
          <button
            type="button"
            onClick={() => void readQuery.refetch()}
            className="mt-3 text-[0.88rem] font-semibold text-red-800 underline underline-offset-4"
          >
            Try again
          </button>
        </div>
      </Shell>
    );
  }

  const read = readQuery.data;
  const name = read.company.name ?? "This company";
  const profile = (profileQuery.data?.profile ?? null) as LegacyProfileDocument | null;
  const overview = profile?.overview;
  const facts = [text(overview?.industry), text(overview?.size), text(overview?.headquarters)].filter(Boolean);
  const website = text(overview?.website);
  const researching = read.research?.status === "queued" || read.research?.status === "running";
  const postingTraits = new Map(
    (read.posting?.traits ?? []).map((trait) => [trait.dimension, trait] as const),
  );

  let body: ReactNode;
  if (read.state === "core_required") {
    body = (
      <section className={`${PANEL} space-y-4 px-5 py-5`}>
        <h2 className={REPORT_H2}>Start with how you like to work</h2>
        <p className={BODY_MUTED}>
          Your read of {name} compares it with your own preferences, so it needs your Work
          Pulse answers first.
        </p>
        <button type="button" onClick={() => navigate("/work-pulse")} className={PRIMARY}>
          Take Work Pulse
        </button>
      </section>
    );
  } else if (read.state === "not_researched") {
    body = (
      <section className={`${PANEL} space-y-4 px-5 py-5`}>
        <h2 className={REPORT_H2}>We haven't researched {name} yet</h2>
        <p className={BODY_MUTED}>
          {researching
            ? "Research on this company is under way. Come back in a few minutes and your read will be here."
            : "We read what's public about how work runs there, on six traits, and set it beside your answers. It takes a few minutes."}
        </p>
        {researching ? (
          <button type="button" className={QUIET_BUTTON} onClick={() => void readQuery.refetch()}>
            Check again
          </button>
        ) : (
          <ResearchCompanyForm fixedName={name} hideOpenLink pollTiming={pollTiming} />
        )}
      </section>
    );
  } else {
    body = (
      <>
        <ReadSummary read={read} />
        <section className="space-y-3" aria-label="Trait by trait">
          {(read.traits ?? []).map((trait) => (
            <TraitReadCard
              key={trait.dimension}
              trait={trait}
              posting={postingTraits.get(trait.dimension) ?? null}
            />
          ))}
        </section>
        <PostingPanel
          companyId={read.company.id}
          companyName={name}
          postingId={postingId}
          progress={{ status: postingStatus, error: postingPoll.error }}
          read={read.posting}
          onPostingChange={setPosting}
        />
        <TookThisJob companyId={read.company.id} companyName={name} />
      </>
    );
  }

  return (
    <Shell>
      <BackLink />
      <header className="space-y-2">
        <p className="text-[0.8rem] font-semibold uppercase tracking-[0.12em] text-forest-light">
          CompanyLens™
        </p>
        <h1 className={PAGE_H1}>{name}</h1>
        {facts.length > 0 && <p className={BODY_MUTED}>{facts.join(" · ")}</p>}
        {website && /^https?:\/\//i.test(website) && (
          <a href={website} target="_blank" rel="noopener noreferrer" className={`${TEXT_LINK} text-[0.93rem]`}>
            {website}
          </a>
        )}
      </header>
      {body}
      {profile && hasLegacyContent(profile) && <LegacyProfile profile={profile} />}
    </Shell>
  );
}
