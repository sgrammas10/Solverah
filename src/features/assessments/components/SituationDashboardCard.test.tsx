/**
 * SituationDashboardCard (BUILD_PLAN D-6), over the real `useSituationReport`
 * hook and a real query client -- only `fetchWithAuth` is mocked, per
 * SituationReportPage.test.tsx's precedent.
 *
 * THE D-15 ASSERTION IS THE POINT OF THE `complete` CASES. The payload carries
 * `env_score` per dimension and a `rank`, and the dashboard is exactly where a
 * reader would look for a number to watch week to week. The fixtures use env
 * scores whose decimals would be conspicuous if they leaked, and the `complete`
 * renderings assert that the card contains NO digit at all -- stricter than the
 * report page's own guard, which it can afford because this card has no dates,
 * no counts and no prose with a number in it.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";

import SituationDashboardCard, { nextActionFor } from "./SituationDashboardCard";
import { createQueryClient } from "../../../shared/api/queryClient";
import { ApiError } from "../../../shared/api/apiError";
import type {
  SituationComplete,
  SituationNeedsCore,
  SituationNeedsEnvironmentReport,
  StrainDimensionEntry,
} from "../useSituationReport";

const mocks = vi.hoisted(() => ({ fetchWithAuth: vi.fn() }));

vi.mock("../../auth/useAuth", () => ({
  useAuth: () => ({ fetchWithAuth: mocks.fetchWithAuth }),
}));

beforeEach(() => vi.clearAllMocks());

function renderCard(props: { workPulseOfferedElsewhere?: boolean } = {}) {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <SituationDashboardCard {...props} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const NEEDS_CORE: SituationNeedsCore = {
  state: "needs_core",
  manager: { has_profile: false },
  environment: null,
};

const NEEDS_ENV: SituationNeedsEnvironmentReport = {
  state: "needs_environment_report",
  manager: { has_profile: false },
  can_submit_environment_report: true,
};

const FIRST_JOB: SituationNeedsEnvironmentReport = {
  ...NEEDS_ENV,
  can_submit_environment_report: false,
};

function strain(
  dimension: StrainDimensionEntry["dimension"],
  bucket: "notable" | "straining",
  rank: number,
  env_score: number,
): StrainDimensionEntry {
  return {
    dimension,
    env_score,
    bucket,
    direction: "under",
    rank,
    diagnosis: { headline: "Headline", text: "Text" },
    registers: {},
    defers_to_decoder: false,
    decoder_crossref: null,
  };
}

const COMPLETE: SituationComplete = {
  state: "complete",
  manager: { has_profile: false },
  career_status: "employed",
  needs_forward: false,
  guidance_notice: "Notice",
  events_since_report: [],
  dimensions: [
    strain("autonomy", "straining", 1, 0.17),
    strain("feedback", "notable", 2, 0.42),
    {
      dimension: "pace",
      env_score: 0.63,
      bucket: "aligned",
      direction: null,
      rank: 3,
      aligned_note: "Pace note",
    },
  ],
};

/** No digit may appear anywhere in the card in the `complete` state. */
function expectNoDigitsInCard() {
  const text = screen.getByTestId("situation-card").textContent ?? "";
  expect(text, "a number reached the conditions summary").not.toMatch(/\d/);
}

describe("SituationDashboardCard - states", () => {
  it("needs_core: names the first half and suggests Work Pulse", async () => {
    mocks.fetchWithAuth.mockResolvedValue(NEEDS_CORE);
    renderCard();
    expect(
      await screen.findByText("Your conditions, once we have your side"),
    ).toBeInTheDocument();
    expect(screen.getByText("Work Pulse is the first of those two, and it isn't", { exact: false }))
      .toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Start Work Pulse/ })).toHaveAttribute(
      "href",
      "/work-pulse",
    );
    // Nothing to see yet, so no link into the report itself.
    expect(screen.queryByRole("link", { name: /See your Situation Report/ })).toBeNull();
  });

  it("needs_core: stays quiet about Work Pulse when the banner already offers it", async () => {
    mocks.fetchWithAuth.mockResolvedValue(NEEDS_CORE);
    renderCard({ workPulseOfferedElsewhere: true });
    await screen.findByText("Your conditions, once we have your side");
    expect(screen.queryByRole("link", { name: /Start Work Pulse/ })).toBeNull();
    expect(screen.queryByText("Next")).toBeNull();
  });

  it("needs_environment_report: suggests describing the job", async () => {
    mocks.fetchWithAuth.mockResolvedValue(NEEDS_ENV);
    renderCard();
    expect(await screen.findByText("One half to go")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Describe your job/ })).toHaveAttribute(
      "href",
      "/environment-report",
    );
  });

  it("first_job: links to the report and suggests FocusType instead of a form it cannot offer", async () => {
    mocks.fetchWithAuth.mockResolvedValue(FIRST_JOB);
    renderCard();
    expect(await screen.findByText("Your report starts when the job does")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /See your Situation Report/ })).toHaveAttribute(
      "href",
      "/situation-report",
    );
    expect(screen.getByRole("link", { name: /Start FocusType/ })).toHaveAttribute(
      "href",
      "/focus-type",
    );
    // The form this user can never submit must not be offered anywhere.
    expect(screen.queryByRole("link", { name: /Describe your job/ })).toBeNull();
  });

  it("complete: renders bucket chips as words, the report link, and the Decoder action", async () => {
    mocks.fetchWithAuth.mockResolvedValue(COMPLETE);
    renderCard();
    expect(await screen.findByText("How your conditions sit")).toBeInTheDocument();
    expect(screen.getByText("Autonomy — Straining")).toBeInTheDocument();
    expect(screen.getByText("Feedback — Notable")).toBeInTheDocument();
    expect(screen.getByText("Pace — Aligned")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /See your Situation Report/ })).toHaveAttribute(
      "href",
      "/situation-report",
    );
    expect(screen.getByRole("link", { name: /Profile your manager/ })).toHaveAttribute(
      "href",
      "/manager-profile",
    );
    expectNoDigitsInCard();
  });

  it("complete: sends a user who already has a manager profile to the playbook", async () => {
    mocks.fetchWithAuth.mockResolvedValue({
      ...COMPLETE,
      manager: { has_profile: true },
    });
    renderCard();
    expect(await screen.findByText("How your conditions sit")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open your manager playbook/ })).toHaveAttribute(
      "href",
      "/manager-profile/playbook",
    );
    expect(screen.queryByRole("link", { name: /Profile your manager/ })).toBeNull();
    expectNoDigitsInCard();
  });

  it("complete: renders the past-tense heading when the report needs forward", async () => {
    mocks.fetchWithAuth.mockResolvedValue({ ...COMPLETE, needs_forward: true });
    renderCard();
    expect(await screen.findByText("What to look for next")).toBeInTheDocument();
    expectNoDigitsInCard();
  });

  it("complete with nothing straining: says so in words rather than showing an empty strip", async () => {
    mocks.fetchWithAuth.mockResolvedValue({ ...COMPLETE, dimensions: [] });
    renderCard();
    expect(await screen.findByText(/Nothing is straining/)).toBeInTheDocument();
    expect(screen.queryByRole("list")).toBeNull();
    expectNoDigitsInCard();
  });
});

describe("SituationDashboardCard - silence", () => {
  it("renders nothing while the report is in flight", () => {
    mocks.fetchWithAuth.mockReturnValue(new Promise(() => {}));
    renderCard();
    expect(screen.queryByTestId("situation-card")).toBeNull();
  });

  it("renders nothing rather than an error box when the report cannot be loaded", async () => {
    // A 4xx rather than a 5xx: `shouldRetry` retries 5xx with backoff, so a 500
    // fixture would still be mid-retry when the assertion runs.
    mocks.fetchWithAuth.mockRejectedValue(new ApiError("boom", { status: 403 }));
    renderCard();
    await waitFor(() => expect(mocks.fetchWithAuth).toHaveBeenCalled());
    expect(screen.queryByTestId("situation-card")).toBeNull();
  });
});

describe("nextActionFor", () => {
  // The derivation returns ONE action or none. This asserts the shape as well
  // as the values: a regression that turned it into a list would fail here
  // before it reached the screen.
  it("returns a single action or null for every state", () => {
    const cases = [
      nextActionFor(NEEDS_CORE, false),
      nextActionFor(NEEDS_CORE, true),
      nextActionFor(NEEDS_ENV, false),
      nextActionFor(FIRST_JOB, false),
      nextActionFor(COMPLETE, false),
      nextActionFor({ ...COMPLETE, manager: { has_profile: true } }, false),
    ];
    for (const action of cases) {
      expect(action === null || typeof action.to === "string").toBe(true);
      expect(Array.isArray(action)).toBe(false);
    }
    expect(cases.map((a) => a?.to ?? null)).toEqual([
      "/work-pulse",
      null,
      "/environment-report",
      "/focus-type",
      "/manager-profile",
      "/manager-profile/playbook",
    ]);
  });
});
