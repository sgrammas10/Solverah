/**
 * PathFitPanel.test.tsx — the Tier-2 panel (BUILD_PLAN F-6).
 *
 * Selected by role and behaviour rather than by copy: Julie owns every string
 * here and revises them on the built product, so a test that matched them would
 * turn a wording edit into a red suite. The one place copy is asserted is the
 * *shape* of a failure — whether a "Try again" exists — and that is a decision
 * rather than a phrase: offering retry for a permanent 404 is how a user ends up
 * pressing a button forever.
 */
import { render, screen, fireEvent } from "@testing-library/react";

import PathFitPanel from "./PathFitPanel";
import { PATH_FIT_EXPECTED_MS, type PathFit } from "../usePathFeedback";

const FIT = {
  onet_code: "11-2021.00",
  title: "Marketing Managers",
  fit_score: 0.71,
  retrieval_cosine: 0.83,
  centroid_score: 0.6,
  coverage_score: 0.8,
  skills_score: 0.7,
  work_style_score: 0.45,
  zone: {
    user_zone: 4,
    user_zone_resolved: true,
    occupation_zone: 4,
    delta: 0,
    score: 0.6,
  },
  matched_skills: ["Python", "SQL"],
  gap_skills: [
    { name: "Market research", importance: 82.4 },
    { name: "Budgeting", importance: 61 },
  ],
  tasks: ["Plan campaigns.", "Set the budget."],
  tech_stack: ["Salesforce", "Google Analytics"],
  weights: { role: 0.35, coverage: 0.455, zone: 0.195, style: 0 },
  onet_calls: 4,
  narrative: null,
  computed_at: "2026-09-16T12:00:00Z",
  cached: false,
} as unknown as PathFit;

function renderPanel(overrides: Partial<React.ComponentProps<typeof PathFitPanel>> = {}) {
  const props = {
    title: "Marketing Managers",
    fit: null,
    pending: false,
    errorCode: null,
    onClose: vi.fn(),
    onRetry: vi.fn(),
    ...overrides,
  };
  render(<PathFitPanel {...props} />);
  return props;
}

describe("PathFitPanel - loading", () => {
  it("shows a busy region while the fit is being computed", () => {
    renderPanel({ pending: true });
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("is sized to the measured common-case latency, not the warm one", () => {
    // 844 ms is another user opening the same card, which is what most clicks
    // are; 12 ms is this user re-opening it. Sizing to 12 would flash a spinner
    // on nearly every real click.
    renderPanel({ pending: true });
    expect(screen.getByRole("status").dataset.expectedMs).toBe(String(PATH_FIT_EXPECTED_MS));
    expect(PATH_FIT_EXPECTED_MS).toBeGreaterThan(500);
    expect(PATH_FIT_EXPECTED_MS).toBeLessThan(2000);
  });

  it("shows no content and no error while pending", () => {
    renderPanel({ pending: true, fit: FIT });
    expect(screen.queryByText("Python")).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("PathFitPanel - the analysis", () => {
  it("names the skills the user already has", () => {
    renderPanel({ fit: FIT });
    expect(screen.getByText("Python")).toBeInTheDocument();
    expect(screen.getByText("SQL")).toBeInTheDocument();
  });

  it("names each gap with its importance", () => {
    renderPanel({ fit: FIT });
    expect(screen.getByText("Market research")).toBeInTheDocument();
    expect(screen.getByText("82")).toBeInTheDocument();
  });

  it("renders the tasks and the tech stack", () => {
    renderPanel({ fit: FIT });
    expect(screen.getByText("Plan campaigns.")).toBeInTheDocument();
    expect(screen.getByText("Salesforce")).toBeInTheDocument();
  });

  it("renders the fit score as a rounded percentage", () => {
    renderPanel({ fit: FIT });
    expect(screen.getByText("71%")).toBeInTheDocument();
  });

  it("renders a zone with no occupation value without crashing", () => {
    // 93 of the 1,016 corpus rows carry no Job Zone, and a missing zone is
    // NEUTRAL rather than a penalty -- the panel has to say so rather than
    // render "NaN".
    renderPanel({
      fit: {
        ...FIT,
        zone: { ...FIT.zone, occupation_zone: null, delta: null },
      } as unknown as PathFit,
    });
    expect(screen.queryByText(/NaN/)).toBeNull();
  });

  it("renders whatever gap the API sends, without second-guessing it", () => {
    // This case exists because the backend once sent exactly this: a user with
    // "SQL" told that "Structured query language SQL" was a gap. F-8 box 5 fixed
    // that at the source, so the payload below no longer occurs -- but the rule
    // it proves outlives the bug. The panel does not filter, so the next
    // backend defect is visible to the people who could report it rather than
    // swallowed here.
    renderPanel({
      fit: {
        ...FIT,
        matched_skills: ["SQL"],
        gap_skills: [{ name: "Structured query language SQL", importance: 70 }],
      } as unknown as PathFit,
    });
    expect(screen.getByText("Structured query language SQL")).toBeInTheDocument();
  });
});

describe("PathFitPanel - failures", () => {
  it("offers a retry for a transient failure", () => {
    const props = renderPanel({ errorCode: "corpus_unavailable" });
    expect(screen.getByRole("alert")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(props.onRetry).toHaveBeenCalled();
  });

  it.each(["unsupported_occupation", "unknown_occupation", "invalid_onet_code"])(
    "offers no retry for %s, which retrying cannot fix",
    (code) => {
      renderPanel({ errorCode: code });
      expect(screen.getByRole("alert")).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /try again/i })).toBeNull();
    }
  );

  it("falls back to a retryable message for a code it has never seen", () => {
    renderPanel({ errorCode: "something_new" });
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });

  it("shows the failure instead of stale content", () => {
    renderPanel({ errorCode: "corpus_unavailable", fit: FIT });
    expect(screen.queryByText("Python")).toBeNull();
  });
});

describe("PathFitPanel - dismissal", () => {
  it("closes from the close control", () => {
    const props = renderPanel({ fit: FIT });
    fireEvent.click(screen.getByRole("button", { name: /close/i }));
    expect(props.onClose).toHaveBeenCalled();
  });

  it("closes on Escape", () => {
    const props = renderPanel({ fit: FIT });
    fireEvent.keyDown(window, { key: "Escape" });
    expect(props.onClose).toHaveBeenCalled();
  });

  it("is announced as a dialog", () => {
    renderPanel({ fit: FIT });
    expect(screen.getByRole("dialog")).toHaveAttribute("aria-modal", "true");
  });
});
