"""App factory, session monitor, and entry points."""

import asyncio
import logging

from aiohttp import web

from . import ITERM2_AVAILABLE, _iterm2, LOG_PATH
from .storage import (
    DEFAULT_SESSION, get_current_session_id, set_current_session_id,
    get_current_tab_session_ids, set_current_tab_session_ids, set_iterm2_connection,
    set_current_tab_project_key, cwd_to_project_key,
)
from . import WATCHDOG_AVAILABLE
from .streaming import broadcast, start_watchdog, start_todo_watchdog, start_poll_fallback, set_event_loop
from .handlers import (
    handle_options, handle_get_ui, handle_post_note, handle_get_notes,
    handle_delete_notes, handle_put_note, handle_patch_note, handle_get_session,
    handle_activate_session, handle_get_session_status, handle_health,
    handle_sse, handle_run,
    handle_get_todos, handle_get_prefs, handle_put_prefs, _handle_favicon,
    handle_register_session, handle_unregister_session, handle_get_sessions,
)

log = logging.getLogger(__name__)


def build_app() -> web.Application:
    app = web.Application(client_max_size=1_000_000)  # 1MB request limit
    app.router.add_route("OPTIONS", "/{path_info:.*}", handle_options)
    app.router.add_get("/", handle_get_ui)
    app.router.add_post("/api/notes", handle_post_note)
    app.router.add_get("/api/notes", handle_get_notes)
    app.router.add_delete("/api/notes", handle_delete_notes)
    app.router.add_put("/api/notes/{note_id}", handle_put_note)
    app.router.add_patch("/api/notes/{note_id}", handle_patch_note)
    app.router.add_get("/api/session", handle_get_session)
    app.router.add_post("/api/sessions/{session_id}/activate", handle_activate_session)
    app.router.add_get("/api/session/status", handle_get_session_status)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/events", handle_sse)
    app.router.add_post("/api/exec", handle_run)
    app.router.add_get("/api/todos", handle_get_todos)
    app.router.add_get("/api/prefs", handle_get_prefs)
    app.router.add_put("/api/prefs", handle_put_prefs)
    app.router.add_post("/api/sessions/register", handle_register_session)
    app.router.add_post("/api/sessions/unregister", handle_unregister_session)
    app.router.add_get("/api/sessions", handle_get_sessions)
    app.router.add_get("/favicon.ico", _handle_favicon)
    return app


async def _session_monitor(connection) -> None:
    """Watch iTerm2 focus changes and keep _current_session_id current.

    Uses FocusMonitor (not LayoutChangeMonitor) because tab switches
    are focus events, not layout events.
    """

    set_iterm2_connection(connection)

    try:
        app = await _iterm2.async_get_app(connection)
    except Exception as exc:
        log.error("Failed to get iTerm2 app — session awareness disabled: %s", exc)
        return

    def _pick_active_session():
        try:
            window = app.current_window
            if window is None:
                set_current_tab_session_ids([])
                return DEFAULT_SESSION
            tab = window.current_tab
            if tab is None:
                set_current_tab_session_ids([])
                return DEFAULT_SESSION
            # Collect all session IDs in this tab (all panes/splits)
            tab_sids = [s.session_id for s in tab.sessions if s.session_id]
            set_current_tab_session_ids(tab_sids)
            session = tab.current_session
            if session is None:
                return DEFAULT_SESSION
            return session.session_id or DEFAULT_SESSION
        except Exception as exc:
            log.warning("Session detection error: %s", exc)
            set_current_tab_session_ids([])
            return DEFAULT_SESSION

    async def _update_tab_project_key():
        """Query cwd from the active iTerm2 session and derive project key."""
        try:
            window = app.current_window
            if window and window.current_tab:
                session = window.current_tab.current_session
                if session:
                    cwd = await session.async_get_variable("path") or ""
                    pk = cwd_to_project_key(cwd)
                    set_current_tab_project_key(pk)
                    log.info("Tab project key: %s (cwd=%s)", pk, cwd)
                    return
        except Exception as exc:
            log.warning("Failed to get tab cwd: %s", exc)
        set_current_tab_project_key("")

    try:
        set_current_session_id(_pick_active_session())
        await _update_tab_project_key()
        log.info("Initial session_id=%s", get_current_session_id())
    except Exception as exc:
        log.error("Failed to set initial session: %s", exc)

    async with _iterm2.FocusMonitor(connection) as monitor:
        while True:
            try:
                update = await monitor.async_get_next_update()
                # React to tab switches and session focus changes
                if update.selected_tab_changed or update.active_session_changed:
                    new_id = _pick_active_session()
                    if new_id != get_current_session_id():
                        log.info("Session changed: %s -> %s", get_current_session_id(), new_id)
                        set_current_session_id(new_id)
                        await _update_tab_project_key()
                        await broadcast("session_changed", {
                            "session_id": new_id,
                            "tab_session_ids": get_current_tab_session_ids(),
                        })
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.error("Session monitor error (continuing): %s", exc)


async def _run_server() -> web.AppRunner:
    """Start the aiohttp server; returns runner so caller can cleanup()."""
    set_event_loop(asyncio.get_running_loop())
    app = build_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 9999)
    await site.start()
    log.info("Server running on http://localhost:9999 (session=%s)", get_current_session_id())
    return runner


async def _iterm2_main(connection) -> None:
    """iTerm2 AutoLaunch entry point: register toolbelt panel + session monitor."""
    await _iterm2.tool.async_register_web_view_tool(
        connection,
        "AI Scratchpad",
        "com.danieliser.ai-scratchpad",
        True,
        "http://localhost:9999/",
    )
    log.info("Registered iTerm2 Toolbelt webview panel")

    runner = await _run_server()
    observer = start_watchdog()
    todo_observer = start_todo_watchdog()
    poll_tasks = []
    if not WATCHDOG_AVAILABLE:
        poll_tasks = start_poll_fallback()
    try:
        await _session_monitor(connection)
    finally:
        for t in poll_tasks:
            t.cancel()
        if observer:
            observer.stop()
            observer.join()
        if todo_observer:
            todo_observer.stop()
            todo_observer.join()
        await runner.cleanup()


def main() -> None:
    """Entry point — dual-mode: iTerm2 AutoLaunch or standalone."""
    from . import WATCHDOG_AVAILABLE
    log.info("Starting AI Scratchpad (iterm2=%s, watchdog=%s)", ITERM2_AVAILABLE, WATCHDOG_AVAILABLE)
    log.info("Log file: %s", LOG_PATH)

    if ITERM2_AVAILABLE:
        _iterm2.run_forever(_iterm2_main)
    else:
        async def _standalone_main():
            runner = await _run_server()
            observer = start_watchdog()
            todo_observer = start_todo_watchdog()
            poll_tasks = []
            if not WATCHDOG_AVAILABLE:
                poll_tasks = start_poll_fallback()
            try:
                while True:
                    await asyncio.sleep(3600)
            finally:
                for t in poll_tasks:
                    t.cancel()
                if observer:
                    observer.stop()
                    observer.join()
                if todo_observer:
                    todo_observer.stop()
                    todo_observer.join()
                await runner.cleanup()

        asyncio.run(_standalone_main())
