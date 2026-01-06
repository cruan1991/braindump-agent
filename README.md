# BrainDump Agent 🧠

A minimalist task management tool designed for people with ADHD and anxiety.

## ✨ Features

- 🎯 **Voice/Text Input** - Dump all the messy thoughts in your head
- 📋 **Smart Organization** - AI picks the 3-5 most important tasks for today
- ✅ **One-Click Done** - Click to complete, get praise + fireworks 🎆
- 🎨 **3 Praise Styles** - Snarky / Neutral / Warm
- 📦 **Auto Archive** - Done Archive + Weekly Summary

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install fastapi uvicorn groq
```

### 2. Set API Key

```bash
export GROQ_API_KEY='your_groq_api_key'
```

Get free key: https://console.groq.com

### 3. Run

```bash
./gui
# or
uvicorn app:app --reload
```

Open http://127.0.0.1:8000

## 📖 How to Use

1. **Input thoughts** - Type anything, or click mic for voice input
2. **Click Replan** - AI organizes into actionable tasks
3. **Complete tasks** - Click "Done", add notes (optional)
4. **Watch fireworks** - Say "All done!" when finished 🎉

## 📁 Files

| File | Description |
|------|-------------|
| `app.py` | FastAPI backend |
| `static/index.html` | Frontend |
| `state.md` | Task state (your data) |
| `prompts/brain_dump.md` | AI prompt |
| `runs/` | History snapshots |
| `summaries/` | Weekly summaries |

## 📜 License

MIT
