import { render, screen } from "@testing-library/react";
import WorkPulseUnlock from "./WorkPulseUnlock";

vi.mock("react-router-dom", () => ({
  Link: ({
    to,
    children,
    onClick,
  }: {
    to: string;
    children: React.ReactNode;
    onClick?: () => void;
  }) => (
    <a href={to} onClick={onClick}>
      {children}
    </a>
  ),
}));

const ARCHETYPE = "Structured Deep Thinker";
const NARRATIVE =
  "Your responses reveal someone who does their best work in focused, uninterrupted stretches. You carry a high cognitive load gracefully, but only when the environment cooperates.";

describe("WorkPulseUnlock", () => {
  it("renders archetype and narrative preview when props are provided", () => {
    render(<WorkPulseUnlock archetype={ARCHETYPE} narrativePreview={NARRATIVE} />);
    expect(screen.getByText(ARCHETYPE)).toBeInTheDocument();
    expect(screen.getByText(NARRATIVE)).toBeInTheDocument();
    expect(screen.getByText(/✦ Unlocked/i)).toBeInTheDocument();
  });

  it("shows a 'Read full analysis' link pointing to /work-pulse/results", () => {
    render(<WorkPulseUnlock archetype={ARCHETYPE} narrativePreview={NARRATIVE} />);
    const link = screen.getByRole("link", { name: /read full analysis/i });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute("href", "/work-pulse/results");
  });

  it("renders the completion variant, with NO results link, when props are omitted", () => {
    // The no-data variant is the card for the CURRENT 24-item instrument, which has no
    // results screen by design (D-15): completion is the whole story. A link here would
    // promise a payoff the data layer deliberately withholds.
    render(<WorkPulseUnlock />);
    expect(
      screen.getByText(/work pulse complete — your answers now power your matching/i)
    ).toBeInTheDocument();
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.queryByText(ARCHETYPE)).not.toBeInTheDocument();
  });
});
