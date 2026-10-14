/**
 * TierBar.test.tsx -- Pro is on the path but not built, so it must say so,
 * and nothing on the bar may look like a control.
 */
import { render, screen } from "@testing-library/react";

import TierBar from "./TierBar";

it("labels Work Pulse Pro as coming soon", () => {
  render(<TierBar />);

  expect(screen.getByText("Work Pulse Pro · coming soon")).toBeInTheDocument();
  expect(screen.queryByText("Work Pulse Pro")).toBeNull();
});

it("renders no buttons or links", () => {
  render(<TierBar />);

  expect(screen.queryAllByRole("button")).toHaveLength(0);
  expect(screen.queryAllByRole("link")).toHaveLength(0);
});

it("uses a plain heading, not an uppercase eyebrow", () => {
  render(<TierBar />);

  expect(screen.getByText("Your Solverah journey")).not.toHaveClass("uppercase");
});
