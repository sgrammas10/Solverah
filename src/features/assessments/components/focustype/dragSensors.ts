/**
 * dragSensors -- the input setup shared by the three FocusType drag scenes
 * (1, 2 and 5): mouse, touch and keyboard.
 *
 * WHY NOT dnd-kit's PointerSensor. It treats a finger like a mouse, so it needs
 * `touch-action: none` on every draggable, and that stops the page scrolling
 * under a finger resting on a card. On a phone Scene 2 is a column of ten
 * full-width cards, and Scene 5's placed blocks fill a timeline that scrolls
 * sideways; with `touch-action: none` there is almost nowhere left to swipe.
 * So mouse and touch get separate sensors:
 *
 *  - MouseSensor starts a drag after 8px of movement, as the old PointerSensor did.
 *  - TouchSensor starts a drag after a 200ms press-and-hold. A swipe that moves
 *    more than the tolerance first is a scroll, so scrolling the page or the
 *    Scene 5 timeline keeps working. Once the drag starts, dnd-kit cancels the
 *    touchmove so the page stays put under the card. That is why draggables
 *    carry `touch-action: manipulation` (pan and pinch allowed, double-tap zoom
 *    off), which is dnd-kit's recommendation for this sensor, and not `none`.
 *  - KeyboardSensor: Space picks up, arrows move, Space drops, Escape cancels.
 *    Each scene passes the coordinate getter that suits its layout.
 */
import {
  KeyboardSensor,
  MouseSensor,
  TouchSensor,
  useSensor,
  useSensors,
  type Collision,
  type CollisionDetection,
  type KeyboardCoordinateGetter,
} from "@dnd-kit/core";
import type { CSSProperties } from "react";

export const MOUSE_ACTIVATION = { distance: 8 } as const;
export const TOUCH_ACTIVATION = { delay: 200, tolerance: 8 } as const;

/** Spread onto every draggable's `style`. */
export const DRAGGABLE_TOUCH_STYLE: CSSProperties = {
  touchAction: "manipulation",
  // A long press would otherwise open iOS's callout menu instead of a drag.
  WebkitTouchCallout: "none",
};

export function useSceneSensors(coordinateGetter?: KeyboardCoordinateGetter) {
  return useSensors(
    useSensor(MouseSensor, { activationConstraint: MOUSE_ACTIVATION }),
    useSensor(TouchSensor, { activationConstraint: TOUCH_ACTIVATION }),
    useSensor(KeyboardSensor, coordinateGetter ? { coordinateGetter } : undefined)
  );
}

const FORWARD = ["ArrowDown", "ArrowRight"];
const BACKWARD = ["ArrowUp", "ArrowLeft"];

/**
 * Keyboard movement that jumps between droppable containers in a fixed order
 * (Scene 2's pile and buckets). An arrow key moves the card's top-left corner
 * onto the next or previous container's, so a press is always one container,
 * whatever the layout.
 */
export function containerKeyboardCoordinates(order: readonly string[]): KeyboardCoordinateGetter {
  return (event, { context }) => {
    const step = FORWARD.includes(event.code) ? 1 : BACKWARD.includes(event.code) ? -1 : 0;
    if (step === 0) return undefined;
    event.preventDefault();

    const { active, over, droppableRects, collisionRect } = context;
    if (!active || !collisionRect) return undefined;

    const current = over ? order.indexOf(String(over.id)) : -1;
    const next = Math.min(Math.max(current + step, 0), order.length - 1);
    const rect = droppableRects.get(order[next]);
    if (!rect) return undefined;
    return { x: rect.left, y: rect.top };
  };
}

/** `slot-<n>` -> n, or null for anything else. */
export function slotIndexOf(id: unknown): number | null {
  if (typeof id !== "string" || !id.startsWith("slot-")) return null;
  const n = parseInt(id.slice("slot-".length), 10);
  return Number.isNaN(n) ? null : n;
}

/**
 * Keyboard movement along Scene 5's timeline. Left and right move one slot.
 * Up, or any first press, lands on the first slot; Down moves the block off the
 * timeline, where dropping it sends a placed block back to the tray.
 */
export function slotKeyboardCoordinates(totalSlots: number): KeyboardCoordinateGetter {
  return (event, { context, currentCoordinates }) => {
    const keys = ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"];
    if (!keys.includes(event.code)) return undefined;
    event.preventDefault();

    const { active, over, droppableRects, collisionRect } = context;
    if (!active || !collisionRect) return undefined;

    const first = droppableRects.get("slot-0");
    if (!first) return undefined;

    if (event.code === "ArrowDown") {
      return { x: currentCoordinates.x, y: first.bottom + collisionRect.height };
    }

    const current = over ? slotIndexOf(over.id) : null;
    let next = 0;
    if (current !== null) {
      if (event.code === "ArrowRight") next = Math.min(current + 1, totalSlots - 1);
      else if (event.code === "ArrowLeft") next = Math.max(current - 1, 0);
      else next = current;
    }
    const rect = droppableRects.get(`slot-${next}`);
    if (!rect) return undefined;
    return { x: rect.left, y: rect.top };
  };
}

/**
 * Scene 5's collision detection. A mouse or finger drop lands on the slot under
 * the pointer (`pointerWithin`, passed in). A keyboard drag has no pointer, so it
 * lands on the slot holding the dragged block's left edge, which is where the
 * keyboard getter above puts it.
 */
export function slotCollision(pointerDetection: CollisionDetection): CollisionDetection {
  return (args) => {
    if (args.pointerCoordinates) return pointerDetection(args);
    const { collisionRect, droppableContainers, droppableRects } = args;
    const x = collisionRect.left + 1;
    const y = collisionRect.top + collisionRect.height / 2;
    const hits: Collision[] = [];
    for (const container of droppableContainers) {
      const rect = droppableRects.get(container.id);
      if (!rect) continue;
      if (x >= rect.left && x < rect.right && y >= rect.top && y <= rect.bottom) {
        hits.push({ id: container.id, data: { droppableContainer: container, value: 0 } });
      }
    }
    return hits;
  };
}
