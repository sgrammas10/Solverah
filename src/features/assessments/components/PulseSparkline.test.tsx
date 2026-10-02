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

  // F2 (2026-10-02): the trend chart is responsive -- a viewBox and a
  // percentage width, so a 520-wide logical chart never forces a horizontal
  // scroll at 375px -- and it carries its own axes.
  it("scales to its container through a viewBox rather than a fixed pixel width", () => {
    const { container } = render(
      <PulseSparkline
        ariaLabel="test"
        width={520}
        height={140}
        points={[
          { date: "2026-09-10T12:00:00Z", value: 2 },
          { date: "2026-09-17T12:00:00Z", value: 4 },
        ]}
      />,
    );
    const svg = container.querySelector("svg") as SVGSVGElement;
    expect(svg).toHaveAttribute("viewBox", "0 0 520 140");
    expect(svg).toHaveAttribute("width", "100%");
    expect((container.firstChild as HTMLElement).style.width).toBe("100%");
  });

  it("labels the 1-5 scale and the first and last dates when not compact", () => {
    const { container } = render(
      <PulseSparkline
        ariaLabel="test"
        width={520}
        height={140}
        points={[
          { date: "2026-09-10T12:00:00Z", value: 2 },
          { date: "2026-09-17T12:00:00Z", value: 4 },
        ]}
      />,
    );
    const labels = Array.from(container.querySelectorAll("text")).map((t) => t.textContent);
    ["1", "2", "3", "4", "5"].forEach((tick) => expect(labels).toContain(tick));
    expect(labels.filter((l) => /Sep 1[07]/.test(l ?? ""))).toHaveLength(2);
  });

  it("labels only the ends of the scale on a short chart", () => {
    const { container } = render(
      <PulseSparkline
        ariaLabel="test"
        width={240}
        height={72}
        points={[
          { date: "2026-09-10T12:00:00Z", value: 2 },
          { date: "2026-09-17T12:00:00Z", value: 4 },
        ]}
      />,
    );
    const labels = Array.from(container.querySelectorAll("text")).map((t) => t.textContent);
    expect(labels).toContain("1");
    expect(labels).toContain("5");
    expect(labels).not.toContain("3");
  });

  it("draws no axes in compact mode", () => {
    const { container } = render(
      <PulseSparkline
        ariaLabel="test"
        compact
        points={[
          { date: "2026-09-10T12:00:00Z", value: 2 },
          { date: "2026-09-17T12:00:00Z", value: 4 },
        ]}
      />,
    );
    expect(container.querySelectorAll("text")).toHaveLength(0);
  });

  it("wraps an event tooltip with a long note instead of running off the chart", () => {
    render(
      <PulseSparkline
        ariaLabel="test"
        width={520}
        height={140}
        points={[
          { date: "2026-09-10T12:00:00Z", value: 2 },
          { date: "2026-09-17T12:00:00Z", value: 4 },
        ]}
        events={[
          {
            date: "2026-09-16T12:00:00Z",
            label: "Reorg",
            note: "Team split in two and the new lead moved the standup to eight in the morning",
          },
        ]}
      />,
    );
    fireEvent.mouseEnter(screen.getByRole("button", { name: /^Reorg on/ }));

    const tooltip = screen.getByRole("status");
    expect(tooltip).toHaveTextContent(/Team split in two/);
    expect(tooltip.className).toMatch(/whitespace-normal/);
    expect(tooltip.className).not.toMatch(/whitespace-nowrap/);
    expect(tooltip.className).toMatch(/max-w-/);
    // Positioned in percentages of the chart, so it follows the mark whatever
    // width the container renders at; an event near the right edge hugs it.
    expect(tooltip.style.left).toMatch(/%$/);
    expect(tooltip.className).toMatch(/-translate-x-full/);
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
