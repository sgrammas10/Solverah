import { useState } from "react";
import {
  DndContext,
  closestCenter,
  DragOverlay,
  type Announcements,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
  useSortable,
  arrayMove,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { DRAGGABLE_TOUCH_STYLE, useSceneSensors } from "./dragSensors";

// ---------------------------------------------------------------------------
// Card data — IDs must match focus_type/score.py _S1_CARD_SCORES keys
// ---------------------------------------------------------------------------

const CARDS = [
  { id: "big_project",       emoji: "📄", label: "Big complex project you've been putting off" },
  { id: "emails",            emoji: "📧", label: "14 unread emails" },
  { id: "teammate_feedback", emoji: "👀", label: "Teammate's draft waiting for your feedback" },
  { id: "planning_doc",      emoji: "🗓️",  label: "Planning doc that needs updating" },
  { id: "urgent_client",     emoji: "⚡", label: "One urgent client request flagged overnight" },
  { id: "admin_tasks",       emoji: "✅", label: "Three small admin tasks (5 min each)" },
] as const;

type CardId = (typeof CARDS)[number]["id"];

function cardName(id: unknown): string {
  return CARDS.find((c) => c.id === id)?.label ?? "card";
}

/** Read aloud during a drag. Positions are 1-based, as the screen shows them. */
function makeAnnouncements(order: readonly string[]): Announcements {
  const position = (id: unknown) => order.indexOf(String(id)) + 1;
  return {
    onDragStart: ({ active }) =>
      `Picked up ${cardName(active.id)}, position ${position(active.id)} of ${order.length}.`,
    onDragOver: ({ active, over }) =>
      over ? `${cardName(active.id)} is over position ${position(over.id)}.` : undefined,
    onDragEnd: ({ active, over }) =>
      over
        ? `${cardName(active.id)} dropped at position ${position(over.id)}.`
        : `${cardName(active.id)} put back.`,
    onDragCancel: ({ active }) => `Cancelled. ${cardName(active.id)} put back.`,
  };
}

// ---------------------------------------------------------------------------
// Sortable card — used inside SortableContext
// ---------------------------------------------------------------------------

function SortableCard({
  id,
  emoji,
  label,
  rank,
}: {
  id: string;
  emoji: string;
  label: string;
  rank: number;
}) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id });

  return (
    <div
      ref={setNodeRef}
      style={{
        ...DRAGGABLE_TOUCH_STYLE,
        transform: CSS.Transform.toString(transform),
        transition,
      }}
      {...attributes}
      {...listeners}
      className={`flex items-center gap-3 px-4 py-3.5 rounded-lg border bg-white cursor-grab active:cursor-grabbing select-none transition-shadow ${
        isDragging
          ? "opacity-30 border-forest-light"
          : "border-cream-muted shadow-sm hover:shadow-md hover:border-forest-light/50"
      }`}
    >
      <span className="w-5 text-center text-xs font-bold text-ink-tertiary flex-shrink-0">
        {rank}
      </span>
      <span className="text-xl flex-shrink-0">{emoji}</span>
      <span className="text-sm font-medium text-ink-primary leading-snug flex-1 min-w-0">
        {label}
      </span>
      <span className="text-ink-tertiary text-base flex-shrink-0 ml-1" aria-hidden>
        ⠿
      </span>
    </div>
  );
}

// Non-interactive copy rendered inside DragOverlay (appears to float)
function FloatingCard({ id }: { id: string }) {
  const card = CARDS.find((c) => c.id === id);
  if (!card) return null;
  return (
    <div className="flex items-center gap-3 px-4 py-3.5 rounded-lg border border-forest-light bg-white shadow-xl cursor-grabbing select-none">
      <span className="text-xl flex-shrink-0">{card.emoji}</span>
      <span className="text-sm font-medium text-ink-primary leading-snug flex-1 min-w-0">
        {card.label}
      </span>
      <span className="text-ink-tertiary text-base flex-shrink-0 ml-1" aria-hidden>
        ⠿
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Scene 1
// ---------------------------------------------------------------------------

export interface Scene1Props {
  onComplete: (payload: string[]) => void;
}

export default function Scene1({ onComplete }: Scene1Props) {
  const [order, setOrder] = useState<CardId[]>(CARDS.map((c) => c.id));
  const [hasDragged, setHasDragged] = useState(false);
  const [activeId, setActiveId] = useState<string | null>(null);

  const sensors = useSceneSensors(sortableKeyboardCoordinates);

  function handleDragStart({ active }: DragStartEvent) {
    setActiveId(active.id as string);
  }

  function handleDragEnd({ active, over }: DragEndEvent) {
    setActiveId(null);
    if (!over || active.id === over.id) return;
    setHasDragged(true);
    setOrder((prev) => {
      const oldIdx = prev.indexOf(active.id as CardId);
      const newIdx = prev.indexOf(over.id as CardId);
      return arrayMove(prev, oldIdx, newIdx);
    });
  }

  return (
    <div className="space-y-6">
      {/* Scene header */}
      <div className="space-y-1.5">
        <p className="font-display text-lg font-semibold text-ink-primary">
          The Morning Stack
        </p>
        <p className="text-sm text-ink-secondary leading-relaxed">
          It's 9am. Six things are waiting for you. Drag them into the order
          you'd actually tackle them — top to bottom.
        </p>
        <p className="text-xs text-ink-tertiary">
          On a touchscreen, press and hold a card to pick it up. With a keyboard,
          Space picks a card up, the arrow keys move it, and Space puts it down.
        </p>
      </div>

      {/* Sortable list */}
      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        accessibility={{ announcements: makeAnnouncements(order) }}
        onDragStart={handleDragStart}
        onDragEnd={handleDragEnd}
        onDragCancel={() => setActiveId(null)}
      >
        <SortableContext items={order} strategy={verticalListSortingStrategy}>
          <div className="flex flex-col gap-2">
            {order.map((id, idx) => {
              const card = CARDS.find((c) => c.id === id)!;
              return (
                <SortableCard
                  key={id}
                  id={id}
                  emoji={card.emoji}
                  label={card.label}
                  rank={idx + 1}
                />
              );
            })}
          </div>
        </SortableContext>

        <DragOverlay dropAnimation={null}>
          {activeId ? <FloatingCard id={activeId} /> : null}
        </DragOverlay>
      </DndContext>

      {/* Submit */}
      <button
        type="button"
        onClick={() => onComplete([...order])}
        disabled={!hasDragged}
        className={`w-full font-semibold py-3.5 rounded transition-colors text-sm ${
          hasDragged
            ? "bg-forest-dark text-white hover:bg-forest-mid"
            : "bg-cream-muted text-ink-tertiary cursor-not-allowed"
        }`}
      >
        {hasDragged
          ? "Lock in my priorities →"
          : "Drag the cards to set your order first"}
      </button>
    </div>
  );
}
