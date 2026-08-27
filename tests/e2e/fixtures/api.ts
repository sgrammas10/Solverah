/**
 * Contract-shaped stubs for the endpoints the smoke path touches.
 *
 * WHY THE API IS STUBBED HERE -- read this before treating a green run as proof
 * the backend works, because it is not that.
 *
 * Two of the four steps cannot be driven against a live backend without either
 * reaching into the database or reading a mailbox. Registration issues a 6-digit
 * code that is mailed and never returned on the wire, so `verify` has no
 * automatable input; and `matches` only returns rows once companies have been
 * scored against the respondent's stored culture profile. Supplying either one
 * against a live API means writing rows behind the app's back, which is a worse
 * lie than a stub and a slower one.
 *
 * There is also a concrete local reason. These stubs write nothing, so the suite
 * cannot collide with the backend suite over the shared development database --
 * a real failure mode on this repo, where two pytest processes on one database
 * once produced a red run that looked like a code defect.
 *
 * WHAT THIS STILL EXERCISES, which is more than a component test does:
 *
 *   - the built production bundle served by `vite preview`, including the lazy
 *     route chunks -- a broken dynamic import fails here and nowhere else;
 *   - real routing, real navigation, real redirects, and the ProtectedRoute
 *     role check on /work-pulse and /company-lens;
 *   - real form state: the register page's own password rules and terms gate,
 *     the 6-digit verify guard, the stepper's per-question Next/Finish gating;
 *   - the REQUEST side of the contract. Every payload the SPA sends is recorded
 *     in the journal below and asserted in the spec, so a call site that changes
 *     shape fails here.
 *
 * WHAT IT DOES NOT EXERCISE: any backend code whatsoever. The response shapes
 * below are transcribed from the types the frontend declares -- SessionResponse
 * in src/contexts/authContext.ts, AssessmentForm in src/hooks/useAssessment.ts,
 * MatchesPage in src/pages/CompanyLensPage.tsx -- so they can drift from what
 * Flask actually returns. tests/test_frontend_contract.py is the check that
 * catches that drift: it asserts every path the SPA calls is one the API serves.
 * The two are complementary and neither replaces the other.
 */
import type { Page } from "@playwright/test";

export const TEST_USER = {
  name: "Smoke Test",
  email: "e2e.smoke@example.test",
  // Satisfies the register page's own rules: 12+ chars, upper, lower, digit, symbol.
  password: "Sm0ke-Test-Passw0rd!",
  verificationCode: "123456",
  id: "01931f4e-0000-7000-8000-00000000e2e5",
  role: "job-seeker" as const,
};

/** EXPECTED_ITEM_COUNT in src/hooks/useAssessment.ts. The hook refuses to submit anything else. */
export const ITEM_COUNT = 24;
const ITEMS_PER_BLOCK = 6;

/**
 * An assessment form in the wire shape, with opaque tokens.
 *
 * Deliberately carries no dimension labels and no item ids, because the real
 * payload carries none -- see the header of useAssessment.ts. The stepper renders
 * the blocks flattened in the order received, so the token order here is also the
 * order the spec answers them in.
 */
export function buildAssessmentForm() {
  const blocks = [];
  for (let b = 0; b < ITEM_COUNT / ITEMS_PER_BLOCK; b += 1) {
    const items = [];
    for (let i = 0; i < ITEMS_PER_BLOCK; i += 1) {
      const n = b * ITEMS_PER_BLOCK + i + 1;
      items.push({
        token: "e2e-token-" + String(n).padStart(2, "0"),
        prompt: "Question " + n + ": which of these describes how you prefer to work?",
        options: [
          { key: "A", text: "Option A for question " + n },
          { key: "B", text: "Option B for question " + n },
        ],
      });
    }
    blocks.push({ block: b + 1, items });
  }
  return { form_version: "e2e-1", respondent_id: "e2e-respondent", blocks };
}

function companyMatch(id: number, name: string, fit: number) {
  return {
    id,
    name,
    slug: name.toLowerCase().replace(/[^a-z0-9]+/g, "-"),
    industry: "Software",
    fit_score: fit,
    top_matching_dimensions: ["pace", "harmony"],
    top_mismatching_dimensions: ["data_orientation"],
    fit_summary: name + " lines up with how you work on pace and harmony.",
  };
}

export const BEST_MATCHES = [
  companyMatch(101, "Northwind Labs", 0.92),
  companyMatch(102, "Harbour Systems", 0.87),
];
export const WORST_MATCHES = [
  companyMatch(201, "Grindstone Corp", 0.31),
  companyMatch(202, "Ledger and Co", 0.24),
];

/** Everything the SPA sent, so the spec can assert on the request side. */
export interface ApiJournal {
  register?: Record<string, unknown>;
  verify?: Record<string, unknown>;
  login?: Record<string, unknown>;
  submission?: { responses: Record<string, string> };
  /** `order` query param of each GET /me/matches, in call order. */
  matchOrders: string[];
  /** Any /api/v1 request with no handler below. Asserted empty -- see the spec. */
  unhandled: string[];
  /** The form actually served, so the spec can check the tokens that came back. */
  servedForm: ReturnType<typeof buildAssessmentForm>;
}

/**
 * Intercept every `/api/v1/**` request for this page and answer it in shape.
 *
 * Stateful on purpose: `GET /auth/session` must 401 before sign-in and return a
 * user after it, because each `page.goto` remounts AuthProvider and re-probes.
 * A fixed 200 would let the assessment and matches steps pass without the login
 * step having done anything, which is the exact failure a smoke suite exists to
 * rule out.
 */
export async function installApiStubs(page: Page): Promise<ApiJournal> {
  const servedForm = buildAssessmentForm();
  const journal: ApiJournal = { matchOrders: [], unhandled: [], servedForm };
  const state = { signedIn: false, wpV2Completed: false };

  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace(/^.*\/api\/v1/, "");
    const key = request.method() + " " + path;

    const json = (status: number, body: unknown) =>
      route.fulfill({
        status,
        contentType: "application/json",
        body: JSON.stringify(body),
      });

    const sessionUser = {
      id: TEST_USER.id,
      email: TEST_USER.email,
      name: TEST_USER.name,
      role: TEST_USER.role,
    };

    switch (key) {
      case "GET /auth/session":
        if (!state.signedIn) return json(401, { error: "Not authenticated" });
        return json(200, {
          user: sessionUser,
          csrf_token: "e2e-csrf-token",
          flags: {
            email_confirmed: true,
            wpl_completed: false,
            wpll_completed: false,
            wp_v2_completed: state.wpV2Completed,
          },
        });

      case "POST /auth/register":
        journal.register = request.postDataJSON();
        return json(201, { message: "Account created. Check your email for a code." });

      case "POST /auth/email/verify":
        journal.verify = request.postDataJSON();
        return json(200, { message: "Email verified" });

      case "POST /auth/login":
        journal.login = request.postDataJSON();
        state.signedIn = true;
        // The login envelope still nests the profile document inside `user`;
        // AuthContext.splitLoginUser strips it out into the query cache.
        return json(200, {
          user: { ...sessionUser, profileComplete: false, profileData: {} },
          csrfToken: "e2e-csrf-token",
        });

      case "POST /auth/logout":
        state.signedIn = false;
        return json(200, { message: "Signed out" });

      case "GET /me/profile":
        return json(200, { profile: {} });

      case "GET /me/dashboard":
        return json(200, {
          profileCompletion: "40%",
          jobMatches: 2,
          applications: 0,
          hasIntakeSubmission: false,
          recentActivity: [],
          recommendations: [],
        });

      case "GET /assessments/core/form":
        return json(200, servedForm);

      case "POST /assessments/core/submissions":
        journal.submission = request.postDataJSON();
        state.wpV2Completed = true;
        return json(201, {
          submission_id: "e2e-submission",
          scoring_key_version: "e2e-key-1",
          dimensions_scored: 6,
        });

      case "GET /me/matches": {
        const order = url.searchParams.get("order") ?? "";
        journal.matchOrders.push(order);
        return json(200, {
          data: order === "best" ? BEST_MATCHES : WORST_MATCHES,
          next_cursor: null,
          total_companies_scored: BEST_MATCHES.length + WORST_MATCHES.length,
          lens: "culture",
          order,
        });
      }

      default:
        // Recorded rather than silently answered: an endpoint appearing here is
        // the SPA calling something this suite does not model, and the spec
        // asserts the list is empty so it cannot pass unnoticed.
        journal.unhandled.push(key);
        return json(200, {});
    }
  });

  return journal;
}
