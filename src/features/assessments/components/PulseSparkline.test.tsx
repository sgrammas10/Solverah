import { render, screen, fireEvent } from "@testing-library/react";
import PulseSparkline from "./PulseSparkline";

describe("PulseSparkline", () => {
  it("renders nothing for zero points", () => {
    const { container } = render(<PulseSparkline ariaLabel="test" points={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders a single dot, no line, for one point", () => {
    const { container } = render(
      <PulseSparkline ariaLabel="test" points={[{ date: "2026-09-01", value: 3 }]} />,
    );
    expect(container.querySelectorAll("circle")).toHaveLength(1);
    expect(container.querySelector("path")).not.toBeInTheDocument();
  });

  it("draws a connecting line for two or more points", () => {
    const { container } = render(
      <PulseSparkline
        ariaLabel="test"
        points={[
          { date: "2026-09-01", value: 2 },
          { date: "2026-09-08", value: 4 },
        ]}
      />,
    );
    expect(container.querySelector("path")).toBeInTheDocument();
  });

  it("shows a tooltip with the date and value on hover, non-compact", () => {
    render(
      <PulseSparkline
        ariaLabel="test"
        points={[
          { date: "2026-09-01T00:00:00Z", value: 2 },
          { date: "2026-09-08T00:00:00Z", value: 4 },
        ]}
      />,
    );
    const hitTargets = screen.getAllByRole("button");
    fireEvent.mouseEnter(hitTargets[hitTargets.length - 1]);
    expect(screen.getByRole("status")).toHaveTextContent("4");
  });

  it("skips hover targets and events entirely in compact mode", () => {
    render(
      <PulseSparkline
        ariaLabel="test"
        compact
        points={[
          { date: "2026-09-01", value: 2 },
          { date: "2026-09-08", value: 4 },
        ]}
        events={[{ date: "2026-09-04", label: "New manager" }]}
      />,
    );
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });

  it("renders an event tick with an accessible label when not compact", () => {
    render(
      <PulseSparkline
        ariaLabel="test"
        points={[
          { date: "2026-09-01", value: 2 },
          { date: "2026-09-08", value: 4 },
        ]}
        events={[{ date: "2026-09-04", label: "New manager", note: "Switched teams" }]}
      />,
    );
    expect(
      screen.getByRole("button", { name: /New manager on .*: Switched teams/ }),
    ).toBeInTheDocument();
  });
});
