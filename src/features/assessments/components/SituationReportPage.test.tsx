/**
 * SituationReportPage.test.tsx -- every state `GET /me/situation-report` can
 * return, over the real hook and a real query client (only `fetchWithAuth` is
 * mocked, per ManagerPlaybookPage.test.tsx's precedent).
 *
 * The 409 the recalibrate button can hit is fixtured as an `ApiError` carrying
 * `errors[0].code`, never as a bare `Error` with a matching message: the page
 * branches on `error.errorFor("core")?.code` and a bare Error would prove
 * nothing about that branch.
 *
 * THE D-15 ASSERTION IS THE POINT OF THIS FILE, not a nicety at the end of it.
 * The payload carries `env_score` per dimension and a `rank`, and neither may
 * reach the page in any form -- no digit, no bar, no percentage. The fixtures
 * below deliberately use env scores whose decimals would be conspicuous if
 * they leaked, and `expectNoScoresLeaked` is asserted on every rendering of the
 * `complete` state rather than once. A regression here is not cosmetic: three
 * coarse buckets are what makes the report un-hill-climbable, and a rendered
 * number hands back the resolution they exist to withhold.
 */
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";

import SituationReportPage from "./SituationReportPage";
import { createQueryClient } from "../../../shared/api/queryClient";
import { ApiError } from "../../../shared/api/apiError";
import type {
  SituationComplete,
  SituationDimensionEntry,
  SituationNeedsCore,
  SituationNeedsEnvironmentReport,
  StrainDimensionEntry,
} from "../useSituationReport";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  fetchWithAuth: vi.fn(),
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mocks.navigate };
});

vi.mock("../../auth/useAuth", () => ({
  useAuth: () => ({ fetchWithAuth: mocks.fetchWithAuth }),
}));

beforeEach(() => {
  vi.clearAllMocks();
});

function renderPage() {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <SituationReportPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** Serve the report, whatever the recalibrate button asks for after it, and
 *  the Pulse history the experienced-trend section reads -- zero check-ins by
 *  default, since most of these tests have nothing to do with that section. */
function serve(
  report: unknown,
  recalibrate?: () => Promise<unknown>,
  pulseHistory: unknown = { checkins: [], events: [] },
  experiments: unknown = { experiments: [] },
) {
  mocks.fetchWithAuth.mockImplementation((path: string) => {
    if (path === "/me/situation-report") return Promise.resolve(report);
    if (path === "/me/situation-report/recalibrate") {
      return recalibrate ? recalibrate() : Promise.resolve({ recalibrated: false });
    }
    if (path === "/me/pulse/history") return Promise.resolve(pulseHistory);
    if (path === "/me/experiments") return Promise.resolve(experiments);
    return Promise.reject(new Error(`unexpected path ${path}`));
  });
}

const GUIDANCE_NOTICE =
  "This guidance is general, not personal. Nothing here is a judgement about your employer.";

const STRAINING_AUTONOMY: SituationDimensionEntry = {
  dimension: "autonomy",
  env_score: 0.1234,
  bucket: "straining",
  direction: "under",
  rank: 0,
  diagnosis: {
    headline: "The role decides more of the how than you want decided",
    text: "This role settles more of that before it reaches you.",
  },
  registers: {
    change_in_place: {
      experiment_name: "One piece, your method, for a fortnight",
      experiment: "Pick one live piece of work and run the approach yourself.",
      steps: ["Name the piece before you start.", "Put one checkpoint in the middle."],
      signal: "How many decisions you made without waiting.",
    },
    negotiate: {
      who_and_where: "Whoever sets the approach on your work.",
      opening: "Open on the work rather than on how it feels.",
      scripts: ["I'd like to own the approach on X end to end."],
      if_no: "Ask whether the constraint is real or a preference.",
    },
    rarely_moves: {
      why_fixed: "Decision rights are usually set well above the person you would ask.",
      cost_of_staying: "The judgement you are best at does not get exercised.",
      what_it_implies: "A question about fit and not a failure on either side.",
    },
  },
  defers_to_decoder: false,
  decoder_crossref: "Some of what limits your latitude may be your manager rather than the role.",
};

const NOTABLE_FEEDBACK: SituationDimensionEntry = {
  dimension: "feedback",
  env_score: 0.8765,
  bucket: "notable",
  direction: "over",
  rank: 1,
  diagnosis: {
    headline: "Critique arrives more often and more bluntly than you want it",
    text: "This place says it as it sees it, immediately.",
  },
  registers: {
    rarely_moves: {
      why_fixed: "Feedback culture is enacted by one person at a time.",
      cost_of_staying: "A running commentary you brace for.",
      what_it_implies: "Worth separating the place from the person.",
    },
  },
  defers_to_decoder: true,
  decoder_crossref: null,
};

/** A second straining, change-in-place-carrying dimension, distinct from
 *  `STRAINING_AUTONOMY` -- the condition-experiments tests need two real
 *  cells to prove "disabled elsewhere" means something. */
const STRAINING_PACE: SituationDimensionEntry = {
  dimension: "pace",
  env_score: 0.7654,
  bucket: "straining",
  direction: "over",
  rank: 1,
  diagnosis: {
    headline: "The tempo is set higher than you can hold",
    text: "This role runs faster and hotter than that.",
  },
  registers: {
    change_in_place: {
      experiment_name: "Defend one block, for two weeks",
      experiment: "Take one protected block back and prove it costs nothing.",
      steps: ["Pick the block and put it in the calendar."],
      signal: "How much of the week is reactive rather than planned.",
    },
  },
  defers_to_decoder: false,
  decoder_crossref: null,
};

const ALIGNED_PACE: SituationDimensionEntry = {
  dimension: "pace",
  env_score: 0.5432,
  bucket: "aligned",
  direction: null,
  rank: 2,
  aligned_note: "You and this job want much the same tempo, and that is worth protecting.",
};

const COMPLETE: SituationComplete = {
  state: "complete",
  manager: { has_profile: false },
  career_status: "employed",
  needs_forward: false,
  dimensions: [STRAINING_AUTONOMY, NOTABLE_FEEDBACK, ALIGNED_PACE],
  guidance_notice: GUIDANCE_NOTICE,
  events_since_report: [],
};

/** The needs-forward slice of the autonomy row, written out in full rather
 *  than spread from `STRAINING_AUTONOMY`. Spreading would inherit whatever the
 *  present-tense fixture happens to carry, and the whole claim of these tests
 *  is that the SERVER already removed three specific things -- so the fixture
 *  has to be the shape that actually arrives, not the other one minus edits.
 *  Aligned rows are dropped, `change_in_place` is reduced to its `signal`,
 *  `negotiate` is gone and `decoder_crossref` is null. */
const NEEDS_FORWARD_AUTONOMY: StrainDimensionEntry = {
  dimension: "autonomy",
  env_score: 0.1234,
  bucket: "straining",
  direction: "under",
  rank: 0,
  diagnosis: {
    headline: "The role decides more of the how than you want decided",
    text: "What to seek: a role that hands you the outcome and leaves the route open.",
  },
  registers: {
    change_in_place: { signal: "Who signs off on what, and how a decision got made last month." },
    rarely_moves: {
      why_fixed: "Decision rights are usually set well above the person you would ask.",
      cost_of_staying: "The judgement you are best at does not get exercised.",
      what_it_implies: "A question about fit and not a failure on either side.",
    },
  },
  defers_to_decoder: false,
  decoder_crossref: null,
};

const COMPLETE_NEEDS_FORWARD: SituationComplete = {
  state: "complete",
  manager: { has_profile: true },
  career_status: "between_jobs",
  needs_forward: true,
  dimensions: [NEEDS_FORWARD_AUTONOMY],
  guidance_notice: GUIDANCE_NOTICE,
  events_since_report: [],
};

/** No digit from `env_score` or `rank` may appear anywhere on the page. */
function expectNoScoresLeaked() {
  const text = document.body.textContent ?? "";
  expect(text, "a 0-1 env_score leaked into the report").not.toMatch(/0\.\d/);
  expect(text, "a percentage appeared in a report that has no numbers").not.toMatch(/\d\s?%/);
}

describe("SituationReportPage", () => {
  it("shows a loading state while the report is in flight", () => {
    mocks.fetchWithAuth.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByText(/Loading your Situation Report/)).toBeInTheDocument();
  });

  it("offers a retry when the report cannot be loaded", async () => {
    // A 4xx rather than a 5xx on purpose: `shouldRetry` retries 5xx twice with
    // backoff, so a 500 fixture would still be mid-retry when the assertion
    // runs and would be testing the retry policy, not this branch.
    mocks.fetchWithAuth.mockRejectedValue(new ApiError("boom", { status: 403 }));
    renderPage();
    expect(
      await screen.findByText(/We couldn't load your Situation Report right now/),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  describe("needs_core", () => {
    const NEEDS_CORE: SituationNeedsCore = {
      state: "needs_core",
      manager: { has_profile: false },
      environment: null,
    };

    it("bridges to Work Pulse", async () => {
      serve(NEEDS_CORE);
      renderPage();

      expect(
        await screen.findByRole("heading", { name: "This one needs your side first" }),
      ).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: /Start Work Pulse/ }));
      expect(mocks.navigate).toHaveBeenCalledWith("/work-pulse");
    });

    it("acknowledges an environment report already on file, without buckets", async () => {
      serve({
        ...NEEDS_CORE,
        environment: {
          dimensions: [{ dimension: "autonomy", env_score: 0.9 }],
          career_status: "employed",
          submitted_at: "2026-09-10T00:00:00Z",
        },
      });
      renderPage();

      expect(await screen.findByText(/that half is done/)).toBeInTheDocument();
      // Echoed scores must not become a rendering.
      expect(screen.queryByText(/Straining|Notable|Aligned/)).not.toBeInTheDocument();
      expectNoScoresLeaked();
    });
  });

  describe("needs_environment_report", () => {
    const NEEDS_ENV: SituationNeedsEnvironmentReport = {
      state: "needs_environment_report",
      manager: { has_profile: false },
      can_submit_environment_report: true,
    };

    it("prompts for the environment report", async () => {
      serve(NEEDS_ENV);
      renderPage();

      expect(await screen.findByRole("heading", { name: "One half to go" })).toBeInTheDocument();
      expect(screen.getByText(/fifteen questions about your job/)).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: /Describe your job/ }));
      expect(mocks.navigate).toHaveBeenCalledWith("/environment-report");
    });

    it("renders forward, with no form to offer, when the user cannot submit one", async () => {
      serve({ ...NEEDS_ENV, can_submit_environment_report: false });
      renderPage();

      expect(
        await screen.findByRole("heading", { name: "Your report starts when the job does" }),
      ).toBeInTheDocument();
      // The whole point: no prompt this user could act on.
      expect(screen.queryByRole("button", { name: /Describe your job/ })).not.toBeInTheDocument();
      // And no invented per-dimension guidance, since there are no gaps to have.
      expect(screen.queryByText(/Straining|Notable|Aligned/)).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: /Start FocusType/ })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /Start ManagerMatch/ })).toBeInTheDocument();
    });
  });

  describe("complete", () => {
    it("ranks dimensions in the order the server sent them, with no rank numbers", async () => {
      serve(COMPLETE);
      renderPage();

      expect(await screen.findByRole("heading", { name: "You, and this job" })).toBeInTheDocument();

      const headings = screen
        .getAllByRole("heading", { level: 3 })
        .map((h) => h.textContent);
      expect(headings).toEqual(["Autonomy", "Feedback", "Pace"]);
      expectNoScoresLeaked();
    });

    it("renders magnitude and direction as words", async () => {
      serve(COMPLETE);
      renderPage();

      expect(await screen.findByText("Straining")).toBeInTheDocument();
      expect(screen.getByText("Notable")).toBeInTheDocument();
      expect(screen.getByText("Aligned")).toBeInTheDocument();
      expect(screen.getByText("Less than you need")).toBeInTheDocument();
      expect(screen.getByText("More than you need")).toBeInTheDocument();
    });

    it("renders the at-a-glance strip in document order, words only and no digits", async () => {
      serve(COMPLETE);
      renderPage();

      const heading = await screen.findByText("At a glance");
      const strip = heading.closest("section");
      expect(strip).not.toBeNull();

      const chips = within(strip as HTMLElement).getAllByRole("listitem");
      expect(chips.map((chip) => chip.textContent)).toEqual([
        "Autonomy — Straining",
        "Feedback — Notable",
        "Pace — Aligned",
      ]);
      expect(strip?.textContent ?? "").not.toMatch(/\d/);
    });

    it("renders all three guidance registers on a straining dimension", async () => {
      serve(COMPLETE);
      renderPage();

      expect(await screen.findByText("Change it in place")).toBeInTheDocument();
      expect(screen.getByText("Negotiate it")).toBeInTheDocument();
      expect(screen.getAllByText("This one rarely moves").length).toBeGreaterThan(0);

      expect(screen.getByText("One piece, your method, for a fortnight")).toBeInTheDocument();
      expect(screen.getByText("Name the piece before you start.")).toBeInTheDocument();
      expect(screen.getByText(/I'd like to own the approach on X end to end/)).toBeInTheDocument();
      expect(screen.getByText(/Ask whether the constraint is real/)).toBeInTheDocument();
      expect(screen.getByText(/How you'll know it worked/)).toBeInTheDocument();
    });

    it("renders the aligned note on an aligned dimension, and no registers", async () => {
      serve(COMPLETE);
      renderPage();

      expect(
        await screen.findByText(/You and this job want much the same tempo/),
      ).toBeInTheDocument();
      // One straining dimension carries the registers; the aligned one adds none.
      expect(screen.getAllByText("Change it in place")).toHaveLength(1);
    });

    it("hands the deferred dimension to the Decoder, and cross-refs the softer one", async () => {
      serve(COMPLETE);
      renderPage();

      expect(
        await screen.findByText(/How feedback actually reaches you is enacted by one person/),
      ).toBeInTheDocument();
      expect(
        screen.getByText(/Some of what limits your latitude may be your manager/),
      ).toBeInTheDocument();
    });

    it("routes the manager links to the profile flow when there is no profile yet", async () => {
      serve(COMPLETE);
      renderPage();

      const links = await screen.findAllByRole("link", { name: /Profile your manager/ });
      expect(links.length).toBeGreaterThan(0);
      links.forEach((link) => expect(link).toHaveAttribute("href", "/manager-profile"));
      expect(screen.queryByRole("link", { name: /Open your playbook/ })).not.toBeInTheDocument();
    });

    it("routes the manager links to the playbook when a profile exists", async () => {
      serve({ ...COMPLETE, manager: { has_profile: true } });
      renderPage();

      const links = await screen.findAllByRole("link", { name: /Open your playbook/ });
      expect(links.length).toBeGreaterThan(0);
      links.forEach((link) =>
        expect(link).toHaveAttribute("href", "/manager-profile/playbook"),
      );
    });

    it("renders the guidance notice and the honest footer", async () => {
      serve(COMPLETE);
      renderPage();

      expect(await screen.findByText(GUIDANCE_NOTICE)).toBeInTheDocument();
      expect(
        screen.getByRole("heading", { name: "What this is, and what it isn't" }),
      ).toBeInTheDocument();
      expect(screen.getByRole("link", { name: /How this works, and what we hold back/ })).toHaveAttribute(
        "href",
        "/trust",
      );
    });

    it("says so plainly when nothing is straining", async () => {
      serve({ ...COMPLETE, dimensions: [] });
      renderPage();

      expect(await screen.findByText(/Nothing is straining/)).toBeInTheDocument();
      expect(screen.queryByText("At a glance")).not.toBeInTheDocument();
      expectNoScoresLeaked();
    });
  });

  describe("complete, needs-forward", () => {
    it("carries the one line about the dropped aligned set", async () => {
      serve(COMPLETE_NEEDS_FORWARD);
      renderPage();

      expect(
        await screen.findByRole("heading", { name: "What to look for next" }),
      ).toBeInTheDocument();
      expect(
        screen.getByText(/If you and that role fitted on some dimension, it is not listed below/),
      ).toBeInTheDocument();
    });

    it("renders the server's slice without filling the gaps back in", async () => {
      serve(COMPLETE_NEEDS_FORWARD);
      renderPage();

      await screen.findByRole("heading", { name: "What to look for next" });

      // change_in_place is reduced to its signal, under a forward-facing heading.
      expect(screen.getByText(/What to watch for next time/)).toBeInTheDocument();
      expect(screen.queryByText(/How you'll know it worked/)).not.toBeInTheDocument();
      // negotiate is gone entirely, and so is the Decoder cross-reference.
      expect(screen.queryByText("Negotiate it")).not.toBeInTheDocument();
      expect(
        screen.queryByText(/Some of what limits your latitude may be your manager/),
      ).not.toBeInTheDocument();
      // rarely_moves carries over unchanged.
      expect(screen.getByText("This one rarely moves")).toBeInTheDocument();
      // No aligned card, because the server dropped those rows.
      expect(screen.queryByText("Aligned")).not.toBeInTheDocument();
      expectNoScoresLeaked();
    });

    it("puts the direction in the past tense", async () => {
      serve(COMPLETE_NEEDS_FORWARD);
      renderPage();
      expect(await screen.findByText("Less than you needed")).toBeInTheDocument();
    });

    it("shows fewer chips in the strip rather than backfilling the dropped aligned dimension", async () => {
      serve(COMPLETE_NEEDS_FORWARD);
      renderPage();

      const heading = await screen.findByText("At a glance");
      const strip = heading.closest("section");
      const chips = within(strip as HTMLElement).getAllByRole("listitem");
      expect(chips.map((chip) => chip.textContent)).toEqual(["Autonomy — Straining"]);
    });
  });

  describe("resubmission banner (BUILD_PLAN B-4)", () => {
    it("says nothing when no events landed since the report", async () => {
      serve(COMPLETE);
      renderPage();

      await screen.findByRole("heading", { name: "You, and this job" });
      expect(screen.queryByText(/still describe this job/)).not.toBeInTheDocument();
      expect(screen.queryByRole("link", { name: /Describe it again/ })).not.toBeInTheDocument();
    });

    it("uses new_manager's specific wording and links to the environment form", async () => {
      serve({
        ...COMPLETE,
        events_since_report: [{ type: "new_manager", date: "2026-09-12T00:00:00Z" }],
      });
      renderPage();

      expect(
        await screen.findByText(
          "You logged a new manager since this report — does your Situation Report still describe this job?",
        ),
      ).toBeInTheDocument();
      expect(screen.getByRole("link", { name: /Describe it again/ })).toHaveAttribute(
        "href",
        "/environment-report",
      );
    });

    it.each([
      ["reorg", "Your team went through a reorg since this report"],
      ["remote_change", "Where you work changed since this report"],
      ["role_change", "Your role changed since this report"],
    ] as const)("uses %s's specific wording", async (eventType, lead) => {
      serve({
        ...COMPLETE,
        events_since_report: [{ type: eventType, date: "2026-09-12T00:00:00Z" }],
      });
      renderPage();

      expect(await screen.findByText(new RegExp(lead))).toBeInTheDocument();
    });

    it("falls back to the generic line for 'other', which has no sensible specific wording", async () => {
      serve({
        ...COMPLETE,
        events_since_report: [{ type: "other", date: "2026-09-12T00:00:00Z" }],
      });
      renderPage();

      expect(
        await screen.findByText(/Something about this job has changed since this report/),
      ).toBeInTheDocument();
    });

    it("words the banner off the most recent event when more than one landed", async () => {
      serve({
        ...COMPLETE,
        events_since_report: [
          { type: "role_change", date: "2026-09-13T00:00:00Z" },
          { type: "new_manager", date: "2026-09-10T00:00:00Z" },
        ],
      });
      renderPage();

      expect(
        await screen.findByText(/Your role changed since this report/),
      ).toBeInTheDocument();
      expect(screen.queryByText(/new manager/)).not.toBeInTheDocument();
    });
  });

  describe("experienced trend (BUILD_PLAN B-4)", () => {
    it("invites a user with no check-ins to Pulse, rather than showing an empty chart", async () => {
      serve(COMPLETE, undefined, { checkins: [], events: [] });
      renderPage();

      expect(
        await screen.findByText(/You haven't checked in on Pulse yet/),
      ).toBeInTheDocument();
      expect(screen.getByRole("link", { name: /Check in/ })).toHaveAttribute("href", "/pulse");
      // No trend link when there is nothing to see a trend of.
      expect(screen.queryByRole("link", { name: /See your full trend/ })).not.toBeInTheDocument();
    });

    it("degrades to a single point with the honest one-checkin caption", async () => {
      serve(COMPLETE, undefined, {
        checkins: [
          {
            id: 1,
            taken_at: "2026-09-10T00:00:00Z",
            sequence: 0,
            item_scores: { fragmentation: 3 },
            experienced: 4,
            version: "v1",
          },
        ],
        events: [],
      });
      renderPage();

      expect(
        await screen.findByText(/One check-in so far — the line fills in as you add more/),
      ).toBeInTheDocument();
      expect(screen.getByRole("link", { name: /See your full trend/ })).toHaveAttribute(
        "href",
        "/pulse/trend",
      );
    });

    it("draws the line at two or more check-ins, with no one-point caption", async () => {
      serve(COMPLETE, undefined, {
        checkins: [
          {
            id: 2,
            taken_at: "2026-09-12T00:00:00Z",
            sequence: 1,
            item_scores: { fragmentation: 4 },
            experienced: 3,
            version: "v1",
          },
          {
            id: 1,
            taken_at: "2026-09-05T00:00:00Z",
            sequence: 0,
            item_scores: { fragmentation: 3 },
            experienced: 4,
            version: "v1",
          },
        ],
        events: [],
      });
      renderPage();

      const link = await screen.findByRole("link", { name: /See your full trend/ });
      expect(link).toHaveAttribute("href", "/pulse/trend");
      expect(screen.queryByText(/One check-in so far/)).not.toBeInTheDocument();
    });
  });

  describe("the pin", () => {
    it("says the report moved when the re-pin actually moved it", async () => {
      serve(COMPLETE, () => Promise.resolve({ recalibrated: true }));
      renderPage();

      fireEvent.click(
        await screen.findByRole("button", { name: /Re-read this against my latest Work Pulse/ }),
      );
      expect(await screen.findByText(/Re-pinned\./)).toBeInTheDocument();
    });

    it("says nothing moved when the report was already current", async () => {
      serve(COMPLETE, () => Promise.resolve({ recalibrated: false }));
      renderPage();

      fireEvent.click(
        await screen.findByRole("button", { name: /Re-read this against my latest Work Pulse/ }),
      );
      expect(await screen.findByText(/nothing moved/)).toBeInTheDocument();
    });

    it("explains the 409 rather than showing a raw failure", async () => {
      serve(COMPLETE, () =>
        Promise.reject(
          new ApiError("Take the core assessment first.", {
            status: 409,
            fieldErrors: [{ field: "core", code: "no_core_sitting" }],
          }),
        ),
      );
      renderPage();

      fireEvent.click(
        await screen.findByRole("button", { name: /Re-read this against my latest Work Pulse/ }),
      );
      await waitFor(() =>
        expect(screen.getByText(/There is no Work Pulse sitting to pin to yet/)).toBeInTheDocument(),
      );
    });
  });

  describe("condition experiments (BUILD_PLAN B-5)", () => {
    const TWO_CELL_REPORT: SituationComplete = {
      ...COMPLETE,
      dimensions: [STRAINING_AUTONOMY, STRAINING_PACE],
    };

    /** A stateful mock: POST starts/abandons mutate `experiments` in place, so
     *  the GET the query-client refetches after invalidation reflects the
     *  write -- the same round trip the real API/react-query pair makes. */
    function serveWithExperiments(experiments: Record<string, unknown>[]) {
      let nextId = experiments.length + 1;
      mocks.fetchWithAuth.mockImplementation((path: string, options?: { method?: string; body?: string }) => {
        if (path === "/me/situation-report") return Promise.resolve(TWO_CELL_REPORT);
        if (path === "/me/pulse/history") return Promise.resolve({ checkins: [], events: [] });

        if (path === "/me/experiments" && (!options || options.method === "GET" || !options.method)) {
          return Promise.resolve({ experiments });
        }
        if (path === "/me/experiments" && options?.method === "POST") {
          const { dimension, direction } = JSON.parse(options.body ?? "{}");
          const created = {
            id: nextId++,
            dimension, direction,
            started_at: "2026-09-14T00:00:00Z",
            ends_at: "2026-09-28T00:00:00Z",
            status: "active",
            abandoned_at: null,
            phase: "running",
            experiment_name: "Defend one block, for two weeks",
            readout: { verdict: "not_enough_data", before_count: 0, after_count: 0 },
          };
          experiments.unshift(created);
          return Promise.resolve(created);
        }
        const abandonMatch = path.match(/^\/me\/experiments\/(\d+)\/abandon$/);
        if (abandonMatch) {
          const id = Number(abandonMatch[1]);
          const row = experiments.find((e) => e.id === id);
          if (row) {
            row.status = "abandoned";
            row.phase = "abandoned";
            row.abandoned_at = "2026-09-15T00:00:00Z";
          }
          return Promise.resolve(row);
        }
        return Promise.reject(new Error(`unexpected path ${path}`));
      });
    }

    it("offers a button on a change-in-place cell when nothing is running", async () => {
      serveWithExperiments([]);
      renderPage();

      const buttons = await screen.findAllByRole("button", { name: /Try this for two weeks/ });
      expect(buttons).toHaveLength(2);
      buttons.forEach((button) => expect(button).not.toBeDisabled());
    });

    it("starts an experiment and shows the running state", async () => {
      serveWithExperiments([]);
      renderPage();

      const [firstButton] = await screen.findAllByRole("button", { name: /Try this for two weeks/ });
      fireEvent.click(firstButton);

      expect(await screen.findByText(/Running since/)).toBeInTheDocument();
      expect(await screen.findByRole("button", { name: "Abandon" })).toBeInTheDocument();
    });

    it("disables the other cell's button with a one-line reason once one is running", async () => {
      serveWithExperiments([
        {
          id: 1, dimension: "autonomy", direction: "under",
          started_at: "2026-09-01T00:00:00Z", ends_at: "2026-09-15T00:00:00Z",
          status: "active", abandoned_at: null, phase: "running",
          experiment_name: "One piece, your method, for a fortnight",
          readout: { verdict: "not_enough_data", before_count: 0, after_count: 0 },
        },
      ]);
      renderPage();

      expect(await screen.findByText(/Running since/)).toBeInTheDocument();
      const otherButton = await screen.findByRole("button", { name: /Try this for two weeks/ });
      expect(otherButton).toBeDisabled();
      expect(
        screen.getByText(/Only one experiment can run at a time/),
      ).toBeInTheDocument();
    });

    it("abandons a running experiment with one plain click and no confirmation step", async () => {
      serveWithExperiments([
        {
          id: 1, dimension: "autonomy", direction: "under",
          started_at: "2026-09-01T00:00:00Z", ends_at: "2026-09-15T00:00:00Z",
          status: "active", abandoned_at: null, phase: "running",
          experiment_name: "One piece, your method, for a fortnight",
          readout: { verdict: "not_enough_data", before_count: 0, after_count: 0 },
        },
      ]);
      renderPage();

      const abandon = await screen.findByRole("button", { name: "Abandon" });
      // No modal, no window.confirm -- one click is the whole interaction.
      fireEvent.click(abandon);

      await waitFor(() => expect(screen.queryByText(/Running since/)).not.toBeInTheDocument());
      const buttons = await screen.findAllByRole("button", { name: /Try this for two weeks/ });
      expect(buttons).toHaveLength(2);
    });

    it("shows the ended readout in words, with counts, and no digit in the verdict sentence", async () => {
      serveWithExperiments([
        {
          id: 1, dimension: "autonomy", direction: "under",
          started_at: "2026-08-01T00:00:00Z", ends_at: "2026-08-15T00:00:00Z",
          status: "active", abandoned_at: null, phase: "ended",
          experiment_name: "One piece, your method, for a fortnight",
          readout: { verdict: "moved_up", before_count: 2, after_count: 3 },
        },
      ]);
      renderPage();

      const verdict = await screen.findByText("Your numbers moved up over those two weeks.");
      expect(verdict.textContent ?? "").not.toMatch(/\d/);
      expect(
        screen.getByText("That's based on 2 check-ins before, 3 after."),
      ).toBeInTheDocument();
    });

    it("lists past experiments under the guidance section", async () => {
      serveWithExperiments([
        {
          id: 1, dimension: "autonomy", direction: "under",
          started_at: "2026-08-01T00:00:00Z", ends_at: "2026-08-15T00:00:00Z",
          status: "abandoned", abandoned_at: "2026-08-10T00:00:00Z", phase: "abandoned",
          experiment_name: "One piece, your method, for a fortnight",
          readout: { verdict: "not_enough_data", before_count: 0, after_count: 1 },
        },
      ]);
      renderPage();

      const heading = await screen.findByText("Your experiments");
      const guidance = await screen.findByText(GUIDANCE_NOTICE);
      // Positioned after the guidance notice, per the brief's "under the
      // guidance section".
      expect(heading.compareDocumentPosition(guidance) & Node.DOCUMENT_POSITION_PRECEDING).toBeTruthy();

      const list = heading.closest("section") as HTMLElement;
      expect(within(list).getByText(/One piece, your method, for a fortnight/)).toBeInTheDocument();
      expect(within(list).getByText("Abandoned")).toBeInTheDocument();
    });

    it("does not offer the experiment button in the needs-forward rendering", async () => {
      serve(COMPLETE_NEEDS_FORWARD, undefined, { checkins: [], events: [] }, { experiments: [] });
      renderPage();

      await screen.findByRole("heading", { name: "What to look for next" });
      expect(
        screen.queryByRole("button", { name: /Try this for two weeks/ }),
      ).not.toBeInTheDocument();
      expect(screen.queryByText("Your experiments")).not.toBeInTheDocument();
    });
  });
});
