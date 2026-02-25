import { useCallback, useEffect, useState } from "react";
import type { Note } from "../types";
import { fetchNotes, clearAllNotes } from "../lib/api";

const PINNED_KEY = "scratchpad_pinned";

function loadPinned(): string[] {
  try {
    return JSON.parse(localStorage.getItem(PINNED_KEY) || "[]");
  } catch {
    return [];
  }
}

export function useNotes() {
  const [notes, setNotes] = useState<Note[]>([]);
  const [pinnedIds, setPinnedIds] = useState<string[]>(loadPinned);
  const [activeFilter, setActiveFilter] = useState("all");

  const load = useCallback(async () => {
    try {
      const loaded = await fetchNotes();
      setNotes(loaded);
    } catch (e) {
      console.error("Failed to load notes", e);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const addNote = useCallback((note: Note) => {
    setNotes((prev) => [...prev, note]);
  }, []);

  const clearNotes = useCallback(async () => {
    await clearAllNotes();
    setNotes([]);
  }, []);

  const togglePin = useCallback((id: string) => {
    setPinnedIds((prev) => {
      const next = prev.includes(id)
        ? prev.filter((p) => p !== id)
        : [...prev, id];
      localStorage.setItem(PINNED_KEY, JSON.stringify(next));
      return next;
    });
  }, []);

  // Derived: unique sources for filter bar
  const sources = Array.from(new Set(notes.map((n) => n.source || "unknown")));

  // Derived: filtered + sorted notes
  const filtered =
    activeFilter === "all"
      ? notes
      : notes.filter((n) => (n.source || "unknown") === activeFilter);

  const sorted = [...filtered].sort((a, b) => {
    const ap = pinnedIds.includes(a.id) ? 1 : 0;
    const bp = pinnedIds.includes(b.id) ? 1 : 0;
    if (ap !== bp) return bp - ap;
    return new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime();
  });

  return {
    notes: sorted,
    allNotes: notes,
    sources,
    pinnedIds,
    activeFilter,
    setActiveFilter,
    addNote,
    clearNotes,
    togglePin,
    reload: load,
  };
}
