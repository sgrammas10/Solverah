import { render, screen, fireEvent } from "@testing-library/react";
import StatementSelector from "../StatementSelector";
import { CAREER_STATEMENTS } from "../../../data/careerStatements";

describe("StatementSelector", () => {
  const onToggle = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders all 7 statements", () => {
    render(<StatementSelector selectedIds={[]} onToggle={onToggle} />);
    CAREER_STATEMENTS.forEach((s) => {
      expect(screen.getByText(s.text)).toBeInTheDocument();
    });
  });

  it("calls onToggle with the correct ID when a card is clicked", () => {
    render(<StatementSelector selectedIds={[]} onToggle={onToggle} />);
    fireEvent.click(screen.getByText(CAREER_STATEMENTS[0].text));
    expect(onToggle).toHaveBeenCalledWith("dir-1");
  });

  it("selected cards have aria-checked='true'", () => {
    render(<StatementSelector selectedIds={["dir-1", "sus-1"]} onToggle={onToggle} />);
    const checked = screen
      .getAllByRole("checkbox")
      .filter((el) => el.getAttribute("aria-checked") === "true");
    expect(checked).toHaveLength(2);
  });

  it("unselected cards have aria-checked='false'", () => {
    render(<StatementSelector selectedIds={["dir-1"]} onToggle={onToggle} />);
    const unchecked = screen
      .getAllByRole("checkbox")
      .filter((el) => el.getAttribute("aria-checked") === "false");
    expect(unchecked).toHaveLength(CAREER_STATEMENTS.length - 1);
  });
});
