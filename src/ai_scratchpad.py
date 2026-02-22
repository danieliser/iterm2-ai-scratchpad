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
    app.router.add_get("/events", handle_sse)
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
