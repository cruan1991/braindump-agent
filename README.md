# BrainDump Agent 🧠

一个极简的任务管理工具，专为 ADHD 和容易焦虑的人设计。

## 特性

- 🎯 **语音/文字输入** - 把脑子里乱七八糟的想法倒出来
- 📋 **智能整理** - AI 帮你筛选出今天最重要的 3-5 件事
- ✅ **一键完成** - 点击完成，获得夸夸 + 烟花 🎆
- 🎨 **三种夸夸风格** - 毒舌 / 中性 / 温柔
- 📦 **自动归档** - Done Archive + 每周总结

## 快速开始

### 1. 安装依赖

```bash
pip install fastapi uvicorn groq
```

### 2. 设置 API Key

```bash
export GROQ_API_KEY='your_groq_api_key'
```

（免费获取：https://console.groq.com）

### 3. 运行

```bash
./gui
# 或
uvicorn app:app --reload
```

打开 http://127.0.0.1:8000

## 使用方法

1. **输入想法** - 在文本框里随便写，或点麦克风语音输入
2. **点击重排** - AI 会帮你整理成今天能做的任务
3. **完成任务** - 点"完成"按钮，写两句感想（可选）
4. **看烟花** - 全部完成时，说"所有事都做完了"🎉

## 文件说明

- `app.py` - FastAPI 后端
- `static/index.html` - 前端页面
- `state.md` - 你的任务状态（唯一需要关心的文件）
- `prompts/brain_dump.md` - AI 提示词
- `runs/` - 历史快照
- `summaries/` - 每周总结

## 许可

MIT
