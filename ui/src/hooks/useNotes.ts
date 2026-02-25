import { useCallback, useEffect, useState } from "react";
import type { Note } from "../types";
import { fetchNotes, clearAllNotes, updateNoteStatus } from "../lib/api";

const PINNED_KEY = "scratchpad_pinned";
const FILTER_KEY = "scratchpad_filter";
const SORT_KEY = "scratchpad_sort";

export type FilterState = {
  source: string;
  status: "active" | "done" | "all";
  searchText: string;
};

export type SortOption = {
  field: "timestamp" | "source";
  order: "asc" | "desc";
};

interface NoteWithStatus extends Note {
  status?: "active" | "done";
}

function loadPinned(): string[] {
  try {
    return JSON.parse(localStorage.getItem(PINNED_KEY) || "[]");
  } catch {
    return [];
  }
}

function loadFilter(): FilterState {
  try {
    return JSON.parse(localStorage.getItem(FILTER_KEY) || "null") || {
      source: "all",
      status: "all",
      searchText: "",
    };
  } catch {
    return { source: "all", status: "all", searchText: "" };
  }
}

function loadSort(): SortOption {
  try {
    return JSON.parse(localStorage.getItem(SORT_KEY) || "null") || {
      field: "timestamp",
      order: "desc",
    };
  } catch {
    return { field: "timestamp", order: "desc" };
  }
}

export function useNotes() {
  const [notes, setNotes] = useState<NoteWithStatus[]>([]);
  const [pinnedIds, setPinnedIds] = useState<string[]>(loadPinned);
  const [filter, setFilter] = useState<FilterState>(loadFilter);
  const [sort, setSort] = useState<SortOption>(loadSort);

  const updateFilter = useCallback((newFilter: Partial<FilterState>) => {
    setFilter((prev) => {
      const next = { ...prev, ...newFilter };
      localStorage.setItem(FILTER_KEY, JSON.stringify(next));
      return next;
    });
  }, []);

  const updateSort = useCallback((newSort: Partial<SortOption>) => {
    setSort((prev) => {
      const next = { ...prev, ...newSort };
      localStorage.setItem(SORT_KEY, JSON.stringify(next));
      return next;
    });
  }, []);

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
    setNotes((prev) => [...prev, { ...note, status: "active" }]);
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

  const toggleDone = useCallback((id: string) => {
    // Optimistic update
    setNotes((prev) =>
      prev.map((n) =>
        n.id === id
          ? { ...n, status: n.status === "done" ? "active" : "done" }
          : n,
      ),
    );
    // Update backend
    const note = notes.find((n) => n.id === id);
    const newStatus = note?.status === "done" ? "active" : "done";
    updateNoteStatus(id, newStatus);
  }, [notes]);

  // Derived: unique sources for filter bar
  const sources = Array.from(new Set(notes.map((n) => n.source || "unknown")));

  // Apply filters with AND logic: source AND status AND text search
  let filtered = notes;

  if (filter.source !== "all") {
    filtered = filtered.filter((n) => (n.source || "unknown") === filter.source);
  }

  if (filter.status !== "all") {
    filtered = filtered.filter((n) => (n.status || "active") === filter.status);
  }

  if (filter.searchText) {
    const query = filter.searchText.toLowerCase();
    filtered = filtered.filter(
      (n) =>
        n.text.toLowerCase().includes(query) ||
        (n.source || "unknown").toLowerCase().includes(query),
    );
  }

  // Sort: primary by sort option, but pinned notes always float to top
  const sorted = [...filtered].sort((a, b) => {
    const ap = pinnedIds.includes(a.id) ? 1 : 0;
    const bp = pinnedIds.includes(b.id) ? 1 : 0;
    if (ap !== bp) return bp - ap;

    if (sort.field === "source") {
      const cmp = (a.source || "unknown").localeCompare(b.source || "unknown");
      return sort.order === "asc" ? cmp : -cmp;
    }

    // timestamp sort (default)
    const aCmp = new Date(a.timestamp).getTime();
    const bCmp = new Date(b.timestamp).getTime();
    const diff = aCmp - bCmp;
    return sort.order === "asc" ? diff : -diff;
  });

  return {
    notes: sorted,
    allNotes: notes,
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
    reload: load,
  };
}
