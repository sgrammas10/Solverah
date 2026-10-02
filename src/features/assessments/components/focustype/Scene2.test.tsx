import { render, screen, waitFor, within } from "@testing-library/react";
import Scene2 from "./Scene2";
import { liveRegionText, mockRects, press, touchHold } from "./dndTestUtils";

function card(label: RegExp) {
  return screen.getByText(label).closest('[role="button"]') as HTMLElement;
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Scene2 - drag input (F1)", () => {
  it("lets a finger scroll past the cards: touch-action is manipulation, not none", () => {
    render(<Scene2 onComplete={vi.fn()} />);
    expect(card(/Teammate asking a quick question/).style.touchAction).toBe("manipulation");
  });

  it("picks a card up on a touch press-and-hold", async () => {
    render(<Scene2 onComplete={vi.fn()} />);
    await touchHold(card(/Teammate asking a quick question/));
    await waitFor(() =>
      expect(liveRegionText()).toMatch(/Picked up Teammate asking a quick question/)
    );
  });

  it("moves a card into a bucket with the keyboard alone", async () => {
    // Regression: Scene 2 had no KeyboardSensor at all, so Space did nothing
    // and the scene could not be finished without a mouse.
    //
    // The pile on the left; the three buckets stacked on the right. Cards and
    // the drag overlay take the fallback box, inside the pile.
    mockRects(
      {
        "bucket-unassigned": [0, 0, 200, 600],
        "bucket-now": [300, 0, 200, 100],
        "bucket-later": [300, 120, 200, 100],
        "bucket-ignore": [300, 240, 200, 100],
      },
      [0, 0, 100, 40]
    );
    render(<Scene2 onComplete={vi.fn()} />);

    const target = card(/Teammate asking a quick question/);
    target.focus();
    await press(target, "Space"); // pick up, over the pile
    await press(target, "ArrowDown"); // -> NOW
    await press(target, "ArrowDown"); // -> LATER
    await press(target, "Space"); // drop

    const later = screen.getByTestId("bucket-later");
    await waitFor(() =>
      expect(within(later).getByText(/Teammate asking a quick question/)).toBeInTheDocument()
    );
    expect(within(screen.getByTestId("bucket-unassigned")).queryByText(/Teammate asking/)).toBeNull();
    expect(screen.getByText("9 unsorted")).toBeInTheDocument();
  });
});
