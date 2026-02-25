"""HTTP route handlers, CORS, and request validation."""

import asyncio
import json
import logging
import os
import shlex
import time as _time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from aiohttp import web

from .storage import (
    NOTES_DIR, CLAUDE_TODOS_DIR, CLAUDE_TASKS_DIR, DEFAULT_SESSION,
    get_current_session_id, get_start_time, get_session_summary,
    get_iterm2_connection, get_current_tab_session_ids,
    load_notes, save_notes, load_all_notes, load_tab_notes, append_note, update_note_in_file,
    load_prefs, save_prefs,
)
from . import ITERM2_AVAILABLE, _iterm2
from .streaming import broadcast, get_sse_clients, get_sse_lock
from .ui import build_html

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CORS helper
# ---------------------------------------------------------------------------
_ALLOWED_ORIGINS = {"http://localhost:9999", "http://127.0.0.1:9999"}
CORS_HEADERS = {
    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, PATCH, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}


def cors(response: web.Response, *, origin: str = "") -> web.Response:
    """Add CORS headers. Only allows localhost origins (for WebView)."""
    response.headers.update(CORS_HEADERS)
    # Prevent WKWebView from caching API responses
    response.headers["Cache-Control"] = "no-store"
    if origin in _ALLOWED_ORIGINS or origin == "null":
        response.headers["Access-Control-Allow-Origin"] = origin
    else:
        response.headers["Access-Control-Allow-Origin"] = "http://localhost:9999"
    return response


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------
async def handle_options(request: web.Request) -> web.Response:
    return cors(web.Response(status=204))


async def handle_get_ui(request: web.Request) -> web.Response:
    # In dev mode, redirect to Vite dev server for HMR
    if os.environ.get("SCRATCHPAD_DEV"):
        vite_url = os.environ.get("SCRATCHPAD_VITE_URL", "http://localhost:5173")
        raise web.HTTPFound(vite_url)

    dist_html = Path(__file__).resolve().parent.parent.parent / "ui" / "dist" / "index.html"

    def _read_ui():
        if dist_html.exists():
            return dist_html.read_text()
        return build_html()

    html = await asyncio.to_thread(_read_ui)
    resp = web.Response(content_type="text/html", text=html)
    resp.headers["Cache-Control"] = "no-store"
    return cors(resp)


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

    # Use agent-provided session_id if available (from ITERM_SESSION_ID env var),
    # otherwise fall back to the currently focused tab's session
    session_id = body.get("session_id", "") or get_current_session_id()

    source = body.get("source", "unknown")
    if source in ("agent", "unknown", ""):
        prefix = session_id[:7] if session_id != DEFAULT_SESSION else ""
        subagent = body.get("metadata", {}).get("subagent_name", "")
        # Build source: "agent:session_prefix" or "agent:subagent:session_prefix"
        parts = ["agent"]
        if subagent:
            parts.append(subagent)
        if prefix:
            parts.append(prefix)
        source = ":".join(parts)

    note = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "text": text,
        "source": source,
        "status": "active",
        "session_id": session_id,
        "metadata": body.get("metadata", {}),
    }

    await asyncio.to_thread(append_note, note, session_id)
    log.info("Note added id=%s source=%s session=%s", note["id"], note["source"], session_id)

    await broadcast("note_added", note, event_id=note["id"])

    return cors(web.Response(
        status=201,
        content_type="application/json",
        text=json.dumps({"status": "ok", "id": note["id"], "timestamp": note["timestamp"]}),
    ))


async def handle_get_notes(request: web.Request) -> web.Response:
    session = request.query.get("session", "")
    if session == "current":
        session = get_current_session_id()
    if session == "current_tab":
        tab_ids = get_current_tab_session_ids()
        if tab_ids:
            notes = await asyncio.to_thread(load_tab_notes, tab_ids)
        else:
            notes = await asyncio.to_thread(load_notes, get_current_session_id())
    elif session:
        notes = await asyncio.to_thread(load_notes, session)
    else:
        notes = await asyncio.to_thread(load_all_notes)
    return cors(web.Response(
        content_type="application/json",
        text=json.dumps({
            "notes": notes,
            "count": len(notes),
            "session_id": get_current_session_id(),
            "tab_session_ids": get_current_tab_session_ids(),
        }),
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


async def handle_put_note(request: web.Request) -> web.Response:
    """Replace a note's content (for live-updating status cards)."""
    note_id = request.match_info.get("note_id", "")
    if not note_id:
        return cors(web.Response(status=400, text="note_id required"))

    try:
        body = await request.json()
    except Exception:
        return cors(web.Response(status=400, text="Invalid JSON"))

    updates = {}
    if "text" in body:
        text = body["text"].strip()
        if not text:
            return cors(web.Response(status=400, text="text cannot be empty"))
        if len(text) > 100_000:
            return cors(web.Response(status=413, text="text too large (100KB max)"))
        updates["text"] = text
    if "source" in body:
        updates["source"] = body["source"]
    if "metadata" in body:
        updates["metadata"] = body["metadata"]

    if not updates:
        return cors(web.Response(status=400, text="nothing to update"))

    updated = await asyncio.to_thread(update_note_in_file, note_id, updates)
    if updated is None:
        return cors(web.Response(status=404, text="Note not found"))

    log.info("Note replaced id=%s", note_id)
    await broadcast("note_updated", updated, event_id=note_id)

    return cors(web.Response(
        content_type="application/json",
        text=json.dumps({"status": "ok", "note": updated}),
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

    updated = await asyncio.to_thread(update_note_in_file, note_id, {"status": new_status})
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


async def handle_activate_session(request: web.Request) -> web.Response:
    """Activate an iTerm2 tab by session ID."""
    session_id = request.match_info.get("session_id", "")
    if not session_id:
        return cors(web.Response(status=400, text="session_id required"))

    if not ITERM2_AVAILABLE:
        return cors(web.Response(
            status=501,
            content_type="application/json",
            text=json.dumps({"error": "iTerm2 not available"}),
        ))

    connection = get_iterm2_connection()
    if not connection:
        return cors(web.Response(
            status=503,
            content_type="application/json",
            text=json.dumps({"error": "iTerm2 connection not ready"}),
        ))

    try:
        app = await _iterm2.async_get_app(connection)
        for window in app.windows:
            for tab in window.tabs:
                for session in tab.sessions:
                    if session.session_id == session_id:
                        await tab.async_activate()
                        await session.async_activate()
                        log.info("Activated session %s", session_id)
                        return cors(web.Response(
                            content_type="application/json",
                            text=json.dumps({"status": "ok", "session_id": session_id}),
                        ))
        return cors(web.Response(
            status=404,
            content_type="application/json",
            text=json.dumps({"error": "session not found", "session_id": session_id}),
        ))
    except Exception as exc:
        log.error("Failed to activate session %s: %s", session_id, exc)
        return cors(web.Response(
            status=500,
            content_type="application/json",
            text=json.dumps({"error": str(exc)}),
        ))


# ---------------------------------------------------------------------------
# Command running (uses subprocess_exec for safety — no shell injection)
# ---------------------------------------------------------------------------
_run_timestamps: list = []
_RUN_RATE_LIMIT = 30  # per minute
_BG_PROC_TIMEOUT = 300  # 5 minutes


async def _cleanup_bg_proc(proc: asyncio.subprocess.Process) -> None:
    """Kill background process after timeout."""
    try:
        await asyncio.wait_for(proc.wait(), timeout=_BG_PROC_TIMEOUT)
    except asyncio.TimeoutError:
        proc.kill()
        log.warning("Background process pid=%d killed after %ds timeout", proc.pid, _BG_PROC_TIMEOUT)


async def handle_run(request: web.Request) -> web.Response:
    """Run a command and return output. No CORS — localhost WebView only."""
    origin = request.headers.get("Origin", "")
    if origin and origin not in _ALLOWED_ORIGINS and origin != "null":
        return web.Response(status=403, text='{"error":"forbidden"}', content_type="application/json")

    now = _time.time()
    _run_timestamps[:] = [t for t in _run_timestamps if now - t < 60]
    if len(_run_timestamps) >= _RUN_RATE_LIMIT:
        return web.Response(status=429, text='{"error":"rate limited"}', content_type="application/json")
    _run_timestamps.append(now)

    try:
        body = await request.json()
    except Exception:
        return web.Response(status=400, text='{"error":"invalid json"}', content_type="application/json")
    cmd = body.get("command", "").strip()
    if not cmd:
        return web.Response(status=400, text='{"error":"no command"}', content_type="application/json")

    cwd = body.get("cwd") or str(Path.home())
    try:
        resolved_cwd = Path(cwd).resolve()
        if not str(resolved_cwd).startswith(str(Path.home())):
            return web.Response(status=403, text='{"error":"cwd outside home"}', content_type="application/json")
        cwd = str(resolved_cwd)
    except (ValueError, RuntimeError):
        return web.Response(status=400, text='{"error":"invalid cwd"}', content_type="application/json")

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


# ---------------------------------------------------------------------------
# Todos / tasks
# ---------------------------------------------------------------------------
async def handle_get_todos(_request: web.Request) -> web.Response:
    """Return active Claude Code todos and team tasks."""
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


# ---------------------------------------------------------------------------
# Preferences (persisted server-side)
# ---------------------------------------------------------------------------
async def handle_get_prefs(_request: web.Request) -> web.Response:
    prefs = await asyncio.to_thread(load_prefs)
    return cors(web.Response(
        content_type="application/json",
        text=json.dumps(prefs),
    ))


async def handle_put_prefs(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return cors(web.Response(status=400, text="Invalid JSON"))
    # Merge with existing prefs (partial updates allowed)
    prefs = await asyncio.to_thread(load_prefs)
    prefs.update(body)
    await asyncio.to_thread(save_prefs, prefs)
    return cors(web.Response(
        content_type="application/json",
        text=json.dumps(prefs),
    ))


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------
async def _handle_favicon(_request: web.Request) -> web.Response:
    return web.Response(status=204)


async def _get_session_info(session) -> dict:
    """Get cwd, job, and git status for a single iTerm2 session object."""
    cwd = await session.async_get_variable("path") or ""
    job = await session.async_get_variable("jobName") or ""
    git_info = await _get_git_status(cwd) if cwd else None
    return {
        "session_id": session.session_id or "",
        "cwd": cwd,
        "job": job,
        "git": git_info,
    }


async def handle_get_session_status(request: web.Request) -> web.Response:
    """Return live session info: cwd, foreground job, and git state.

    ?scope=tab returns all panes in the active tab as a `panels` array.
    Default returns the active session only.
    """
    if not ITERM2_AVAILABLE:
        return cors(web.Response(
            status=501,
            content_type="application/json",
            text=json.dumps({"error": "iTerm2 not available"}),
        ))

    connection = get_iterm2_connection()
    if not connection:
        return cors(web.Response(
            status=503,
            content_type="application/json",
            text=json.dumps({"error": "iTerm2 connection not ready"}),
        ))

    scope = request.query.get("scope", "panel")

    try:
        app = await _iterm2.async_get_app(connection)
        tab = app.current_terminal_window.current_tab

        if scope == "tab":
            panels = await asyncio.gather(
                *[_get_session_info(s) for s in tab.sessions]
            )
            return cors(web.Response(
                content_type="application/json",
                text=json.dumps({"panels": list(panels)}),
            ))

        # Single-panel (default)
        info = await _get_session_info(tab.current_session)
        return cors(web.Response(
            content_type="application/json",
            text=json.dumps(info),
        ))

    except Exception as exc:
        log.warning("Session status lookup failed: %s", exc)
        return cors(web.Response(
            status=503,
            content_type="application/json",
            text=json.dumps({"error": str(exc)}),
        ))


async def _get_git_status(cwd: str) -> dict | None:
    """Run git commands in cwd to get branch, dirty count, ahead/behind.

    Uses create_subprocess_exec (not shell) — all arguments are hardcoded
    strings, no user input is interpolated.
    """
    try:
        # Check if it's a git repo
        proc = await asyncio.create_subprocess_exec(
            "git", "rev-parse", "--is-inside-work-tree",
            cwd=cwd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=3)
        if proc.returncode != 0:
            return None

        # Branch name
        proc = await asyncio.create_subprocess_exec(
            "git", "rev-parse", "--abbrev-ref", "HEAD",
            cwd=cwd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=3)
        branch = stdout.decode().strip() if proc.returncode == 0 else ""

        # Dirty file count
        proc = await asyncio.create_subprocess_exec(
            "git", "status", "--porcelain",
            cwd=cwd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=3)
        dirty = len([line for line in stdout.decode().splitlines() if line.strip()]) if proc.returncode == 0 else 0

        # Ahead/behind upstream
        ahead, behind = 0, 0
        proc = await asyncio.create_subprocess_exec(
            "git", "rev-list", "--count", "--left-right", "HEAD...@{upstream}",
            cwd=cwd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=3)
        if proc.returncode == 0:
            parts = stdout.decode().strip().split("\t")
            if len(parts) == 2:
                ahead, behind = int(parts[0]), int(parts[1])

        return {
            "branch": branch,
            "dirty": dirty,
            "ahead": ahead,
            "behind": behind,
        }
    except (asyncio.TimeoutError, Exception) as exc:
        log.warning("Git status check failed in %s: %s", cwd, exc)
        return None


async def handle_health(request: web.Request) -> web.Response:
    from . import WATCHDOG_AVAILABLE, ITERM2_AVAILABLE
    uptime = (datetime.now(timezone.utc) - get_start_time()).total_seconds()
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
    _sse_lock = get_sse_lock()
    _sse_clients = get_sse_clients()

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
