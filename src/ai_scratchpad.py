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
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

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
# Storage
# ---------------------------------------------------------------------------
NOTES_DIR = Path.home() / ".config" / "iterm2" / "notes" / "by-session"
DEFAULT_SESSION = "default"


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

    note = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "text": text,
        "source": body.get("source", "unknown"),
        "metadata": body.get("metadata", {}),
    }

    notes = load_notes()
    notes.append(note)
    save_notes(notes)
    log.info("Note added id=%s source=%s", note["id"], note["source"])

    await broadcast("note_added", note)

    return cors(web.Response(
        status=201,
        content_type="application/json",
        text=json.dumps({"status": "ok", "id": note["id"], "timestamp": note["timestamp"]}),
    ))


async def handle_get_notes(request: web.Request) -> web.Response:
    notes = load_notes()
    return cors(web.Response(
        content_type="application/json",
        text=json.dumps({"notes": notes, "session_id": DEFAULT_SESSION, "count": len(notes)}),
    ))


async def handle_delete_notes(request: web.Request) -> web.Response:
    notes = load_notes()
    cleared = len(notes)
    save_notes([])
    log.info("All notes cleared (count=%d)", cleared)
    await broadcast("notes_cleared", {})
    return cors(web.Response(
        content_type="application/json",
        text=json.dumps({"status": "ok", "cleared": cleared}),
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
# Watchdog file monitor
# Debounced FSEvents watcher: broadcasts SSE when notes files change on disk
# (supports direct file-append ingestion path, not just HTTP POST).
# ---------------------------------------------------------------------------
_debounce_timers: dict = {}
_loop: asyncio.AbstractEventLoop | None = None


class _NoteFileHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.is_directory:
            return
        path = event.src_path
        if not path.endswith(".json"):
            return
        self._debounce(path)

    def on_created(self, event):
        self.on_modified(event)

    def _debounce(self, path: str) -> None:
        if path in _debounce_timers:
            _debounce_timers[path].cancel()
        timer = threading.Timer(0.15, self._fire, args=(path,))
        _debounce_timers[path] = timer
        timer.start()

    def _fire(self, path: str) -> None:
        _debounce_timers.pop(path, None)
        if _loop is None:
            return
        asyncio.run_coroutine_threadsafe(
            broadcast("notes_updated", {"path": path}),
            _loop,
        )


def start_watchdog() -> Observer:
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    observer = Observer()
    observer.schedule(_NoteFileHandler(), str(NOTES_DIR), recursive=False)
    observer.start()
    log.info("Watchdog monitoring %s", NOTES_DIR)
    return observer


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
    white-space: pre-wrap;
    word-break: break-word;
  }
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
  <span id="status">connecting\u2026</span>
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
    text.textContent = note.text;

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
# App factory & entry point
# ---------------------------------------------------------------------------
def build_app() -> web.Application:
    app = web.Application()
    app.router.add_route("OPTIONS", "/{path_info:.*}", handle_options)
    app.router.add_get("/", handle_get_ui)
    app.router.add_post("/api/notes", handle_post_note)
    app.router.add_get("/api/notes", handle_get_notes)
    app.router.add_delete("/api/notes", handle_delete_notes)
    app.router.add_get("/events", handle_sse)
    return app


async def _main():
    global _loop
    _loop = asyncio.get_running_loop()
    observer = start_watchdog()
    try:
        app = build_app()
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 9999)
        await site.start()
        log.info("Starting AI Scratchpad server on http://localhost:9999")
        log.info("Log file: %s", LOG_PATH)
        # Run forever
        while True:
            await asyncio.sleep(3600)
    finally:
        observer.stop()
        observer.join()


if __name__ == "__main__":
    asyncio.run(_main())
