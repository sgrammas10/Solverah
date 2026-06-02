import { useState } from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import WorkPulseBanner from "./WorkPulseBanner";

const mockNavigate = vi.fn();
vi.mock("react-router-dom", () => ({
  useNavigate: () => mockNavigate,
}));

function renderBanner(onDismiss = vi.fn()) {
  return render(<WorkPulseBanner onDismiss={onDismiss} />);
}

function BannerWithParentState({ wplCompleted }: { wplCompleted: boolean }) {
  const [dismissed, setDismissed] = useState(false);
  if (wplCompleted || dismissed) return null;
  return <WorkPulseBanner onDismiss={() => setDismissed(true)} />;
}

describe("WorkPulseBanner", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the headline and CTA when wpl_completed is false", () => {
    renderBanner();
    expect(screen.getByText("Complete your Work Pulse")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /start now/i })).toBeInTheDocument();
  });

  it("clicking the dismiss button calls onDismiss", () => {
    const onDismiss = vi.fn();
    renderBanner(onDismiss);
    fireEvent.click(screen.getByRole("button", { name: /dismiss/i }));
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it("navigates to /work-pulse when the CTA is clicked", () => {
    renderBanner();
    fireEvent.click(screen.getByRole("button", { name: /start now/i }));
    expect(mockNavigate).toHaveBeenCalledWith("/work-pulse");
  });

  it("does not render when wpl_completed is true", () => {
    render(<BannerWithParentState wplCompleted={true} />);
    expect(screen.queryByText("Complete your Work Pulse")).not.toBeInTheDocument();
  });

  it("hides the banner after dismiss is triggered", () => {
    render(<BannerWithParentState wplCompleted={false} />);
    expect(screen.getByText("Complete your Work Pulse")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /dismiss/i }));
    expect(screen.queryByText("Complete your Work Pulse")).not.toBeInTheDocument();
  });
});
