import { useState } from "react";
import {
  DndContext,
  DragOverlay,
  rectIntersection,
  PointerSensor,
  useSensor,
  useSensors,
  useDroppable,
  useDraggable,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";

// ---------------------------------------------------------------------------
// Card data — IDs must match focus_type/score.py Scene 2 card sets
// ---------------------------------------------------------------------------

interface CardDef {
  id: string;
  icon: string;
  source: string;
  label: string;
}

const CARDS: CardDef[] = [
  { id: "slack_teammate_question", icon: "💬", source: "Slack",    label: "Teammate asking a quick question" },
  { id: "email_newsletter",        icon: "📧", source: "Email",    label: "Non-urgent weekly newsletter" },
  { id: "calendar_meeting_invite", icon: "🗓️",  source: "Calendar", label: "Meeting invite for next week" },
  { id: "task_new_ticket",         icon: "✅", source: "Task",     label: "New ticket assigned to you (no deadline)" },
  { id: "slack_mentioned",         icon: "💬", source: "Slack",    label: "Someone @mentioned you in a thread" },
  { id: "email_client_important",  icon: "📧", source: "Email",    label: "Client follow-up marked important" },
  { id: "task_planning_doc",       icon: "✅", source: "Task",     label: "Reminder to update your planning doc" },
  { id: "slack_team_channel",      icon: "💬", source: "Slack",    label: "Team channel has 12 new messages" },
  { id: "email_system_report",     icon: "📧", source: "Email",    label: "Automated system report" },
  { id: "calendar_team_lunch",     icon: "🗓️",  source: "Calendar", label: "Optional team lunch tomorrow" },
];

type ContainerId = "unassigned" | "now" | "later" | "ignore";

interface Containers {
  unassigned: string[];
  now: string[];
  later: string[];
  ignore: string[];
}

function cardById(id: string): CardDef | undefined {
  return CARDS.find((c) => c.id === id);
}

function findContainer(cardId: string, containers: Containers): ContainerId | null {
  for (const key of Object.keys(containers) as ContainerId[]) {
    if (containers[key].includes(cardId)) return key;
  }
  return null;
}

// ---------------------------------------------------------------------------
// Draggable card — used in both the unassigned pile and inside buckets
// ---------------------------------------------------------------------------

function DraggableCard({
  id,
  compact = false,
}: {
  id: string;
  compact?: boolean;
}) {
  const card = cardById(id);
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({ id });
  if (!card) return null;

  return (
    <div
      ref={setNodeRef}
      {...listeners}
      {...attributes}
      className={`flex items-center gap-2.5 px-3 py-2.5 rounded-lg border bg-white cursor-grab active:cursor-grabbing select-none transition-all ${
        isDragging
          ? "opacity-25 border-forest-light"
          : "border-cream-muted shadow-sm hover:shadow-md hover:border-forest-light/50"
      }`}
    >
      <span className="text-base flex-shrink-0">{card.icon}</span>
      <div className="flex-1 min-w-0">
        <span className="text-[10px] font-bold uppercase tracking-wide text-ink-tertiary">
          {card.source}
        </span>
        <p className={`text-sm text-ink-primary leading-snug ${compact ? "truncate" : ""}`}>
          {card.label}
        </p>
      </div>
    </div>
  );
}

// Non-interactive copy that floats in the DragOverlay
function OverlayCard({ id }: { id: string }) {
  const card = cardById(id);
  if (!card) return null;
  return (
    <div className="flex items-center gap-2.5 px-3 py-2.5 rounded-lg border border-forest-light bg-white shadow-xl cursor-grabbing select-none">
      <span className="text-base flex-shrink-0">{card.icon}</span>
      <div className="flex-1 min-w-0">
        <span className="text-[10px] font-bold uppercase tracking-wide text-ink-tertiary">
          {card.source}
        </span>
        <p className="text-sm text-ink-primary leading-snug">{card.label}</p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Droppable bucket
// ---------------------------------------------------------------------------

interface BucketDef {
  id: ContainerId;
  label: string;
  borderClass: string;
  labelClass: string;
  bgClass: string;
}

const BUCKETS: BucketDef[] = [
  {
    id: "now",
    label: "NOW",
    borderClass: "border-red-300",
    labelClass: "text-red-600",
    bgClass: "bg-red-50",
  },
  {
    id: "later",
    label: "LATER",
    borderClass: "border-amber-300",
    labelClass: "text-amber-600",
    bgClass: "bg-amber-50",
  },
  {
    id: "ignore",
    label: "IGNORE",
    borderClass: "border-gray-300",
    labelClass: "text-gray-500",
    bgClass: "bg-gray-50",
  },
];

function DroppableBucket({
  id,
  label,
  borderClass,
  labelClass,
  bgClass,
  cards,
}: BucketDef & { cards: string[] }) {
  const { setNodeRef, isOver } = useDroppable({ id });

  return (
    <div
      ref={setNodeRef}
      className={`rounded-xl border-2 p-3 flex flex-col gap-2 min-h-[100px] transition-all duration-150 ${
        isOver
          ? "border-forest-dark bg-forest-pale/40 scale-[1.01]"
          : `${borderClass} ${bgClass}`
      }`}
    >
      <p className={`text-[11px] font-bold uppercase tracking-widest ${labelClass}`}>
        {label}
      </p>
      {cards.map((cardId) => (
        <DraggableCard key={cardId} id={cardId} compact />
      ))}
      {cards.length === 0 && (
        <p className="text-xs text-ink-tertiary italic text-center py-2">
          Drop cards here
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Unassigned pile (also droppable so cards can be moved back)
// ---------------------------------------------------------------------------

function UnassignedPile({ cards }: { cards: string[] }) {
  const { setNodeRef, isOver } = useDroppable({ id: "unassigned" });

  return (
    <div
      ref={setNodeRef}
      className={`flex flex-col gap-2 min-h-[48px] rounded-xl p-1 transition-all duration-150 ${
        isOver ? "bg-cream-muted/60" : ""
      }`}
    >
      {cards.map((id) => (
        <DraggableCard key={id} id={id} />
      ))}
      {cards.length === 0 && (
        <p className="text-xs text-center text-ink-tertiary italic py-3">
          All sorted ✓
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Scene 2
// ---------------------------------------------------------------------------

export interface Scene2Props {
  onComplete: (payload: { now: string[]; later: string[]; ignore: string[] }) => void;
}

export default function Scene2({ onComplete }: Scene2Props) {
  const [containers, setContainers] = useState<Containers>({
    unassigned: CARDS.map((c) => c.id),
    now: [],
    later: [],
    ignore: [],
  });
  const [activeId, setActiveId] = useState<string | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } })
  );

  const allPlaced = containers.unassigned.length === 0;

  function handleDragStart({ active }: DragStartEvent) {
    setActiveId(active.id as string);
  }

  function handleDragEnd({ active, over }: DragEndEvent) {
    setActiveId(null);
    if (!over) return;

    const cardId = active.id as string;
    const target = over.id as ContainerId;
    const source = findContainer(cardId, containers);

    if (!source || source === target) return;

    setContainers((prev) => {
      const next = { ...prev };
      next[source] = next[source].filter((id) => id !== cardId);
      next[target] = [...next[target], cardId];
      return next;
    });
  }

  return (
    <div className="space-y-6">
      {/* Scene header */}
      <div className="space-y-1.5">
        <p className="font-display text-lg font-semibold text-ink-primary">
          The Inbox Flood
        </p>
        <p className="text-sm text-ink-secondary leading-relaxed">
          Ten things just landed. Drag each card into a bucket:{" "}
          <strong className="text-ink-primary">NOW</strong>,{" "}
          <strong className="text-ink-primary">LATER</strong>, or{" "}
          <strong className="text-ink-primary">IGNORE</strong>.
        </p>
      </div>

      <DndContext
        sensors={sensors}
        collisionDetection={rectIntersection}
        onDragStart={handleDragStart}
        onDragEnd={handleDragEnd}
      >
        <div className="flex flex-col sm:flex-row gap-5">
          {/* Unassigned pile */}
          <div className="flex-1 space-y-2">
            {containers.unassigned.length > 0 && (
              <p className="text-xs font-semibold uppercase tracking-wider text-ink-tertiary">
                {containers.unassigned.length} unsorted
              </p>
            )}
            <UnassignedPile cards={containers.unassigned} />
          </div>

          {/* Divider on desktop */}
          <div className="hidden sm:block w-px bg-cream-muted self-stretch" />

          {/* Buckets */}
          <div className="flex-1 flex flex-col gap-3">
            {BUCKETS.map((b) => (
              <DroppableBucket
                key={b.id}
                {...b}
                cards={containers[b.id]}
              />
            ))}
          </div>
        </div>

        <DragOverlay dropAnimation={null}>
          {activeId ? <OverlayCard id={activeId} /> : null}
        </DragOverlay>
      </DndContext>

      {/* Submit */}
      <button
        type="button"
        onClick={() =>
          onComplete({
            now: containers.now,
            later: containers.later,
            ignore: containers.ignore,
          })
        }
        disabled={!allPlaced}
        className={`w-full font-semibold py-3.5 rounded transition-colors text-sm ${
          allPlaced
            ? "bg-forest-dark text-white hover:bg-forest-mid"
            : "bg-cream-muted text-ink-tertiary cursor-not-allowed"
        }`}
      >
        {allPlaced
          ? "See what this says about you →"
          : `Sort all ${containers.unassigned.length} remaining cards to continue`}
      </button>
    </div>
  );
}
