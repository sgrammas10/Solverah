import { render, screen, waitFor } from "@testing-library/react";
import Scene1 from "./Scene1";
import { liveRegionText, press, touchHold } from "./dndTestUtils";

function card(label: RegExp) {
  return screen.getByText(label).closest('[role="button"]') as HTMLElement;
}

describe("Scene1 - drag input (F1)", () => {
  it("lets a finger scroll past the cards: touch-action is manipulation, not none", () => {
    render(<Scene1 onComplete={vi.fn()} />);
    expect(card(/Big complex project/).style.touchAction).toBe("manipulation");
  });

  it("picks a card up on a touch press-and-hold", async () => {
    // Regression: the scene had only a PointerSensor and no touch-action, so a
    // finger never started a drag. jsdom fires no pointer events for a touch,
    // which is what makes this test fail without the TouchSensor.
    render(<Scene1 onComplete={vi.fn()} />);
    await touchHold(card(/Big complex project/));
    await waitFor(() => expect(liveRegionText()).toMatch(/Big complex project/));
  });

  it("picks a card up with the keyboard", async () => {
    render(<Scene1 onComplete={vi.fn()} />);
    const target = card(/Big complex project/);
    target.focus();
    await press(target, "Space");
    await waitFor(() => expect(liveRegionText()).toMatch(/Big complex project/));
  });
});
