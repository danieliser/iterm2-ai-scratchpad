import type { Note } from "../types";
import { NoteCard } from "./NoteCard";

interface Props {
  notes: Note[];
  pinnedIds: string[];
  onTogglePin: (id: string) => void;
  emptyMessage: string;
}

export function NoteList({ notes, pinnedIds, onTogglePin, emptyMessage }: Props) {
  if (notes.length === 0) {
    return <div className="empty">{emptyMessage}</div>;
  }

  return (
    <div className="notes-container">
      {notes.map((note) => (
        <NoteCard
          key={note.id}
          note={note}
          pinned={pinnedIds.includes(note.id)}
          onTogglePin={() => onTogglePin(note.id)}
        />
      ))}
    </div>
  );
}
