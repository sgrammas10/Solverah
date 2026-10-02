/**
 * Test-only helpers for the FocusType drag scenes. jsdom has no layout, so every
 * element measures 0x0 and dnd-kit finds no collisions. `mockRects` gives the
 * elements named by `data-testid` a fixed box and everything else a default
 * one, which is enough for a keyboard drag to land somewhere real.
 *
 * Imported by the Scene tests only; nothing in the app imports this file.
 */
import { act, fireEvent } from "@testing-library/react";
import { vi } from "vitest";

export type Box = [left: number, top: number, width: number, height: number];

function rect([left, top, width, height]: Box): DOMRect {
  return {
    x: left,
    y: top,
    left,
    top,
    width,
    height,
    right: left + width,
    bottom: top + height,
    toJSON: () => ({}),
  } as DOMRect;
}

export function mockRects(boxes: Record<string, Box>, fallback: Box) {
  return vi
    .spyOn(Element.prototype, "getBoundingClientRect")
    .mockImplementation(function (this: Element) {
      const id = this.getAttribute("data-testid");
      return rect((id && boxes[id]) || fallback);
    });
}

/** dnd-kit attaches its keydown listener on the next tick after a pick-up. */
export async function tick() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

/** Press one key on whatever has focus (dnd-kit listens on the window). */
export async function press(target: Element, code: string) {
  await act(async () => {
    fireEvent.keyDown(target, { code, key: code === "Space" ? " " : code });
  });
  await tick();
}

/** A press-and-hold touch. Fires touchstart and waits past the hold delay. */
export async function touchHold(target: Element, holdMs = 260) {
  await act(async () => {
    fireEvent.touchStart(target, { touches: [{ clientX: 10, clientY: 10 }] });
  });
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, holdMs));
  });
}

/** The text dnd-kit's live region is announcing. */
export function liveRegionText(): string {
  return Array.from(document.querySelectorAll('[role="status"][aria-live]'))
    .map((el) => el.textContent ?? "")
    .join(" ");
}
