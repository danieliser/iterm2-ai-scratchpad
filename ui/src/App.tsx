import { useCallback, useEffect } from "react";
import { useNotes } from "./hooks/useNotes";
import { useSSE } from "./hooks/useSSE";
import { useToast } from "./hooks/useToast";
import { useTaskWatcher } from "./hooks/useTaskWatcher";
import { Header } from "./components/Header";
import { FilterBar } from "./components/FilterBar";
import { NoteList } from "./components/NoteList";
import { TodoBoard } from "./components/TodoBoard";
import { ToastContainer } from "./components/ToastContainer";
import type { Note } from "./types";

export default function App() {
  const {
    notes,
    allNotes,
    sources,
    pinnedIds,
    activeFilter,
    setActiveFilter,
    addNote,
    clearNotes,
    togglePin,
    reload,
  } = useNotes();

  const { toasts, showToast } = useToast();
  const { sessions, teams, reload: reloadTodos } = useTaskWatcher();

  const onNoteAdded = useCallback(
    (note: Note) => {
      addNote(note);
      const preview =
        (note.text || "").slice(0, 60) +
        ((note.text || "").length > 60 ? "..." : "");
      const src = (note.source || "unknown").toUpperCase();
      const type = /error|fail|exception/i.test(note.text || "")
        ? "error"
        : /warn|caution/i.test(note.text || "")
          ? "warning"
          : ("" as const);
      showToast(`${src}: ${preview}`, type);
    },
    [addNote, showToast],
  );

  const connected = useSSE({
    onNoteAdded,
    onNotesCleared: useCallback(() => reload(), [reload]),
    onNotesUpdated: useCallback(() => reload(), [reload]),
    onSessionChanged: useCallback(() => reload(), [reload]),
    onTodosUpdated: useCallback(() => reloadTodos(), [reloadTodos]),
  });

  // Refresh relative timestamps every 30s
  useEffect(() => {
    if (allNotes.length === 0) return;
    const id = setInterval(() => reload(), 30000);
    return () => clearInterval(id);
  }, [allNotes.length, reload]);

  const handleClear = async () => {
    if (!confirm("Clear all notes?")) return;
    await clearNotes();
  };

  const emptyMessage =
    allNotes.length === 0
      ? "No notes yet. AI agents will post here."
      : `No notes from "${activeFilter}"`;

  return (
    <>
      <ToastContainer toasts={toasts} />
      <Header connected={connected} onClear={handleClear} />
      <TodoBoard sessions={sessions} teams={teams} />
      <FilterBar
        sources={sources}
        active={activeFilter}
        onSelect={setActiveFilter}
      />
      <NoteList
        notes={notes}
        pinnedIds={pinnedIds}
        onTogglePin={togglePin}
        emptyMessage={emptyMessage}
      />
    </>
  );
}
