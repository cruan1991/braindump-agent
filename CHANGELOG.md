# Changelog

## v0.1 — 2026-01-06

First release. Daily driver status.

### Features

- Local web GUI (FastAPI + vanilla HTML/JS)
- Voice input via browser Speech API
- LLM-powered task reorganization (Groq)
- One-click task completion with praise
- Three praise styles: Snarky / Neutral / Warm
- "Clear all" with fireworks effect
- Automatic Done Archive with dates
- Weekly summary generation
- Micro-action suggestions after completing tasks
- `state.md` as single source of truth

### Technical

- Most interactions (complete, archive, style switch) don't call the LLM
- Metadata stored in HTML comments inside `state.md`
- Snapshots saved to `runs/` on each replan

