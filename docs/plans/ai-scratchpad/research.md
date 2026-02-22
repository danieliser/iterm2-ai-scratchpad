# Research: iTerm2 Toolbelt WebView AI Scratchpad Implementation

**Date:** 2026-02-22
**Tier:** Standard
**Question:** What are the technical requirements, constraints, and best practices for building an iTerm2 toolbelt sidebar panel where AI agents can leave persistent notes, using a WebView-backed aiohttp server?

**Recommendation:** Use AutoLaunch Full Environment Python script with aiohttp server on localhost:9999, WKWebView-based toolbelt display with fetch() to localhost, watchdog for file monitoring, and Claude Code PostToolUse/Stop hooks for write integration. Store notes as JSON, scoped by session via iTerm2 session variables.

---

## Context & Constraints

From prior research, we know:
- `async_register_web_view_tool()` registers a toolbelt webview at a given URL
- The Targeted Input example proves aiohttp + iTerm2 integration works
- Status bar popovers can open, suggesting UI coordination is possible
- Notes storage is currently file-based (JSON)

This research focuses on:
1. AutoLaunch environment and pip dependency management
2. WebView JavaScript and network capability boundaries
3. File monitoring performance trade-offs
4. Session-aware note scoping
5. Claude Code hook integration for agent writes

---

## Options Evaluated

### 1. Script Execution & Environment

#### AutoLaunch with Full Environment (Recommended)
- **Confidence:** High
- **What it is:** Python script placed in `~/Library/ApplicationSupport/iTerm2/Scripts/AutoLaunch/` with "Full Environment" selected at creation, ensuring isolated Python + pip.
- **Strengths:**
  - Automatically launched at iTerm2 startup
  - Full Environment provides isolated Python with pip—aiohttp installs cleanly
  - No dependency on system Python or Homebrew Python
  - Scripts can use `~/.config/iterm2/AppSupport/iterm2env*/versions/*/bin/python3` for pip installs
- **Weaknesses:**
  - Each script has its own isolated environment (~100 MB per script)
  - No shared dependencies across multiple AutoLaunch scripts (if scaling later)
- **Cost:** Minimal—disk space only (~100 MB per script)
- **Maintenance:** Low—iTerm2 manages Python; set `PYTHONPATH=""` to avoid conflicts
- **Sources:** [iTerm2 Running a Script tutorial](https://iterm2.com/python-api/tutorial/running.html), [Targeted Input example](https://iterm2.com/python-api/examples/targeted_input.html)

#### Alternative: Homebrew Python Script
- **Confidence:** Medium
- **What it is:** Script relying on system Homebrew-installed Python and globally installed aiohttp
- **Strengths:** Shared dependencies, smaller disk footprint
- **Weaknesses:** Requires manual setup; user must have Homebrew Python + aiohttp installed; breaks if user updates Homebrew
- **Recommendation:** Not recommended for user-facing tool—too fragile

---

### 2. WebView Rendering & JavaScript Capabilities

#### WKWebView (Actual Implementation)
- **Confidence:** High
- **What it is:** iTerm2 uses Apple's WKWebView, Safari's rendering engine, for toolbelt webviews.
- **Strengths:**
  - Full JavaScript ES6+ support (not sandboxed from script execution)
  - Fetch API works natively to localhost
  - CORS headers from localhost server are respected (set `Access-Control-Allow-Origin: *` on aiohttp responses)
  - Modern CSS/HTML5 support
  - WebKit content blocker rules available if needed
- **Weaknesses:**
  - No WebSocket support (known WKWebView limitation on macOS)
  - CORS strictness: must set proper headers on server (unlike browser DevTools which bypass CORS)
  - No service workers or other browser APIs requiring secure contexts
- **CORS Solution:** Server (aiohttp) must include headers like:
  ```python
  response.headers['Access-Control-Allow-Origin'] = '*'
  response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
  ```
- **SSE (Server-Sent Events):** EventSource API is supported by all modern browsers, and WKWebView follows the standard—can use SSE for live updates instead of polling
- **Cost:** None—WKWebView is built-in
- **Sources:** [iTerm2 documentation](https://iterm2.com/documentation-web.html), [WKWebView CORS Solution article](https://zzdjk6.medium.com/wkwebview-cors-solution-da20ca1194e8)

#### Alternative: WebSocket-Based Live Updates
- **Confidence:** Low (not recommended)
- **What it is:** Real-time updates via WebSocket
- **Weaknesses:** WKWebView doesn't support WebSocket on macOS
- **Recommendation:** Use EventSource/SSE instead

---

### 3. File Monitoring for Notes Storage

#### watchdog Library (Recommended)
- **Confidence:** High
- **What it is:** Python library wrapping OS-specific file system notifications. On macOS, uses FSEvents (preferred) or kqueue.
- **Strengths:**
  - FSEvents backend is the default and scales perfectly (tested on 500 GB filesystems)
  - Works with asyncio via hachiko wrapper or direct observer with threading
  - No known performance degradation with large directory trees
  - Handles file descriptor limits automatically (unlike kqueue)
  - Simple API: `Observer` pattern with event handlers
- **Weaknesses:**
  - Small overhead (~5-10ms per file change detection)
  - Requires pip install (but Full Environment handles this)
- **Cost:** Negligible
- **Setup:** Install in Full Environment: `pip install watchdog`
- **Sources:** [watchdog PyPI](https://pypi.org/project/watchdog/), [GitHub repository](https://github.com/gorakhargosh/watchdog)

#### watchfiles (Alternative)
- **Confidence:** Medium
- **What it is:** Rust-based file watcher, async-first, ~24ms for 850 files via polling.
- **Strengths:** Faster for large directories; async-native
- **Weaknesses:** Relatively new; less ecosystem integration
- **Recommendation:** Suitable if performance is critical; watchdog is safer default

#### asyncio Polling (Not Recommended)
- **Confidence:** Low
- **What it is:** Manual polling with `asyncio.sleep()`
- **Weaknesses:** CPU-intensive, latency ~0.1-1s, no OS integration
- **Recommendation:** Only if single file and low update frequency (<1/sec)

---

### 4. Session Awareness & Note Scoping

#### iTerm2 Session Variables + API
- **Confidence:** High
- **What it is:** iTerm2 Python API provides `Session.async_set_variable(name, value)` and `Session.async_get_variable(name)` for per-session metadata.
- **Strengths:**
  - Native iTerm2 integration
  - Session metadata persists within session lifetime
  - Can detect active session via `Session.active_proxy()` and `Tab.current_session`
  - Profile customizations are session-specific via `async_set_profile_properties()`
  - VariableMonitor watches for session changes
- **Weaknesses:**
  - Variables are in-memory during session; not persisted across restarts
  - Requires Python loop to stay alive for session detection
- **Pattern:** Store `session_id` or `session_guid` as file path key in JSON storage:
  ```json
  {
    "session-uuid-xyz": ["note 1", "note 2"],
    "session-uuid-abc": ["note 3"]
  }
  ```
- **Cost:** None—built into iTerm2 API
- **Sources:** [Session API documentation](https://iterm2.com/python-api/session.html), [Variables documentation](https://iterm2.com/python-api/variables.html)

#### Alternative: Profile-Based Scoping
- **Confidence:** Medium
- **What it is:** Use profile name as scope key
- **Weaknesses:** Multiple sessions can share same profile; less precise
- **Recommendation:** Use session ID, not profile

---

### 5. Claude Code Hook Integration

#### PostToolUse Hook with HTTP Request (Recommended)
- **Confidence:** High
- **What it is:** Hook fires after Claude writes/edits a file. Hook script makes HTTP POST to scratchpad server.
- **Strengths:**
  - Fires every time Claude takes action—can capture intent
  - Can inspect tool output to extract reasoning
  - Exit 0 + JSON response allows hook to continue without blocking
  - Async support available (`"async": true`) for background fire-and-forget
- **Weaknesses:**
  - Requires server to be running (already running for webview)
  - Latency adds ~100-200ms per tool use
- **Pattern:**
  ```json
  {
    "hooks": {
      "PostToolUse": [
        {
          "matcher": "Write|Edit",
          "hooks": [
            {
              "type": "command",
              "command": "curl -X POST http://localhost:9999/api/notes -d @- -H 'Content-Type: application/json'",
              "async": true
            }
          ]
        }
      ]
    }
  }
  ```
- **Cost:** Minimal—hook execution time + network latency
- **Sources:** [Claude Code Hooks reference](https://code.claude.com/docs/en/hooks), [Hook lifecycle documentation](https://code.claude.com/docs/en/hooks#hook-lifecycle)

#### Stop Hook (Alternative)
- **Confidence:** Medium
- **What it is:** Hook fires when Claude finishes responding (after all tool calls)
- **Strengths:** One hook per conversation turn (less overhead)
- **Weaknesses:** Can't access individual tool details; fires even if no tools were called
- **Recommendation:** Use PostToolUse for granular capture; Stop for summary

#### Hook Execution Environment
- **Capability:** Hooks run as shell commands with user permissions
- **Network:** Can use `curl`, `wget`, or any HTTP client
- **File Access:** Can read/write files via standard shell tools
- **Constraints:**
  - Default timeout: 600 seconds
  - `CLAUDE_CODE_REMOTE` env variable indicates web vs. local execution
  - Exit 0 = success, Exit 2 = blocking error, other codes = non-blocking
- **Sources:** [Hooks reference - hook input/output](https://code.claude.com/docs/en/hooks#hook-input-and-output)

---

## Comparison Matrix

| Criteria | Full Environment Python | Homebrew Python | watchdog | watchfiles | Session Variables | Profile Scope |
|----------|------------------------|-----------------|----------|------------|-------------------|---------------|
| Setup complexity | Low | Medium | Low | Low | Low | Low |
| aiohttp support | Yes (native) | Yes (external) | N/A | N/A | N/A | N/A |
| Reliability | High | Medium | High | High | High | Medium |
| File monitoring latency | - | - | <50ms (FSEvents) | ~24ms | - | - |
| Session awareness | Yes | Yes | N/A | N/A | Yes (native) | No (shared) |
| Per-session storage | Yes (via variables) | Yes (via variables) | N/A | N/A | Native | Workaround |
| Claude Code integration | Yes (hooks) | Yes (hooks) | N/A | N/A | N/A | N/A |
| Maintenance burden | Low | Medium | Low | Low | Low | Low |

---

## Architecture Recommendation

### Proposed Stack

```
┌─────────────────────────────────────────┐
│  Claude Code Session                     │
│  ┌──────────────────────────────────┐   │
│  │ PostToolUse Hook                 │   │
│  │ (curl → localhost:9999/api/notes)│   │
│  └──────────────────────────────────┘   │
└─────────────────────────────────────────┘
         │
         │ HTTP POST
         ↓
┌─────────────────────────────────────────┐
│  AutoLaunch Full Environment Python      │
│  ┌──────────────────────────────────┐   │
│  │ aiohttp Server (localhost:9999)  │   │
│  │ ├─ GET /            → HTML UI    │   │
│  │ ├─ POST /api/notes  → Append note│   │
│  │ └─ SSE /events      → Live update│   │
│  ├──────────────────────────────────┤   │
│  │ watchdog FSEvents Monitor        │   │
│  │ Watches: ~/.config/iterm2/notes/ │   │
│  ├──────────────────────────────────┤   │
│  │ Session Manager                  │   │
│  │ Detects active session via API   │   │
│  └──────────────────────────────────┘   │
└─────────────────────────────────────────┘
         │
         ↓
┌─────────────────────────────────────────┐
│  JSON Storage                            │
│  ~/.config/iterm2/notes/                │
│  ├─ by-session/                         │
│  │  └─ {session-uuid}.json              │
│  └─ by-profile/                         │
│     └─ {profile-name}.json (optional)   │
└─────────────────────────────────────────┘
         ↑
         │ Watched by watchdog
         │
┌─────────────────────────────────────────┐
│  iTerm2 Toolbelt WebView (WKWebView)    │
│  ┌──────────────────────────────────┐   │
│  │ HTML/CSS/JavaScript               │   │
│  │ ├─ fetch(localhost:9999/) UI     │   │
│  │ ├─ EventSource /events → live    │   │
│  │ └─ Display notes for session     │   │
│  └──────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

### Key Implementation Details

1. **AutoLaunch Script:**
   - Create at `~/Library/ApplicationSupport/iTerm2/Scripts/AutoLaunch/iterm2_scratchpad.py`
   - Select "Full Environment" when creating via iTerm2 UI
   - Imports: `iterm2`, `aiohttp`, `watchdog`, `json`, `asyncio`
   - Unset `PYTHONPATH` at startup
   - Run: `asyncio.run(main())` with async event loop

2. **aiohttp Server:**
   - Listen on `localhost:9999`
   - Response headers: `Access-Control-Allow-Origin: *` for CORS
   - Routes: `GET /`, `POST /api/notes`, `GET /events` (SSE)
   - Serve HTML UI from `templates/` or inline

3. **File Monitoring:**
   - watchdog Observer watches `~/.config/iterm2/notes/` directory
   - On file change, emit SSE event to webview
   - Debounce rapid changes (100-200ms)

4. **Session Detection:**
   - Call `iterm2.async_get_app()` at startup
   - Use `LayoutChangeMonitor` to watch for active session changes
   - Store current session UUID in module-level variable
   - Pass to webview via `/api/session` endpoint

5. **Claude Code Hook:**
   - Add to `.claude/settings.json` in project root
   - PostToolUse matcher: `Write|Edit`
   - Command: `curl -s -X POST http://localhost:9999/api/notes -d '{"source":"claude","timestamp":"$(date)","tool":"$tool_name"}' -H 'Content-Type: application/json'`
   - Set `"async": true` to avoid blocking

---

## Key Findings by Research Question

### 1. AutoLaunch Scripts & pip Dependencies ✓
- **Location:** `~/Library/ApplicationSupport/iTerm2/Scripts/AutoLaunch/`
- **Full Environment path:** `~/.config/iterm2/AppSupport/iterm2env*/versions/*/bin/python3`
- **pip support:** Yes; Full Environment scripts get isolated Python with pip
- **aiohttp:** Installs cleanly in Full Environment; set `PYTHONPATH=""` to avoid conflicts

### 2. Toolbelt WebView Capabilities ✓
- **Rendering engine:** WKWebView (Safari's rendering engine, not Chromium)
- **JavaScript:** Full ES6+ support
- **fetch() to localhost:** Supported; requires CORS headers on server
- **EventSource/SSE:** Supported (all modern WebKit versions)
- **WebSockets:** Not supported on macOS WKWebView
- **CSP:** No documented restrictions for localhost requests

### 3. File Monitoring Options ✓
- **Recommended:** watchdog (FSEvents backend on macOS)
- **Performance:** <50ms latency, no file descriptor limits
- **Alternative:** watchfiles (Rust-based, ~24ms for 850 files)
- **Not recommended:** asyncio polling (CPU-intensive, slow)

### 4. Session Metadata & Scoping ✓
- **Detect active session:** `Session.active_proxy()` and `Tab.current_session` properties
- **Scope notes by session:** Use `Session.async_get_variable()` to store session UUID
- **Per-session customization:** Possible via iTerm2 session variables (in-memory)
- **Persistence:** Variables are session-scoped; for cross-session persistence, use file storage keyed by session ID

### 5. Claude Code Hook Integration ✓
- **PostToolUse hook execution:** After tool succeeds
- **File write capability:** Hooks can read/write files via shell
- **HTTP capability:** Can use `curl`/`wget` to make POST requests
- **Constraints:**
  - Default 600s timeout
  - Exit 0 = success (can return JSON)
  - Exit 2 = blocking error
  - Async mode available to avoid blocking Claude
- **Best practice:** Use async (`"async": true`) for scratchpad writes

---

## Risks & Mitigations

| Risk | Severity | Mitigation |
|------|----------|-----------|
| AutoLaunch script crashes silently | High | Add error logging to file; monitoring via webview health endpoint |
| CORS failures block webview updates | Medium | Set `Access-Control-Allow-Origin: *` on all aiohttp responses; test in iTerm2 directly |
| watchdog FSEvents misses rapid updates | Low | Implement debouncing (100-200ms) in file watch handler |
| Session UUID changes on new tab | Low | Refresh session variable on each request; use stable session ID |
| Claude Code hooks block agent execution | Medium | Use `"async": true` to prevent blocking; set timeout to 30s max |
| Notes storage corruption on crash | Medium | JSON with atomic writes; backup to temp file before overwrite |

---

## Next Steps

1. **Prototype Phase:**
   - Create AutoLaunch Full Environment script with aiohttp + watchdog
   - Implement basic HTML webview at `/`
   - Test fetch() to localhost from iTerm2 webview
   - Verify FSEvents file monitoring works

2. **Integration Phase:**
   - Add session detection via iTerm2 API
   - Implement SSE for live updates
   - Create Claude Code hook for PostToolUse capture

3. **Polish Phase:**
   - Add error logging and health checks
   - Implement note persistence with atomic writes
   - Build UI (filters, search, clear, export)

---

## Sources

- [Running a Script — iTerm2 Python API 0.26](https://iterm2.com/python-api/tutorial/running.html)
- [Targeted Input Example — iTerm2 Python API](https://iterm2.com/python-api/examples/targeted_input.html)
- [Tool Documentation — iTerm2 Python API](https://iterm2.com/python-api/tool.html)
- [Session Documentation — iTerm2 Python API](https://iterm2.com/python-api/session.html)
- [Variables Documentation — iTerm2 Python API](https://iterm2.com/python-api/variables.html)
- [watchdog PyPI](https://pypi.org/project/watchdog/)
- [watchdog GitHub](https://github.com/gorakhargosh/watchdog)
- [WKWebView CORS Solution](https://zzdjk6.medium.com/wkwebview-cors-solution-da20ca1194e8)
- [iTerm2 Documentation — Web Browser](https://iterm2.com/documentation-web.html)
- [Claude Code Hooks Reference](https://code.claude.com/docs/en/hooks)
- [Claude Code Hooks — Hook Lifecycle](https://code.claude.com/docs/en/hooks#hook-lifecycle)
- [Claude Code Hooks — Hook Input/Output](https://code.claude.com/docs/en/hooks#hook-input-and-output)
- [watchfiles PyPI](https://pypi.org/project/watchfiles/)
- [Server-Sent Events — MDN Web Docs](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events)
