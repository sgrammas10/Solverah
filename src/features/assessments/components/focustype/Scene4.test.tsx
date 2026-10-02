import { render, screen, fireEvent, act } from "@testing-library/react";
import Scene4 from "./Scene4";

// Scene 4 drives its 3-second timer from requestAnimationFrame and Date.now, so
// both are faked along with setTimeout (the 320ms card exit).
beforeEach(() => {
  vi.useFakeTimers({
    toFake: ["setTimeout", "clearTimeout", "requestAnimationFrame", "cancelAnimationFrame", "Date"],
  });
});

afterEach(() => {
  vi.useRealTimers();
});

const CARD_COUNT = 8;
/** One card's full cycle: the 3000ms timer, the 320ms exit, and some slack. */
const CARD_CYCLE_MS = 3000 + 320 + 50;

function start(onComplete = vi.fn()) {
  render(<Scene4 onComplete={onComplete} />);
  fireEvent.click(screen.getByRole("button", { name: /I'm ready/i }));
  return onComplete;
}

async function advance(ms: number) {
  await act(async () => {
    vi.advanceTimersByTime(ms);
  });
}

describe("Scene4 - decision timing", () => {
  it("sends null, not 0, when every card times out (F2)", async () => {
    // Regression: the average over zero clicks was sent as 0, which the scorer
    // read as the fastest decider possible (+1 reactivity for a user who never
    // clicked). Null is "no timing signal".
    const onComplete = start();
    for (let i = 0; i < CARD_COUNT; i++) {
      await advance(CARD_CYCLE_MS);
    }
    expect(onComplete).toHaveBeenCalledTimes(1);
    const payload = onComplete.mock.calls[0][0];
    expect(payload.avg_decision_time_ms).toBeNull();
    expect(payload.now).toEqual([]);
    expect(payload.tomorrow).toHaveLength(CARD_COUNT);
  });

  it("averages only the cards that were clicked, leaving timeouts out", async () => {
    const onComplete = start();
    // Card 1: clicked after 1000ms.
    await advance(1000);
    fireEvent.click(screen.getByRole("button", { name: "Do it now" }));
    await advance(400);
    // Cards 2-8: all time out.
    for (let i = 1; i < CARD_COUNT; i++) {
      await advance(CARD_CYCLE_MS);
    }
    expect(onComplete).toHaveBeenCalledTimes(1);
    const payload = onComplete.mock.calls[0][0];
    expect(payload.now).toHaveLength(1);
    // About 1000ms: the timed-out cards' 3000ms are not in the mean.
    expect(payload.avg_decision_time_ms).toBeGreaterThanOrEqual(950);
    expect(payload.avg_decision_time_ms).toBeLessThan(1100);
  });
});
