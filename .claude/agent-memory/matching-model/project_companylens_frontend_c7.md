---
name: companylens-frontend-c7
description: 2026-10-14 C7 (six-trait build) UNCOMMITTED -- CompanyLens + company-page frontend rewrite against the C6 API; file layout across the two slices, copy choices Julie may revise, the no-probability guard, traps hit (contract scan, jsdom min validation)
metadata:
  type: project
---

2026-10-13/14, lane C7 of docs/superpowers/plans/2026-10-13-companylens-six-trait.md.
UNCOMMITTED; orchestrator reviews. No App.tsx change was needed (both routes existed).

**Layout.** matching slice owns the shared pieces and exports them via `matching/index.ts`
(companies imports `"../matching"`, never deep): `useCompanyLens.ts` (types from schema.ts,
`companyLensKeys` -- everything under `["companyLens"]` so a finished research run
invalidates list + read together; `useMatches` infinite query; `useResearchCompany`),
`usePoll.ts` (setTimeout chain, 3 s x1.5 to 20 s, stops on done/4xx/3 retryable failures,
cancelled on unmount), `companyLensCopy.ts` (all words), `lensStyles.ts` (copy of the
Situation Report class strings -- keep in step), `LensBits`, `ResearchCompanyForm`,
`CompanyMatchCard`. companies slice: `useCompanyRead.ts` (read, legacy profile, postings,
links incl. PATCH "I left"), `legacyProfile.ts`, `TraitReadCard`, `PostingPanel`,
`TookThisJob`, `LegacyProfile`. Fixtures + MSW builders + `assertNoProbabilityText` live in
`tests/msw/companyLensHandlers.ts`; a `noProbability.test.tsx` sweep sits in each slice.

**Copy choices (best guess, Julie revises):** direction = "More on the <pole> side than you
prefer" (poles like "invent what does not" cannot take "more X"); tolerance = "inside/outside
your give"; "Based on N of 6" counts known + mixed (mixed enters the ranking at its worse
end) -- open question to Julie/Sebastian whether it should be known only.
Posting disagreement direction is inferred from less<even<more of the two directions;
same direction => "describe X differently".

**Dropped from the legacy profile on purpose:** the retired 8-dim culture bars and the
Glassdoor rating grid (numbers out of 5) -- no-score rule.

**Traps hit:** (1) tests/test_frontend_contract.py reads a fetchWithAuth path up to the first
"?" -- a `${query}` suffix is scanned as a path segment and fails "every path is served";
write the "?" literally in a second call site. (2) jsdom enforces `<input type=date min>` on
submit: a test below min never sends the request. (3) `findByText` with an alternation
regex hits several nodes on gate pages -- use findAll. (4) recordRequests owns the
request:start listener; add your own in beforeAll, never removeAllListeners.

**Open at hand-off:** e2e `tests/e2e/smoke.spec.ts` "matches" step still asserts the old
"92% match" two-ended page (frontend-shell). Stale "coming soon" copy: IntelligencePage card
(profile-hub), WorkPulseResultsPage teaser with "Fit score: --" (core-assessments),
TrustPage "Company matching is not live" (intelligence owner). No list endpoint for a user's
postings, so a posting persists only via `?posting=` in the URL.
