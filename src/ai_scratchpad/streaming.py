"""SSE broadcast, asyncio.Lock, watchdog file handlers, and debounce."""

import asyncio
import json
import logging
import os
import threading

from . import WATCHDOG_AVAILABLE
from .storage import NOTES_DIR, CLAUDE_TODOS_DIR, CLAUDE_TASKS_DIR

if WATCHDOG_AVAILABLE:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler

log = logging.getLogger(__name__)

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


def get_sse_clients() -> set:
    return _sse_clients


def get_sse_lock() -> asyncio.Lock:
    return _sse_lock


# ---------------------------------------------------------------------------
# Watchdog file monitor
# Thread-safe: _debounce_lock guards the timer dict across watchdog + timer threads.
# ---------------------------------------------------------------------------
_debounce_timers: dict = {}
_debounce_lock = threading.Lock()
_event_loop: asyncio.AbstractEventLoop | None = None


def set_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _event_loop
    _event_loop = loop


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
# Polling fallback when watchdog is unavailable
# ---------------------------------------------------------------------------

def _dir_mtime(path: "os.PathLike[str]") -> float:
    """Get the latest mtime of any .json file in a directory (non-recursive)."""
    best = 0.0
    d = str(path)
    try:
        for entry in os.scandir(d):
            if entry.name.endswith(".json") and entry.is_file():
                try:
                    best = max(best, entry.stat().st_mtime)
                except OSError:
                    pass
    except OSError:
        pass
    return best


def _dir_mtime_recursive(path: "os.PathLike[str]") -> float:
    """Get the latest mtime of any .json file in a directory tree."""
    best = 0.0
    d = str(path)
    try:
        for root, _dirs, files in os.walk(d):
            for f in files:
                if f.endswith(".json"):
                    try:
                        best = max(best, os.stat(os.path.join(root, f)).st_mtime)
                    except OSError:
                        pass
    except OSError:
        pass
    return best


async def _poll_notes(interval: float = 2.0) -> None:
    """Poll NOTES_DIR for changes and broadcast notes_updated."""
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    last_mtime = _dir_mtime(NOTES_DIR)
    log.info("Polling notes dir %s (interval=%.1fs)", NOTES_DIR, interval)
    while True:
        await asyncio.sleep(interval)
        current = _dir_mtime(NOTES_DIR)
        if current > last_mtime:
            last_mtime = current
            await broadcast("notes_updated", {})


async def _poll_todos(interval: float = 2.0) -> None:
    """Poll Claude todo/task dirs for changes and broadcast todos_updated."""
    dirs = []
    if CLAUDE_TODOS_DIR.exists():
        dirs.append(("todos", CLAUDE_TODOS_DIR, False))
    if CLAUDE_TASKS_DIR.exists():
        dirs.append(("tasks", CLAUDE_TASKS_DIR, True))
    if not dirs:
        log.info("No Claude todo/task directories found — skipping poll")
        return
    log.info("Polling todo dirs %s (interval=%.1fs)",
             ", ".join(str(d) for _, d, _ in dirs), interval)
    last_mtimes = {
        name: (_dir_mtime_recursive(d) if recursive else _dir_mtime(d))
        for name, d, recursive in dirs
    }
    while True:
        await asyncio.sleep(interval)
        for name, d, recursive in dirs:
            current = _dir_mtime_recursive(d) if recursive else _dir_mtime(d)
            if current > last_mtimes[name]:
                last_mtimes[name] = current
                await broadcast("todos_updated", {"path": str(d)})


def start_poll_fallback() -> list[asyncio.Task]:
    """Start polling tasks for notes and todos when watchdog is unavailable.

    Must be called from an async context (event loop running).
    Returns list of asyncio tasks that can be cancelled for cleanup.
    """
    tasks = []
    tasks.append(asyncio.ensure_future(_poll_notes()))
    tasks.append(asyncio.ensure_future(_poll_todos()))
    log.info("Started polling fallback (watchdog unavailable)")
    return tasks
