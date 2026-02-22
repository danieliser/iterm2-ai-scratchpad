# Intake: iTerm2 AI Scratchpad

**Date:** 2026-02-22
**Tier:** Quick
**Project Type:** Technical / Developer Tooling

## Idea

Build a custom iTerm2 Toolbelt sidebar panel that serves as an AI scratch pad — a place where long-running AI agents (Claude Code, scripts, etc.) can leave notes for the user to review passively.

## Question Framing

**The right question:** What's the simplest way to give long-running AI agents a persistent, visible notification channel inside the iTerm2 terminal workflow?

**Adjacent questions identified:**
- Terminal portability (decided: iTerm2 only)
- Read pattern (decided: passive sidebar)
- Agent sources (decided: generic API + Claude Code hooks)

## Premise Validation

- No existing plugin provides programmatic sidebar notes in iTerm2
- Built-in Notes tool has no programmatic write API
- iTerm2's Toolbelt WebView API (`async_register_web_view_tool`) is stable, documented, and proven by examples (Targeted Input)
- **Premise valid.** Buildable with known APIs.

## Constraints

- iTerm2 only (no cross-terminal portability needed)
- Must work with iTerm2's Python API (v0.26)
- Must not require complex dependencies — keep it lightweight
- Should be installable as a single script + optional CLI

## Success Criteria

- Toolbelt sidebar panel shows notes in reverse-chronological order
- Any process can post a note via file append or HTTP POST
- Claude Code hooks automatically post session events
- Notes persist across iTerm2 restarts
- Live updates without manual refresh

## Non-Goals

- Rich text editing in the sidebar
- Two-way communication (agent reads from scratchpad)
- Cross-terminal compatibility
- Complex categorization/tagging UI
- Mobile/remote access
