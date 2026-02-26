---
name: ai-scratchpad
description: Post notes, status updates, and rich widgets to the iTerm2 AI Scratchpad sidebar
version: 0.1.0
metadata:
  openclaw:
    requirements:
      binaries: [curl]
---

# AI Scratchpad

Post notes to the iTerm2 AI Scratchpad sidebar running at `http://localhost:9999`. The scratchpad is a real-time dashboard in iTerm2's toolbelt — use it for status updates, metrics, task tracking, and anything the user should see at a glance without interrupting the terminal.

## Posting a note

```bash
curl -s -X POST http://localhost:9999/api/notes \
  -H 'Content-Type: application/json' \
  -d '{"text": "Your markdown content here", "source": "openclaw"}'
```

### Parameters

| Field | Required | Description |
|-------|----------|-------------|
| `text` | yes | Markdown content, supports widget syntax below |
| `source` | no | Label for filtering: `openclaw` (default), `ci`, `monitor`, `debug` |

### Other endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/notes` | List all notes |
| `DELETE` | `/api/notes` | Clear all notes |
| `PATCH` | `/api/notes/{id}` | Update note status (`{"status": "done"}`) |
| `GET` | `/health` | Health check |

## Widget syntax

Embed rich widgets in the `text` field using bracket syntax. Two forms: inline `[type:arg1:arg2]` and block `[type]content[/type]`.

### Inline widgets

- `[status:success:Build Passed]` — badge (success|warning|error|info)
- `[progress:75:Deploying...]` — progress bar 0-100
- `[metric:42ms:Latency:down]` — big number with trend (up|down|flat)
- `[timer:5m:Label]` — countdown (5m, 1h30m, 90s)
- `[chart:10,45,30,80:Label]` — sparkline
- `[link:Title:https://url]` — clickable link card
- `[ports:3000,5432]` — live port status indicators

### Block widgets

- `[kv]Key=Value\nKey2=Value2[/kv]` — key-value table
- `[todo]Task 1\n[x]Done task\nTask 3[/todo]` — interactive checklist
- `[diff]-removed line\n+added line[/diff]` — diff view
- `[log:error]Error messages here[/log]` — log block (error|warn|info|debug)
- `[tree]src/\n  src/main.ts\n  src/utils.ts[/tree]` — file tree
- `[mermaid]graph LR\n  A-->B[/mermaid]` — diagram
- `[run:Run Tests]pytest -x[/run]` — executable command button
- `[clip:Copy Token]abc123xyz[/clip]` — click-to-copy
- `[details:Show More]Hidden content here[/details]` — collapsible section

### Example: rich status update

```bash
curl -s -X POST http://localhost:9999/api/notes \
  -H 'Content-Type: application/json' \
  -d '{
    "text": "## Deploy Pipeline\n[status:success:Build Passed] [status:warning:Staging]\n\n[progress:78:Deploying to staging...]\n\n[kv]Branch=main\nCommits=12 ahead of master\nCoverage=87.3%[/kv]",
    "source": "ci"
  }'
```

## When to use

- Status updates on multi-step tasks
- Build/deploy results with badges and progress bars
- Data summaries with key-value pairs, metrics, or charts
- Task checklists for complex work
- Architecture diagrams or file trees when explaining structure

## When NOT to use

- Don't post every minor action — it's a dashboard, not a log stream
- Don't duplicate what's already visible in the terminal
- If the server isn't running (`curl` fails), continue without it
