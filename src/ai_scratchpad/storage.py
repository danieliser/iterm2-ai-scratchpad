"""Note/session persistence, summary cache, and session ID management."""

import json
import logging
import os
import re
import tempfile
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
DEFAULT_SESSION = "default"

# Active iTerm2 session UUID — updated by session monitor when running inside iTerm2
_current_session_id: str = DEFAULT_SESSION

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
