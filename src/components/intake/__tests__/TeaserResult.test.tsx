import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import TeaserResult from "../TeaserResult";

const MOCK_ANSWERS = [
  { questionId: "wpll-q1", optionId: "wpll-q1-a" },
  { questionId: "wpll-q2", optionId: "wpll-q2-b" },
];

const MOCK_RESPONSE = {
  insight_text: "You show strong signs of career misalignment.",
  locked_sections: ["Environmental Friction Score", "Work Rhythm Pattern", "Emerging Archetype Signals"],
};

vi.mock("../../../utils/api", () => ({ API_BASE: "http://localhost:5000/api" }));

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
    vi.resetAllMocks();
    globalThis.fetch = vi.fn();
  });

  it("renders insight text immediately when cachedInsightText is provided — no fetch", () => {
    render(
      <TeaserResult
        {...makeProps({ cachedInsightText: "Cached insight here." })}
      />
    );

    expect(screen.getByText("Cached insight here.")).toBeInTheDocument();
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it("shows loading state on mount then renders insight after fetch resolves", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => MOCK_RESPONSE,
    });

    render(<TeaserResult {...makeProps()} />);

    expect(screen.getByText("Reading your responses…")).toBeInTheDocument();

    await waitFor(() =>
      expect(screen.getByText(MOCK_RESPONSE.insight_text)).toBeInTheDocument()
    );
  });

  it("renders exactly 3 locked section cards", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => MOCK_RESPONSE,
    });

    render(<TeaserResult {...makeProps()} />);

    await waitFor(() =>
      expect(screen.getByText(MOCK_RESPONSE.insight_text)).toBeInTheDocument()
    );

    const unlockTexts = screen.getAllByText("Unlock with a free account");
    expect(unlockTexts).toHaveLength(3);
  });

  it("renders each locked section title", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => MOCK_RESPONSE,
    });

    render(<TeaserResult {...makeProps()} />);

    await waitFor(() =>
      expect(screen.getByText("Environmental Friction Score")).toBeInTheDocument()
    );
    expect(screen.getByText("Work Rhythm Pattern")).toBeInTheDocument();
    expect(screen.getByText("Emerging Archetype Signals")).toBeInTheDocument();
  });

  it("calls onInsightReceived with the insight text from fetch", async () => {
    const onInsightReceived = vi.fn();
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => MOCK_RESPONSE,
    });

    render(<TeaserResult {...makeProps({ onInsightReceived })} />);

    await waitFor(() =>
      expect(onInsightReceived).toHaveBeenCalledWith(MOCK_RESPONSE.insight_text)
    );
  });

  it("shows error state when fetch rejects and retry re-triggers fetch", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>)
      .mockRejectedValueOnce(new Error("Network error"))
      .mockResolvedValueOnce({
        ok: true,
        json: async () => MOCK_RESPONSE,
      });

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

    expect(globalThis.fetch).toHaveBeenCalledTimes(2);
  });

  it("calls onContinue when the CTA button is clicked", async () => {
    const onContinue = vi.fn();
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => MOCK_RESPONSE,
    });

    render(<TeaserResult {...makeProps({ onContinue })} />);

    await waitFor(() =>
      expect(screen.getByText(MOCK_RESPONSE.insight_text)).toBeInTheDocument()
    );

    fireEvent.click(screen.getByRole("button", { name: /create my free account/i }));
    expect(onContinue).toHaveBeenCalledTimes(1);
  });
});
