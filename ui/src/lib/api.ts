import type { Note, ExecResult } from "../types";

const API = import.meta.env.DEV ? "" : "";

export async function fetchNotes(): Promise<Note[]> {
  try {
    const r = await fetch(`${API}/api/notes`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json();
    return data.notes ?? [];
  } catch (e) {
    console.error("fetchNotes failed:", e);
    return [];
  }
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
