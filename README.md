# BrainDump Agent 🧠

> 一个极简的任务管理工具，专为 ADHD 和容易焦虑的人设计。
> 
> A minimalist task management tool designed for people with ADHD and anxiety.

## ✨ 特性 / Features

- 🎯 **语音/文字输入** - 把脑子里乱七八糟的想法倒出来
  - **Voice/Text Input** - Dump all the messy thoughts in your head
- 📋 **智能整理** - AI 帮你筛选出今天最重要的 3-5 件事
  - **Smart Organization** - AI picks the 3-5 most important tasks for today
- ✅ **一键完成** - 点击完成，获得夸夸 + 烟花
  - **One-Click Done** - Click to complete, get praise + fireworks 🎆
- 🎨 **三种夸夸风格** - 毒舌 / 中性 / 温柔
  - **3 Praise Styles** - Snarky / Neutral / Warm
- 📦 **自动归档** - Done Archive + 每周总结
  - **Auto Archive** - Done Archive + Weekly Summary

## 🚀 快速开始 / Quick Start

### 1. 安装依赖 / Install Dependencies

```bash
pip install fastapi uvicorn groq
```

### 2. 设置 API Key / Set API Key

```bash
export GROQ_API_KEY='your_groq_api_key'
```

免费获取 / Get free key: https://console.groq.com

### 3. 运行 / Run

```bash
./gui
# 或 / or
uvicorn app:app --reload
```

打开 / Open http://127.0.0.1:8000

## 📖 使用方法 / How to Use

1. **输入想法** - 在文本框里随便写，或点麦克风语音输入
   - **Input thoughts** - Type anything, or click mic for voice input
2. **点击重排** - AI 会帮你整理成今天能做的任务
   - **Click Replan** - AI organizes into actionable tasks
3. **完成任务** - 点"完成"按钮，写两句感想（可选）
   - **Complete tasks** - Click "Done", add notes (optional)
4. **看烟花** - 全部完成时，说"所有事都做完了" 🎉
   - **Watch fireworks** - Say "All done!" when finished 🎉

## 📁 文件说明 / Files

| 文件 / File | 说明 / Description |
|-------------|---------------------|
| `app.py` | FastAPI 后端 / Backend |
| `static/index.html` | 前端页面 / Frontend |
| `state.md` | 任务状态 / Task state (your data) |
| `prompts/brain_dump.md` | AI 提示词 / AI prompt |
| `runs/` | 历史快照 / History snapshots |
| `summaries/` | 每周总结 / Weekly summaries |

## 📜 License

MIT
