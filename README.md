# BrainDump

A tiny agent that reorganizes your to-do list when your brain is fried.

![screenshot](https://github.com/user-attachments/assets/f2f71dfc-45e3-46f3-b234-4870e9191093)

## What it does

- Takes your messy brain dump and picks 3–5 tasks you can actually start today
- Marks tasks done with one click, gives you a short praise, shows fireworks
- Keeps a `state.md` file as the single source of truth
- Archives completed items automatically with dates
- Works offline after initial setup (most interactions don't call LLM)

## What it deliberately does NOT do

- No account, no login, no cloud sync
- No calendar integration, no notifications, no reminders
- No "smart prioritization" — just picks what's easiest to start
- No mobile app — it's a local web page
- No team features — this is for one tired person

## How it works

```
You type/speak → state.md gets updated → Groq LLM reorganizes → state.md gets overwritten
                                              ↓
                         Most actions (complete, archive) skip the LLM entirely
```

- **Backend**: FastAPI (Python)
- **Frontend**: Single HTML file, vanilla JS
- **LLM**: Groq (free tier works fine)
- **Data**: Everything lives in `state.md`

## Quick Start

```bash
pip install fastapi uvicorn groq
export GROQ_API_KEY='your_key'   # free at console.groq.com
./gui                            # opens http://127.0.0.1:8000
```

## Cost

Groq free tier: 100k tokens/day. Typical usage: ~2k tokens per replan. You won't hit the limit unless you replan 50+ times a day.

## Status

Personally used daily. Still evolving. Works on macOS, should work on Linux. Windows untested.

---

**Designed for ADHD and low-energy moments.**

`state.md` is the only file that matters. Back it up if you care about your history.
