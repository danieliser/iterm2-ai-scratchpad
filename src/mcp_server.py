#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["mcp[cli]>=1.0"]
# ///
"""MCP server for AI Scratchpad — lets Claude Code agents post notes."""

import json
import os
import urllib.request
from mcp.server.fastmcp import FastMCP

SCRATCHPAD_URL = "http://localhost:9999"

mcp = FastMCP(
    "ai-scratchpad",
    instructions="""\
Post notes to the AI Scratchpad sidebar. Notes support markdown and rich widgets.

## When to use it

- **Status updates** — post progress on multi-step tasks so the user can glance at the sidebar
- **Build/deploy results** — badges and progress bars for pipeline status
- **Data summaries** — key-value pairs, metrics, charts for quick reference
- **Architecture notes** — mermaid diagrams, file trees when explaining structure
- **Runnable commands** — give the user clickable run buttons for common operations
- **Task tracking** — todo checklists for complex work

## When NOT to use it

- Don't post every minor action — it's a dashboard, not a log stream
- Don't duplicate what's already visible in the terminal output
- If the scratchpad server isn't running, the tool returns a graceful error — just continue without it

## Source labels

Use the `source` parameter to categorize notes for filtering:
- `"agent"` — general agent output (default)
- `"ci"` — build/deploy/pipeline status
- `"monitor"` — health checks, metrics, port status
- `"debug"` — debugging sessions, error analysis

## Updating notes

`post_note` returns an ID. Use `update_note(note_id, text)` to replace a note's \
content in-place — ideal for status cards, progress indicators, or anything that \
should refresh rather than duplicate.\
""",
)


def _default_source() -> str:
    """Derive a human-readable source: project:session_prefix."""
    cwd = os.environ.get("PWD", os.getcwd())
    project = os.path.basename(cwd) or "agent"
    session = _iterm_session_id()
    prefix = session[:7] if session else ""
    return f"{project}:{prefix}" if prefix else project


def _iterm_session_id() -> str:
    """Extract the iTerm2 session UUID from the agent's environment.

    ITERM_SESSION_ID has format "w0t2p0:UUID" — we want just the UUID part.
    This tells the server which terminal the agent is running in, so the note
    gets tagged to the correct session regardless of which tab has UI focus.
    """
    raw = os.environ.get("ITERM_SESSION_ID", "")
    if ":" in raw:
        return raw.split(":", 1)[1]
    return raw


@mcp.tool()
def post_note(text: str, source: str = "agent") -> str:
    """Post a note to the AI Scratchpad sidebar.

    Notes appear in real-time in the iTerm2 sidebar. Content is markdown with
    optional rich widgets using bracket syntax.

    ## Markdown
    Standard markdown: **bold**, *italic*, `code`, ```code blocks```, lists, links, etc.
    Also supports ### headings, ---, unordered lists (- item), and markdown tables.

    ## Widgets
    Embed interactive widgets using bracket syntax. Two forms:
    - Inline: [type:arg1:arg2] — self-closing, single line
    - Block: [type]content[/type] — wraps multi-line content

    **Status & Progress:**
    - [status:success:Deployed] — badge (success|warning|error|info), label optional
    - [progress:75] or [progress:75:Building...] — progress bar 0-100, label optional
    - [metric:42ms:Latency] or [metric:99%:Uptime:up] — big number (trend: up|down|flat)

    **Data Display (block widgets):**
    - [kv]Key1=Value1\\nKey2=Value2[/kv] — key-value pairs, one per line
    - [log:info]line1\\nline2[/log] — log block (error|warn|info|debug)
    - [diff]-removed line\\n+added line\\n context line[/diff] — diff view

    **Interactive:**
    - [todo]Item 1\\n[x]Done item\\nItem 3[/todo] — checklist, [x] prefix = checked
    - [details:Summary]Hidden content shown on click[/details] — collapsible
    - [timer:5m:Label] — countdown timer (5m, 1h30m, 90s), label optional
    - [clip:Button Label]text to copy[/clip] — click-to-copy

    **Rich Content:**
    - [link:Title:https://example.com] — clickable link card
    - [tree]src/\\n  src/main.ts\\n  src/lib/[/tree] — file tree (dirs end with /)
    - [chart:10,45,30,80:Requests/s] — sparkline chart, label optional
    - [deadline:2026-03-01T00:00:00:Launch day] — countdown to date, label optional
    - [ports:3000,5432,9999] — live port status monitor
    - [mermaid]graph LR\\n  A-->B[/mermaid] — mermaid diagram
    - [run:Label]shell command[/run] — executable command with Run/BG buttons

    **Combinable:** Mix markdown and widgets freely in a single note.

    Args:
        text: The note content (markdown + widgets)
        source: Label for who posted it (default: "agent")
    """
    # Enrich source with project context when it's the generic default
    effective_source = source if source not in ("agent", "unknown", "") else _default_source()

    payload: dict = {"text": text, "source": effective_source}

    # Tag note to the agent's terminal session, not the focused tab
    session_id = _iterm_session_id()
    if session_id:
        payload["session_id"] = session_id

    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{SCRATCHPAD_URL}/api/notes",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=2)
        result = json.loads(resp.read())
        return f"Note posted (id={result.get('id', '?')})"
    except Exception:
        return "Note not posted — scratchpad server is not running. Continue without it."


@mcp.tool()
def update_note(note_id: str, text: str, source: str = "") -> str:
    """Update an existing note's content. Use this to replace a note in-place
    instead of posting a new one — ideal for status cards, progress indicators,
    or any note that should refresh rather than duplicate.

    Args:
        note_id: The note ID returned by post_note (e.g. "abc-123...")
        text: The new markdown + widget content to replace the note with
        source: Optional new source label (omit to keep existing)
    """
    payload: dict = {"text": text}
    if source:
        payload["source"] = source

    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{SCRATCHPAD_URL}/api/notes/{note_id}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="PUT",
    )
    try:
        resp = urllib.request.urlopen(req, timeout=2)
        result = json.loads(resp.read())
        if result.get("status") == "ok":
            return f"Note updated (id={note_id})"
        return f"Update failed: {result}"
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return f"Note {note_id} not found — it may have been cleared. Post a new note instead."
        return f"Update failed (HTTP {e.code})"
    except Exception:
        return "Update failed — scratchpad server is not running. Continue without it."


if __name__ == "__main__":
    mcp.run()
