/**
 * scoringJobHandlers.ts — doubles for the Phase 3c job endpoints.
 *
 * Not part of `defaultHandlers` — like `signedIn()` and the resume-parse
 * builders, these are opted into by the tests that exercise a job flow, via
 * `server.use(...)`.
 *
 * ── EVERY BUILDER HERE IS A FACTORY, AND THAT IS LOAD-BEARING ───────────────
 *
 * `scoringJobProgresses`'s call counter is local to the handler instance the
 * `resolve()` closure captures, not to this module. Call the builder fresh
 * inside each test that needs staged progression; hoisting one instance's
 * handler into a module-level constant would let one test's polling advance
 * another test's counter, and the symptom — a job that is already `succeeded`
 * on its first poll — looks like a bug in the hook rather than in the fixture.
 *
 * ── WHY A NON-MATCHING KIND FALLS THROUGH RATHER THAN 404-ING ───────────────
 *
 * `/assessments/{kind}/scoring-jobs` is one route for three instruments, so a
 * handler bound to that path matches all three and has to check `params.kind`
 * itself. When the kind is not the one the builder was made for, the resolver
 * returns `undefined`: MSW then tries the next matching handler and, if there
 * is none, `onUnhandledRequest: "error"` fails the test. Answering 404 instead
 * would let a test that stubbed `wpll` silently absorb a call the code made to
 * `manager_match` — which is precisely the drift `server.ts` set that option to
 * catch.
 */
import { HttpResponse } from "msw";

import { mock } from "./contract";
import type { components } from "../../src/api/schema";
import type { ScoringJobKind, ScoringJobResult } from "../../src/hooks/useScoringJob";

type ScoringJobAccepted = components["schemas"]["ScoringJobAccepted"];
type PathSuggestionJobAccepted = components["schemas"]["PathSuggestionJobAccepted"];
type PathSuggestionsResponse = components["schemas"]["PathSuggestionsResponse"];

/**
 * One step of a job's progression.
 *
 * `result` is that kind's own result model — a `WpllResultResponse` cannot be
 * handed to a `manager_match` builder, for the same reason the hook narrows per
 * kind (A12). The doubles enforce the contract they exist to describe.
 */
export interface ScoringJobStep<K extends ScoringJobKind> {
  status: string;
  result?: ScoringJobResult<K> | null;
  error?: string | null;
}

/** `POST /assessments/{kind}/scoring-jobs` -> 202 with a job handle. */
export function scoringJobAccepted(kind: ScoringJobKind, jobId = "job-1") {
  return mock("post", "/api/v1/assessments/{kind}/scoring-jobs").resolve(({ params }) => {
    if (params.kind !== kind) return undefined;
    // Typed against the contract even though `resolve` does not check the body
    // for us the way `reply` does — see the header of contract.ts.
    const body: ScoringJobAccepted = {
      job_id: jobId,
      status: "queued",
      status_url: `/api/v1/assessments/${kind}/scoring-jobs/${jobId}`,
    };
    return HttpResponse.json(body, { status: 202 });
  });
}

/**
 * `GET /assessments/{kind}/scoring-jobs/{job_id}` -> advances one step per call,
 * then holds on the last step.
 *
 * A 404 for another job id of the same kind, matching the real endpoint's answer
 * for an unknown or foreign handle. A different *kind* falls through instead —
 * see the header.
 */
export function scoringJobProgresses<K extends ScoringJobKind>(
  kind: K,
  jobId: string,
  steps: ScoringJobStep<K>[],
) {
  let call = 0;
  return mock("get", "/api/v1/assessments/{kind}/scoring-jobs/{job_id}").resolve(
    ({ params }) => {
      if (params.kind !== kind) return undefined;
      if (params.job_id !== jobId) {
        return HttpResponse.json({ error: "Not found" }, { status: 404 });
      }
      const step = steps[Math.min(call, steps.length - 1)];
      call += 1;
      return HttpResponse.json({
        job_id: jobId,
        status: step.status,
        result: step.result ?? null,
        error: step.error ?? null,
      });
    },
  );
}

/**
 * `GET /assessments/{kind}/scoring-jobs/{job_id}` -> always 404 for this kind
 * (unknown / stale / someone else's handle).
 *
 * `jobId` isn't read — every request to this kind's poll 404s — but is kept in
 * the signature so a test reads clearly about which handle it is simulating as
 * gone, the same way `resumeParseJobNotFound` does.
 */
export function scoringJobNotFound(kind: ScoringJobKind, _jobId: string) {
  return mock("get", "/api/v1/assessments/{kind}/scoring-jobs/{job_id}").resolve(
    ({ params }) => {
      if (params.kind !== kind) return undefined;
      return HttpResponse.json({ error: "Not found" }, { status: 404 });
    },
  );
}

/** `POST /me/path-suggestion-jobs` -> 202 with a job handle. */
export function pathSuggestionJobAccepted(jobId = "path-job-1") {
  const body: PathSuggestionJobAccepted = {
    job_id: jobId,
    status: "queued",
    status_url: `/api/v1/me/path-suggestion-jobs/${jobId}`,
  };
  return mock("post", "/api/v1/me/path-suggestion-jobs").reply(202, body);
}

/** One step of a `pathSuggestionJobProgresses` sequence. */
export interface PathSuggestionJobStep {
  status: string;
  result?: PathSuggestionsResponse | null;
  error?: string | null;
}

/**
 * `GET /me/path-suggestion-jobs/{job_id}` -> advances one step per call, then
 * holds. A 404 for any other job id.
 */
export function pathSuggestionJobProgresses(jobId: string, steps: PathSuggestionJobStep[]) {
  let call = 0;
  return mock("get", "/api/v1/me/path-suggestion-jobs/{job_id}").resolve(({ params }) => {
    if (params.job_id !== jobId) {
      return HttpResponse.json({ error: "Not found" }, { status: 404 });
    }
    const step = steps[Math.min(call, steps.length - 1)];
    call += 1;
    return HttpResponse.json({
      job_id: jobId,
      status: step.status,
      result: step.result ?? null,
      error: step.error ?? null,
    });
  });
}
