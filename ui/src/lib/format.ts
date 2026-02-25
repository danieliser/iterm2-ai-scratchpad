export function formatTime(isoStr: string): string {
  const d = new Date(isoStr);
  const now = new Date();
  const diff = Math.floor((now.getTime() - d.getTime()) / 1000);
  if (diff < 5) return "just now";
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return d.toLocaleDateString();
}

export function parseDuration(dur: string): number {
  let secs = 0;
  const hm = dur.match(/(\d+)h/);
  const mm = dur.match(/(\d+)m(?!s)/);
  const sm = dur.match(/(\d+)s/);
  if (hm) secs += parseInt(hm[1]) * 3600;
  if (mm) secs += parseInt(mm[1]) * 60;
  if (sm) secs += parseInt(sm[1]);
  if (secs === 0) secs = parseInt(dur) || 60;
  return secs;
}

export function formatCountdown(secs: number): string {
  if (secs <= 0) return "EXPIRED";
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  return h > 0
    ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`
    : `${m}:${String(s).padStart(2, "0")}`;
}

export function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
