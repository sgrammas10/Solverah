/**
 * companyLensHandlers.ts -- doubles and fixtures for the six-trait CompanyLens API.
 *
 * Not part of `defaultHandlers`: the CompanyLens and company-page tests opt in with
 * `server.use(...)`, like the scoring-job and resume builders.
 *
 * Fixtures follow Daniel's journey (Solverah_IP/match_model_alignment/
 * 05_USER_JOURNEYS.md): a 2,000-person logistics firm read on 4 of 6 traits,
 * Autonomy a must-have and mixed (corporate vs sites, explained by scope), Feedback
 * unknown, and a pasted posting that disagrees with the company on Autonomy.
 *
 * Every progression builder is a FACTORY (see scoringJobHandlers.ts for why): its
 * call counter lives in the handler it returns, never at module scope.
 *
 * `assertNoProbabilityText` is the C7 guard: the page may show coverage counts and
 * dates, never a percentage or a number beside "fit", "match" or "score".
 */
import { HttpResponse } from "msw";

import { mock } from "./contract";
import type { components } from "../../src/shared/api/schema";

type S = components["schemas"];
export type MatchesResponse = S["MatchesResponse"];
export type MatchEntry = S["MatchEntry"];
export type CompanyReadResponse = S["CompanyReadResponse"];
export type TraitRead = S["TraitRead"];
export type PostingRead = S["PostingRead"];
export type ResearchRunStatus = S["ResearchRunStatus"];
export type JobPostingStatus = S["JobPostingStatus"];
export type CompanyLinkEntry = S["CompanyLinkEntry"];
export type CompanyDetailResponse = S["CompanyDetailResponse"];
export type ProblemDetailResponse = S["ProblemDetailResponse"];

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const POLES = {
  autonomy: { label: "Autonomy", low_pole: "directed", high_pole: "self-directed" },
  pace: { label: "Pace", low_pole: "steady", high_pole: "fast" },
  collaboration: { label: "Collaboration", low_pole: "solo", high_pole: "collective" },
  feedback: { label: "Feedback", low_pole: "sparse and gentle", high_pole: "frequent and blunt" },
  innovation: { label: "Innovation", low_pole: "refine what exists", high_pole: "invent what does not" },
  decision: { label: "Decision basis", low_pole: "judgement", high_pole: "data and analysis" },
} as const;

export const NORTHWIND_ID = 41;
export const GRINDSTONE_ID = 42;
export const STUDIO_ID = 43;

export const COVERAGE_4_OF_6: S["CoverageCounts"] = { known: 3, mixed: 1, unknown: 2, total: 6 };

export const MATCH_NORTHWIND: MatchEntry = {
  id: NORTHWIND_ID,
  name: "Northwind Freight",
  slug: "northwind-freight",
  state: "ranked",
  rank: 1,
  coverage: COVERAGE_4_OF_6,
  flags: { must_have_breaks: 0, risks: 1, investigate: 0 },
  next_step: {
    category: "investigate",
    reason: "Autonomy is one of your must-haves and the evidence on it disagrees.",
  },
  must_have_reads: [
    {
      dimension: "autonomy",
      ...POLES.autonomy,
      status: "mixed",
      must_have: true,
      direction: null,
      within_tolerance: null,
      flag: "risk",
    },
  ],
  missing: ["feedback", "decision"],
  size_note:
    "Thousands of people: the company-wide read says less about any one team. Ask about the team, and the manager.",
  research: null,
};

export const MATCH_GRINDSTONE: MatchEntry = {
  id: GRINDSTONE_ID,
  name: "Grindstone Corp",
  slug: "grindstone-corp",
  state: "ranked",
  rank: 2,
  coverage: { known: 5, mixed: 0, unknown: 1, total: 6 },
  flags: { must_have_breaks: 1, risks: 0, investigate: 0 },
  next_step: { category: "decide", reason: "Most of what matters to you is clear here." },
  must_have_reads: [
    {
      dimension: "pace",
      ...POLES.pace,
      status: "known",
      must_have: true,
      direction: "more",
      within_tolerance: false,
      flag: "must_have_break",
    },
  ],
  missing: ["innovation"],
  size_note: "Hundreds of people: teams here can differ from the company-wide read. Ask about the team.",
  research: { run_id: 9, company_id: GRINDSTONE_ID, status: "running", error: null, created_at: null, finished_at: null, company: null },
};

export const MATCH_STUDIO: MatchEntry = {
  id: STUDIO_ID,
  name: "Little Studio",
  slug: "little-studio",
  state: "not_enough_evidence",
  rank: null,
  coverage: { known: 2, mixed: 0, unknown: 4, total: 6 },
  flags: { must_have_breaks: 0, risks: 0, investigate: 0 },
  next_step: { category: "explore", reason: "We found too little to read this company well." },
  must_have_reads: [],
  missing: ["autonomy", "collaboration", "feedback", "decision"],
  size_note: "Tens of people: the company-wide read is a fair guide to most teams here.",
  research: null,
};

export function matchesBody(overrides: Partial<MatchesResponse> = {}): MatchesResponse {
  return {
    state: "ranked",
    data: [MATCH_NORTHWIND, MATCH_GRINDSTONE, MATCH_STUDIO],
    next_cursor: null,
    total_companies: 3,
    preferences_answered: true,
    ...overrides,
  };
}

const CORPORATE_ITEM: S["EvidenceItem"] = {
  paraphrase: "Office staff describe owning their projects with light approval.",
  source_type: "employee_review",
  scope: "division",
  scope_label: "Corporate office",
  published_at: "2026-03-02",
  source_url: "https://reviews.example.com/a",
  abstained: false,
};

const SITE_ITEM: S["EvidenceItem"] = {
  paraphrase: "Warehouse staff describe tight procedures and sign-off for most changes.",
  source_type: "employee_review",
  scope: "location",
  scope_label: "Regional sites",
  published_at: "2026-05-18",
  source_url: null,
  abstained: false,
};

const PACE_ITEMS: S["EvidenceItem"][] = [1, 2, 3, 4].map((n) => ({
  paraphrase: `Pace evidence ${n}: deadlines are steady and planned weeks ahead.`,
  source_type: n === 4 ? "news" : "employee_review",
  scope: "company",
  scope_label: null,
  published_at: `2025-0${n}-10`,
  source_url: `https://example.com/pace/${n}`,
  abstained: false,
}));

function trait(dimension: keyof typeof POLES, rest: Partial<TraitRead>): TraitRead {
  return {
    dimension,
    ...POLES[dimension],
    status: "unknown",
    must_have: false,
    direction: null,
    within_tolerance: null,
    flag: null,
    evidence: null,
    scope_note: null,
    mixed: null,
    paraphrases: [],
    explanation: null,
    questions: [],
    ...rest,
  };
}

export const TRAITS: TraitRead[] = [
  trait("autonomy", {
    status: "mixed",
    must_have: true,
    flag: "risk",
    evidence: { count: 6, abstained: 1, first_dated: "2025-01-04", last_dated: "2026-05-18", source_types: ["employee_review"] },
    scope_note:
      "The split follows where the evidence comes from: different parts of the company describe different things.",
    mixed: {
      explanation:
        "The split follows where the evidence comes from: different parts of the company describe different things.",
      low_end: { direction: "less", within_tolerance: false, evidence: [SITE_ITEM] },
      high_end: { direction: "even", within_tolerance: true, evidence: [CORPORATE_ITEM] },
    },
    explanation:
      "The evidence disagrees on autonomy: some parts of the company describe real ownership, others describe sign-off for everything. Find out which this team is.",
    questions: [
      "Walk me through the last process change on this team. Who proposed it, and who had to approve it?",
      "What decisions would I make without checking with you first?",
    ],
  }),
  trait("pace", {
    status: "known",
    direction: "even",
    within_tolerance: true,
    evidence: { count: 4, abstained: 0, first_dated: "2025-01-10", last_dated: "2025-04-10", source_types: ["employee_review", "news"] },
    paraphrases: PACE_ITEMS,
  }),
  trait("collaboration", {
    status: "known",
    direction: "more",
    within_tolerance: true,
    evidence: { count: 3, abstained: 0, first_dated: "2025-06-01", last_dated: "2025-06-01", source_types: ["careers_page"] },
    paraphrases: [
      {
        paraphrase: "The careers page says most work is done in cross-site teams.",
        source_type: "careers_page",
        scope: "company",
        scope_label: null,
        published_at: "2025-06-01",
        source_url: "https://northwind.example.com/careers",
        abstained: false,
      },
    ],
  }),
  trait("feedback", {
    status: "unknown",
    explanation:
      "We found too little on how feedback works here. If it matters to you, ask about it directly.",
  }),
  trait("innovation", {
    status: "known",
    direction: "less",
    within_tolerance: false,
    evidence: { count: 3, abstained: 0, first_dated: null, last_dated: null, source_types: ["news"] },
    paraphrases: [],
  }),
  trait("decision", { status: "unknown", explanation: "We found too little on how decisions get made here." }),
];

export function readBody(overrides: Partial<CompanyReadResponse> = {}): CompanyReadResponse {
  return {
    state: "ranked",
    company: {
      id: NORTHWIND_ID,
      name: "Northwind Freight",
      slug: "northwind-freight",
      size_band: 4,
      size_note: MATCH_NORTHWIND.size_note,
    },
    research: null,
    preferences_answered: true,
    coverage: COVERAGE_4_OF_6,
    flags: { must_have_breaks: 0, risks: 1, investigate: 0 },
    next_step: MATCH_NORTHWIND.next_step,
    missing: ["feedback", "decision"],
    traits: TRAITS,
    posting: null,
    ...overrides,
  };
}

export const POSTING_ID = 77;

export function postingStatus(overrides: Partial<JobPostingStatus> = {}): JobPostingStatus {
  return {
    id: POSTING_ID,
    company_id: NORTHWIND_ID,
    title: "Regional Operations Manager",
    status: "pending",
    created_at: "2026-10-13T10:00:00",
    has_read: false,
    ...overrides,
  };
}

/**
 * The posting reads Autonomy as self-directed (the company is mixed there, so the
 * server cannot call it a disagreement: both sides must be known) and Collaboration
 * as solo, against a company that is known on the collective side -- that one
 * disagrees.
 */
const POSTING_KNOWN: Record<string, { direction: "more" | "less"; disagrees: boolean }> = {
  autonomy: { direction: "more", disagrees: false },
  collaboration: { direction: "less", disagrees: true },
};

export const POSTING_READ: PostingRead = {
  ...postingStatus({ status: "scored", has_read: true }),
  disagreements: ["collaboration"],
  traits: TRAITS.map((t) => ({
    dimension: t.dimension,
    label: t.label,
    low_pole: t.low_pole,
    high_pole: t.high_pole,
    must_have: t.must_have,
    flag: null,
    status: POSTING_KNOWN[t.dimension] ? "known" : "unknown",
    direction: POSTING_KNOWN[t.dimension]?.direction ?? null,
    within_tolerance: POSTING_KNOWN[t.dimension] ? true : null,
    disagrees: POSTING_KNOWN[t.dimension]?.disagrees ?? false,
    evidence: null,
    explanation: null,
    paraphrases:
      t.dimension === "autonomy"
        ? [
            {
              paraphrase: "The posting says the role owns the regional process end to end.",
              source_type: "user_pasted_posting",
              scope: "role",
              scope_label: "Regional Operations Manager",
              published_at: null,
              source_url: null,
              abstained: false,
            },
          ]
        : [],
    questions: [],
  })),
};

export function researchRun(overrides: Partial<ResearchRunStatus> = {}): ResearchRunStatus {
  return {
    run_id: 501,
    company_id: 60,
    status: "queued",
    error: null,
    created_at: "2026-10-13T10:00:00",
    finished_at: null,
    company: { id: 60, name: "Acme Logistics", slug: "acme-logistics", industry: null },
    ...overrides,
  };
}

export const LEGACY_PROFILE = {
  overview: { name: "Northwind Freight", industry: "Logistics", size: "2,000 people", headquarters: "Leeds" },
  culture: {
    culture_narrative_company: "The company describes itself as practical and steady.",
    empathy: 0.82,
  },
  glassdoor: { overall_rating: 3.9, key_positives: "Stable hours." },
};

// ---------------------------------------------------------------------------
// Handlers
// ---------------------------------------------------------------------------

export function matchesReply(body: MatchesResponse = matchesBody()) {
  return mock("get", "/api/v1/me/matches").reply(200, body);
}

/** `GET /companies/{id}/read`: `withPosting` answers when `?posting_id=` is present. */
export function companyReadReply(
  body: CompanyReadResponse = readBody(),
  withPosting: CompanyReadResponse | null = null,
) {
  return mock("get", "/api/v1/companies/{company_id}/read").resolve(({ request }) => {
    const postingId = new URL(request.url).searchParams.get("posting_id");
    return HttpResponse.json(postingId && withPosting ? withPosting : body, { status: 200 });
  });
}

/** Answers the read with each body in turn, holding on the last. */
export function companyReadSequence(bodies: CompanyReadResponse[]) {
  let call = 0;
  return mock("get", "/api/v1/companies/{company_id}/read").resolve(() => {
    const body = bodies[Math.min(call, bodies.length - 1)];
    call += 1;
    return HttpResponse.json(body, { status: 200 });
  });
}

export function companyProfileReply(profile: CompanyDetailResponse["profile"] = null) {
  return mock("get", "/api/v1/companies/{company_id}").resolve(({ params }) => {
    const body: CompanyDetailResponse = {
      id: Number(params.company_id),
      name: "Northwind Freight",
      slug: "northwind-freight",
      profile,
    };
    return HttpResponse.json(body, { status: 200 });
  });
}

export function researchAccepted(run: ResearchRunStatus = researchRun(), cached = false) {
  return mock("post", "/api/v1/companies/research").reply(202, { run, cached });
}

/** A refusal body: a problem document (any subset of its fields) or a bare `{error}`. */
export type RefusalBody = Partial<ProblemDetailResponse>;

export function researchRefused(status: 429 | 503 | 400, body: RefusalBody) {
  return mock("post", "/api/v1/companies/research").resolve(() =>
    HttpResponse.json(body, { status }),
  );
}

export const DAILY_LIMIT_PROBLEM: ProblemDetailResponse = {
  instance: "/api/v1/companies/research",
  request_id: null,
  type: "https://solverah.com/errors/rate_limited",
  title: "Too many requests",
  status: 429,
  detail:
    "You can start research on up to five new companies a day; companies already researched are always free.",
  errors: [{ field: "name", code: "research_daily_limit" }],
};

/** `GET /companies/research/{run_id}`: one status per call, holding on the last. */
export function researchProgresses(statuses: ResearchRunStatus["status"][], base = researchRun()) {
  let call = 0;
  return mock("get", "/api/v1/companies/research/{run_id}").resolve(({ params }) => {
    // Wrong id: fall through, so onUnhandledRequest "error" fails the test (see scoringJobHandlers.ts).
    if (Number(params.run_id) !== base.run_id) return undefined;
    const status = statuses[Math.min(call, statuses.length - 1)];
    call += 1;
    return HttpResponse.json(researchRun({ ...base, status }), { status: 200 });
  });
}

export function postingAccepted(posting: JobPostingStatus = postingStatus()) {
  return mock("post", "/api/v1/me/job-postings").reply(202, { posting });
}

export function postingProgresses(steps: JobPostingStatus[]) {
  let call = 0;
  return mock("get", "/api/v1/me/job-postings/{posting_id}").resolve(() => {
    const posting = steps[Math.min(call, steps.length - 1)];
    call += 1;
    return HttpResponse.json({ posting }, { status: 200 });
  });
}

export function companyLinksReply(data: CompanyLinkEntry[] = []) {
  return mock("get", "/api/v1/me/company-links").reply(200, { data });
}

export function companyLink(overrides: Partial<CompanyLinkEntry> = {}): CompanyLinkEntry {
  return {
    id: 5,
    company_id: NORTHWIND_ID,
    started_on: "2026-11-02",
    ended_on: null,
    created_at: "2026-10-13T10:00:00",
    company: { id: NORTHWIND_ID, name: "Northwind Freight", slug: "northwind-freight", industry: null },
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// The no-probability guard
// ---------------------------------------------------------------------------

const PERCENT = /%|\bper\s?cent\b/i;
const NUMBER_NEAR_FIT_WORD =
  /\d[\d.,]*\s*(?:\/\s*\d+\s*)?(?:fit|match(?:es|ed)?|score[sd]?)\b|\b(?:fit|match(?:es|ed)?|score[sd]?)\b[^.\d]{0,12}\d/i;
const OUT_OF = /\b\d+(?:\.\d+)?\s*(?:\/|out of)\s*(?:5|10|100)\b/i;
const STARS = /[★☆⭐]/;
// A bare decimal ("0.82", ".5", "3.9"): the shape every raw model value and rating takes.
// Dates, years, "2,000" and "4 of 6" have no decimal point between digits.
const DECIMAL = /(?<![\w.])\d*\.\d+(?!\w)/;
// "Rated 3.9", "rated 4", "4 stars", "5-star".
const RATED = /(?:^|\W)rated\s+\d|\d+(?:\.\d+)?[\s-]*stars?(?:\W|$)/i;

/** Throw when `text` carries anything that reads as a probability or a score. */
export function assertNoProbabilityText(text: string): void {
  const problems: string[] = [];
  if (PERCENT.test(text)) problems.push("a percentage");
  if (NUMBER_NEAR_FIT_WORD.test(text)) problems.push("a number beside fit/match/score");
  if (OUT_OF.test(text)) problems.push("a number out of 5/10/100");
  if (STARS.test(text)) problems.push("a star rating");
  if (DECIMAL.test(text)) problems.push("a bare decimal");
  if (RATED.test(text)) problems.push("a rating");
  if (problems.length > 0) {
    throw new Error(`Rendered text carries ${problems.join(", ")}:\n${text}`);
  }
}
