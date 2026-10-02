import { render, screen, waitFor } from "@testing-library/react";
import Scene5 from "./Scene5";
import { liveRegionText, mockRects, press, touchHold, type Box } from "./dndTestUtils";

function trayBlock(label: string) {
  return screen.getByText(label).closest('[role="button"]') as HTMLElement;
}

/** The eight 100px slots along the top; everything else sits below them. */
const SLOT_BOXES: Record<string, Box> = Object.fromEntries(
  Array.from({ length: 8 }, (_, i) => [`slot-${i}`, [i * 100, 0, 100, 80] as Box])
);
const BELOW_TIMELINE: Box = [0, 300, 120, 40];

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Scene5 - drag input (F1)", () => {
  it("lets a finger scroll the timeline: touch-action is manipulation, not none", () => {
    render(<Scene5 onComplete={vi.fn()} />);
    expect(trayBlock("Deep work").style.touchAction).toBe("manipulation");
  });

  it("picks a block up on a touch press-and-hold", async () => {
    render(<Scene5 onComplete={vi.fn()} />);
    await touchHold(trayBlock("Deep work"));
    await waitFor(() => expect(liveRegionText()).toMatch(/Picked up Deep work/));
  });

  it("places a block on the timeline with the keyboard alone", async () => {
    // Regression: no KeyboardSensor, and pointerWithin collision detection,
    // which finds nothing when there is no pointer. Both had to change.
    mockRects(SLOT_BOXES, BELOW_TIMELINE);
    render(<Scene5 onComplete={vi.fn()} />);

    const target = trayBlock("Deep work");
    target.focus();
    await press(target, "Space"); // pick up, in the tray
    await press(target, "ArrowRight"); // -> 6pm slot
    await press(target, "ArrowRight"); // -> 6:30pm slot
    await press(target, "Space"); // drop

    await waitFor(() =>
      expect(screen.getByText(/6 blocks available/)).toBeInTheDocument()
    );
    // Deep work is four slots long and now starts at slot 1.
    const placed = screen.getByText("Deep work").closest('[role="button"]') as HTMLElement;
    expect(placed.style.left).toBe("100px");
    expect(screen.getByText("2h planned")).toBeInTheDocument();
  });

  it("sends a placed block back to the tray with the keyboard", async () => {
    mockRects(SLOT_BOXES, BELOW_TIMELINE);
    render(<Scene5 onComplete={vi.fn()} />);

    const target = trayBlock("Focused sprint");
    target.focus();
    await press(target, "Space");
    await press(target, "ArrowRight");
    await press(target, "Space");
    await waitFor(() => expect(screen.getByText(/6 blocks available/)).toBeInTheDocument());

    const placed = screen.getByText("Focused sprint").closest('[role="button"]') as HTMLElement;
    placed.focus();
    await press(placed, "Space");
    await press(placed, "ArrowDown"); // off the timeline
    await press(placed, "Space");
    await waitFor(() => expect(screen.getByText(/7 blocks available/)).toBeInTheDocument());
  });
});
