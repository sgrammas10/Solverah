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

/** Open every strained card's guidance, the way a reader would: one click
 *  per card toggle. The panels stay in the DOM while closed (print shows them),
 *  so role queries -- which skip `hidden` content -- are the ones that need this. */
function expandAll() {
  screen
    .getAllByRole("button", { name: /^Show guidance for/ })
    .forEach((toggle) => fireEvent.click(toggle));
}

/** The card for one dimension, found by its heading. */
function cardFor(name: string): HTMLElement {
  return screen.getByRole("heading", { level: 3, name }).closest("article") as HTMLElement;
}

/** The dimension names in the order the list renders them. */
function renderedOrder(): string[] {
  const list = screen.getByRole("region", { name: "Dimension by dimension" });
  return within(list)
    .getAllByRole("listitem")
    .map((item) => within(item).getByRole("heading", { level: 3 }).textContent ?? "");
}

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
      expect(renderedOrder()).toEqual(["Autonomy", "Feedback", "Pace"]);
      expectNoScoresLeaked();
    });

    it("never re-sorts: an order the client would not have chosen renders exactly as sent", async () => {
      // Aligned first, notable before straining -- not the server's tiering,
      // which is the point: a client that groups or sorts by bucket fails here.
      serve({ ...COMPLETE, dimensions: [ALIGNED_PACE, NOTABLE_FEEDBACK, STRAINING_AUTONOMY] });
      renderPage();

      await screen.findByRole("heading", { name: "You, and this job" });
      expect(renderedOrder()).toEqual(["Pace", "Feedback", "Autonomy"]);
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

    it("leads with one line naming the most strained dimension, from the payload, no digits", async () => {
      serve(COMPLETE);
      renderPage();

      const lead = await screen.findByText(/where you and this job sit furthest apart/);
      expect(lead.textContent).toBe(
        "Autonomy is where you and this job sit furthest apart. The rest follow in order, most strain first.",
      );
      expect(lead.textContent ?? "").not.toMatch(/\d/);
      // The old "In short" box restated the list below it; it is gone.
      expect(screen.queryByRole("region", { name: "In short" })).not.toBeInTheDocument();
    });

    it("leads with the first strained row even when the server put an aligned row first", async () => {
      serve({ ...COMPLETE, dimensions: [ALIGNED_PACE, NOTABLE_FEEDBACK, STRAINING_AUTONOMY] });
      renderPage();

      expect(
        await screen.findByText(/^Feedback is where you and this job sit furthest apart/),
      ).toBeInTheDocument();
    });

    it("says nothing is straining in the lead when every row is aligned", async () => {
      serve({ ...COMPLETE, dimensions: [ALIGNED_PACE] });
      renderPage();

      expect(
        await screen.findByText(/^Nothing is straining: on every dimension we measure/),
      ).toBeInTheDocument();
    });

    it("shows each strained dimension compactly: name, bucket, direction, headline", async () => {
      serve(COMPLETE);
      renderPage();

      await screen.findByRole("heading", { level: 3, name: "Autonomy" });
      const card = cardFor("Autonomy");
      expect(within(card).getByText("Straining")).toBeVisible();
      expect(within(card).getByText("Less than you need")).toBeVisible();
      expect(
        within(card).getByText("The role decides more of the how than you want decided"),
      ).toBeVisible();
      // The guidance itself is behind the disclosure until asked for.
      expect(within(card).getByRole("tab", { name: "Try a change", hidden: true })).not.toBeVisible();
      expect(
        within(card).getByText("This role settles more of that before it reaches you."),
      ).not.toBeVisible();
    });

    it("expands and collapses a card's guidance with an accessible disclosure", async () => {
      serve(COMPLETE);
      renderPage();

      const toggle = await screen.findByRole("button", { name: "Show guidance for Autonomy" });
      expect(toggle).toHaveAttribute("aria-expanded", "false");
      const panel = document.getElementById(toggle.getAttribute("aria-controls") ?? "");
      expect(panel).not.toBeNull();
      expect(panel).not.toBeVisible();

      fireEvent.click(toggle);
      expect(toggle).toHaveAttribute("aria-expanded", "true");
      expect(toggle).toHaveAccessibleName("Hide guidance for Autonomy");
      expect(panel).toBeVisible();
      expect(within(panel as HTMLElement).getByRole("tab", { name: "Negotiate it" })).toBeVisible();
      // Only the card that was asked for opens.
      expect(screen.getByRole("button", { name: "Show guidance for Feedback" })).toHaveAttribute(
        "aria-expanded",
        "false",
      );

      fireEvent.click(toggle);
      expect(toggle).toHaveAttribute("aria-expanded", "false");
      expect(panel).not.toBeVisible();
    });

    it("opens and closes every card at once", async () => {
      serve(COMPLETE);
      renderPage();

      fireEvent.click(await screen.findByRole("button", { name: "Open all" }));
      expect(screen.getByRole("button", { name: "Hide guidance for Autonomy" })).toHaveAttribute(
        "aria-expanded",
        "true",
      );
      expect(screen.getByRole("button", { name: "Hide guidance for Feedback" })).toHaveAttribute(
        "aria-expanded",
        "true",
      );

      fireEvent.click(screen.getByRole("button", { name: "Close all" }));
      expect(screen.getAllByRole("button", { name: /^Show guidance for/ })).toHaveLength(2);
    });

    it("prints every card expanded and every register, with the toggles and tabs hidden", async () => {
      serve(COMPLETE);
      renderPage();

      const toggles = await screen.findAllByRole("button", { name: /^Show guidance for/ });
      expect(toggles).toHaveLength(2);
      toggles.forEach((toggle) => {
        // Collapsed on screen, but `print:block` overrides `hidden` on paper.
        const panel = document.getElementById(toggle.getAttribute("aria-controls") ?? "");
        expect(panel).toHaveAttribute("hidden");
        expect(panel).toHaveClass("print:block");
        expect(toggle).toHaveClass("print:hidden");
      });
      // The unselected registers are hidden on screen and printed on paper,
      // each under its own print-only heading, with the tab strip left off.
      const tabpanels = cardFor("Autonomy").querySelectorAll("[role=tabpanel]");
      expect(tabpanels).toHaveLength(3);
      tabpanels.forEach((tabpanel) => expect(tabpanel).toHaveClass("print:block"));
      expect(cardFor("Autonomy").querySelector("[role=tablist]")).toHaveClass("print:hidden");
      expect(screen.getByRole("button", { name: "Open all" })).toHaveClass("print:hidden");
      expect(screen.getByRole("button", { name: "Print this report" }).parentElement).toHaveClass(
        "print:hidden",
      );
    });

    it("shows one register at a time, as tabs, starting with the first the server sent", async () => {
      serve(COMPLETE);
      renderPage();

      await screen.findByRole("heading", { name: "You, and this job" });
      expandAll();
      const card = cardFor("Autonomy");

      expect(within(card).getByText("This role settles more of that before it reaches you.")).toBeVisible();
      const tabs = within(card).getAllByRole("tab");
      expect(tabs.map((tab) => tab.textContent)).toEqual([
        "Try a change",
        "Negotiate it",
        "If it won't move",
      ]);
      expect(tabs[0]).toHaveAttribute("aria-selected", "true");

      // Change it in place: visible; the others are not.
      expect(within(card).getByText("One piece, your method, for a fortnight")).toBeVisible();
      expect(
        within(card).getByText("Pick one live piece of work and run the approach yourself."),
      ).toBeVisible();
      expect(within(card).getByText("Name the piece before you start.")).toBeVisible();
      expect(within(card).getByText("Put one checkpoint in the middle.")).toBeVisible();
      expect(within(card).getByText("How many decisions you made without waiting.")).toBeVisible();
      expect(within(card).getByText(/How you'll know it worked/)).toBeVisible();
      expect(within(card).getByText("Whoever sets the approach on your work.")).not.toBeVisible();

      fireEvent.click(within(card).getByRole("tab", { name: "Negotiate it" }));
      expect(within(card).getByRole("tab", { name: "Negotiate it" })).toHaveAttribute("aria-selected", "true");
      expect(within(card).getByText("Whoever sets the approach on your work.")).toBeVisible();
      expect(within(card).getByText("Open on the work rather than on how it feels.")).toBeVisible();
      expect(within(card).getByText(/I'd like to own the approach on X end to end/)).toBeVisible();
      expect(within(card).getByText(/Ask whether the constraint is real/)).toBeVisible();
      expect(within(card).getByText("One piece, your method, for a fortnight")).not.toBeVisible();

      fireEvent.click(within(card).getByRole("tab", { name: "If it won't move" }));
      expect(within(card).getByText(/Decision rights are usually set well above/)).toBeVisible();
      expect(within(card).getByText(/The judgement you are best at does not get exercised/)).toBeVisible();
      expect(within(card).getByText(/A question about fit and not a failure/)).toBeVisible();
    });

    it("moves between register tabs with the arrow keys, Home and End", async () => {
      serve(COMPLETE);
      renderPage();

      await screen.findByRole("heading", { name: "You, and this job" });
      expandAll();
      const card = cardFor("Autonomy");
      const [first, second, third] = within(card).getAllByRole("tab");
      expect(first).toHaveAttribute("tabindex", "0");
      expect(second).toHaveAttribute("tabindex", "-1");

      fireEvent.keyDown(first, { key: "ArrowRight" });
      expect(second).toHaveAttribute("aria-selected", "true");
      expect(second).toHaveFocus();
      fireEvent.keyDown(second, { key: "End" });
      expect(third).toHaveAttribute("aria-selected", "true");
      fireEvent.keyDown(third, { key: "ArrowRight" });
      expect(first).toHaveAttribute("aria-selected", "true");
      fireEvent.keyDown(first, { key: "ArrowLeft" });
      expect(third).toHaveAttribute("aria-selected", "true");
      fireEvent.keyDown(third, { key: "Home" });
      expect(first).toHaveAttribute("aria-selected", "true");
    });

    it("renders a lone register under a plain heading, with no one-tab strip", async () => {
      serve(COMPLETE);
      renderPage();

      await screen.findByRole("heading", { name: "You, and this job" });
      expandAll();
      const card = cardFor("Feedback");
      expect(within(card).queryByRole("tablist")).not.toBeInTheDocument();
      expect(within(card).getByRole("heading", { level: 4, name: "If it won't move" })).toBeVisible();
      expect(within(card).getByText(/A running commentary you brace for/)).toBeVisible();
    });

    it("renders the aligned note on an aligned dimension, and no registers", async () => {
      serve(COMPLETE);
      renderPage();

      expect(
        await screen.findByText(/You and this job want much the same tempo/),
      ).toBeVisible();
      // A one-sentence note is the whole of it: nothing to open.
      expect(screen.queryByRole("button", { name: /for Pace$/ })).not.toBeInTheDocument();
      expandAll();
      // One straining dimension carries the change register; the aligned one adds none.
      expect(screen.getAllByRole("tab", { name: "Try a change" })).toHaveLength(1);
    });

    it("leads an aligned row with its note's first sentence and keeps the rest behind 'Read more'", async () => {
      serve({
        ...COMPLETE,
        dimensions: [
          {
            ...ALIGNED_PACE,
            aligned_note: "You and this job want much the same tempo. That is worth protecting.",
          },
        ],
      });
      renderPage();

      const card = await screen.findByRole("heading", { level: 3, name: "Pace" });
      const article = card.closest("article") as HTMLElement;
      expect(within(article).getByText("You and this job want much the same tempo.")).toBeVisible();
      expect(within(article).getByText("That is worth protecting.")).not.toBeVisible();

      fireEvent.click(within(article).getByRole("button", { name: "Read more for Pace" }));
      expect(within(article).getByText("That is worth protecting.")).toBeVisible();
    });

    it("hands the deferred dimension to the Decoder, and cross-refs the softer one", async () => {
      serve(COMPLETE);
      renderPage();

      await screen.findByRole("heading", { name: "You, and this job" });
      expandAll();
      expect(within(cardFor("Feedback")).getByText(/How feedback reaches you is set by one person/)).toBeVisible();
      expect(
        within(cardFor("Autonomy")).getByText(/Some of what limits your latitude may be your manager/),
      ).toBeVisible();
    });

    it("routes the manager links to the profile flow when there is no profile yet", async () => {
      serve(COMPLETE);
      renderPage();

      await screen.findByRole("heading", { name: "You, and this job" });
      expandAll();
      const links = screen.getAllByRole("link", { name: /Profile your manager/ });
      // The manager section plus both Decoder hand-offs inside the cards.
      expect(links).toHaveLength(3);
      links.forEach((link) => expect(link).toHaveAttribute("href", "/manager-profile"));
      expect(screen.queryByRole("link", { name: /Open your playbook/ })).not.toBeInTheDocument();
    });

    it("routes the manager links to the playbook when a profile exists", async () => {
      serve({ ...COMPLETE, manager: { has_profile: true } });
      renderPage();

      await screen.findByRole("heading", { name: "You, and this job" });
      expandAll();
      const links = screen.getAllByRole("link", { name: /Open your playbook/ });
      expect(links).toHaveLength(3);
      links.forEach((link) =>
        expect(link).toHaveAttribute("href", "/manager-profile/playbook"),
      );
    });

    it("says each thing about the report once: the notice, not-advice, the pin, and the trust link", async () => {
      serve(COMPLETE);
      renderPage();

      await screen.findByRole("heading", { name: "About this report" });
      expect(screen.getAllByText(GUIDANCE_NOTICE)).toHaveLength(1);
      expect(screen.getAllByText(/advice to leave or to stay/)).toHaveLength(1);
      expect(screen.getAllByText(/retaking Work Pulse/)).toHaveLength(1);
      // The old four-paragraph footer restated the notice; it is gone.
      expect(
        screen.queryByRole("heading", { name: "What this is, and what it isn't" }),
      ).not.toBeInTheDocument();
      expect(screen.getByRole("link", { name: /How this works, and what we hold back/ })).toHaveAttribute(
        "href",
        "/trust",
      );
    });

    it("says so plainly when nothing is straining", async () => {
      serve({ ...COMPLETE, dimensions: [] });
      renderPage();

      expect(await screen.findByText(/Nothing is straining/)).toBeInTheDocument();
      expect(screen.queryByRole("region", { name: "Dimension by dimension" })).not.toBeInTheDocument();
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
      expandAll();

      // change_in_place is reduced to its signal, under a forward-facing heading.
      expect(screen.getByRole("tab", { name: "What to look for" })).toBeVisible();
      expect(screen.getByText(/What to watch for next time/)).toBeVisible();
      expect(screen.queryByText(/How you'll know it worked/)).not.toBeInTheDocument();
      // negotiate is gone entirely, and so is the Decoder cross-reference.
      expect(screen.queryByRole("tab", { name: "Negotiate it" })).not.toBeInTheDocument();
      expect(
        screen.queryByText(/Some of what limits your latitude may be your manager/),
      ).not.toBeInTheDocument();
      // rarely_moves carries over unchanged.
      fireEvent.click(screen.getByRole("tab", { name: "Why it rarely moves" }));
      expect(screen.getByText(/Decision rights are usually set well above/)).toBeVisible();
      // No aligned card, because the server dropped those rows.
      expect(screen.queryByText("Aligned")).not.toBeInTheDocument();
      expectNoScoresLeaked();
    });

    it("puts the direction in the past tense", async () => {
      serve(COMPLETE_NEEDS_FORWARD);
      renderPage();
      expect(await screen.findByText("Less than you needed")).toBeInTheDocument();
    });

    it("leads in the past tense without backfilling the dropped aligned dimension", async () => {
      serve(COMPLETE_NEEDS_FORWARD);
      renderPage();

      expect(
        await screen.findByText(/^Autonomy was where you and that role sat furthest apart/),
      ).toBeInTheDocument();
      expect(renderedOrder()).toEqual(["Autonomy"]);
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

      fireEvent.click(await screen.findByRole("button", { name: "Open all" }));
      const buttons = await screen.findAllByRole("button", { name: /Try this for two weeks/ });
      expect(buttons).toHaveLength(2);
      buttons.forEach((button) => expect(button).not.toBeDisabled());
    });

    it("starts an experiment and shows the running state", async () => {
      serveWithExperiments([]);
      renderPage();

      fireEvent.click(await screen.findByRole("button", { name: "Open all" }));
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

      fireEvent.click(await screen.findByRole("button", { name: "Open all" }));
      expect(await screen.findByText(/Running since/)).toBeVisible();
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

      fireEvent.click(await screen.findByRole("button", { name: "Open all" }));
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
      // Under the guidance: after the dimension list, before the footer.
      const list = screen.getByRole("region", { name: "Dimension by dimension" });
      const footer = screen.getByRole("heading", { name: "About this report" });
      expect(heading.compareDocumentPosition(list) & Node.DOCUMENT_POSITION_PRECEDING).toBeTruthy();
      expect(heading.compareDocumentPosition(footer) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

      const record = heading.closest("section") as HTMLElement;
      expect(within(record).getByText(/One piece, your method, for a fortnight/)).toBeInTheDocument();
      expect(within(record).getByText("Abandoned")).toBeInTheDocument();
    });

    it("does not offer the experiment button in the needs-forward rendering", async () => {
      serve(COMPLETE_NEEDS_FORWARD, undefined, { checkins: [], events: [] }, { experiments: [] });
      renderPage();

      await screen.findByRole("heading", { name: "What to look for next" });
      expandAll();
      expect(
        screen.queryByRole("button", { name: /Try this for two weeks/ }),
      ).not.toBeInTheDocument();
      expect(screen.queryByText("Your experiments")).not.toBeInTheDocument();
    });

    // G5: a failed or pending `/me/experiments` must not read as "nothing
    // running," which is what an empty array renders as -- see
    // SituationReportPage.tsx's `ExperimentsStatus`.
    it("offers no start button and shows a retry notice when experiments fail to load", async () => {
      const TWO_CELL_REPORT: SituationComplete = {
        ...COMPLETE,
        dimensions: [STRAINING_AUTONOMY, STRAINING_PACE],
      };
      let attempt = 0;
      mocks.fetchWithAuth.mockImplementation((path: string) => {
        if (path === "/me/situation-report") return Promise.resolve(TWO_CELL_REPORT);
        if (path === "/me/pulse/history") return Promise.resolve({ checkins: [], events: [] });
        if (path === "/me/experiments") {
          attempt += 1;
          return attempt === 1
            ? Promise.reject(new ApiError("boom", { status: 403 }))
            : Promise.resolve({ experiments: [] });
        }
        return Promise.reject(new Error(`unexpected path ${path}`));
      });
      renderPage();

      await screen.findByRole("heading", { name: "You, and this job" });
      expandAll();
      // Without the fix, `experiments ?? []` reads a failed fetch as "nothing
      // running" and both cells offer their button anyway.
      expect(
        screen.queryByRole("button", { name: /Try this for two weeks/ }),
      ).not.toBeInTheDocument();
      const notice = await screen.findByText("We couldn't load your experiments right now.");
      fireEvent.click(within(notice.closest("section") as HTMLElement).getByRole("button", { name: "Try again" }));

      const buttons = await screen.findAllByRole("button", { name: /Try this for two weeks/ });
      expect(buttons).toHaveLength(2);
    });

    it("offers no start button while experiments are still loading", async () => {
      const TWO_CELL_REPORT: SituationComplete = {
        ...COMPLETE,
        dimensions: [STRAINING_AUTONOMY, STRAINING_PACE],
      };
      mocks.fetchWithAuth.mockImplementation((path: string) => {
        if (path === "/me/situation-report") return Promise.resolve(TWO_CELL_REPORT);
        if (path === "/me/pulse/history") return Promise.resolve({ checkins: [], events: [] });
        if (path === "/me/experiments") return new Promise(() => {});
        return Promise.reject(new Error(`unexpected path ${path}`));
      });
      renderPage();

      await screen.findByRole("heading", { name: "You, and this job" });
      expandAll();
      expect(
        screen.queryByRole("button", { name: /Try this for two weeks/ }),
      ).not.toBeInTheDocument();
    });
  });
});
