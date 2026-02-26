#!/usr/bin/env bash
# session-register.sh — Claude Code SessionStart/SessionEnd hook
#
# Registers/unregisters the Claude session with the scratchpad server
# so the todo board can filter by project.
#
# Hook data comes via stdin as JSON:
#   { "session_id": "...", "cwd": "...", "session_file": "..." }

set -euo pipefail

SERVER="${SCRATCHPAD_URL:-http://localhost:9999}"
ACTION="${1:-register}"  # "register" or "unregister"

# Read hook data from stdin
INPUT="$(cat)"

SESSION_ID="$(printf '%s' "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)"
if [[ -z "$SESSION_ID" ]]; then
    exit 0  # No session ID, nothing to do
fi

CWD="$(printf '%s' "$INPUT" | jq -r '.cwd // empty' 2>/dev/null)"
GIT_BRANCH="$(printf '%s' "$INPUT" | jq -r '.git_branch // empty' 2>/dev/null)"

# Derive project key from cwd (same slug format as Claude Code)
PROJECT_KEY=""
if [[ -n "$CWD" ]]; then
    PROJECT_KEY="$(printf '%s' "$CWD" | sed 's|/|-|g')"
fi

# Get iTerm2 session ID from environment if available
ITERM_SESSION="${ITERM_SESSION_ID:-}"

if [[ "$ACTION" == "register" ]]; then
    PAYLOAD="$(jq -cn \
        --arg sid "$SESSION_ID" \
        --arg cwd "$CWD" \
        --arg pk "$PROJECT_KEY" \
        --arg is "$ITERM_SESSION" \
        --arg gb "$GIT_BRANCH" \
        --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        '{session_id: $sid, cwd: $cwd, project_key: $pk, iterm_session: $is, git_branch: $gb, started_at: $ts}')"
    curl -sf -X POST "${SERVER}/api/sessions/register" \
        -H 'Content-Type: application/json' \
        -d "$PAYLOAD" >/dev/null 2>&1 || true
else
    PAYLOAD="$(jq -cn --arg sid "$SESSION_ID" '{session_id: $sid}')"
    curl -sf -X POST "${SERVER}/api/sessions/unregister" \
        -H 'Content-Type: application/json' \
        -d "$PAYLOAD" >/dev/null 2>&1 || true
fi
