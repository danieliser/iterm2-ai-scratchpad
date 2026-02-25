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
