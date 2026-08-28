import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { HttpResponse } from "msw";

import TeaserResult from "../TeaserResult";
import { mock } from "../../../../tests/msw/contract";
import { server, useApiMocks, recordRequests } from "../../../../tests/msw/server";

const MOCK_ANSWERS = [
  { questionId: "wpll-q1", optionId: "wpll-q1-a" },
  { questionId: "wpll-q2", optionId: "wpll-q2-b" },
];

const MOCK_RESPONSE = {
  insight_text: "You show strong signs of career misalignment.",
  locked_sections: ["Environmental Friction Score", "Work Rhythm Pattern", "Emerging Archetype Signals"],
};

/**
 * This file used to stub `utils/api` with
 * `{ API_BASE: "http://localhost:5000/api" }` -- the *unversioned* base, which
 * Phase 1b retired. Nothing caught it, because the fetch stub answered whatever
 * URL it was handed; the test was exercising a base URL the app has not used
 * since the `/api/v1` cutover and would have kept passing if the real one broke.
 *
 * The mock is gone and the component now resolves the real `API_BASE`. That is
 * only safe because the handler below is bound to a contract path and
 * unhandled requests are errors: if the component posted to `/api/...` again,
 * no handler would match and the test would fail rather than shrug.
 */
useApiMocks();
const { requests } = recordRequests();

const SUBMIT = "POST /api/v1/assessments/wpll/submissions";

/** The teaser submission, answering with the WPLL result shape. */
function teaserReturns(body = MOCK_RESPONSE) {
  return mock("post", "/api/v1/assessments/{kind}/submissions").reply(200, body);
}

function makeProps(overrides: Partial<Parameters<typeof TeaserResult>[0]> = {}) {
  return {
    wpllAnswers: MOCK_ANSWERS,
    onInsightReceived: vi.fn(),
    cachedInsightText: "",
    onContinue: vi.fn(),
    ...overrides,
  };
}

describe("TeaserResult", () => {
  beforeEach(() => {
    server.use(teaserReturns());
  });

  it("renders insight text immediately when cachedInsightText is provided — no request", () => {
    render(
      <TeaserResult
        {...makeProps({ cachedInsightText: "Cached insight here." })}
      />
    );

    expect(screen.getByText("Cached insight here.")).toBeInTheDocument();
    expect(requests).toEqual([]);
  });

  it("shows loading state on mount then renders insight after the request resolves", async () => {
    render(<TeaserResult {...makeProps()} />);

    expect(screen.getByText("Reading your responses…")).toBeInTheDocument();

    await waitFor(() =>
      expect(screen.getByText(MOCK_RESPONSE.insight_text)).toBeInTheDocument()
    );
  });

  it("posts the answers to the wpll submissions endpoint", async () => {
    // The old stub could not see the path at all, so the `{kind}` in it -- the
    // thing that decides which of the five result shapes comes back -- went
    // unchecked.
    let sent: { answers?: unknown } | undefined;
    server.use(
      mock("post", "/api/v1/assessments/{kind}/submissions").resolve(async ({ request }) => {
        sent = (await request.json()) as { answers?: unknown };
        return HttpResponse.json(MOCK_RESPONSE);
      }),
    );

    render(<TeaserResult {...makeProps()} />);
    await waitFor(() =>
      expect(screen.getByText(MOCK_RESPONSE.insight_text)).toBeInTheDocument()
    );

    expect(requests).toEqual([SUBMIT]);
    expect(sent?.answers).toEqual([
      { question_id: "wpll-q1", option_id: "wpll-q1-a" },
      { question_id: "wpll-q2", option_id: "wpll-q2-b" },
    ]);
  });

  it("renders exactly 3 locked section cards", async () => {
    render(<TeaserResult {...makeProps()} />);

    await waitFor(() =>
      expect(screen.getByText(MOCK_RESPONSE.insight_text)).toBeInTheDocument()
    );

    const unlockTexts = screen.getAllByText("Unlock with a free account");
    expect(unlockTexts).toHaveLength(3);
  });

  it("renders each locked section title", async () => {
    render(<TeaserResult {...makeProps()} />);

    await waitFor(() =>
      expect(screen.getByText("Environmental Friction Score")).toBeInTheDocument()
    );
    expect(screen.getByText("Work Rhythm Pattern")).toBeInTheDocument();
    expect(screen.getByText("Emerging Archetype Signals")).toBeInTheDocument();
  });

  it("calls onInsightReceived with the insight text from the response", async () => {
    const onInsightReceived = vi.fn();

    render(<TeaserResult {...makeProps({ onInsightReceived })} />);

    await waitFor(() =>
      expect(onInsightReceived).toHaveBeenCalledWith(MOCK_RESPONSE.insight_text)
    );
  });

  it("shows error state when the request fails and retry re-issues it", async () => {
    let attempt = 0;
    server.use(
      mock("post", "/api/v1/assessments/{kind}/submissions").resolve(() => {
        attempt += 1;
        return attempt === 1 ? HttpResponse.error() : HttpResponse.json(MOCK_RESPONSE);
      }),
    );

    render(<TeaserResult {...makeProps()} />);

    await waitFor(() =>
      expect(
        screen.getByText("We couldn't generate your insight right now.")
      ).toBeInTheDocument()
    );

    fireEvent.click(screen.getByRole("button", { name: /try again/i }));

    await waitFor(() =>
      expect(screen.getByText(MOCK_RESPONSE.insight_text)).toBeInTheDocument()
    );

    expect(requests).toEqual([SUBMIT, SUBMIT]);
  });

  it("calls onContinue when the CTA button is clicked", async () => {
    const onContinue = vi.fn();

    render(<TeaserResult {...makeProps({ onContinue })} />);

    await waitFor(() =>
      expect(screen.getByText(MOCK_RESPONSE.insight_text)).toBeInTheDocument()
    );

    fireEvent.click(screen.getByRole("button", { name: /create my free account/i }));
    expect(onContinue).toHaveBeenCalledTimes(1);
  });
});
