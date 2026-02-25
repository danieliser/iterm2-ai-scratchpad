#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["aiohttp>=3.9"]
# [tool.uv.sources]
# ///
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
import re
import shlex
import tempfile
import threading
import time as _time
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
CLAUDE_TODOS_DIR = Path.home() / ".claude" / "todos"
CLAUDE_TASKS_DIR = Path.home() / ".claude" / "tasks"
CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"
SUMMARY_CACHE_PATH = Path.home() / ".config" / "iterm2-scratchpad" / "session-summaries.json"
DEFAULT_SESSION = "default"

# Session summary cache — maps session UUID prefix to first user message
_summary_cache: dict = {}
_summary_cache_loaded = False


def _load_summary_cache() -> dict:
    global _summary_cache, _summary_cache_loaded
    if _summary_cache_loaded:
        return _summary_cache
    _summary_cache_loaded = True
    if SUMMARY_CACHE_PATH.exists():
        try:
            _summary_cache = json.loads(SUMMARY_CACHE_PATH.read_text())
        except Exception:
            _summary_cache = {}
    return _summary_cache


def _save_summary_cache() -> None:
    SUMMARY_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(_summary_cache, indent=2)
    fd, tmp = tempfile.mkstemp(dir=SUMMARY_CACHE_PATH.parent, prefix=".cache_tmp_")
    try:
        os.write(fd, data.encode())
        os.fsync(fd)
        os.close(fd)
        os.replace(tmp, SUMMARY_CACHE_PATH)
    except Exception:
        os.close(fd)
        os.unlink(tmp)
        raise


def _extract_command_name(content: str) -> str:
    """Extract slash command + args from a command-message user turn."""
    import re
    m = re.search(r"<command-name>/?([^<]+)</command-name>", content)
    if not m:
        return ""
    cmd = m.group(1).strip()
    args_m = re.search(r"<command-args>([^<]*)</command-args>", content)
    args = args_m.group(1).strip() if args_m else ""
    return f"/{cmd} {args}".strip()[:100] if args else f"/{cmd}"[:100]


def _is_system_content(content: str) -> bool:
    """Detect system-injected user messages (skill prompts, agent context)."""
    stripped = content.lstrip()
    # Command messages have XML tags
    if stripped.startswith("<command-message>"):
        return True
    # Skill/agent preambles
    if stripped.startswith(("Base directory", "You are ")):
        return True
    # Agent context blocks (markdown headers followed by agent instructions)
    if "Your name is **" in content[:200] or "you are executing tasks" in content[:300].lower():
        return True
    # Empty messages (approval/continue)
    if not stripped:
        return True
    return False


def _extract_first_user_message(jsonl_path: Path) -> str:
    """Read a JSONL transcript and return a human-readable summary."""
    try:
        user_count = 0
        command_name = ""
        with open(jsonl_path) as f:
            for line in f:
                d = json.loads(line)
                if d.get("type") != "user" or "message" not in d:
                    continue
                user_count += 1
                if user_count > 15:
                    break
                msg = d["message"]
                content = ""
                if isinstance(msg, dict):
                    c = msg.get("content", "")
                    if isinstance(c, list):
                        for part in c:
                            if isinstance(part, dict) and part.get("type") == "text":
                                content = part["text"]
                                break
                    elif isinstance(c, str):
                        content = c
                elif isinstance(msg, str):
                    content = msg

                # On first message, check for slash command
                if user_count == 1 and "<command-name>" in content:
                    command_name = _extract_command_name(content)
                    continue  # keep looking for real human text

                if _is_system_content(content):
                    continue

                # Find first meaningful line
                for raw_line in content.split("\n"):
                    text = raw_line.strip().lstrip("#").strip()
                    if text and len(text) > 5 and " " in text:
                        return text[:100]

        # Fallback to command name if no human text found
        return command_name
    except Exception:
        return ""


def get_session_summary(session_id: str) -> str:
    """Get a human-readable summary for a session, using cache."""
    cache = _load_summary_cache()
    if session_id in cache:
        return cache[session_id]

    # Search across all project dirs for matching JSONL
    if CLAUDE_PROJECTS_DIR.exists():
        for project_dir in CLAUDE_PROJECTS_DIR.iterdir():
            if not project_dir.is_dir():
                continue
            for jsonl in project_dir.glob(f"{session_id}*.jsonl"):
                summary = _extract_first_user_message(jsonl)
                if summary:
                    _summary_cache[session_id] = summary
                    _save_summary_cache()
                    return summary

    # Not found — cache empty string to avoid re-scanning
    _summary_cache[session_id] = ""
    _save_summary_cache()
    return ""


# Active iTerm2 session UUID — updated by session monitor when running inside iTerm2
_current_session_id: str = DEFAULT_SESSION

# Server start time for uptime reporting
_start_time: datetime = datetime.now(timezone.utc)


def get_current_session_id() -> str:
    return _current_session_id


_SESSION_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def notes_path(session_id: str = DEFAULT_SESSION) -> Path:
    if not _SESSION_ID_RE.match(session_id):
        raise ValueError(f"Invalid session_id: {session_id!r}")
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


def load_all_notes() -> list:
    """Load and merge notes from ALL session files, sorted by timestamp."""
    all_notes = []
    if not NOTES_DIR.exists():
        return []
    for path in NOTES_DIR.glob("*.json"):
        try:
            notes = json.loads(path.read_text())
            if isinstance(notes, list):
                all_notes.extend(notes)
        except Exception as exc:
            log.error("Failed to read notes from %s: %s", path, exc)
    all_notes.sort(key=lambda n: n.get("timestamp", ""))
    return all_notes


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
_sse_lock = asyncio.Lock()


async def broadcast(event_type: str, data: dict, event_id: str = "") -> None:
    id_line = f"id: {event_id}\n" if event_id else ""
    payload = f"{id_line}event: {event_type}\ndata: {json.dumps(data)}\n\n"
    dead = set()
    async with _sse_lock:
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


if WATCHDOG_AVAILABLE:
    class _TodoFileHandler(FileSystemEventHandler):
        """Watch ~/.claude/todos/ and ~/.claude/tasks/ for live task updates."""
        def on_modified(self, event):
            if not event.is_directory and event.src_path.endswith(".json"):
                self._debounce(event.src_path)

        def on_created(self, event):
            self.on_modified(event)

        def _debounce(self, path: str) -> None:
            key = f"todo:{path}"
            with _debounce_lock:
                existing = _debounce_timers.get(key)
                if existing:
                    existing.cancel()
                timer = threading.Timer(0.15, self._fire, args=(path,))
                _debounce_timers[key] = timer
                timer.start()

        def _fire(self, path: str) -> None:
            key = f"todo:{path}"
            with _debounce_lock:
                _debounce_timers.pop(key, None)
            if _event_loop is not None:
                asyncio.run_coroutine_threadsafe(
                    broadcast("todos_updated", {"path": path}),
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


def start_todo_watchdog() -> "Observer | None":
    """Watch Claude Code todo/task directories for live sidebar updates."""
    if not WATCHDOG_AVAILABLE:
        return None
    observer = Observer()
    handler = _TodoFileHandler()
    watched = []
    if CLAUDE_TODOS_DIR.exists():
        observer.schedule(handler, str(CLAUDE_TODOS_DIR), recursive=False)
        watched.append(str(CLAUDE_TODOS_DIR))
    if CLAUDE_TASKS_DIR.exists():
        observer.schedule(handler, str(CLAUDE_TASKS_DIR), recursive=True)
        watched.append(str(CLAUDE_TASKS_DIR))
    if not watched:
        log.info("No Claude todo/task directories found — skipping todo watchdog")
        return None
    observer.start()
    log.info("Todo watchdog monitoring %s", ", ".join(watched))
    return observer


# ---------------------------------------------------------------------------
# CORS helper
# ---------------------------------------------------------------------------
_ALLOWED_ORIGINS = {"http://localhost:9999", "http://127.0.0.1:9999"}
CORS_HEADERS = {
    "Access-Control-Allow-Methods": "GET, POST, DELETE, PATCH, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}


def cors(response: web.Response, *, origin: str = "") -> web.Response:
    """Add CORS headers. Only allows localhost origins (for WebView)."""
    response.headers.update(CORS_HEADERS)
    # Allow null origin for file:// and embedded WebView contexts
    if origin in _ALLOWED_ORIGINS or origin == "null":
        response.headers["Access-Control-Allow-Origin"] = origin
    else:
        # Default to localhost for same-origin requests (no Origin header)
        response.headers["Access-Control-Allow-Origin"] = "http://localhost:9999"
    return response


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------
async def handle_options(request: web.Request) -> web.Response:
    return cors(web.Response(status=204))


async def handle_get_ui(request: web.Request) -> web.Response:
    # Prefer pre-built React UI from ui/dist/index.html
    dist_html = Path(__file__).resolve().parent.parent / "ui" / "dist" / "index.html"

    def _read_ui():
        if dist_html.exists():
            return dist_html.read_text()
        return build_html()

    html = await asyncio.to_thread(_read_ui)
    return cors(web.Response(content_type="text/html", text=html))


async def handle_post_note(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return cors(web.Response(status=400, text="Invalid JSON"))

    text = body.get("text", "").strip()
    if not text:
        return cors(web.Response(status=400, text="text is required"))
    if len(text) > 100_000:
        return cors(web.Response(status=413, text="text too large (100KB max)"))

    session_id = get_current_session_id()

    # Auto-enrich generic source labels with session context
    source = body.get("source", "unknown")
    if source in ("agent", "unknown", ""):
        prefix = session_id[:8] if session_id != DEFAULT_SESSION else "default"
        subagent = body.get("metadata", {}).get("subagent_name", "")
        source = f"{prefix}:{subagent}" if subagent else prefix

    note = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "text": text,
        "source": source,
        "status": "active",
        "metadata": body.get("metadata", {}),
    }

    notes = await asyncio.to_thread(load_notes, session_id)
    notes.append(note)
    await asyncio.to_thread(save_notes, notes, session_id)
    log.info("Note added id=%s source=%s session=%s", note["id"], note["source"], session_id)

    await broadcast("note_added", note, event_id=note["id"])

    return cors(web.Response(
        status=201,
        content_type="application/json",
        text=json.dumps({"status": "ok", "id": note["id"], "timestamp": note["timestamp"]}),
    ))


async def handle_get_notes(request: web.Request) -> web.Response:
    # Scratchpad shows same content across all tabs — merge all sessions
    notes = await asyncio.to_thread(load_all_notes)
    return cors(web.Response(
        content_type="application/json",
        text=json.dumps({"notes": notes, "count": len(notes)}),
    ))


async def handle_delete_notes(request: web.Request) -> web.Response:
    def _clear_all():
        count = 0
        if NOTES_DIR.exists():
            for path in NOTES_DIR.glob("*.json"):
                try:
                    notes = json.loads(path.read_text())
                    count += len(notes) if isinstance(notes, list) else 0
                    path.write_text("[]")
                except Exception:
                    pass
        return count

    cleared = await asyncio.to_thread(_clear_all)
    log.info("All notes cleared count=%d", cleared)
    await broadcast("notes_cleared", {})
    return cors(web.Response(
        content_type="application/json",
        text=json.dumps({"status": "ok", "cleared": cleared}),
    ))


async def handle_patch_note(request: web.Request) -> web.Response:
    """Update a note's status (active/done). Searches all session files."""
    note_id = request.match_info.get("note_id", "")
    if not note_id:
        return cors(web.Response(status=400, text="note_id required"))

    try:
        body = await request.json()
    except Exception:
        return cors(web.Response(status=400, text="Invalid JSON"))

    new_status = body.get("status")
    if new_status not in ("active", "done"):
        return cors(web.Response(status=400, text="status must be 'active' or 'done'"))

    def _update_note():
        """Find note across all session files and update its status."""
        if not NOTES_DIR.exists():
            return None
        for path in NOTES_DIR.glob("*.json"):
            try:
                notes = json.loads(path.read_text())
                if not isinstance(notes, list):
                    continue
                for note in notes:
                    if note.get("id") == note_id:
                        note["status"] = new_status
                        save_notes(notes, path.stem)
                        return note
            except Exception:
                continue
        return None

    updated = await asyncio.to_thread(_update_note)
    if updated is None:
        return cors(web.Response(status=404, text="Note not found"))

    log.info("Note updated id=%s status=%s", note_id, new_status)
    await broadcast("note_updated", updated, event_id=note_id)

    return cors(web.Response(
        content_type="application/json",
        text=json.dumps({"status": "ok", "note": updated}),
    ))


async def handle_get_session(request: web.Request) -> web.Response:
    return cors(web.Response(
        content_type="application/json",
        text=json.dumps({"session_id": get_current_session_id()}),
    ))


# Rate limiter for /api/exec
_exec_timestamps: list = []
_EXEC_RATE_LIMIT = 30  # per minute
_BG_PROC_TIMEOUT = 300  # 5 minutes


async def _cleanup_bg_proc(proc: asyncio.subprocess.Process) -> None:
    """Kill background process after timeout."""
    try:
        await asyncio.wait_for(proc.wait(), timeout=_BG_PROC_TIMEOUT)
    except asyncio.TimeoutError:
        proc.kill()
        log.warning("Background process pid=%d killed after %ds timeout", proc.pid, _BG_PROC_TIMEOUT)


async def handle_exec(request: web.Request) -> web.Response:
    """Execute a command and return output. No CORS — localhost WebView only."""
    # Origin validation — reject cross-origin requests entirely
    origin = request.headers.get("Origin", "")
    if origin and origin not in _ALLOWED_ORIGINS and origin != "null":
        return web.Response(status=403, text='{"error":"forbidden"}', content_type="application/json")

    # Rate limiting
    now = _time.time()
    _exec_timestamps[:] = [t for t in _exec_timestamps if now - t < 60]
    if len(_exec_timestamps) >= _EXEC_RATE_LIMIT:
        return web.Response(status=429, text='{"error":"rate limited"}', content_type="application/json")
    _exec_timestamps.append(now)

    try:
        body = await request.json()
    except Exception:
        return web.Response(status=400, text='{"error":"invalid json"}', content_type="application/json")
    cmd = body.get("command", "").strip()
    if not cmd:
        return web.Response(status=400, text='{"error":"no command"}', content_type="application/json")

    # Validate cwd — must resolve under $HOME
    cwd = body.get("cwd") or str(Path.home())
    try:
        resolved_cwd = Path(cwd).resolve()
        if not str(resolved_cwd).startswith(str(Path.home())):
            return web.Response(status=403, text='{"error":"cwd outside home"}', content_type="application/json")
        cwd = str(resolved_cwd)
    except (ValueError, RuntimeError):
        return web.Response(status=400, text='{"error":"invalid cwd"}', content_type="application/json")

    # Parse command safely
    try:
        args = shlex.split(cmd)
    except ValueError:
        return web.Response(status=400, text='{"error":"invalid command syntax"}', content_type="application/json")

    bg = body.get("background", False)

    if bg:
        proc = await asyncio.create_subprocess_exec(
            *args, cwd=cwd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        asyncio.create_task(_cleanup_bg_proc(proc))
        return web.Response(
            content_type="application/json",
            text=json.dumps({"status": "started", "pid": proc.pid}),
        )

    timeout = min(body.get("timeout", 30), 120)
    try:
        proc = await asyncio.create_subprocess_exec(
            *args, cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        output = stdout.decode("utf-8", errors="replace")[-10000:]
        return web.Response(
            content_type="application/json",
            text=json.dumps({
                "status": "completed",
                "exit_code": proc.returncode,
                "output": output,
            }),
        )
    except asyncio.TimeoutError:
        proc.kill()
        return web.Response(
            content_type="application/json",
            text=json.dumps({"status": "timeout", "error": f"Command exceeded {timeout}s timeout"}),
        )


async def handle_get_todos(_request: web.Request) -> web.Response:
    """Return active Claude Code todos and team tasks.

    Only returns sessions/teams modified within the last 2 hours —
    older files are abandoned sessions whose pending items will never complete.
    """
    def _scan_todos():
        sessions = []
        teams = []
        max_age = 2 * 3600
        now = _time.time()

        if CLAUDE_TODOS_DIR.exists():
            files = sorted(
                (f for f in CLAUDE_TODOS_DIR.iterdir()
                 if f.suffix == ".json" and f.stat().st_size > 10),
                key=lambda f: f.stat().st_mtime,
                reverse=True,
            )
            for f in files[:20]:
                try:
                    mtime = f.stat().st_mtime
                    if now - mtime > max_age:
                        break
                    data = json.loads(f.read_text())
                    if not data:
                        continue
                    has_active = any(
                        item.get("status") != "completed"
                        for item in data
                        if isinstance(item, dict)
                    )
                    if not has_active:
                        continue
                    sid = f.stem.split("-agent-")[0] if "-agent-" in f.stem else f.stem
                    sessions.append({
                        "file": f.name,
                        "session_id": sid,
                        "summary": get_session_summary(sid),
                        "items": data,
                        "has_active": has_active,
                        "mtime": mtime,
                    })
                    if len(sessions) >= 5:
                        break
                except Exception:
                    continue

        if CLAUDE_TASKS_DIR.exists():
            for team_dir in sorted(
                (d for d in CLAUDE_TASKS_DIR.iterdir() if d.is_dir()),
                key=lambda d: d.stat().st_mtime,
                reverse=True,
            )[:5]:
                if now - team_dir.stat().st_mtime > max_age:
                    break
                tasks = []
                for tf in team_dir.glob("*.json"):
                    try:
                        task = json.loads(tf.read_text())
                        if isinstance(task, dict) and task.get("status") != "deleted":
                            tasks.append(task)
                    except Exception:
                        continue
                active_tasks = [t for t in tasks if t.get("status") != "completed"]
                if tasks and active_tasks:
                    team_id = team_dir.name
                    teams.append({
                        "team": team_id,
                        "summary": get_session_summary(team_id),
                        "tasks": sorted(tasks, key=lambda t: int(t.get("id", 0))),
                        "mtime": team_dir.stat().st_mtime,
                    })

        return {"sessions": sessions, "teams": teams}

    result = await asyncio.to_thread(_scan_todos)
    return cors(web.Response(
        content_type="application/json",
        text=json.dumps(result),
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
    async with _sse_lock:
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
        async with _sse_lock:
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
  /* Timers */
  .widget-timer { display: inline-flex; align-items: center; gap: 6px; background: #1e1e1e; border: 1px solid #3c3c3c; border-radius: 4px; padding: 3px 10px; margin: 4px 0; font-family: "SF Mono", Menlo, monospace; font-size: 13px; color: #4ec94e; }
  .widget-timer.expired { color: #f44747; border-color: #5a2d2d; }
  .widget-timer-icon { font-size: 10px; }
  .widget-timer-label { font-size: 10px; color: #808080; font-family: -apple-system, sans-serif; }
  /* Diff blocks */
  .widget-diff { background: #1e1e1e; border-radius: 4px; margin: 4px 0; overflow: hidden; font-family: "SF Mono", Menlo, monospace; font-size: 11px; line-height: 1.5; }
  .widget-diff-line { padding: 0 8px; white-space: pre-wrap; }
  .widget-diff-add { background: #1a2e1a; color: #4ec94e; }
  .widget-diff-del { background: #2e1a1a; color: #f44747; }
  .widget-diff-ctx { color: #808080; }
  /* Todo checklists */
  .widget-todo { margin: 4px 0; }
  .widget-todo-item { display: flex; align-items: center; gap: 6px; padding: 2px 0; font-size: 11px; cursor: pointer; }
  .widget-todo-item:hover { color: #fff; }
  .widget-todo-check { width: 14px; height: 14px; border: 1px solid #555; border-radius: 3px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; font-size: 10px; }
  .widget-todo-item.done .widget-todo-check { background: #1a3a1a; border-color: #4ec94e; color: #4ec94e; }
  .widget-todo-item.done .widget-todo-text { text-decoration: line-through; color: #808080; }
  /* Key-value pairs */
  .widget-kv { display: grid; grid-template-columns: auto 1fr; gap: 2px 12px; margin: 4px 0; padding: 6px 8px; background: #1e1e1e; border-radius: 4px; font-size: 11px; }
  .widget-kv-key { color: #569cd6; font-weight: 600; white-space: nowrap; }
  .widget-kv-val { color: #d4d4d4; }
  /* Log blocks */
  .widget-log { margin: 4px 0; padding: 4px 8px; border-radius: 4px; border-left: 3px solid; font-family: "SF Mono", Menlo, monospace; font-size: 11px; line-height: 1.4; white-space: pre-wrap; }
  .widget-log-error { background: #2a1515; border-color: #f44747; color: #f44747; }
  .widget-log-warn  { background: #2a2515; border-color: #e0c040; color: #e0c040; }
  .widget-log-info  { background: #152a2a; border-color: #569cd6; color: #87ceeb; }
  .widget-log-debug { background: #1e1e1e; border-color: #555; color: #808080; }
  /* Link cards */
  .widget-link { display: inline-flex; align-items: center; gap: 6px; background: #1e1e1e; border: 1px solid #3c3c3c; border-radius: 4px; padding: 3px 10px; margin: 2px 0; text-decoration: none; color: #569cd6; font-size: 11px; cursor: pointer; }
  .widget-link:hover { background: #252525; border-color: #569cd6; }
  .widget-link-icon { font-size: 10px; }
  /* File trees */
  .widget-tree { background: #1e1e1e; border-radius: 4px; padding: 6px 8px; margin: 4px 0; font-family: "SF Mono", Menlo, monospace; font-size: 11px; line-height: 1.6; color: #d4d4d4; white-space: pre; }
  .widget-tree-dir { color: #569cd6; }
  .widget-tree-file { color: #d4d4d4; }
  /* Metric cards */
  .widget-metric { display: inline-flex; flex-direction: column; align-items: center; background: #1e1e1e; border: 1px solid #3c3c3c; border-radius: 6px; padding: 8px 16px; margin: 4px 4px 4px 0; min-width: 80px; }
  .widget-metric-value { font-size: 20px; font-weight: 700; font-family: "SF Mono", Menlo, monospace; }
  .widget-metric-label { font-size: 9px; color: #808080; text-transform: uppercase; letter-spacing: 0.05em; margin-top: 2px; }
  .widget-metric-trend { font-size: 10px; margin-top: 1px; }
  .widget-metric-trend.up { color: #f44747; }
  .widget-metric-trend.down { color: #4ec94e; }
  .widget-metric-trend.flat { color: #808080; }
  /* Clipboard widget */
  .widget-clip { display: flex; align-items: center; gap: 8px; background: #1e1e1e; border: 1px solid #3c3c3c; border-radius: 4px; padding: 4px 8px; margin: 4px 0; font-family: "SF Mono", Menlo, monospace; font-size: 11px; }
  .widget-clip-content { flex: 1; overflow-x: auto; white-space: nowrap; color: #d4d4d4; }
  .widget-clip-btn { background: #333; border: 1px solid #555; color: #ccc; padding: 2px 8px; border-radius: 3px; cursor: pointer; font-size: 10px; flex-shrink: 0; }
  .widget-clip-btn:hover { background: #444; }
  .widget-clip-label { color: #569cd6; font-size: 10px; font-weight: 600; font-family: -apple-system, sans-serif; flex-shrink: 0; }
  /* Deadline countdown */
  .widget-deadline { display: inline-flex; align-items: center; gap: 8px; background: #1e1e1e; border: 1px solid #3c3c3c; border-radius: 4px; padding: 4px 10px; margin: 4px 0; font-size: 12px; }
  .widget-deadline-time { font-family: "SF Mono", Menlo, monospace; color: #e0c040; font-weight: 600; }
  .widget-deadline.urgent .widget-deadline-time { color: #f44747; }
  .widget-deadline.past .widget-deadline-time { color: #f44747; }
  .widget-deadline-label { color: #808080; font-size: 10px; }
  /* Port monitor */
  .widget-ports { display: flex; gap: 10px; margin: 4px 0; flex-wrap: wrap; }
  .widget-port { display: inline-flex; align-items: center; gap: 4px; font-family: "SF Mono", Menlo, monospace; font-size: 11px; padding: 2px 8px; background: #1e1e1e; border-radius: 3px; }
  .widget-port-dot { width: 6px; height: 6px; border-radius: 50%; }
  .widget-port-dot.up { background: #4ec94e; box-shadow: 0 0 4px #4ec94e; }
  .widget-port-dot.down { background: #f44747; box-shadow: 0 0 4px #f44747; }
  .widget-port-dot.checking { background: #e0c040; }
  /* Toast notifications */
  .toast-container { position: fixed; top: 40px; right: 8px; z-index: 1000; display: flex; flex-direction: column; gap: 4px; }
  .toast { background: #2d2d2d; border: 1px solid #569cd6; border-radius: 4px; padding: 6px 12px; font-size: 11px; color: #d4d4d4; box-shadow: 0 2px 8px rgba(0,0,0,0.4); animation: toastIn 0.3s ease, toastOut 0.3s ease 2.7s; opacity: 0; animation-fill-mode: forwards; max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .toast.error { border-color: #f44747; }
  .toast.warning { border-color: #e0c040; }
  @keyframes toastIn { from { opacity: 0; transform: translateX(20px); } to { opacity: 1; transform: translateX(0); } }
  @keyframes toastOut { from { opacity: 1; } to { opacity: 0; } }
  /* Pinned notes */
  .note.pinned { border-color: #569cd6; border-left: 3px solid #569cd6; }
  .note-pin { cursor: pointer; font-size: 10px; color: #555; margin-left: 6px; }
  .note.pinned .note-pin { color: #569cd6; }
  /* Note categories / source filter */
  #filters { display: flex; gap: 4px; padding: 4px 10px; background: #252526; border-bottom: 1px solid #3c3c3c; flex-wrap: wrap; flex-shrink: 0; }
  .filter-btn { background: none; border: 1px solid #3c3c3c; color: #808080; padding: 1px 8px; border-radius: 9px; cursor: pointer; font-size: 9px; text-transform: uppercase; letter-spacing: 0.03em; }
  .filter-btn:hover { color: #d4d4d4; border-color: #555; }
  .filter-btn.active { color: #569cd6; border-color: #569cd6; background: #1a2a3a; }
  /* Mermaid diagrams */
  .widget-mermaid { background: #1e1e1e; border-radius: 4px; padding: 8px; margin: 4px 0; overflow-x: auto; }
  .widget-mermaid svg { max-width: 100%; }
  /* Note threading */
  .note-thread-btn { background: none; border: none; color: #555; font-size: 10px; cursor: pointer; padding: 2px 4px; }
  .note-thread-btn:hover { color: #d4d4d4; }
  .note-replies { margin-left: 12px; border-left: 2px solid #3c3c3c; padding-left: 8px; }
  .note-reply-input { display: flex; gap: 4px; margin-top: 4px; }
  .note-reply-input input { flex: 1; background: #1e1e1e; border: 1px solid #3c3c3c; color: #d4d4d4; padding: 3px 6px; border-radius: 3px; font-size: 10px; }
  .note-reply-input button { background: #333; border: 1px solid #555; color: #ccc; padding: 3px 8px; border-radius: 3px; cursor: pointer; font-size: 10px; }
  /* Run widget */
  .widget-run { background: #1e1e1e; border: 1px solid #3c3c3c; border-radius: 4px; margin: 4px 0; overflow: hidden; }
  .widget-run-header { display: flex; align-items: center; gap: 6px; padding: 4px 8px; background: #252526; border-bottom: 1px solid #3c3c3c; }
  .widget-run-prompt { color: #4ec94e; font-size: 10px; font-weight: 700; }
  .widget-run-cmd { flex: 1; font-family: "SF Mono", Menlo, monospace; font-size: 11px; color: #d4d4d4; overflow-x: auto; white-space: nowrap; }
  .widget-run-btn { background: #1a3a1a; border: 1px solid #2d5a2d; color: #4ec94e; padding: 2px 10px; border-radius: 3px; cursor: pointer; font-size: 10px; font-weight: 600; }
  .widget-run-btn:hover { background: #2d5a2d; }
  .widget-run-btn.bg { background: #1a2a3a; border-color: #2d4a5a; color: #569cd6; }
  .widget-run-btn.bg:hover { background: #2d4a5a; }
  .widget-run-btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .widget-run-output { padding: 6px 8px; font-family: "SF Mono", Menlo, monospace; font-size: 11px; line-height: 1.4; white-space: pre-wrap; max-height: 200px; overflow-y: auto; display: none; border-top: 1px solid #3c3c3c; }
  .widget-run-output.visible { display: block; }
  .widget-run-output.error { color: #f44747; }
  .widget-run-output.success { color: #d4d4d4; }
  .widget-run-spinner { display: inline-block; width: 10px; height: 10px; border: 2px solid #4ec94e; border-top-color: transparent; border-radius: 50%; animation: spin 0.8s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  #empty {
    color: #555;
    text-align: center;
    padding: 40px 20px;
    font-size: 11px;
  }
</style>
</head>
<body>
<div class="toast-container" id="toasts"></div>
<div id="header">
  <h1>AI Scratchpad</h1>
  <span id="status">connecting…</span>
  <button id="clear-btn" onclick="clearNotes()">Clear All</button>
</div>
<div id="filters"></div>
<div id="notes"></div>

<script>
const API = 'http://localhost:9999';
let notes = [];
let activeFilter = 'all';
let pinnedIds = JSON.parse(localStorage.getItem('scratchpad_pinned') || '[]');

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
  // Timers: [timer:5m:Label] or [timer:90s] or [timer:1h30m]
  s = s.replace(/\\[timer:([^:\\]]+)(?::([^\\]]*))?\\]/g, function(_, dur, label) {
    const id = 'timer-' + (++_widgetId);
    let secs = 0;
    const hm = dur.match(/(\\d+)h/); const mm = dur.match(/(\\d+)m(?!s)/); const sm = dur.match(/(\\d+)s/);
    if (hm) secs += parseInt(hm[1]) * 3600;
    if (mm) secs += parseInt(mm[1]) * 60;
    if (sm) secs += parseInt(sm[1]);
    if (secs === 0) secs = parseInt(dur) || 60;
    const lbl = label || '';
    return '<div class="widget-timer" id="' + id + '" data-secs="' + secs + '">' +
      '<span class="widget-timer-icon">&#9202;</span>' +
      '<span class="widget-timer-display">--:--</span>' +
      (lbl ? '<span class="widget-timer-label">' + lbl + '</span>' : '') +
      '</div>';
  });
  // Diff blocks: [diff]- old\\n+ new[/diff]
  s = s.replace(/\\[diff\\]([\\s\\S]*?)\\[\\/diff\\]/g, function(_, content) {
    const lines = content.trim().split('\\n');
    let html = '<div class="widget-diff">';
    lines.forEach(function(line) {
      if (line.charAt(0) === '+') html += '<div class="widget-diff-line widget-diff-add">' + line + '</div>';
      else if (line.charAt(0) === '-') html += '<div class="widget-diff-line widget-diff-del">' + line + '</div>';
      else html += '<div class="widget-diff-line widget-diff-ctx">' + line + '</div>';
    });
    return html + '</div>';
  });
  // Todo checklists: [todo]Item one\\n[x]Done item\\nItem three[/todo]
  s = s.replace(/\\[todo\\]([\\s\\S]*?)\\[\\/todo\\]/g, function(_, content) {
    const items = content.trim().split('\\n');
    let html = '<div class="widget-todo">';
    items.forEach(function(item) {
      const done = item.match(/^\\[x\\]/i);
      const text = done ? item.slice(3).trim() : item.trim();
      if (!text) return;
      const cls = done ? 'widget-todo-item done' : 'widget-todo-item';
      html += '<div class="' + cls + '" onclick="this.classList.toggle(&quot;done&quot;);var c=this.querySelector(&quot;.widget-todo-check&quot;);c.textContent=this.classList.contains(&quot;done&quot;)?&quot;&#10003;&quot;:&quot;&quot;">' +
        '<span class="widget-todo-check">' + (done ? '&#10003;' : '') + '</span>' +
        '<span class="widget-todo-text">' + text + '</span></div>';
    });
    return html + '</div>';
  });
  // Key-value pairs: [kv]Key:Value|Key2:Value2[/kv]
  s = s.replace(/\\[kv\\]([\\s\\S]*?)\\[\\/kv\\]/g, function(_, content) {
    const pairs = content.trim().split('|');
    let html = '<div class="widget-kv">';
    pairs.forEach(function(pair) {
      const idx = pair.indexOf(':');
      if (idx === -1) return;
      html += '<span class="widget-kv-key">' + pair.slice(0, idx).trim() + '</span>' +
              '<span class="widget-kv-val">' + pair.slice(idx + 1).trim() + '</span>';
    });
    return html + '</div>';
  });
  // Log blocks: [log:error]message[/log]
  s = s.replace(/\\[log:(error|warn|info|debug)\\]([\\s\\S]*?)\\[\\/log\\]/g, function(_, level, content) {
    return '<div class="widget-log widget-log-' + level + '">' + content.trim() + '</div>';
  });
  // Link cards: [link:Label:https://...]
  s = s.replace(/\\[link:([^:]+):([^\\]]*)\\]/g, function(_, label, url) {
    return '<a class="widget-link" href="' + url + '" target="_blank" rel="noopener">' +
      '<span class="widget-link-icon">&#128279;</span>' + label + '</a>';
  });
  // File trees: [tree]src/\\n  file.ts[/tree]
  s = s.replace(/\\[tree\\]([\\s\\S]*?)\\[\\/tree\\]/g, function(_, content) {
    const lines = content.trim().split('\\n');
    let html = '<div class="widget-tree">';
    lines.forEach(function(line) {
      if (line.match(/\\/[\\s]*$/)) html += '<span class="widget-tree-dir">' + line + '</span>\\n';
      else html += '<span class="widget-tree-file">' + line + '</span>\\n';
    });
    return html + '</div>';
  });
  // Metric cards: [metric:42ms:Latency:down] or [metric:99.9%:Uptime:flat]
  s = s.replace(/\\[metric:([^:]+):([^:]+)(?::(up|down|flat))?\\]/g, function(_, value, label, trend) {
    const t = trend || 'flat';
    const arrow = t === 'up' ? '&#9650;' : t === 'down' ? '&#9660;' : '&#9644;';
    return '<div class="widget-metric">' +
      '<span class="widget-metric-value">' + value + '</span>' +
      '<span class="widget-metric-label">' + label + '</span>' +
      '<span class="widget-metric-trend ' + t + '">' + arrow + '</span></div>';
  });
  // Clipboard widget: [clip:label]content[/clip]
  s = s.replace(/\\[clip:([^\\]]+)\\]([\\s\\S]*?)\\[\\/clip\\]/g, function(_, label, content) {
    const id = 'clip-' + (++_widgetId);
    const escaped = content.trim().replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&quot;/g,'"');
    return '<div class="widget-clip">' +
      '<span class="widget-clip-label">' + label + '</span>' +
      '<span class="widget-clip-content">' + content.trim() + '</span>' +
      '<button class="widget-clip-btn" onclick="navigator.clipboard.writeText(decodeURIComponent(&quot;' + encodeURIComponent(escaped) + '&quot;));this.textContent=&quot;Copied!&quot;;setTimeout(()=>this.textContent=&quot;Copy&quot;,1500)">Copy</button></div>';
  });
  // Deadline countdown: [deadline:2026-02-23T17:00:00:Sprint ends]
  s = s.replace(/\\[deadline:([^:\\]]+)(?::([^\\]]*))?\\]/g, function(_, iso, label) {
    const id = 'deadline-' + (++_widgetId);
    const lbl = label || '';
    return '<div class="widget-deadline" id="' + id + '" data-target="' + iso + '">' +
      '<span class="widget-deadline-time">--</span>' +
      (lbl ? '<span class="widget-deadline-label">' + lbl + '</span>' : '') +
      '</div>';
  });
  // Port monitor: [ports:3000,5432,9999]
  s = s.replace(/\\[ports:([\\d,]+)\\]/g, function(_, portList) {
    const ports = portList.split(',');
    const id = 'ports-' + (++_widgetId);
    let html = '<div class="widget-ports" id="' + id + '">';
    ports.forEach(function(p) {
      html += '<span class="widget-port"><span class="widget-port-dot checking" data-port="' + p.trim() + '"></span>' + p.trim() + '</span>';
    });
    return html + '</div>';
  });
  // Mermaid diagrams: [mermaid]graph LR; A-->B[/mermaid]
  s = s.replace(/\\[mermaid\\]([\\s\\S]*?)\\[\\/mermaid\\]/g, function(_, content) {
    const id = 'mermaid-' + (++_widgetId);
    return '<div class="widget-mermaid" id="' + id + '" data-mermaid="' + encodeURIComponent(content.trim().replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&quot;/g,'"')) + '"><pre style="color:#808080;font-size:10px">Loading diagram...</pre></div>';
  });
  // Run widget: [run:label]command[/run]
  s = s.replace(/\\[run(?::([^\\]]+))?\\]([\\s\\S]*?)\\[\\/run\\]/g, function(_, label, cmd) {
    const id = 'run-' + (++_widgetId);
    const command = cmd.trim().replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&quot;/g,'"');
    const encoded = encodeURIComponent(command);
    const lbl = label || '';
    return '<div class="widget-run" id="' + id + '">' +
      '<div class="widget-run-header">' +
      '<span class="widget-run-prompt">' + (lbl || '&#36;') + '</span>' +
      '<span class="widget-run-cmd">' + cmd.trim() + '</span>' +
      '<button class="widget-run-btn" onclick="execCmd(&quot;' + id + '&quot;,&quot;' + encoded + '&quot;,false)">&#9654; Run</button>' +
      '<button class="widget-run-btn bg" onclick="execCmd(&quot;' + id + '&quot;,&quot;' + encoded + '&quot;,true)">BG</button>' +
      '</div>' +
      '<div class="widget-run-output" id="' + id + '-output"></div></div>';
  });
  return s;
}

// Execute command via /api/exec
function execCmd(widgetId, encodedCmd, bg) {
  const cmd = decodeURIComponent(encodedCmd);
  const output = document.getElementById(widgetId + '-output');
  const widget = document.getElementById(widgetId);
  const btns = widget.querySelectorAll('.widget-run-btn');

  if (bg) {
    // Background — fire and forget
    fetch(API + '/api/exec', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({command: cmd, background: true})
    }).then(r => r.json()).then(data => {
      output.className = 'widget-run-output visible success';
      output.textContent = 'Started in background (PID ' + data.pid + ')';
    }).catch(err => {
      output.className = 'widget-run-output visible error';
      output.textContent = 'Failed: ' + err.message;
    });
    return;
  }

  // Foreground — show spinner, disable buttons, stream output
  btns.forEach(b => b.disabled = true);
  output.className = 'widget-run-output visible';
  output.innerHTML = '<span class="widget-run-spinner"></span> Running...';

  fetch(API + '/api/exec', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({command: cmd, background: false, timeout: 30})
  }).then(r => r.json()).then(data => {
    btns.forEach(b => b.disabled = false);
    if (data.status === 'completed') {
      output.className = 'widget-run-output visible ' + (data.exit_code === 0 ? 'success' : 'error');
      output.textContent = data.output || '(no output)';
      if (data.exit_code !== 0) output.textContent += '\\nExit code: ' + data.exit_code;
    } else if (data.status === 'timeout') {
      output.className = 'widget-run-output visible error';
      output.textContent = data.error;
    } else {
      output.className = 'widget-run-output visible error';
      output.textContent = 'Unexpected: ' + JSON.stringify(data);
    }
  }).catch(err => {
    btns.forEach(b => b.disabled = false);
    output.className = 'widget-run-output visible error';
    output.textContent = 'Failed: ' + err.message;
  });
}

// Toast notification system
function showToast(text, type) {
  const container = document.getElementById('toasts');
  const toast = document.createElement('div');
  toast.className = 'toast' + (type ? ' ' + type : '');
  toast.textContent = text;
  container.appendChild(toast);
  setTimeout(function() { toast.remove(); }, 3000);
}

// Source filter bar
function updateFilters() {
  const sources = ['all', ...new Set(notes.map(n => n.source || 'unknown'))];
  const container = document.getElementById('filters');
  while (container.firstChild) container.removeChild(container.firstChild);
  if (sources.length <= 2) return;
  sources.forEach(function(src) {
    const btn = document.createElement('button');
    btn.className = 'filter-btn' + (activeFilter === src ? ' active' : '');
    btn.textContent = src;
    btn.addEventListener('click', function() {
      activeFilter = src;
      updateFilters();
      renderNotes();
    });
    container.appendChild(btn);
  });
}

// Pin management
function togglePin(noteId) {
  const idx = pinnedIds.indexOf(noteId);
  if (idx >= 0) pinnedIds.splice(idx, 1);
  else pinnedIds.push(noteId);
  localStorage.setItem('scratchpad_pinned', JSON.stringify(pinnedIds));
  renderNotes();
}

function renderNotes() {
  const container = document.getElementById('notes');
  while (container.firstChild) container.removeChild(container.firstChild);
  updateFilters();

  // Filter by source
  let filtered = activeFilter === 'all' ? notes : notes.filter(n => (n.source || 'unknown') === activeFilter);

  if (filtered.length === 0) {
    const empty = document.createElement('div');
    empty.id = 'empty';
    empty.textContent = notes.length === 0 ? 'No notes yet. AI agents will post here.' : 'No notes from "' + activeFilter + '"';
    container.appendChild(empty);
    return;
  }

  // Sort: pinned first, then reverse-chronological
  const sorted = [...filtered].sort((a, b) => {
    const ap = pinnedIds.includes(a.id) ? 1 : 0;
    const bp = pinnedIds.includes(b.id) ? 1 : 0;
    if (ap !== bp) return bp - ap;
    return new Date(b.timestamp) - new Date(a.timestamp);
  });

  sorted.forEach(note => {
    const isPinned = pinnedIds.includes(note.id);
    const div = document.createElement('div');
    div.className = 'note' + (isPinned ? ' pinned' : '');
    div.dataset.noteId = note.id;

    const meta = document.createElement('div');
    meta.className = 'note-meta';

    const src = document.createElement('span');
    src.className = 'note-source';
    src.textContent = note.source || 'unknown';

    const metaRight = document.createElement('span');
    const pin = document.createElement('span');
    pin.className = 'note-pin';
    pin.textContent = isPinned ? '&#9733;' : '&#9734;';
    pin.innerHTML = isPinned ? '&#9733;' : '&#9734;';
    pin.title = isPinned ? 'Unpin' : 'Pin to top';
    pin.addEventListener('click', function() { togglePin(note.id); });

    const time = document.createElement('span');
    time.className = 'note-time';
    time.title = note.timestamp;
    time.textContent = formatTime(note.timestamp);

    metaRight.appendChild(time);
    metaRight.appendChild(pin);
    meta.appendChild(src);
    meta.appendChild(metaRight);

    const text = document.createElement('div');
    text.className = 'note-text';
    text.innerHTML = renderMarkdown(note.text);

    const actions = document.createElement('div');
    actions.style.cssText = 'display:flex;gap:4px;margin-top:6px';

    const copyBtn = document.createElement('button');
    copyBtn.className = 'copy-btn';
    copyBtn.textContent = 'Copy';
    copyBtn.addEventListener('click', function() {
      navigator.clipboard.writeText(note.text).then(function() {
        copyBtn.textContent = 'Copied!';
        setTimeout(function() { copyBtn.textContent = 'Copy'; }, 1500);
      });
    });
    actions.appendChild(copyBtn);

    div.appendChild(meta);
    div.appendChild(text);
    div.appendChild(actions);
    container.appendChild(div);
  });
  initTimers();
  initDeadlines();
  initPorts();
  initMermaid();
}

// Timer countdown logic — finds all [timer] widgets and ticks them
const _timerIntervals = [];
function initTimers() {
  _timerIntervals.forEach(clearInterval);
  _timerIntervals.length = 0;
  document.querySelectorAll('.widget-timer[data-secs]').forEach(function(el) {
    let remaining = parseInt(el.dataset.secs);
    const display = el.querySelector('.widget-timer-display');
    function tick() {
      if (remaining <= 0) {
        display.textContent = 'EXPIRED';
        el.classList.add('expired');
        return;
      }
      const h = Math.floor(remaining / 3600);
      const m = Math.floor((remaining % 3600) / 60);
      const sec = remaining % 60;
      display.textContent = h > 0
        ? h + ':' + String(m).padStart(2, '0') + ':' + String(sec).padStart(2, '0')
        : m + ':' + String(sec).padStart(2, '0');
      remaining--;
    }
    tick();
    _timerIntervals.push(setInterval(tick, 1000));
  });
}

// Deadline countdown — updates relative time display
const _deadlineIntervals = [];
function initDeadlines() {
  _deadlineIntervals.forEach(clearInterval);
  _deadlineIntervals.length = 0;
  document.querySelectorAll('.widget-deadline[data-target]').forEach(function(el) {
    const target = new Date(el.dataset.target);
    const display = el.querySelector('.widget-deadline-time');
    function tick() {
      const now = new Date();
      const diff = target - now;
      if (diff <= 0) {
        const ago = Math.abs(diff);
        const mins = Math.floor(ago / 60000);
        display.textContent = mins < 60 ? mins + 'm overdue' : Math.floor(mins / 60) + 'h ' + (mins % 60) + 'm overdue';
        el.classList.add('past');
        return;
      }
      const days = Math.floor(diff / 86400000);
      const hrs = Math.floor((diff % 86400000) / 3600000);
      const mins = Math.floor((diff % 3600000) / 60000);
      if (days > 0) display.textContent = days + 'd ' + hrs + 'h';
      else if (hrs > 0) display.textContent = hrs + 'h ' + mins + 'm';
      else display.textContent = mins + 'm';
      if (diff < 3600000) el.classList.add('urgent');
    }
    tick();
    _deadlineIntervals.push(setInterval(tick, 30000));
  });
}

// Port monitor — pings ports via fetch to detect if they are up
function initPorts() {
  document.querySelectorAll('.widget-port-dot[data-port]').forEach(function(dot) {
    const port = dot.dataset.port;
    fetch('http://localhost:' + port + '/').then(function() {
      dot.className = 'widget-port-dot up';
    }).catch(function() {
      // Try /health as fallback
      fetch('http://localhost:' + port + '/health').then(function() {
        dot.className = 'widget-port-dot up';
      }).catch(function() {
        dot.className = 'widget-port-dot down';
      });
    });
  });
}

// Mermaid diagram rendering — loads mermaid.js from CDN on first use
let _mermaidLoaded = false;
function initMermaid() {
  const els = document.querySelectorAll('.widget-mermaid[data-mermaid]');
  if (els.length === 0) return;
  if (!_mermaidLoaded) {
    _mermaidLoaded = true;
    const script = document.createElement('script');
    script.src = 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js';
    script.onload = function() {
      window.mermaid.initialize({ theme: 'dark', themeVariables: { darkMode: true, background: '#1e1e1e', primaryColor: '#569cd6', primaryTextColor: '#d4d4d4', lineColor: '#808080' }});
      renderMermaidDiagrams(els);
    };
    document.head.appendChild(script);
  } else if (window.mermaid) {
    renderMermaidDiagrams(els);
  }
}
function renderMermaidDiagrams(els) {
  els.forEach(function(el) {
    const code = decodeURIComponent(el.dataset.mermaid);
    const id = el.id + '-svg';
    try {
      window.mermaid.render(id, code).then(function(result) {
        el.innerHTML = result.svg;
        el.removeAttribute('data-mermaid');
      }).catch(function(err) {
        el.innerHTML = '<pre style="color:#f44747;font-size:10px">Diagram error: ' + err.message + '</pre>';
      });
    } catch(err) {
      el.innerHTML = '<pre style="color:#f44747;font-size:10px">Diagram error: ' + err + '</pre>';
    }
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
    // Toast notification
    const preview = (note.text || '').slice(0, 60) + ((note.text || '').length > 60 ? '...' : '');
    const src = note.source || 'unknown';
    const toastType = (note.text || '').match(/error|fail|exception/i) ? 'error' : (note.text || '').match(/warn|caution/i) ? 'warning' : '';
    showToast(src.toUpperCase() + ': ' + preview, toastType);
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
    app = web.Application(client_max_size=1_000_000)  # 1MB request limit
    app.router.add_route("OPTIONS", "/{path_info:.*}", handle_options)
    app.router.add_get("/", handle_get_ui)
    app.router.add_post("/api/notes", handle_post_note)
    app.router.add_get("/api/notes", handle_get_notes)
    app.router.add_delete("/api/notes", handle_delete_notes)
    app.router.add_patch("/api/notes/{note_id}", handle_patch_note)
    app.router.add_get("/api/session", handle_get_session)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/events", handle_sse)
    app.router.add_post("/api/exec", handle_exec)
    app.router.add_get("/api/todos", handle_get_todos)
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

    # Start aiohttp server + watchdogs, then run session monitor
    runner = await _run_server()
    observer = start_watchdog()
    todo_observer = start_todo_watchdog()
    try:
        await _session_monitor(connection)
    finally:
        if observer:
            observer.stop()
            observer.join()
        if todo_observer:
            todo_observer.stop()
            todo_observer.join()
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
            todo_observer = start_todo_watchdog()
            try:
                while True:
                    await asyncio.sleep(3600)
            finally:
                if observer:
                    observer.stop()
                    observer.join()
                if todo_observer:
                    todo_observer.stop()
                    todo_observer.join()
                await runner.cleanup()

        asyncio.run(_standalone_main())
