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
    filter,
    updateFilter,
    sort,
    updateSort,
    addNote,
    clearNotes,
    togglePin,
    toggleDone,
    scope,
    updateScope,
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
    onNotesCleared: () => reload(),
    onNotesUpdated: () => reload(),
    onSessionChanged: () => reload(),
    onTodosUpdated: () => reloadTodos(),
  });

  // Refresh relative timestamps every 30s
  useEffect(() => {
    if (allNotes.length === 0) return;
    const id = setInterval(() => reload(), 30000);
    return () => clearInterval(id);
  }, [allNotes.length, reload]);

  const handleClear = async () => {
    await clearNotes();
  };

  const emptyMessage =
    allNotes.length === 0
      ? "No notes yet. AI agents will post here."
      : `No notes matching filters`;

  return (
    <>
      <ToastContainer toasts={toasts} />
      <Header connected={connected} onClear={handleClear} scope={scope} onScopeChange={updateScope} />
      <TodoBoard sessions={sessions} teams={teams} />
      <FilterBar
        sources={sources}
        activeSource={filter.source}
        onSourceChange={(source) => updateFilter({ source })}
        activeStatus={filter.status}
        onStatusChange={(status) => updateFilter({ status })}
        searchText={filter.searchText}
        onSearchChange={(searchText) => updateFilter({ searchText })}
        sortField={sort.field}
        sortOrder={sort.order}
        onSortChange={(field, order) => updateSort({ field, order })}
      />
      <NoteList
        notes={notes}
        pinnedIds={pinnedIds}
        onTogglePin={togglePin}
        onToggleDone={toggleDone}
        emptyMessage={emptyMessage}
      />
    </>
  );
}
