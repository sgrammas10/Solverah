import { render, screen, fireEvent } from "@testing-library/react";
import SkillProficiencyModal from "./SkillProficiencyModal";

const defaultProps = {
  skills: ["React", "Python", "ARIMA"],
  initialLevels: {},
  saving: false,
  onSave: vi.fn(),
  onSkip: vi.fn(),
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("SkillProficiencyModal", () => {
  it("renders all skills", () => {
    render(<SkillProficiencyModal {...defaultProps} />);
    expect(screen.getByText("React")).toBeInTheDocument();
    expect(screen.getByText("Python")).toBeInTheDocument();
    expect(screen.getByText("ARIMA")).toBeInTheDocument();
  });

  it("defaults all skills to Beginner when no initial levels provided", () => {
    render(<SkillProficiencyModal {...defaultProps} />);
    // Three skills × three level buttons each = 9 buttons total.
    // The Beginner buttons for all three should visually appear as selected (dark bg).
    const beginnerButtons = screen
      .getAllByRole("button", { name: /beginner/i })
      .filter((btn) => btn.className.includes("bg-forest-dark"));
    expect(beginnerButtons).toHaveLength(3);
  });

  it("pre-selects level from initialLevels", () => {
    render(
      <SkillProficiencyModal
        {...defaultProps}
        initialLevels={{ React: "advanced" }}
      />
    );
    const advancedButtons = screen
      .getAllByRole("button", { name: /advanced/i })
      .filter((btn) => btn.className.includes("bg-forest-dark"));
    expect(advancedButtons).toHaveLength(1);
  });

  it("calls onSave with current ratings when Save is clicked", () => {
    render(<SkillProficiencyModal {...defaultProps} skills={["React"]} />);
    const intermediateBtn = screen.getByRole("button", { name: /intermediate/i });
    fireEvent.click(intermediateBtn);
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    expect(defaultProps.onSave).toHaveBeenCalledWith({ React: "intermediate" });
  });

  it("calls onSkip when Skip is clicked", () => {
    render(<SkillProficiencyModal {...defaultProps} />);
    fireEvent.click(screen.getByRole("button", { name: /skip/i }));
    expect(defaultProps.onSkip).toHaveBeenCalledTimes(1);
  });

  it("disables buttons while saving", () => {
    render(<SkillProficiencyModal {...defaultProps} saving={true} />);
    expect(screen.getByRole("button", { name: /saving/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /skip/i })).toBeDisabled();
  });
});
