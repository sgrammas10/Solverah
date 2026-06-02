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

  it("renders the placeholder variant when archetype and narrativePreview are omitted", () => {
    render(<WorkPulseUnlock />);
    expect(screen.getByText(/work pulse complete — view your results/i)).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /view full analysis/i });
    expect(link).toHaveAttribute("href", "/work-pulse/results");
    expect(screen.queryByText(ARCHETYPE)).not.toBeInTheDocument();
  });
});
