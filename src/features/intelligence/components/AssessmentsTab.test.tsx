import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import AssessmentsTab from "./AssessmentsTab";
import type { ProfileFormData } from "../../profile";

function renderTab() {
  render(
    <MemoryRouter>
      <AssessmentsTab formData={{ quizResults: {} } as unknown as ProfileFormData} />
    </MemoryRouter>,
  );
}

describe("AssessmentsTab - closing strip (G40)", () => {
  it("makes no promise about employers seeing the quizzes", () => {
    // /trust: "Employers do not see your answers". The strip used to say the
    // quizzes would "help you stand out to employers".
    renderTab();
    expect(screen.queryByText(/stand out to employers/i)).toBeNull();
    expect(screen.getByText(/employers never see them/i)).toBeInTheDocument();
  });

  it("does not claim the quizzes improve matching", () => {
    renderTab();
    expect(screen.queryByText(/matching accuracy/i)).toBeNull();
  });
});
