import type { Note, ExecResult } from "../types";

const API = import.meta.env.DEV ? "" : "";

export type NotesResponse = {
  notes: Note[];
  count: number;
  session_id: string;
};

export async function fetchNotes(
  session?: string,
  retries = 3,
): Promise<NotesResponse> {
  const url = session
    ? `${API}/api/notes?session=${encodeURIComponent(session)}`
    : `${API}/api/notes`;
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const r = await fetch(url);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      return {
        notes: data.notes ?? [],
        count: data.count ?? 0,
        session_id: data.session_id ?? "",
      };
    } catch (e) {
      console.error(`fetchNotes attempt ${attempt + 1} failed:`, e);
      if (attempt < retries) {
        await new Promise((r) => setTimeout(r, 500 * (attempt + 1)));
      }
    }
  }
  return { notes: [], count: 0, session_id: "" };
}

export async function clearAllNotes(): Promise<void> {
  try {
    const r = await fetch(`${API}/api/notes`, { method: "DELETE" });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
  } catch (e) {
    console.error("clearAllNotes failed:", e);
  }
}

export async function updateNoteStatus(
  id: string,
  status: "active" | "done",
): Promise<void> {
  try {
    const r = await fetch(`${API}/api/notes/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
  } catch (e) {
    console.error(`updateNoteStatus(${id}) failed:`, e);
  }
}

export type Prefs = {
  scope: "all" | "tab";
  filter: { source: string; status: string; searchText: string };
  sort: { field: string; order: string };
  pinned: string[];
};

export async function fetchPrefs(): Promise<Prefs> {
  try {
    const r = await fetch(`${API}/api/prefs`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  } catch (e) {
    console.error("fetchPrefs failed:", e);
    return { scope: "all", filter: { source: "all", status: "all", searchText: "" }, sort: { field: "timestamp", order: "desc" }, pinned: [] };
  }
}

export async function savePrefs(prefs: Partial<Prefs>): Promise<void> {
  try {
    await fetch(`${API}/api/prefs`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(prefs),
    });
  } catch (e) {
    console.error("savePrefs failed:", e);
  }
}

export async function execCommand(
  command: string,
  background: boolean,
  timeout = 30,
): Promise<ExecResult> {
  try {
    const r = await fetch(`${API}/api/exec`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command, background, timeout }),
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  } catch (e) {
    console.error("execCommand failed:", e);
    return { status: "completed", exit_code: 1, error: String(e) };
  }
}
