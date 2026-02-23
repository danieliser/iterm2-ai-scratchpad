#!/usr/bin/env python3
"""
iTerm2 AI Scratchpad — aiohttp server with embedded HTML UI.
Posts notes from AI agents, displays in iTerm2 Toolbelt sidebar.
"""

# Unset PYTHONPATH to avoid conflicts with system Python packages
import os
os.environ.pop("PYTHONPATH", None)

import asyncio
import json
import logging
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from aiohttp import web

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_PATH = Path.home() / "iterm2_scratchpad.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# iTerm2 integration (optional — graceful fallback when not running inside iTerm2)
# ---------------------------------------------------------------------------
try:
    import iterm2 as _iterm2
    ITERM2_AVAILABLE = True
except ImportError:
    _iterm2 = None
    ITERM2_AVAILABLE = False

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
NOTES_DIR = Path.home() / ".config" / "iterm2-scratchpad" / "notes" / "by-session"
DEFAULT_SESSION = "default"

# Active iTerm2 session UUID — updated by session monitor when running inside iTerm2
_current_session_id: str = DEFAULT_SESSION

# Server start time for uptime reporting
_start_time: datetime = datetime.now(timezone.utc)


def get_current_session_id() -> str:
    return _current_session_id


def notes_path(session_id: str = DEFAULT_SESSION) -> Path:
    return NOTES_DIR / f"{session_id}.json"


def load_notes(session_id: str = DEFAULT_SESSION) -> list:
    path = notes_path(session_id)
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        log.error("Failed to read notes from %s: %s", path, exc)
        return []


def save_notes(notes: list, session_id: str = DEFAULT_SESSION) -> None:
    path = notes_path(session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(notes, indent=2)
    # Atomic write: temp file in same directory, then rename
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".notes_tmp_")
    try:
        os.write(fd, data.encode())
        os.fsync(fd)
        os.close(fd)
        os.replace(tmp, path)
    except Exception:
        os.close(fd)
        os.unlink(tmp)
        raise


# ---------------------------------------------------------------------------
# SSE broadcast
# ---------------------------------------------------------------------------
_sse_clients: set = set()


async def broadcast(event_type: str, data: dict) -> None:
    payload = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
    dead = set()
    for resp in list(_sse_clients):
        try:
            await resp.write(payload.encode())
        except Exception:
            dead.add(resp)
    _sse_clients.difference_update(dead)


# ---------------------------------------------------------------------------
# Watchdog file monitor
# Watches NOTES_DIR for external file writes and broadcasts SSE.
# Thread-safe: _debounce_lock guards the timer dict across watchdog + timer threads.
# ---------------------------------------------------------------------------
_debounce_timers: dict = {}
_debounce_lock = threading.Lock()
_event_loop: asyncio.AbstractEventLoop | None = None


if WATCHDOG_AVAILABLE:
    class _NoteFileHandler(FileSystemEventHandler):
        def on_modified(self, event):
            path = event.src_path
            if (not event.is_directory
                    and path.endswith(".json")
                    and not os.path.basename(path).startswith(".notes_tmp_")):
                self._debounce(path)

        def on_created(self, event):
            self.on_modified(event)

        def _debounce(self, path: str) -> None:
            with _debounce_lock:
                existing = _debounce_timers.get(path)
                if existing:
                    existing.cancel()
                timer = threading.Timer(0.15, self._fire, args=(path,))
                _debounce_timers[path] = timer
            timer.start()

        def _fire(self, path: str) -> None:
            with _debounce_lock:
                _debounce_timers.pop(path, None)
            if _event_loop is not None:
                asyncio.run_coroutine_threadsafe(
                    broadcast("notes_updated", {}),
                    _event_loop,
                )


def start_watchdog() -> "Observer | None":
    if not WATCHDOG_AVAILABLE:
        log.warning("watchdog not installed — file-based SSE updates disabled")
        return None
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    observer = Observer()
    observer.schedule(_NoteFileHandler(), str(NOTES_DIR), recursive=False)
    observer.start()
    log.info("Watchdog monitoring %s", NOTES_DIR)
    return observer


# ---------------------------------------------------------------------------
# CORS helper
# ---------------------------------------------------------------------------
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}


def cors(response: web.Response) -> web.Response:
    response.headers.update(CORS_HEADERS)
    return response


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------
async def handle_options(request: web.Request) -> web.Response:
    return cors(web.Response(status=204))


async def handle_get_ui(request: web.Request) -> web.Response:
    html = build_html()
    return cors(web.Response(content_type="text/html", text=html))


async def handle_post_note(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return cors(web.Response(status=400, text="Invalid JSON"))

    text = body.get("text", "").strip()
    if not text:
        return cors(web.Response(status=400, text="text is required"))

    session_id = get_current_session_id()
    note = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "text": text,
        "source": body.get("source", "unknown"),
        "metadata": body.get("metadata", {}),
    }

    notes = load_notes(session_id)
    notes.append(note)
    save_notes(notes, session_id)
    log.info("Note added id=%s source=%s session=%s", note["id"], note["source"], session_id)

    await broadcast("note_added", note)

    return cors(web.Response(
        status=201,
        content_type="application/json",
        text=json.dumps({"status": "ok", "id": note["id"], "timestamp": note["timestamp"]}),
    ))


async def handle_get_notes(request: web.Request) -> web.Response:
    # Allow explicit session_id override via query param
    session_id = request.rel_url.query.get("session_id") or get_current_session_id()
    notes = load_notes(session_id)
    return cors(web.Response(
        content_type="application/json",
        text=json.dumps({"notes": notes, "session_id": session_id, "count": len(notes)}),
    ))


async def handle_delete_notes(request: web.Request) -> web.Response:
    session_id = get_current_session_id()
    notes = load_notes(session_id)
    cleared = len(notes)
    save_notes([], session_id)
    log.info("All notes cleared session=%s count=%d", session_id, cleared)
    await broadcast("notes_cleared", {})
    return cors(web.Response(
        content_type="application/json",
        text=json.dumps({"status": "ok", "cleared": cleared}),
    ))


async def handle_get_session(request: web.Request) -> web.Response:
    return cors(web.Response(
        content_type="application/json",
        text=json.dumps({"session_id": get_current_session_id()}),
    ))


async def _handle_favicon(_request: web.Request) -> web.Response:
    return web.Response(status=204)


async def handle_health(request: web.Request) -> web.Response:
    uptime = (datetime.now(timezone.utc) - _start_time).total_seconds()
    return cors(web.Response(
        content_type="application/json",
        text=json.dumps({
            "status": "ok",
            "uptime_seconds": int(uptime),
            "notes_dir": str(NOTES_DIR),
            "session_id": get_current_session_id(),
            "watchdog": WATCHDOG_AVAILABLE,
            "iterm2": ITERM2_AVAILABLE,
        }),
    ))


async def handle_sse(request: web.Request) -> web.StreamResponse:
    resp = web.StreamResponse(headers={
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        **CORS_HEADERS,
    })
    await resp.prepare(request)
    _sse_clients.add(resp)
    log.info("SSE client connected (total=%d)", len(_sse_clients))

    # Send a keepalive comment so the client knows we're live
    await resp.write(b": connected\n\n")

    try:
        while not request.transport.is_closing():
            await asyncio.sleep(15)
            await resp.write(b": keepalive\n\n")
    except (asyncio.CancelledError, ConnectionResetError):
        pass
    finally:
        _sse_clients.discard(resp)
        log.info("SSE client disconnected (total=%d)", len(_sse_clients))

    return resp


# ---------------------------------------------------------------------------
# Embedded HTML UI
# ---------------------------------------------------------------------------
def build_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI Scratchpad</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    font-size: 12px;
    background: #1e1e1e;
    color: #d4d4d4;
    display: flex;
    flex-direction: column;
    height: 100vh;
    overflow: hidden;
  }
  #header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 10px;
    background: #252526;
    border-bottom: 1px solid #3c3c3c;
    flex-shrink: 0;
  }
  #header h1 {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: #9cdcfe;
  }
  #status {
    font-size: 10px;
    color: #6a9955;
  }
  #status.disconnected { color: #f44747; }
  #clear-btn, .copy-btn {
    background: none;
    border: 1px solid #555;
    color: #ccc;
    padding: 2px 8px;
    border-radius: 3px;
    cursor: pointer;
    font-size: 10px;
  }
  #clear-btn:hover, .copy-btn:hover { background: #3c3c3c; }
  .copy-btn { margin-top: 6px; }
  #notes {
    flex: 1;
    overflow-y: auto;
    padding: 6px;
  }
  .note {
    background: #2d2d2d;
    border: 1px solid #3c3c3c;
    border-radius: 4px;
    padding: 8px 10px;
    margin-bottom: 6px;
    animation: fadeIn 0.2s ease;
  }
  @keyframes fadeIn { from { opacity: 0; transform: translateY(-4px); } to { opacity: 1; } }
  .note-meta {
    display: flex;
    justify-content: space-between;
    margin-bottom: 4px;
  }
  .note-source {
    font-size: 10px;
    color: #569cd6;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .note-time {
    font-size: 10px;
    color: #808080;
  }
  .note-text {
    color: #d4d4d4;
    line-height: 1.5;
    word-break: break-word;
  }
  .note-text code {
    background: #1e1e1e;
    padding: 1px 4px;
    border-radius: 3px;
    font-family: "SF Mono", Menlo, monospace;
    font-size: 11px;
    color: #ce9178;
  }
  .note-text pre {
    background: #1e1e1e;
    padding: 6px 8px;
    border-radius: 4px;
    margin: 4px 0;
    overflow-x: auto;
    font-family: "SF Mono", Menlo, monospace;
    font-size: 11px;
    line-height: 1.4;
    color: #d4d4d4;
    white-space: pre;
  }
  .note-text strong { color: #dcdcaa; font-weight: 600; }
  .note-text em { color: #9cdcfe; font-style: italic; }
  .note-text ul, .note-text ol {
    margin: 4px 0 4px 18px;
    padding: 0;
  }
  .note-text li { margin: 2px 0; }
  .note-text p { margin: 3px 0; }
  .note-text hr {
    border: none;
    border-top: 1px solid #3c3c3c;
    margin: 6px 0;
  }
  .note-text h3 {
    font-size: 11px;
    color: #9cdcfe;
    font-weight: 600;
    margin: 6px 0 3px;
    text-transform: uppercase;
    letter-spacing: 0.03em;
  }
  /* Progress bars */
  .widget-progress { display: flex; align-items: center; gap: 8px; margin: 4px 0; }
  .widget-progress-bar { flex: 1; height: 6px; background: #1e1e1e; border-radius: 3px; overflow: hidden; }
  .widget-progress-fill { height: 100%; border-radius: 3px; transition: width 0.3s ease; }
  .widget-progress-label { font-size: 10px; color: #808080; min-width: 32px; text-align: right; }
  /* Status badges */
  .widget-badge { display: inline-block; padding: 1px 8px; border-radius: 9px; font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; margin: 0 2px; }
  .widget-badge-success { background: #1a3a1a; color: #4ec94e; border: 1px solid #2d5a2d; }
  .widget-badge-warning { background: #3a3520; color: #e0c040; border: 1px solid #5a5030; }
  .widget-badge-error   { background: #3a1a1a; color: #f44747; border: 1px solid #5a2d2d; }
  .widget-badge-info    { background: #1a2a3a; color: #569cd6; border: 1px solid #2d4a5a; }
  /* Collapsible details */
  .widget-details { margin: 4px 0; border: 1px solid #3c3c3c; border-radius: 4px; overflow: hidden; }
  .widget-details-toggle { display: flex; align-items: center; gap: 6px; padding: 4px 8px; background: #1e1e1e; cursor: pointer; font-size: 11px; color: #d4d4d4; user-select: none; width: 100%; border: none; text-align: left; }
  .widget-details-toggle:hover { background: #252525; }
  .widget-details-arrow { font-size: 8px; transition: transform 0.2s; color: #808080; }
  .widget-details.open .widget-details-arrow { transform: rotate(90deg); }
  .widget-details-body { padding: 6px 8px; display: none; border-top: 1px solid #3c3c3c; font-size: 11px; }
  .widget-details.open .widget-details-body { display: block; }
  /* Tables */
  .widget-table { width: 100%; border-collapse: collapse; margin: 4px 0; font-size: 11px; }
  .widget-table th { text-align: left; padding: 3px 8px; border-bottom: 1px solid #569cd6; color: #9cdcfe; font-weight: 600; }
  .widget-table td { padding: 3px 8px; border-bottom: 1px solid #2a2a2a; }
  .widget-table tr:hover td { background: #1e1e1e; }
  /* Sparkline charts */
  .widget-chart { display: flex; align-items: flex-end; gap: 2px; margin: 4px 0; padding: 4px; background: #1e1e1e; border-radius: 4px; height: 48px; }
  .widget-chart-bar { flex: 1; min-width: 4px; border-radius: 2px 2px 0 0; transition: height 0.3s ease; position: relative; }
  .widget-chart-bar:hover { opacity: 0.8; }
  .widget-chart-bar:hover::after { content: attr(data-val); position: absolute; top: -16px; left: 50%; transform: translateX(-50%); font-size: 9px; color: #d4d4d4; background: #333; padding: 1px 4px; border-radius: 2px; white-space: nowrap; }
  .widget-chart-label { display: flex; justify-content: space-between; font-size: 9px; color: #808080; margin-top: 2px; }
  #empty {
    color: #555;
    text-align: center;
    padding: 40px 20px;
    font-size: 11px;
  }
</style>
</head>
<body>
<div id="header">
  <h1>AI Scratchpad</h1>
  <span id="status">connecting…</span>
  <button id="clear-btn" onclick="clearNotes()">Clear All</button>
</div>
<div id="notes"></div>

<script>
const API = 'http://localhost:9999';
let notes = [];

function formatTime(isoStr) {
  const d = new Date(isoStr);
  const now = new Date();
  const diff = Math.floor((now - d) / 1000);
  if (diff < 5)  return 'just now';
  if (diff < 60) return diff + 's ago';
  if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
  if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
  return d.toLocaleDateString();
}

// Minimal markdown renderer — escapes HTML first, then applies formatting
function esc(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function renderMarkdown(raw) {
  let s = esc(raw);
  // Widgets — process before markdown so bracket syntax survives escaping
  s = renderWidgets(s);
  // Code blocks (``` ... ```)
  s = s.replace(/```([\\s\\S]*?)```/g, (_, code) => '<pre>' + code.trim() + '</pre>');
  // Inline code
  s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
  // Bold
  s = s.replace(/[*][*](.+?)[*][*]/g, '<strong>$1</strong>');
  // Italic
  s = s.replace(/[*](.+?)[*]/g, '<em>$1</em>');
  // Headers (### only)
  s = s.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  // Horizontal rule
  s = s.replace(/^---$/gm, '<hr>');
  // Unordered lists
  s = s.replace(/^- (.+)$/gm, '<li>$1</li>');
  s = s.replace(/(<li>.*<\\/li>\\n?)+/g, m => '<ul>' + m + '</ul>');
  // Markdown tables: |col|col|col|
  s = s.replace(/(^[|].+[|]$\\n?)+/gm, function(block) {
    const rows = block.trim().split('\\n').filter(r => r.trim());
    if (rows.length < 2) return block;
    const sep = rows[1];
    if (!sep.match(/^[|][\\s-:|]+[|]$/)) return block;
    const parseRow = r => r.split('|').slice(1, -1).map(c => c.trim());
    const headers = parseRow(rows[0]);
    let html = '<table class="widget-table"><thead><tr>' + headers.map(h => '<th>' + h + '</th>').join('') + '</tr></thead><tbody>';
    for (let i = 2; i < rows.length; i++) {
      const cells = parseRow(rows[i]);
      html += '<tr>' + cells.map(c => '<td>' + c + '</td>').join('') + '</tr>';
    }
    return html + '</tbody></table>';
  });
  // Paragraphs (double newline)
  s = s.replace(/\\n\\n/g, '</p><p>');
  s = '<p>' + s + '</p>';
  // Single newlines to <br> (but not inside pre/ul/table)
  s = s.replace(/([^>])\\n([^<])/g, '$1<br>$2');
  // Clean up empty paragraphs
  s = s.replace(/<p>\\s*<\\/p>/g, '');
  return s;
}

let _widgetId = 0;
function renderWidgets(s) {
  // Progress bars: [progress:75] or [progress:75:Building...]
  s = s.replace(/\\[progress:(\\d+)(?::([^\\]]*))?\\]/g, function(_, val, label) {
    const v = Math.min(100, Math.max(0, parseInt(val)));
    const color = v >= 80 ? '#4ec94e' : v >= 50 ? '#e0c040' : v >= 25 ? '#569cd6' : '#f44747';
    const lbl = label || '';
    return '<div class="widget-progress">' +
      (lbl ? '<span style="font-size:10px;color:#d4d4d4">' + lbl + '</span>' : '') +
      '<div class="widget-progress-bar"><div class="widget-progress-fill" style="width:' + v + '%;background:' + color + '"></div></div>' +
      '<span class="widget-progress-label">' + v + '%</span></div>';
  });
  // Status badges: [status:success], [status:error:Deploy failed]
  s = s.replace(/\\[status:(success|warning|error|info)(?::([^\\]]*))?\\]/g, function(_, type, label) {
    const text = label || type;
    return '<span class="widget-badge widget-badge-' + type + '">' + text + '</span>';
  });
  // Sparkline charts: [chart:10,45,30,80,60] or [chart:10,45,30:Requests/s]
  s = s.replace(/\\[chart:([\\d,]+)(?::([^\\]]*))?\\]/g, function(_, data, label) {
    const vals = data.split(',').map(Number);
    const max = Math.max(...vals);
    const id = 'chart-' + (++_widgetId);
    const colors = ['#569cd6', '#4ec94e', '#e0c040', '#c586c0', '#ce9178', '#9cdcfe'];
    let bars = '';
    vals.forEach((v, i) => {
      const h = max > 0 ? Math.round((v / max) * 36) : 0;
      const c = colors[i % colors.length];
      bars += '<div class="widget-chart-bar" style="height:' + h + 'px;background:' + c + '" data-val="' + v + '"></div>';
    });
    let html = '<div class="widget-chart" id="' + id + '">' + bars + '</div>';
    if (label) html += '<div class="widget-chart-label"><span>' + label + '</span></div>';
    return html;
  });
  // Collapsible details: [details:Title]content[/details]
  s = s.replace(/\\[details:([^\\]]+)\\]([\\s\\S]*?)\\[\\/details\\]/g, function(_, title, body) {
    const id = 'details-' + (++_widgetId);
    return '<div class="widget-details" id="' + id + '">' +
      '<button class="widget-details-toggle" onclick="this.parentElement.classList.toggle(&quot;open&quot;)">' +
      '<span class="widget-details-arrow">&#9654;</span>' + title + '</button>' +
      '<div class="widget-details-body">' + body.trim() + '</div></div>';
  });
  return s;
}

function renderNotes() {
  const container = document.getElementById('notes');
  // Safe DOM clearing — no untrusted content involved
  while (container.firstChild) container.removeChild(container.firstChild);

  if (notes.length === 0) {
    const empty = document.createElement('div');
    empty.id = 'empty';
    empty.textContent = 'No notes yet. AI agents will post here.';
    container.appendChild(empty);
    return;
  }

  // Reverse-chronological: newest first
  const sorted = [...notes].sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
  sorted.forEach(note => {
    const div = document.createElement('div');
    div.className = 'note';

    const meta = document.createElement('div');
    meta.className = 'note-meta';

    const src = document.createElement('span');
    src.className = 'note-source';
    src.textContent = note.source || 'unknown';

    const time = document.createElement('span');
    time.className = 'note-time';
    time.title = note.timestamp;
    time.textContent = formatTime(note.timestamp);

    meta.appendChild(src);
    meta.appendChild(time);

    const text = document.createElement('div');
    text.className = 'note-text';
    // Safe: renderMarkdown() escapes all HTML before applying formatting
    text.innerHTML = renderMarkdown(note.text);

    const copyBtn = document.createElement('button');
    copyBtn.className = 'copy-btn';
    copyBtn.textContent = 'Copy';
    copyBtn.addEventListener('click', () => {
      navigator.clipboard.writeText(note.text).then(() => {
        copyBtn.textContent = 'Copied!';
        setTimeout(() => { copyBtn.textContent = 'Copy'; }, 1500);
      });
    });

    div.appendChild(meta);
    div.appendChild(text);
    div.appendChild(copyBtn);
    container.appendChild(div);
  });
}

async function loadNotes() {
  try {
    const r = await fetch(API + '/api/notes');
    const data = await r.json();
    notes = data.notes || [];
    renderNotes();
  } catch (e) {
    console.error('Failed to load notes', e);
  }
}

async function clearNotes() {
  if (!confirm('Clear all notes?')) return;
  try {
    await fetch(API + '/api/notes', { method: 'DELETE' });
    notes = [];
    renderNotes();
  } catch (e) {
    console.error('Failed to clear notes', e);
  }
}

function connectSSE() {
  const es = new EventSource(API + '/events');
  const status = document.getElementById('status');

  es.addEventListener('open', () => {
    status.textContent = 'live';
    status.className = '';
  });

  es.addEventListener('note_added', e => {
    const note = JSON.parse(e.data);
    notes.push(note);
    renderNotes();
  });

  es.addEventListener('notes_cleared', () => {
    notes = [];
    renderNotes();
  });

  es.addEventListener('notes_updated', () => loadNotes());

  es.addEventListener('session_changed', () => loadNotes());

  es.onerror = () => {
    status.textContent = 'disconnected';
    status.className = 'disconnected';
    es.close();
    setTimeout(connectSSE, 3000);
  };
}

// Refresh relative timestamps every 30s
setInterval(() => {
  if (notes.length > 0) renderNotes();
}, 30000);

loadNotes();
connectSSE();
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------
def build_app() -> web.Application:
    app = web.Application()
    app.router.add_route("OPTIONS", "/{path_info:.*}", handle_options)
    app.router.add_get("/", handle_get_ui)
    app.router.add_post("/api/notes", handle_post_note)
    app.router.add_get("/api/notes", handle_get_notes)
    app.router.add_delete("/api/notes", handle_delete_notes)
    app.router.add_get("/api/session", handle_get_session)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/events", handle_sse)
    app.router.add_get("/favicon.ico", _handle_favicon)
    return app


# ---------------------------------------------------------------------------
# iTerm2 session monitor
# Tracks the active session UUID and updates _current_session_id whenever
# the user switches tabs or creates new sessions.
# ---------------------------------------------------------------------------
async def _session_monitor(connection) -> None:
    """Watch iTerm2 layout changes and keep _current_session_id current."""
    global _current_session_id

    try:
        app = await _iterm2.async_get_app(connection)
    except Exception as exc:
        log.error("Failed to get iTerm2 app — session awareness disabled: %s", exc)
        return

    def _pick_active_session():
        """Return the UUID of the frontmost session, or DEFAULT_SESSION."""
        try:
            window = app.current_window
            if window is None:
                return DEFAULT_SESSION
            tab = window.current_tab
            if tab is None:
                return DEFAULT_SESSION
            session = tab.current_session
            if session is None:
                return DEFAULT_SESSION
            return session.session_id or DEFAULT_SESSION
        except Exception as exc:
            log.warning("Session detection error: %s", exc)
            return DEFAULT_SESSION

    try:
        _current_session_id = _pick_active_session()
        log.info("Initial session_id=%s", _current_session_id)
    except Exception as exc:
        log.error("Failed to set initial session: %s", exc)

    async with _iterm2.LayoutChangeMonitor(connection) as monitor:
        while True:
            try:
                await monitor.async_get()
                new_id = _pick_active_session()
                if new_id != _current_session_id:
                    log.info("Session changed: %s -> %s", _current_session_id, new_id)
                    _current_session_id = new_id
                    await broadcast("session_changed", {"session_id": new_id})
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.error("Session monitor error (continuing): %s", exc)


# ---------------------------------------------------------------------------
# Entry points — dual-mode: iTerm2 AutoLaunch or standalone
# ---------------------------------------------------------------------------
async def _run_server() -> web.AppRunner:
    """Start the aiohttp server; returns runner so caller can cleanup()."""
    global _event_loop
    _event_loop = asyncio.get_running_loop()
    app = build_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 9999)
    await site.start()
    log.info("Server running on http://localhost:9999 (session=%s)", get_current_session_id())
    return runner


async def _iterm2_main(connection) -> None:
    """iTerm2 AutoLaunch entry point: register toolbelt panel + session monitor."""
    # Register the webview toolbelt panel (positional args per iTerm2 tool API)
    await _iterm2.tool.async_register_web_view_tool(
        connection,
        "AI Scratchpad",
        "com.danieliser.ai-scratchpad",
        True,
        "http://localhost:9999/",
    )
    log.info("Registered iTerm2 Toolbelt webview panel")

    # Start aiohttp server + watchdog, then run session monitor
    runner = await _run_server()
    observer = start_watchdog()
    try:
        await _session_monitor(connection)
    finally:
        if observer:
            observer.stop()
            observer.join()
        await runner.cleanup()


if __name__ == "__main__":
    log.info("Starting AI Scratchpad (iterm2=%s, watchdog=%s)", ITERM2_AVAILABLE, WATCHDOG_AVAILABLE)
    log.info("Log file: %s", LOG_PATH)

    if ITERM2_AVAILABLE:
        # Running as iTerm2 AutoLaunch Full Environment script
        _iterm2.run_forever(_iterm2_main)
    else:
        # Standalone mode — no iTerm2 API, use default session
        async def _standalone_main():
            runner = await _run_server()
            observer = start_watchdog()
            try:
                while True:
                    await asyncio.sleep(3600)
            finally:
                if observer:
                    observer.stop()
                    observer.join()
                await runner.cleanup()

        asyncio.run(_standalone_main())
