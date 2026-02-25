import type { Note, ExecResult } from "../types";

const API = import.meta.env.DEV ? "" : "";

export async function fetchNotes(): Promise<Note[]> {
  const r = await fetch(`${API}/api/notes`);
  const data = await r.json();
  return data.notes ?? [];
}

export async function clearAllNotes(): Promise<void> {
  await fetch(`${API}/api/notes`, { method: "DELETE" });
}

export async function execCommand(
  command: string,
  background: boolean,
  timeout = 30,
): Promise<ExecResult> {
  const r = await fetch(`${API}/api/exec`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ command, background, timeout }),
  });
  return r.json();
}
