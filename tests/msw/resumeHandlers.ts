/**
 * resumeHandlers.ts — doubles for the async resume-parse job endpoints.
 *
 * Not part of `defaultHandlers` — like `signedIn()`, these are opted into by
 * the handful of tests that exercise the resume-parse flow, via `server.use(...)`.
 *
 * `resumeParseJobProgresses`'s call counter is local to the handler instance
 * `resolve()` closes over, not to this module. Call the builder fresh inside
 * each test that needs staged progression; sharing one instance's returned
 * handler across tests (e.g. via a module-level constant) would let one
 * test's polling advance another test's counter.
 */
import { HttpResponse } from "msw";

import { mock } from "./contract";

/** `POST .../parse-jobs` -> 202 with a job handle. */
export function resumeParseJobAccepted(jobId = "job-1") {
  return mock("post", "/api/v1/me/resumes/{resume_id}/parse-jobs").reply(202, {
    job_id: jobId,
    status: "queued",
    status_url: `/api/v1/me/resume-parse-jobs/${jobId}`,
  });
}

/** One step of a `resumeParseJobProgresses` sequence. */
export interface ResumeParseJobStep {
  status: string;
  profile?: Record<string, unknown> | null;
  error?: string | null;
}

/**
 * `GET .../resume-parse-jobs/{job_id}` -> advances one step per call, then
 * holds on the last step. A 404 for any other job id, matching the real
 * endpoint's behaviour for an unknown/foreign handle.
 */
export function resumeParseJobProgresses(jobId: string, steps: ResumeParseJobStep[]) {
  let call = 0;
  return mock("get", "/api/v1/me/resume-parse-jobs/{job_id}").resolve(({ params }) => {
    if (params.job_id !== jobId) {
      return HttpResponse.json({ error: "Not found" }, { status: 404 });
    }
    const step = steps[Math.min(call, steps.length - 1)];
    call += 1;
    return HttpResponse.json({
      job_id: jobId,
      status: step.status,
      profile: step.profile ?? null,
      error: step.error ?? null,
    });
  });
}

/**
 * `GET .../resume-parse-jobs/{job_id}` -> always 404 (unknown / stale / someone
 * else's job). `jobId` isn't read -- every request to this path 404s -- but is
 * kept in the signature for symmetry with the other builders, and so a test
 * reads clearly about which id it's simulating as gone.
 */
export function resumeParseJobNotFound(_jobId: string) {
  return mock("get", "/api/v1/me/resume-parse-jobs/{job_id}").resolve(() =>
    HttpResponse.json({ error: "Not found" }, { status: 404 })
  );
}
