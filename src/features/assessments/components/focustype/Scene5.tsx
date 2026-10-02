import { useState } from "react";
import {
  DndContext,
  DragOverlay,
  pointerWithin,
  useDroppable,
  useDraggable,
  type Announcements,
  type DragEndEvent,
  type DragStartEvent,
  type DragOverEvent,
} from "@dnd-kit/core";
import {
  DRAGGABLE_TOUCH_STYLE,
  slotCollision,
  slotIndexOf,
  slotKeyboardCoordinates,
  useSceneSensors,
} from "./dragSensors";

// ---------------------------------------------------------------------------
// Block definitions — IDs must match backend Scene 5 scoring
// ---------------------------------------------------------------------------

interface BlockDef {
  id: string;
  emoji: string;
  label: string;
  slots: number; // number of 30-min slots (rounded)
  duration: string;
  bgClass: string;
  textClass: string;
  borderClass: string;
}

const BLOCKS: BlockDef[] = [
  {
    id: "deep_work",
    emoji: "🧠",
    label: "Deep work",
    slots: 4,
    duration: "2h",
    bgClass: "bg-forest-dark",
    textClass: "text-white",
    borderClass: "border-forest-dark",
  },
  {
    id: "focused_sprint",
    emoji: "⚡",
    label: "Focused sprint",
    slots: 2,
    duration: "45m",
    bgClass: "bg-forest-mid",
    textClass: "text-white",
    borderClass: "border-forest-mid",
  },
  {
    id: "break",
    emoji: "☕",
    label: "Break",
    slots: 1,
    duration: "30m",
    bgClass: "bg-amber-100",
    textClass: "text-amber-800",
    borderClass: "border-amber-300",
  },
  {
    id: "teammate_checkin",
    emoji: "💬",
    label: "Check in",
    slots: 1,
    duration: "30m",
    bgClass: "bg-sky-100",
    textClass: "text-sky-800",
    borderClass: "border-sky-300",
  },
  {
    id: "planning",
    emoji: "📋",
    label: "Plan & org",
    slots: 1,
    duration: "30m",
    bgClass: "bg-violet-100",
    textClass: "text-violet-800",
    borderClass: "border-violet-300",
  },
  {
    id: "second_sprint",
    emoji: "🔁",
    label: "Second sprint",
    slots: 2,
    duration: "45m",
    bgClass: "bg-teal-100",
    textClass: "text-teal-800",
    borderClass: "border-teal-300",
  },
  {
    id: "wind_down",
    emoji: "🌙",
    label: "Wind down",
    slots: 1,
    duration: "30m",
    bgClass: "bg-slate-100",
    textClass: "text-slate-700",
    borderClass: "border-slate-300",
  },
];

const TOTAL_SLOTS = 8;
const SLOT_WIDTH = 100; // px — each 30-min slot
const TIMELINE_HEIGHT = 80; // px

// Time labels at slot boundaries (slot 8 = right edge = 10pm)
const TIME_LABELS = [
  { label: "6pm", slot: 0 },
  { label: "7pm", slot: 2 },
  { label: "8pm", slot: 4 },
  { label: "9pm", slot: 6 },
  { label: "10pm", slot: 8 },
] as const;

const REQUIRED_SLOTS = 6; // 3 hours minimum

function blockById(id: string): BlockDef | undefined {
  return BLOCKS.find((b) => b.id === id);
}

// A mouse or finger drop lands on the slot under the pointer; a keyboard drag
// moves slot by slot (see dragSensors).
const collisionDetection = slotCollision(pointerWithin);
const keyboardCoordinates = slotKeyboardCoordinates(TOTAL_SLOTS);

/** "6:30pm" for slot 1. */
function slotTime(slot: number): string {
  const minutes = 18 * 60 + slot * 30;
  const hour = Math.floor(minutes / 60) - 12;
  const mins = minutes % 60;
  return `${hour}${mins ? `:${String(mins).padStart(2, "0")}` : ""}pm`;
}

function blockName(id: unknown): string {
  return blockById(String(id))?.label ?? "block";
}

function placeName(id: unknown): string {
  const slot = slotIndexOf(id);
  return slot === null ? "off the timeline" : `the ${slotTime(slot)} slot`;
}

const announcements: Announcements = {
  onDragStart: ({ active }) => `Picked up ${blockName(active.id)}.`,
  onDragOver: ({ active, over }) => `${blockName(active.id)} is over ${placeName(over?.id)}.`,
  onDragEnd: ({ active, over }) =>
    over
      ? `${blockName(active.id)} dropped at ${placeName(over.id)}.`
      : `${blockName(active.id)} back in the tray.`,
  onDragCancel: ({ active }) => `Cancelled. ${blockName(active.id)} not moved.`,
};

// ---------------------------------------------------------------------------
// useTimelineState
// ---------------------------------------------------------------------------

function useTimelineState() {
  const [placed, setPlaced] = useState<Map<string, number>>(new Map());

  // Returns the set of occupied slot indices, optionally excluding one block
  // (used to allow a placed block to "move through" its own slots)
  function getOccupiedSlots(excluding?: string): Set<number> {
    const occupied = new Set<number>();
    for (const [id, start] of placed.entries()) {
      if (id === excluding) continue;
      const block = blockById(id);
      if (!block) continue;
      for (let s = start; s < start + block.slots; s++) occupied.add(s);
    }
    return occupied;
  }

  function canPlace(blockId: string, startSlot: number): boolean {
    const block = blockById(blockId);
    if (!block) return false;
    if (startSlot < 0 || startSlot + block.slots > TOTAL_SLOTS) return false;
    const occupied = getOccupiedSlots(blockId); // exclude self so moves are allowed
    for (let s = startSlot; s < startSlot + block.slots; s++) {
      if (occupied.has(s)) return false;
    }
    return true;
  }

  function placeBlock(blockId: string, startSlot: number): boolean {
    if (!canPlace(blockId, startSlot)) return false;
    setPlaced((prev) => new Map(prev).set(blockId, startSlot));
    return true;
  }

  function removeBlock(blockId: string): void {
    setPlaced((prev) => {
      const next = new Map(prev);
      next.delete(blockId);
      return next;
    });
  }

  const filledSlots = Array.from(placed.entries()).reduce(
    (acc, [id]) => acc + (blockById(id)?.slots ?? 0),
    0
  );

  const orderedBlocks = Array.from(placed.entries())
    .sort(([, a], [, b]) => a - b)
    .map(([id]) => id);

  return { placed, canPlace, placeBlock, removeBlock, filledSlots, orderedBlocks };
}

// ---------------------------------------------------------------------------
// DroppableSlot — one 30-min cell in the timeline background layer
// ---------------------------------------------------------------------------

function DroppableSlot({ index, isOver }: { index: number; isOver: boolean }) {
  const { setNodeRef } = useDroppable({ id: `slot-${index}` });

  return (
    <div
      ref={setNodeRef}
      data-testid={`slot-${index}`}
      style={{ width: SLOT_WIDTH, height: TIMELINE_HEIGHT, flexShrink: 0 }}
      className={`border-r border-cream-muted last:border-r-0 transition-colors duration-100 ${
        isOver ? "bg-forest-pale/50" : ""
      }`}
    />
  );
}

// ---------------------------------------------------------------------------
// DraggableTrayBlock — compact card in the unplaced tray
// ---------------------------------------------------------------------------

function DraggableTrayBlock({ id }: { id: string }) {
  const block = blockById(id)!;
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({ id });

  return (
    <div
      ref={setNodeRef}
      {...listeners}
      {...attributes}
      style={{ ...DRAGGABLE_TOUCH_STYLE, opacity: isDragging ? 0.2 : 1 }}
      className={`flex items-center gap-2 px-3 py-2 rounded-lg border-2 cursor-grab active:cursor-grabbing select-none transition-all shadow-sm hover:shadow-md ${block.bgClass} ${block.textClass} ${block.borderClass}`}
    >
      <span className="text-base leading-none">{block.emoji}</span>
      <div className="flex flex-col min-w-0">
        <span className="text-xs font-semibold leading-tight whitespace-nowrap">{block.label}</span>
        <span className="text-[10px] opacity-60 leading-tight">{block.duration}</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// DraggableTimelineBlock — placed block, absolutely positioned on the strip
// ---------------------------------------------------------------------------

function DraggableTimelineBlock({
  id,
  startSlot,
  isBeingDragged,
}: {
  id: string;
  startSlot: number;
  isBeingDragged: boolean;
}) {
  const block = blockById(id)!;
  const { attributes, listeners, setNodeRef } = useDraggable({ id });

  return (
    <div
      ref={setNodeRef}
      {...listeners}
      {...attributes}
      style={{
        ...DRAGGABLE_TOUCH_STYLE,
        position: "absolute",
        left: startSlot * SLOT_WIDTH,
        width: block.slots * SLOT_WIDTH,
        height: TIMELINE_HEIGHT,
        top: 0,
        zIndex: 10,
        opacity: isBeingDragged ? 0.25 : 1,
      }}
      className={`flex items-center justify-center gap-2 px-2 rounded border-2 cursor-grab active:cursor-grabbing select-none transition-opacity ${block.bgClass} ${block.textClass} ${block.borderClass}`}
    >
      <span className="text-xl leading-none flex-shrink-0">{block.emoji}</span>
      {block.slots >= 2 && (
        <div className="flex flex-col min-w-0">
          <span className="text-xs font-semibold leading-tight truncate">{block.label}</span>
          <span className="text-[10px] opacity-60 leading-tight">{block.duration}</span>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// OverlayBlock — compact card that floats under the cursor during drag
// ---------------------------------------------------------------------------

function OverlayBlock({ id }: { id: string }) {
  const block = blockById(id)!;
  return (
    <div
      className={`flex items-center gap-2 px-3 py-2 rounded-lg border-2 shadow-xl cursor-grabbing select-none ${block.bgClass} ${block.textClass} ${block.borderClass}`}
    >
      <span className="text-base leading-none">{block.emoji}</span>
      <div className="flex flex-col min-w-0">
        <span className="text-xs font-semibold leading-tight whitespace-nowrap">{block.label}</span>
        <span className="text-[10px] opacity-60 leading-tight">{block.duration}</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Scene 5 — The Evening Build
// ---------------------------------------------------------------------------

export interface Scene5Props {
  onComplete: (payload: string[]) => void;
}

export default function Scene5({ onComplete }: Scene5Props) {
  const { placed, canPlace, placeBlock, removeBlock, filledSlots, orderedBlocks } =
    useTimelineState();
  const [activeId, setActiveId] = useState<string | null>(null);
  const [hoverSlot, setHoverSlot] = useState<number | null>(null);

  const sensors = useSceneSensors(keyboardCoordinates);

  const unplacedBlocks = BLOCKS.filter((b) => !placed.has(b.id));
  const canConfirm = filledSlots >= REQUIRED_SLOTS;

  function handleDragStart({ active }: DragStartEvent) {
    setActiveId(active.id as string);
    setHoverSlot(null);
  }

  function handleDragOver({ over }: DragOverEvent) {
    setHoverSlot(over ? slotIndexOf(over.id) : null);
  }

  function handleDragEnd({ active, over }: DragEndEvent) {
    const blockId = active.id as string;
    setActiveId(null);
    setHoverSlot(null);

    if (!over) {
      // Dropped outside the timeline — return placed block to tray
      if (placed.has(blockId)) removeBlock(blockId);
      return;
    }

    const slotIndex = slotIndexOf(over.id);
    if (slotIndex === null) return;
    placeBlock(blockId, slotIndex);
    // If placeBlock fails (overlap / out of bounds), the block stays
    // at its previous position (or in the tray if it wasn't placed).
  }

  // Ghost preview: semi-transparent block at hoverSlot during drag
  const ghostBlock =
    activeId && hoverSlot !== null ? blockById(activeId) ?? null : null;
  const ghostValid = ghostBlock ? canPlace(activeId!, hoverSlot!) : false;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="space-y-1.5">
        <p className="font-display text-lg font-semibold text-ink-primary">
          The Evening Build
        </p>
        <p className="text-sm text-ink-secondary leading-relaxed">
          Drag blocks onto the 6pm–10pm timeline to plan your evening. Fill at least{" "}
          <strong className="text-ink-primary">3 hours</strong> to continue. Blocks
          can&apos;t overlap — not everything needs to fit.
        </p>
        <p className="text-xs text-ink-tertiary">
          On a touchscreen, press and hold a block to pick it up; a quick swipe scrolls
          the timeline. With a keyboard, Space picks a block up, the left and right
          arrows move it a half hour, down takes it off the timeline, and Space puts
          it down.
        </p>
      </div>

      <DndContext
        sensors={sensors}
        collisionDetection={collisionDetection}
        accessibility={{ announcements }}
        onDragStart={handleDragStart}
        onDragOver={handleDragOver}
        onDragEnd={handleDragEnd}
        onDragCancel={() => {
          setActiveId(null);
          setHoverSlot(null);
        }}
      >
        {/* Slot fill indicator */}
        <div className="flex items-center gap-2.5">
          <div className="flex gap-1">
            {Array.from({ length: TOTAL_SLOTS }, (_, i) => (
              <div
                key={i}
                className={`h-1.5 w-6 rounded-full transition-colors duration-200 ${
                  i < filledSlots ? "bg-forest-dark" : "bg-cream-muted"
                }`}
              />
            ))}
          </div>
          <span className="text-xs text-ink-tertiary">
            {Math.floor(filledSlots / 2)}h{filledSlots % 2 === 1 ? "30m" : ""} planned
          </span>
        </div>

        {/* Timeline */}
        <div className="overflow-x-auto -mx-1 px-1 pb-1">
          <div style={{ minWidth: TOTAL_SLOTS * SLOT_WIDTH }}>

            {/* Time axis labels */}
            <div className="relative mb-1" style={{ height: 18 }}>
              {TIME_LABELS.map(({ label, slot }) => (
                <span
                  key={label}
                  style={{
                    position: "absolute",
                    left: slot * SLOT_WIDTH,
                    transform: slot === TOTAL_SLOTS ? "translateX(-100%)" : "none",
                  }}
                  className="text-[10px] font-semibold uppercase tracking-wide text-ink-tertiary"
                >
                  {label}
                </span>
              ))}
            </div>

            {/* Timeline strip */}
            <div
              className="relative rounded-lg border border-cream-muted overflow-hidden bg-cream-subtle/30"
              style={{ height: TIMELINE_HEIGHT }}
            >
              {/* Slot droppables — background layer */}
              <div className="absolute inset-0 flex">
                {Array.from({ length: TOTAL_SLOTS }, (_, i) => (
                  <DroppableSlot
                    key={i}
                    index={i}
                    isOver={hoverSlot === i && ghostValid}
                  />
                ))}
              </div>

              {/* Ghost preview — shows where block will land */}
              {ghostBlock && (
                <div
                  style={{
                    position: "absolute",
                    left: hoverSlot! * SLOT_WIDTH,
                    width: ghostBlock.slots * SLOT_WIDTH,
                    height: TIMELINE_HEIGHT,
                    top: 0,
                    zIndex: 5,
                    pointerEvents: "none",
                  }}
                  className={`rounded border-2 border-dashed transition-colors ${
                    ghostValid
                      ? `${ghostBlock.bgClass} ${ghostBlock.borderClass} opacity-40`
                      : "bg-red-100 border-red-300 opacity-50"
                  }`}
                />
              )}

              {/* Placed blocks — foreground layer */}
              {Array.from(placed.entries()).map(([blockId, startSlot]) => (
                <DraggableTimelineBlock
                  key={blockId}
                  id={blockId}
                  startSlot={startSlot}
                  isBeingDragged={activeId === blockId}
                />
              ))}
            </div>

            {/* Tick marks below timeline */}
            <div className="relative mt-0.5" style={{ height: 6 }}>
              {TIME_LABELS.map(({ slot }) => (
                <div
                  key={slot}
                  style={{
                    position: "absolute",
                    left: slot * SLOT_WIDTH - 0.5,
                    width: 1,
                    height: 6,
                    top: 0,
                  }}
                  className="bg-cream-muted"
                />
              ))}
            </div>
          </div>
        </div>

        {/* Block tray */}
        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-wider text-ink-tertiary">
            {unplacedBlocks.length > 0
              ? `${unplacedBlocks.length} block${unplacedBlocks.length === 1 ? "" : "s"} available — drag onto the timeline`
              : "All blocks placed ✓"}
          </p>
          <div className="flex flex-wrap gap-2">
            {unplacedBlocks.map((block) => (
              <DraggableTrayBlock key={block.id} id={block.id} />
            ))}
            {unplacedBlocks.length === 0 && (
              <p className="text-xs text-ink-tertiary italic">
                Drag a block off the timeline to return it here.
              </p>
            )}
          </div>
        </div>

        {/* Drag overlay — compact card floats at cursor */}
        <DragOverlay dropAnimation={null}>
          {activeId ? <OverlayBlock id={activeId} /> : null}
        </DragOverlay>
      </DndContext>

      {/* Submit */}
      <button
        type="button"
        onClick={() => onComplete(orderedBlocks)}
        disabled={!canConfirm}
        className={`w-full font-semibold py-3.5 rounded transition-colors text-sm ${
          canConfirm
            ? "bg-forest-dark text-white hover:bg-forest-mid"
            : "bg-cream-muted text-ink-tertiary cursor-not-allowed"
        }`}
      >
        {canConfirm
          ? "That's my evening →"
          : `${REQUIRED_SLOTS - filledSlots} more slot${REQUIRED_SLOTS - filledSlots === 1 ? "" : "s"} needed to continue`}
      </button>
    </div>
  );
}
