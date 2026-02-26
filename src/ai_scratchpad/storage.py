"""Note/session persistence, summary cache, and session ID management."""

import json
import logging
import os
import re
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Directories
# ---------------------------------------------------------------------------
NOTES_DIR = Path.home() / ".config" / "iterm2-scratchpad" / "notes" / "by-session"
CLAUDE_TODOS_DIR = Path.home() / ".claude" / "todos"
CLAUDE_TASKS_DIR = Path.home() / ".claude" / "tasks"
CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"
SUMMARY_CACHE_PATH = Path.home() / ".config" / "iterm2-scratchpad" / "session-summaries.json"
PREFS_PATH = Path.home() / ".config" / "iterm2-scratchpad" / "prefs.json"
SESSIONS_REGISTRY_PATH = Path.home() / ".config" / "iterm2-scratchpad" / "active-sessions.json"
DEFAULT_SESSION = "default"

# Active iTerm2 session UUID — updated by session monitor when running inside iTerm2
_current_session_id: str = DEFAULT_SESSION

# Active iTerm2 tab's session IDs — all panes/splits in the current tab
_current_tab_session_ids: list[str] = []

# iTerm2 connection reference — set by session monitor for tab activation
_iterm2_connection = None

# Server start time for uptime reporting
_start_time: datetime = datetime.now(timezone.utc)

# Session summary cache — maps session UUID prefix to first user message
_summary_cache: dict = {}
_summary_cache_loaded = False

_SESSION_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def get_start_time() -> datetime:
    return _start_time


def get_current_session_id() -> str:
    return _current_session_id


def set_current_session_id(value: str) -> None:
    global _current_session_id
    _current_session_id = value


def get_current_tab_session_ids() -> list[str]:
    return _current_tab_session_ids


def set_current_tab_session_ids(ids: list[str]) -> None:
    global _current_tab_session_ids
    _current_tab_session_ids = ids


def load_tab_notes(session_ids: list[str], max_notes: int = 200) -> list:
    """Load and merge notes from all sessions in a tab."""
    all_notes = []
    for sid in session_ids:
        notes = load_notes(sid)
        all_notes.extend(notes)
    all_notes.sort(key=lambda n: n.get("timestamp", ""))
    if len(all_notes) > max_notes:
        all_notes = all_notes[-max_notes:]
    return all_notes


def get_iterm2_connection():
    return _iterm2_connection


def set_iterm2_connection(conn) -> None:
    global _iterm2_connection
    _iterm2_connection = conn


# ---------------------------------------------------------------------------
# Active Claude session registry
# ---------------------------------------------------------------------------
_sessions_registry_lock = threading.Lock()


def _load_sessions_registry() -> dict:
    """Load active sessions from disk."""
    try:
        if SESSIONS_REGISTRY_PATH.exists():
            return json.loads(SESSIONS_REGISTRY_PATH.read_text())
    except Exception:
        pass
    return {}


def _save_sessions_registry(data: dict) -> None:
    """Atomically save active sessions to disk."""
    SESSIONS_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(
        mode="w", dir=SESSIONS_REGISTRY_PATH.parent,
        suffix=".tmp", delete=False,
    )
    try:
        json.dump(data, tmp, indent=2)
        tmp.close()
        os.replace(tmp.name, SESSIONS_REGISTRY_PATH)
    except Exception:
        tmp.close()
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
        raise


def register_session(session_id: str, data: dict) -> None:
    """Register an active Claude Code session."""
    with _sessions_registry_lock:
        registry = _load_sessions_registry()
        registry[session_id] = {
            "session_id": session_id,
            "cwd": data.get("cwd", ""),
            "project_key": data.get("project_key", ""),
            "iterm_session": data.get("iterm_session", ""),
            "git_branch": data.get("git_branch", ""),
            "started_at": data.get("started_at", ""),
        }
        _save_sessions_registry(registry)


def unregister_session(session_id: str) -> None:
    """Remove a Claude Code session from the registry."""
    with _sessions_registry_lock:
        registry = _load_sessions_registry()
        registry.pop(session_id, None)
        _save_sessions_registry(registry)


def get_active_sessions() -> dict:
    """Return the active sessions registry."""
    return _load_sessions_registry()


def get_project_session_ids(project_key: str) -> set[str]:
    """Return Claude session IDs that belong to a given project."""
    registry = _load_sessions_registry()
    return {
        sid for sid, info in registry.items()
        if info.get("project_key") == project_key
    }


def get_active_project_keys() -> set[str]:
    """Return project keys from all active sessions."""
    registry = _load_sessions_registry()
    return {
        info.get("project_key")
        for info in registry.values()
        if info.get("project_key")
    }


# ---------------------------------------------------------------------------
# Summary cache
# ---------------------------------------------------------------------------
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
    if stripped.startswith("<command-message>"):
        return True
    if stripped.startswith(("Base directory", "You are ")):
        return True
    if "Your name is **" in content[:200] or "you are executing tasks" in content[:300].lower():
        return True
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

                if user_count == 1 and "<command-name>" in content:
                    command_name = _extract_command_name(content)
                    continue

                if _is_system_content(content):
                    continue

                for raw_line in content.split("\n"):
                    text = raw_line.strip().lstrip("#").strip()
                    if text and len(text) > 5 and " " in text:
                        return text[:100]

        return command_name
    except Exception:
        return ""


def get_session_summary(session_id: str) -> str:
    """Get a human-readable summary for a session, using cache."""
    cache = _load_summary_cache()
    if session_id in cache:
        return cache[session_id]

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

    _summary_cache[session_id] = ""
    _save_summary_cache()
    return ""


# ---------------------------------------------------------------------------
# Note persistence
# ---------------------------------------------------------------------------
# Per-session locks prevent read-modify-write races when concurrent
# requests write to the same session file.
_session_locks: dict[str, threading.Lock] = {}
_session_locks_guard = threading.Lock()


def _get_session_lock(session_id: str) -> threading.Lock:
    with _session_locks_guard:
        if session_id not in _session_locks:
            _session_locks[session_id] = threading.Lock()
        return _session_locks[session_id]


def notes_path(session_id: str = DEFAULT_SESSION) -> Path:
    if not _SESSION_ID_RE.match(session_id):
        raise ValueError(f"Invalid session_id: {session_id!r}")
    return NOTES_DIR / f"{session_id}.json"


def load_notes(session_id: str = DEFAULT_SESSION) -> list:
    path = notes_path(session_id)
    if not path.exists():
        return []
    try:
        notes = json.loads(path.read_text())
        for n in notes:
            n.setdefault("session_id", session_id)
        return notes
    except Exception as exc:
        log.error("Failed to read notes from %s: %s", path, exc)
        return []


def load_all_notes(max_age_hours: int = 24, max_notes: int = 200) -> list:
    """Load and merge notes from ALL session files, sorted by timestamp.

    Filters to notes from the last *max_age_hours* and caps at *max_notes*
    (most recent first) to prevent stale history from cluttering the UI.
    """
    all_notes = []
    if not NOTES_DIR.exists():
        return []

    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).isoformat()

    for path in NOTES_DIR.glob("*.json"):
        try:
            sid = path.stem
            notes = json.loads(path.read_text())
            if isinstance(notes, list):
                for n in notes:
                    if n.get("timestamp", "") >= cutoff:
                        n.setdefault("session_id", sid)
                        all_notes.append(n)
        except Exception as exc:
            log.error("Failed to read notes from %s: %s", path, exc)
    all_notes.sort(key=lambda n: n.get("timestamp", ""))
    if len(all_notes) > max_notes:
        all_notes = all_notes[-max_notes:]
    return all_notes


def save_notes(notes: list, session_id: str = DEFAULT_SESSION) -> None:
    path = notes_path(session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(notes, indent=2)
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


def append_note(note: dict, session_id: str = DEFAULT_SESSION) -> None:
    """Atomically load→append→save a note. Prevents concurrent write races."""
    lock = _get_session_lock(session_id)
    with lock:
        notes = load_notes(session_id)
        notes.append(note)
        save_notes(notes, session_id)


def update_note_in_file(note_id: str, updates: dict) -> dict | None:
    """Find a note across all session files and update it atomically.

    Returns the updated note dict, or None if not found.
    """
    if not NOTES_DIR.exists():
        return None
    for path in NOTES_DIR.glob("*.json"):
        sid = path.stem
        lock = _get_session_lock(sid)
        with lock:
            try:
                notes = json.loads(path.read_text())
                if not isinstance(notes, list):
                    continue
                for note in notes:
                    if note.get("id") == note_id:
                        note.update(updates)
                        save_notes(notes, sid)
                        return note
            except Exception:
                continue
    return None


# ---------------------------------------------------------------------------
# User preferences (persisted server-side, survives WKWebView reloads)
# ---------------------------------------------------------------------------
_prefs_lock = threading.Lock()

_DEFAULT_PREFS = {
    "scope": "all",
    "filter": {"source": "all", "status": "all", "searchText": ""},
    "sort": {"field": "timestamp", "order": "desc"},
    "pinned": [],
}


def load_prefs() -> dict:
    with _prefs_lock:
        if PREFS_PATH.exists():
            try:
                prefs = json.loads(PREFS_PATH.read_text())
                # Merge with defaults for any missing keys
                return {**_DEFAULT_PREFS, **prefs}
            except Exception:
                pass
        return dict(_DEFAULT_PREFS)


def save_prefs(prefs: dict) -> None:
    with _prefs_lock:
        PREFS_PATH.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=PREFS_PATH.parent, prefix=".prefs_tmp_")
        try:
            os.write(fd, json.dumps(prefs, indent=2).encode())
            os.fsync(fd)
            os.close(fd)
            os.replace(tmp, PREFS_PATH)
        except Exception:
            os.close(fd)
            os.unlink(tmp)
            raise
