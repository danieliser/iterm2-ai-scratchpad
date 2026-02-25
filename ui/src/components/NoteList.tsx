import { AnimatePresence, LayoutGroup } from "motion/react";
import type { Note } from "../types";
import { NoteCard } from "./NoteCard";

interface NoteWithStatus extends Note {
  status?: "active" | "done";
}

interface Props {
  notes: NoteWithStatus[];
  pinnedIds: string[];
  onTogglePin: (id: string) => void;
  onToggleDone?: (id: string) => void;
  emptyMessage: string;
  dismissedCount: number;
  showDismissed: boolean;
  onToggleShowDismissed: () => void;
}

export function NoteList({
  notes,
  pinnedIds,
  onTogglePin,
  onToggleDone,
  emptyMessage,
  dismissedCount,
  showDismissed,
  onToggleShowDismissed,
}: Props) {
  if (notes.length === 0 && dismissedCount === 0) {
    return <div className="empty">{emptyMessage}</div>;
  }

  return (
    <div className="notes-container">
      <LayoutGroup>
        <AnimatePresence mode="popLayout">
          {notes.length === 0 && dismissedCount > 0 ? (
            <div className="empty" key="__empty">No active notes</div>
          ) : (
            notes.map((note) => (
              <NoteCard
                key={note.id}
                note={note}
                pinned={pinnedIds.includes(note.id)}
                onTogglePin={() => onTogglePin(note.id)}
                onToggleDone={onToggleDone ? () => onToggleDone(note.id) : undefined}
              />
            ))
          )}
        </AnimatePresence>
      </LayoutGroup>
      {dismissedCount > 0 && (
        <button
          className="dismissed-toggle"
          onClick={onToggleShowDismissed}
        >
          {showDismissed
            ? `Hide ${dismissedCount} dismissed`
            : `Show ${dismissedCount} dismissed`}
        </button>
      )}
    </div>
  );
}
