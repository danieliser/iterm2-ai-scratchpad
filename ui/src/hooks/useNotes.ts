import { useCallback, useEffect, useRef, useState } from "react";
import type { Note } from "../types";
import { fetchNotes, clearAllNotes, updateNoteStatus, fetchPrefs, savePrefs } from "../lib/api";

export type NoteScope = "all" | "tab";

export type FilterState = {
  source: string;
  searchText: string;
};

export type SortOption = {
  field: "timestamp" | "source";
  order: "asc" | "desc";
};

interface NoteWithStatus extends Note {
  status?: "active" | "done";
}

const DEFAULT_FILTER: FilterState = { source: "all", searchText: "" };
const DEFAULT_SORT: SortOption = { field: "timestamp", order: "desc" };

export function useNotes() {
  const [notes, setNotes] = useState<NoteWithStatus[]>([]);
  const [pinnedIds, setPinnedIds] = useState<string[]>([]);
  const [filter, setFilter] = useState<FilterState>(DEFAULT_FILTER);
  const [sort, setSort] = useState<SortOption>(DEFAULT_SORT);
  const [scope, setScope] = useState<NoteScope>("all");
  const [sessionId, setSessionId] = useState("");
  const [showDismissed, setShowDismissed] = useState(true);
  const prefsLoaded = useRef(false);

  // Load prefs from server on mount
  useEffect(() => {
    fetchPrefs().then((prefs) => {
      setScope((prefs.scope as NoteScope) || "all");
      setPinnedIds(prefs.pinned || []);
      if (prefs.filter) setFilter({ ...DEFAULT_FILTER, ...prefs.filter } as FilterState);
      if (prefs.sort) setSort({ ...DEFAULT_SORT, ...prefs.sort } as SortOption);
      if (prefs.showDismissed !== undefined) setShowDismissed(prefs.showDismissed);
      prefsLoaded.current = true;
    });
  }, []);

  // Debounced save to server — fire-and-forget
  const saveTimer = useRef<ReturnType<typeof setTimeout>>();
  const persistPrefs = useCallback((partial: Record<string, unknown>) => {
    clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => savePrefs(partial), 300);
  }, []);

  const updateFilter = useCallback((newFilter: Partial<FilterState>) => {
    setFilter((prev) => {
      const next = { ...prev, ...newFilter };
      persistPrefs({ filter: next });
      return next;
    });
  }, [persistPrefs]);

  const updateSort = useCallback((newSort: Partial<SortOption>) => {
    setSort((prev) => {
      const next = { ...prev, ...newSort };
      persistPrefs({ sort: next });
      return next;
    });
  }, [persistPrefs]);

  const updateScope = useCallback((s: NoteScope) => {
    setScope(s);
    persistPrefs({ scope: s });
  }, [persistPrefs]);

  const toggleShowDismissed = useCallback(() => {
    setShowDismissed((prev) => {
      const next = !prev;
      persistPrefs({ showDismissed: next });
      return next;
    });
  }, [persistPrefs]);

  const load = useCallback(async () => {
    try {
      const session = scope === "tab" ? "current" : undefined;
      const result = await fetchNotes(session);
      setNotes(result.notes);
      setSessionId(result.session_id);
    } catch (e) {
      console.error("Failed to load notes", e);
    }
  }, [scope]);

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
      persistPrefs({ pinned: next });
      return next;
    });
  }, [persistPrefs]);

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

  // Split active vs dismissed
  const activeNotes = notes.filter((n) => (n.status || "active") !== "done");
  const dismissedNotes = notes.filter((n) => n.status === "done");

  // Combine: active notes first, then dismissed if shown
  let visible = showDismissed ? [...activeNotes, ...dismissedNotes] : activeNotes;

  // Apply filters: source AND text search
  if (filter.source !== "all") {
    visible = visible.filter((n) => (n.source || "unknown") === filter.source);
  }

  if (filter.searchText) {
    const query = filter.searchText.toLowerCase();
    visible = visible.filter(
      (n) =>
        n.text.toLowerCase().includes(query) ||
        (n.source || "unknown").toLowerCase().includes(query),
    );
  }

  // Sort: pinned float to top, then by sort option
  const sorted = [...visible].sort((a, b) => {
    // Dismissed always sink to bottom (after active)
    const aDone = a.status === "done" ? 1 : 0;
    const bDone = b.status === "done" ? 1 : 0;
    if (aDone !== bDone) return aDone - bDone;

    // Pinned float to top within their group
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
    scope,
    updateScope,
    sessionId,
    addNote,
    clearNotes,
    togglePin,
    toggleDone,
    reload: load,
    showDismissed,
    toggleShowDismissed,
    dismissedCount: dismissedNotes.length,
  };
}
