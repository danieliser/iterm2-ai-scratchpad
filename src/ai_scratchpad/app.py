"""App factory, session monitor, and entry points."""

import asyncio
import logging

from aiohttp import web

from . import ITERM2_AVAILABLE, _iterm2, LOG_PATH
from .storage import DEFAULT_SESSION, get_current_session_id, set_current_session_id
from .streaming import broadcast, start_watchdog, start_todo_watchdog, set_event_loop
from .handlers import (
    handle_options, handle_get_ui, handle_post_note, handle_get_notes,
    handle_delete_notes, handle_patch_note, handle_get_session,
    handle_health, handle_sse, handle_run, handle_get_todos,
    handle_get_prefs, handle_put_prefs, _handle_favicon,
)

log = logging.getLogger(__name__)


def build_app() -> web.Application:
    app = web.Application(client_max_size=1_000_000)  # 1MB request limit
    app.router.add_route("OPTIONS", "/{path_info:.*}", handle_options)
    app.router.add_get("/", handle_get_ui)
    app.router.add_post("/api/notes", handle_post_note)
    app.router.add_get("/api/notes", handle_get_notes)
    app.router.add_delete("/api/notes", handle_delete_notes)
    app.router.add_patch("/api/notes/{note_id}", handle_patch_note)
    app.router.add_get("/api/session", handle_get_session)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/events", handle_sse)
    app.router.add_post("/api/exec", handle_run)
    app.router.add_get("/api/todos", handle_get_todos)
    app.router.add_get("/api/prefs", handle_get_prefs)
    app.router.add_put("/api/prefs", handle_put_prefs)
    app.router.add_get("/favicon.ico", _handle_favicon)
    return app


async def _session_monitor(connection) -> None:
    """Watch iTerm2 layout changes and keep _current_session_id current."""

    try:
        app = await _iterm2.async_get_app(connection)
    except Exception as exc:
        log.error("Failed to get iTerm2 app — session awareness disabled: %s", exc)
        return

    def _pick_active_session():
        try:
            window = app.current_window
            if window is None:
                return DEFAULT_SESSION
            tab = window.current_tab
            if tab is None:
                return DEFAULT_SESSION
            session = tab.current_session
            if session is None:
                return DEFAULT_SESSION
            return session.session_id or DEFAULT_SESSION
        except Exception as exc:
            log.warning("Session detection error: %s", exc)
            return DEFAULT_SESSION

    try:
        set_current_session_id(_pick_active_session())
        log.info("Initial session_id=%s", get_current_session_id())
    except Exception as exc:
        log.error("Failed to set initial session: %s", exc)

    async with _iterm2.LayoutChangeMonitor(connection) as monitor:
        while True:
            try:
                await monitor.async_get()
                new_id = _pick_active_session()
                if new_id != get_current_session_id():
                    log.info("Session changed: %s -> %s", get_current_session_id(), new_id)
                    set_current_session_id(new_id)
                    await broadcast("session_changed", {"session_id": new_id})
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
    try:
        await _session_monitor(connection)
    finally:
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
            try:
                while True:
                    await asyncio.sleep(3600)
            finally:
                if observer:
                    observer.stop()
                    observer.join()
                if todo_observer:
                    todo_observer.stop()
                    todo_observer.join()
                await runner.cleanup()

        asyncio.run(_standalone_main())
