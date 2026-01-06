#!/usr/bin/env python3
"""
BrainDump Agent - Web GUI (FastAPI)
"""

from __future__ import annotations

import os
import re
import random
import json
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from groq import Groq

# --- Config ---

ROOT = Path(__file__).parent
PROMPT_PATH = ROOT / "prompts" / "brain_dump.md"
STATE_PATH = ROOT / "state.md"
RUNS_DIR = ROOT / "runs"
SUMMARIES_DIR = ROOT / "summaries"

DEFAULT_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

DONE_ARCHIVE_HEADER = "## Done Archive"
DONE_LINE_RE = re.compile(r"^\s*-\s*\[x\]\s*(.+?)\s*$", re.IGNORECASE)
DATED_DONE_RE = re.compile(r"^\s*-\s*\[x\]\s*(\d{4}-\d{2}-\d{2})\s*—\s*(.+?)\s*$")
META_RE = re.compile(r"^<!--\s*meta:\s*(\{.*\})\s*-->$")

# --- Praise Pools (by style) ---

PRAISE_POOLS = {
    "snarky": [
        "行，你确实动了。",
        "居然做完了，奇迹。",
        "可以，别上头。",
        "完事了，别飘。",
        "行吧，勉强认可。",
        "总算是干了点正事。",
        "这不就做完了，之前纠结啥。",
        "好，收。别继续了。",
    ],
    "neutral": [
        "已完成。",
        "做完了。",
        "一件事，结束。",
        "划掉。",
        "完成，下一个。",
        "搞定。",
        "OK.",
        "Done.",
    ],
    "warm": [
        "做得好，辛苦了。",
        "完成了，真棒。",
        "这一步走得很好。",
        "你做到了，休息一下吧。",
        "很好，可以喘口气了。",
        "完成了，给自己点个赞。",
        "一件事搞定，继续加油。",
        "不错，今天又进步了。",
    ],
}

SAFETY_NOTES = {
    "snarky": "到这收手，别贪。",
    "neutral": "可以停了。",
    "warm": "先到这里，别累着自己。",
}

SHUTDOWN_NOTES = {
    "snarky": "今天够了，别再卷了。",
    "neutral": "今日推荐次数已用完，收工。",
    "warm": "今天已经很努力了，休息吧。",
}

# 完成 parking 任务的特殊提示
PARKING_HINTS = {
    "snarky": {
        "main_first": "主线任务还没动呢，不如先搞那个？",
        "all_done": "全部搞定了？今天你是神。",
        "bonus": "主线清了，这个算加分项。",
    },
    "neutral": {
        "main_first": "主线任务还没完成，建议先做主线。",
        "all_done": "恭喜，今天的任务全部完成。",
        "bonus": "主线已完成，这个是额外收获。",
    },
    "warm": {
        "main_first": "主线任务还在等你呢，要不要先去看看？",
        "all_done": "太棒了！今天超额完成，给自己一个大大的赞！",
        "bonus": "主线都做完了，这个算是额外的成就，真棒！",
    },
}

# --- Micro Actions Library ---

MICRO_ACTIONS = [
    {
        "id": "log_result",
        "title": "记录结果",
        "steps": "把刚完成那件事的结果写一行到 state（比如确认号/关键信息）",
        "eta_seconds": 60,
        "type": "closing",
    },
    {
        "id": "open_doc",
        "title": "打开明天要用的文档",
        "steps": "把需要明天用的文档打开，停在那，不改",
        "eta_seconds": 45,
        "type": "prep",
    },
    {
        "id": "copy_phone",
        "title": "复制电话号码",
        "steps": "把需要打电话的号码复制到 state 顶部",
        "eta_seconds": 30,
        "type": "prep",
    },
    {
        "id": "write_first_step",
        "title": "写下第一步",
        "steps": "把一个任务拆成第一步，写成一句话",
        "eta_seconds": 60,
        "type": "prep",
    },
    {
        "id": "drink_water",
        "title": "喝水",
        "steps": "站起来，倒杯水，喝掉",
        "eta_seconds": 60,
        "type": "reset",
    },
    {
        "id": "stretch",
        "title": "伸展 60 秒",
        "steps": "站起来，伸展一下脖子和肩膀",
        "eta_seconds": 60,
        "type": "reset",
    },
    {
        "id": "walk",
        "title": "走动一下",
        "steps": "离开座位，走几步，60 秒后回来",
        "eta_seconds": 60,
        "type": "reset",
    },
    {
        "id": "close_tabs",
        "title": "关掉多余标签页",
        "steps": "把刚才做完的相关标签页关掉，只留需要的",
        "eta_seconds": 45,
        "type": "closing",
    },
    {
        "id": "note_blocker",
        "title": "记下卡点",
        "steps": "如果有卡住的地方，写一句话到 state 顶部",
        "eta_seconds": 45,
        "type": "closing",
    },
    {
        "id": "set_reminder",
        "title": "设个提醒",
        "steps": "如果明天有截止日期，打开手机设个闹钟",
        "eta_seconds": 60,
        "type": "prep",
    },
]

MAX_MICRO_ACTIONS_PER_DAY = 2


# --- Helpers ---

def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def timestamp_human() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


# --- Metadata in state.md ---

def get_metadata(text: str) -> Dict[str, Any]:
    """Extract metadata from <!-- meta: {...} --> line"""
    for line in text.splitlines():
        m = META_RE.match(line.strip())
        if m:
            try:
                return json.loads(m.group(1))
            except:
                pass
    return {}


def set_metadata(text: str, meta: Dict[str, Any]) -> str:
    """Set or update metadata line in text"""
    meta_line = f"<!-- meta: {json.dumps(meta, ensure_ascii=False)} -->"
    lines = text.splitlines()
    new_lines = [line for line in lines if not META_RE.match(line.strip())]
    # Add metadata at the very end
    new_lines.append("")
    new_lines.append(meta_line)
    return "\n".join(new_lines).strip()


def strip_metadata(text: str) -> str:
    """Remove metadata line from text"""
    return "\n".join(line for line in text.splitlines() if not META_RE.match(line.strip())).strip()


def get_praise_style() -> str:
    raw = read_text(STATE_PATH)
    meta = get_metadata(raw)
    return meta.get("praise_style", "neutral")


def set_praise_style(style: str) -> None:
    raw = read_text(STATE_PATH)
    meta = get_metadata(raw)
    meta["praise_style"] = style
    new_text = set_metadata(strip_metadata(raw), meta)
    write_text(STATE_PATH, new_text)


def get_micro_action_count() -> int:
    """Get today's micro action recommendation count"""
    raw = read_text(STATE_PATH)
    meta = get_metadata(raw)
    count_date = meta.get("micro_action_date", "")
    if count_date != date.today().isoformat():
        return 0
    return meta.get("micro_action_count", 0)


def increment_micro_action_count() -> int:
    """Increment and return new count"""
    raw = read_text(STATE_PATH)
    meta = get_metadata(raw)
    today_str = date.today().isoformat()
    
    if meta.get("micro_action_date") != today_str:
        meta["micro_action_date"] = today_str
        meta["micro_action_count"] = 1
    else:
        meta["micro_action_count"] = meta.get("micro_action_count", 0) + 1
    
    new_text = set_metadata(strip_metadata(raw), meta)
    write_text(STATE_PATH, new_text)
    return meta["micro_action_count"]


# --- Parsing ---

def split_done_archive(text: str) -> tuple[str, List[str]]:
    text = strip_metadata(text)
    if DONE_ARCHIVE_HEADER not in text:
        return text.strip(), []
    main, tail = text.split(DONE_ARCHIVE_HEADER, 1)
    archive_lines = [line.strip() for line in tail.splitlines() if line.strip().lower().startswith("- [x]")]
    return main.strip(), archive_lines


def extract_done_lines(text: str) -> List[str]:
    return [line.strip() for line in text.splitlines() if DONE_LINE_RE.match(line)]


def remove_done_lines(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not DONE_LINE_RE.match(line)).strip()


def normalize_done_item(raw_line: str, done_date: date) -> str:
    line = raw_line.strip()
    if DATED_DONE_RE.match(line):
        m = DATED_DONE_RE.match(line)
        return f"- [x] {m.group(1)} — {m.group(2).strip()}"
    m = DONE_LINE_RE.match(line)
    if not m:
        return line
    return f"- [x] {done_date.isoformat()} — {m.group(1).strip()}"


def dedupe_preserve_order(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for it in items:
        if it not in seen:
            out.append(it)
            seen.add(it)
    return out


def parse_state_sections(text: str) -> dict:
    """解析 state.md 为结构化数据"""
    text = strip_metadata(text)
    main_content, archive_lines = split_done_archive(text)
    
    today_tasks = []
    parking_tasks = []
    extra_tasks = []
    
    current_section = None
    
    for line in main_content.splitlines():
        line_stripped = line.strip()
        line_lower = line_stripped.lower()
        
        if "今天做这几件" in line_stripped or "today" in line_lower:
            current_section = "today"
            continue
        elif "可以不做" in line_stripped or "parking" in line_lower:
            current_section = "parking"
            continue
        elif "如果还有余力" in line_stripped or "extra" in line_lower:
            current_section = "extra"
            continue
        elif line_stripped.startswith("## ") or line_stripped.startswith("---"):
            continue
        
        task_match = re.match(r"^\d+\.\s*\*\*(.+?)\*\*", line_stripped)
        if task_match:
            task_name = task_match.group(1).strip()
            if current_section == "today":
                today_tasks.append({"name": task_name, "hint": ""})
            continue
        
        if line_stripped.startswith("→") and today_tasks and current_section == "today":
            today_tasks[-1]["hint"] = line_stripped[1:].strip()
            continue
        
        parking_match = re.match(r"^-\s*(.+?)\s*—\s*(.+)$", line_stripped)
        if parking_match and current_section == "parking":
            parking_tasks.append({"name": parking_match.group(1).strip(), "reason": parking_match.group(2).strip()})
            continue
        
        if line_stripped.startswith("- ") and current_section == "extra":
            extra_tasks.append(line_stripped[2:].strip())
    
    done_items = []
    for line in archive_lines:
        m = DATED_DONE_RE.match(line)
        if m:
            done_items.append({"date": m.group(1), "text": m.group(2).strip()})
        else:
            m2 = DONE_LINE_RE.match(line)
            if m2:
                done_items.append({"date": "", "text": m2.group(1).strip()})
    
    return {
        "today": today_tasks,
        "parking": parking_tasks,
        "extra": extra_tasks,
        "done": done_items,
    }


# --- Weekly Summary ---

def update_weekly_summary(archive_lines: List[str]) -> None:
    from dataclasses import dataclass
    
    @dataclass(frozen=True)
    class DoneEntry:
        when: date
        text: str
    
    entries = []
    for line in archive_lines:
        m = DATED_DONE_RE.match(line.strip())
        if m:
            entries.append(DoneEntry(when=date.fromisoformat(m.group(1)), text=m.group(2).strip()))
    
    if not entries:
        return
    
    today = date.today()
    y, w, _ = today.isocalendar()
    this_week = [e for e in entries if e.when.isocalendar()[:2] == (y, w)]
    
    if not this_week:
        return
    
    by_day = {}
    for e in this_week:
        by_day.setdefault(e.when, []).append(e.text)
    
    days = sorted(by_day.keys())
    total = sum(len(v) for v in by_day.values())
    
    lines = [f"# Done 摘要 — {y}-W{w:02d}", "", f"- 总完成条目：**{total}**"]
    if days:
        lines.append(f"- 覆盖日期：{days[0].isoformat()} ~ {days[-1].isoformat()}")
    lines += ["", "## 按天", ""]
    for d in days:
        lines.append(f"### {d.isoformat()}（{len(by_day[d])}）")
        lines.extend(f"- {item}" for item in by_day[d])
        lines.append("")
    
    SUMMARIES_DIR.mkdir(exist_ok=True)
    out_path = SUMMARIES_DIR / f"weekly_{y}-W{w:02d}.md"
    write_text(out_path, "\n".join(lines).strip())


# --- Micro Action Selection ---

def select_micro_action(completed_task: str, remaining_tasks: List[dict]) -> Optional[dict]:
    """Select a micro action based on context"""
    # Prioritize by type
    candidates = []
    
    # Closing actions for completed task
    closing_actions = [a for a in MICRO_ACTIONS if a["type"] == "closing"]
    candidates.extend(closing_actions)
    
    # Prep actions if there are remaining tasks
    if remaining_tasks:
        prep_actions = [a for a in MICRO_ACTIONS if a["type"] == "prep"]
        candidates.extend(prep_actions)
    
    # Reset actions (always available)
    reset_actions = [a for a in MICRO_ACTIONS if a["type"] == "reset"]
    candidates.extend(reset_actions)
    
    if not candidates:
        return None
    
    # Randomly select one
    action = random.choice(candidates)
    return {
        "title": action["title"],
        "steps": action["steps"],
        "eta_seconds": action["eta_seconds"],
    }


# --- Groq ---

def generate_new_state(prompt: str, brain_dump: str, completed_today: List[str]) -> str:
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    today_str = date.today().isoformat()

    done_context = ""
    if completed_today:
        done_context = "（已归档的完成项，不要再列出）\n" + "\n".join(completed_today) + "\n\n"

    user_message = f"""{done_context}【用户的 brain dump / 当前状态】

{brain_dump if brain_dump else "（空）"}

---

请根据以上内容：

1. **识别用户说完成了什么**（比如"写完了"、"做完了"、"搞定了"、"弄好了"）
   - 如果用户说完成了某事，在最后输出一个 `## 刚完成` 区块

2. **生成新的任务清单**，格式：

## 今天做这几件就够了

1. **任务名**  
   → 怎么开始（15分钟内能动手）

（最多 3-5 个，选最容易开始的）

---

## 今天可以不做

- 任务 — 原因

（**重要：所有用户提到但没放进"今天做"的任务，必须全部放在这里，不能丢弃任何任务**）

---

## 如果还有余力

- 可选任务

## 刚完成
- [x] {today_str} — xxx（如果用户说完成了什么）

**关键规则（必须遵守）：**
1. 用户提到的所有任务都不能丢失
2. "今天做"最多 3-5 个，优先选最容易开始的
3. 剩余的任务必须全部放到"可以不做"里，给出推迟原因
4. 如果用户说完成了某事，放到"刚完成"区块
5. 只输出上面的格式，不要解释"""

    response = client.chat.completions.create(
        model=DEFAULT_MODEL,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=0.3,
    )
    return response.choices[0].message.content.strip()


def run_replan() -> dict:
    """执行重排流程，返回解析后的结果"""
    prompt = read_text(PROMPT_PATH)
    raw_state = read_text(STATE_PATH)

    if not raw_state:
        return {"today": [], "parking": [], "extra": [], "done": []}

    # Preserve metadata
    meta = get_metadata(raw_state)
    
    # 保留原始任务部分（用于回退）
    original_main, archive_lines = split_done_archive(raw_state)
    original_tasks_section = original_main  # 备份
    
    done_in_main = extract_done_lines(original_main)
    brain_dump = remove_done_lines(original_main)

    today = date.today()
    newly_done_from_user = [normalize_done_item(x, today) for x in done_in_main]

    new_tasks = generate_new_state(prompt, brain_dump, archive_lines + newly_done_from_user)

    model_done = extract_done_lines(new_tasks)
    model_done_normalized = [normalize_done_item(x, today) for x in model_done]

    clean_tasks = new_tasks
    if DONE_ARCHIVE_HEADER in clean_tasks:
        clean_tasks = clean_tasks.split(DONE_ARCHIVE_HEADER, 1)[0].strip()
    if "## 刚完成" in clean_tasks:
        clean_tasks = clean_tasks.split("## 刚完成", 1)[0].strip()
    clean_tasks = remove_done_lines(clean_tasks)

    combined_archive = dedupe_preserve_order(archive_lines + newly_done_from_user + model_done_normalized)

    # 检查模型是否返回了有效任务
    has_today_tasks = "今天做这几件" in clean_tasks or "## Today" in clean_tasks
    
    if not clean_tasks.strip() or not has_today_tasks:
        # 模型没有返回有效任务，生成一个默认状态
        clean_tasks = """## 今天做这几件就够了

1. **休息一下**  
   → 今天已经完成很多了，可以放松

---

## 今天可以不做

- 其他任务 — 明天再说

---

## 如果还有余力

- 想想明天要做什么"""

    final_state = clean_tasks
    if combined_archive:
        final_state += f"\n\n{DONE_ARCHIVE_HEADER}\n" + "\n".join(combined_archive)
    
    # Restore metadata
    if meta:
        final_state = set_metadata(final_state, meta)

    write_text(STATE_PATH, final_state)

    RUNS_DIR.mkdir(exist_ok=True)
    write_text(RUNS_DIR / f"state_{timestamp()}.md", final_state)

    update_weekly_summary(combined_archive)

    return parse_state_sections(final_state)


# --- FastAPI ---

app = FastAPI(title="BrainDump Agent")

STATIC_DIR = ROOT / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class CaptureRequest(BaseModel):
    text: str


class CompleteRequest(BaseModel):
    task_text: str
    note: Optional[str] = ""


class StyleRequest(BaseModel):
    praise_style: str


class MicroActionRequest(BaseModel):
    action_title: str


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/state")
async def get_state():
    raw = read_text(STATE_PATH)
    state = parse_state_sections(raw)
    state["praise_style"] = get_praise_style()
    return state


@app.post("/api/style")
async def set_style(req: StyleRequest):
    if req.praise_style not in ["snarky", "neutral", "warm"]:
        req.praise_style = "neutral"
    set_praise_style(req.praise_style)
    return {"praise_style": req.praise_style}


def detect_all_done(text: str) -> tuple[bool, bool]:
    """检测用户是否说所有事都做完了
    返回 (today_all_done, include_parking)
    """
    # 先检测是否包括 parking（所有所有、全部全部、连XX也）
    include_parking_patterns = [
        r"所有.{0,3}所有",
        r"全部.{0,3}全部",
        r"连.{0,10}(?:可以不做|parking|不做的|可以不做的).{0,5}也",
        r"(?:可以不做|不做的).{0,5}也.{0,5}(?:做完|完成|搞定)",
        r"彻底.{0,5}(?:清空|做完|完成)",
        r"一个不剩",
        r"统统",
    ]
    
    include_parking = False
    for pattern in include_parking_patterns:
        if re.search(pattern, text):
            include_parking = True
            break
    
    # 如果检测到 include_parking，自动认为 today 也要清
    if include_parking:
        return (True, True)
    
    # 检测基本的"全部完成"
    all_done_patterns = [
        r"所有.{0,5}(?:都|全|已).{0,5}(?:做完|完成|搞定)",
        r"(?:都|全部|全).{0,5}(?:做完|完成|搞定)",
        r"(?:做完|完成|搞定).{0,5}(?:所有|全部|都)",
        r"清空了",
        r"全清了",
    ]
    
    today_done = False
    for pattern in all_done_patterns:
        if re.search(pattern, text):
            today_done = True
            break
    
    return (today_done, False)


def detect_completed_items(text: str) -> List[str]:
    """检测用户输入中的完成语句"""
    completed = []
    # 常见的完成表达
    patterns = [
        r"(?:做完了|完成了|搞定了|弄好了|写完了|交了|发了|打了|回了|改完了)[:：]?\s*(.+?)(?:[,，。\n]|$)",
        r"(.+?)(?:做完了|完成了|搞定了|弄好了|写完了)",
    ]
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for m in matches:
            item = m.strip()
            if item and len(item) < 50:  # 合理长度
                completed.append(item)
    return list(set(completed))[:3]  # 最多3个


@app.post("/api/capture")
async def capture(req: CaptureRequest):
    """追加文本到 state.md 顶部，然后重排"""
    raw_state = read_text(STATE_PATH)
    meta = get_metadata(raw_state)
    style = get_praise_style()
    
    # 先解析当前状态
    current_state = parse_state_sections(strip_metadata(raw_state))
    today_tasks = current_state.get("today", [])
    parking_tasks = current_state.get("parking", [])
    
    # 检测用户是否说"所有事都做完了"
    today_done, include_parking = detect_all_done(req.text)
    
    if today_done and (today_tasks or parking_tasks):
        # 返回所有任务作为待确认
        all_task_names = [t["name"] for t in today_tasks]
        parking_task_names = [p["name"] for p in parking_tasks] if include_parking else []
        
        return {
            "state": current_state,
            "praise": None,
            "pending_confirm": all_task_names,
            "pending_parking": parking_task_names if include_parking else None,
            "confirm_all": True,  # 标记这是"全部完成"的确认
            "include_parking": include_parking,
        }
    
    # 检测用户是否说完成了具体的事
    detected_completed = detect_completed_items(req.text)
    
    _, old_archive = split_done_archive(raw_state)
    old_done_count = len(old_archive)
    
    new_content = f"[{timestamp_human()}] {req.text}\n\n{strip_metadata(raw_state)}"
    if meta:
        new_content = set_metadata(new_content, meta)
    write_text(STATE_PATH, new_content)
    
    result = run_replan()
    
    new_done_count = len(result.get("done", []))
    praise = None
    
    # 如果检测到完成项，返回待确认列表（不直接夸）
    if detected_completed:
        return {
            "state": result, 
            "praise": None,
            "pending_confirm": detected_completed,
        }
    
    # 没有检测到完成项，但模型识别出了（直接夸）
    if new_done_count > old_done_count:
        praise = random.choice(PRAISE_POOLS.get(style, PRAISE_POOLS["neutral"]))
    
    return {"state": result, "praise": praise, "pending_confirm": None}


@app.post("/api/complete")
async def complete(req: CompleteRequest):
    """完成某个任务，返回 Aftercare"""
    raw_state = read_text(STATE_PATH)
    meta = get_metadata(raw_state)
    today_str = date.today().isoformat()
    style = get_praise_style()
    
    # Find and mark task as complete
    lines = strip_metadata(raw_state).splitlines()
    new_lines = []
    found = False
    
    for line in lines:
        if req.task_text in line and "**" in line and not found:
            new_lines.append(f"- [x] {req.task_text}")
            found = True
            continue
        if found and line.strip().startswith("→"):
            continue
        new_lines.append(line)
    
    if req.note:
        new_lines.insert(0, f"[{timestamp_human()}] 完成感想：{req.note}\n")
    
    new_content = "\n".join(new_lines)
    if meta:
        new_content = set_metadata(new_content, meta)
    write_text(STATE_PATH, new_content)
    
    # Replan
    result = run_replan()
    
    # 强制从 today 列表中移除刚完成的任务（防止模型又加回来）
    completed_task_lower = req.task_text.lower()
    result["today"] = [t for t in result.get("today", []) if completed_task_lower not in t.get("name", "").lower()]
    
    # Generate Aftercare response
    praise = random.choice(PRAISE_POOLS.get(style, PRAISE_POOLS["neutral"]))
    
    # Check micro action limit
    current_count = get_micro_action_count()
    
    if current_count >= MAX_MICRO_ACTIONS_PER_DAY:
        # Exceeded limit
        return {
            "state": result,
            "praise": praise,
            "praise_style": style,
            "ask": None,
            "micro_action": None,
            "safety_note": SHUTDOWN_NOTES.get(style, SHUTDOWN_NOTES["neutral"]),
        }
    
    # Select micro action
    micro_action = select_micro_action(req.task_text, result.get("today", []))
    
    return {
        "state": result,
        "praise": praise,
        "praise_style": style,
        "ask": "要不要顺便做个小动作？" if micro_action else None,
        "micro_action": micro_action,
        "safety_note": SAFETY_NOTES.get(style, SAFETY_NOTES["neutral"]),
    }


class ConfirmDoneRequest(BaseModel):
    item: str


class CompleteAllRequest(BaseModel):
    tasks: List[str]
    parking_tasks: Optional[List[str]] = None


@app.post("/api/complete_all")
async def complete_all(req: CompleteAllRequest):
    """一键完成所有任务（可选包括 parking）- 不调用 AI，直接归档"""
    raw_state = read_text(STATE_PATH)
    meta = get_metadata(raw_state)
    style = get_praise_style()
    today_str = date.today().isoformat()
    
    all_tasks = req.tasks + (req.parking_tasks or [])
    
    # 获取现有归档
    _, existing_archive = split_done_archive(raw_state)
    
    # 为所有任务创建归档条目
    new_done_lines = [f"- [x] {today_str} — {task}" for task in all_tasks]
    
    # 合并归档（新的在前）
    combined_archive = dedupe_preserve_order(new_done_lines + existing_archive)
    
    # 生成简洁的新 state（不调用 AI）
    new_state = f"""## 今天做这几件就够了

（全部完成！🎉）

---

## 今天可以不做

（也全部完成了！）

---

## 如果还有余力

- 好好休息

{DONE_ARCHIVE_HEADER}
{chr(10).join(combined_archive)}"""
    
    if meta:
        new_state = set_metadata(new_state, meta)
    
    write_text(STATE_PATH, new_state)
    
    # 保存快照
    RUNS_DIR.mkdir(exist_ok=True)
    write_text(RUNS_DIR / f"state_{timestamp()}.md", new_state)
    
    # 更新周报
    update_weekly_summary(combined_archive)
    
    # 解析结果
    result = {
        "today": [],
        "parking": [],
        "extra": ["好好休息"],
        "done": [{"date": today_str, "text": t} for t in all_tasks] + 
                [{"date": d.get("date", ""), "text": d.get("text", "")} 
                 for d in parse_state_sections(raw_state).get("done", [])],
    }
    
    # 返回恭喜
    hints = PARKING_HINTS.get(style, PARKING_HINTS["neutral"])
    
    # 更强烈的恭喜（如果包括 parking）
    if req.parking_tasks:
        super_praise = {
            "snarky": "全清了？！你今天是不是吃了什么？太猛了。",
            "neutral": "恭喜，今天所有任务（包括可选）全部完成。",
            "warm": "太棒了！！所有所有任务都完成了！今天的你超级厉害！🎉",
        }
        praise = super_praise.get(style, super_praise["neutral"])
    else:
        praise = hints["all_done"]
    
    return {
        "state": result,
        "praise": praise,
        "all_done": True,
        "completed_count": len(all_tasks),
        "include_parking": bool(req.parking_tasks),
    }


class CompleteParkingRequest(BaseModel):
    task_name: str
    note: Optional[str] = ""


@app.post("/api/complete_parking")
async def complete_parking(req: CompleteParkingRequest):
    """完成 parking 任务，根据情况给出不同反馈"""
    raw_state = read_text(STATE_PATH)
    meta = get_metadata(raw_state)
    style = get_praise_style()
    
    # 先解析当前状态
    current_state = parse_state_sections(strip_metadata(raw_state))
    today_tasks = current_state.get("today", [])
    parking_tasks = current_state.get("parking", [])
    done_count = len(current_state.get("done", []))
    
    # 标记任务完成
    lines = strip_metadata(raw_state).splitlines()
    new_lines = []
    found = False
    
    for line in lines:
        # 匹配 parking 任务行 (- xxx — reason)
        if req.task_name in line and "—" in line and not found:
            new_lines.append(f"- [x] {req.task_name}")
            found = True
            continue
        new_lines.append(line)
    
    if req.note:
        new_lines.insert(0, f"[{timestamp_human()}] 完成感想：{req.note}\n")
    
    new_content = "\n".join(new_lines)
    if meta:
        new_content = set_metadata(new_content, meta)
    write_text(STATE_PATH, new_content)
    
    # 重排
    result = run_replan()
    
    # 从 parking 中移除刚完成的
    task_lower = req.task_name.lower()
    result["parking"] = [p for p in result.get("parking", []) if task_lower not in p.get("name", "").lower()]
    
    # 判断情况
    hints = PARKING_HINTS.get(style, PARKING_HINTS["neutral"])
    remaining_today = result.get("today", [])
    remaining_parking = result.get("parking", [])
    new_done_count = len(result.get("done", []))
    
    # 情况1：主线任务一个都没做完（done 数量没变或只增加了刚完成的 parking）
    main_done_today = new_done_count - done_count - 1  # 减去刚完成的 parking
    
    if len(remaining_today) > 0 and main_done_today <= 0:
        # 主线还没动
        return {
            "state": result,
            "praise": random.choice(PRAISE_POOLS.get(style, PRAISE_POOLS["neutral"])),
            "praise_style": style,
            "hint": hints["main_first"],
            "hint_type": "main_first",
            "all_done": False,
            "safety_note": SAFETY_NOTES.get(style, SAFETY_NOTES["neutral"]),
        }
    
    # 情况2：所有任务都完成了
    if len(remaining_today) == 0 and len(remaining_parking) == 0:
        return {
            "state": result,
            "praise": hints["all_done"],
            "praise_style": style,
            "hint": None,
            "hint_type": "all_done",
            "all_done": True,
            "safety_note": None,
        }
    
    # 情况3：主线做完了，这个是额外的
    if len(remaining_today) == 0:
        # 推荐一个 parking 任务到 today（如果还有的话）
        recommend = None
        if remaining_parking:
            recommend = remaining_parking[0]
        
        return {
            "state": result,
            "praise": random.choice(PRAISE_POOLS.get(style, PRAISE_POOLS["neutral"])),
            "praise_style": style,
            "hint": hints["bonus"],
            "hint_type": "bonus",
            "all_done": False,
            "recommend_to_today": recommend,
            "safety_note": SAFETY_NOTES.get(style, SAFETY_NOTES["neutral"]),
        }
    
    # 默认情况
    return {
        "state": result,
        "praise": random.choice(PRAISE_POOLS.get(style, PRAISE_POOLS["neutral"])),
        "praise_style": style,
        "hint": None,
        "hint_type": None,
        "all_done": False,
        "safety_note": SAFETY_NOTES.get(style, SAFETY_NOTES["neutral"]),
    }


@app.post("/api/confirm_done")
async def confirm_done(req: ConfirmDoneRequest):
    """用户确认完成某事，归档并返回夸夸"""
    raw_state = read_text(STATE_PATH)
    meta = get_metadata(raw_state)
    today_str = date.today().isoformat()
    style = get_praise_style()
    
    # 添加完成项到 state
    done_line = f"- [x] {req.item}"
    new_content = f"{done_line}\n\n{strip_metadata(raw_state)}"
    if meta:
        new_content = set_metadata(new_content, meta)
    write_text(STATE_PATH, new_content)
    
    # 重排
    result = run_replan()
    
    # 强制从 today 列表中移除刚完成的任务
    completed_item_lower = req.item.lower()
    result["today"] = [t for t in result.get("today", []) if completed_item_lower not in t.get("name", "").lower()]
    
    # 返回夸夸 + Aftercare
    praise = random.choice(PRAISE_POOLS.get(style, PRAISE_POOLS["neutral"]))
    
    current_count = get_micro_action_count()
    if current_count >= MAX_MICRO_ACTIONS_PER_DAY:
        return {
            "state": result,
            "praise": praise,
            "praise_style": style,
            "ask": None,
            "micro_action": None,
            "safety_note": SHUTDOWN_NOTES.get(style, SHUTDOWN_NOTES["neutral"]),
        }
    
    micro_action = select_micro_action(req.item, result.get("today", []))
    
    return {
        "state": result,
        "praise": praise,
        "praise_style": style,
        "ask": "要不要顺便做个小动作？" if micro_action else None,
        "micro_action": micro_action,
        "safety_note": SAFETY_NOTES.get(style, SAFETY_NOTES["neutral"]),
    }


@app.post("/api/accept_micro")
async def accept_micro(req: MicroActionRequest):
    """User accepted micro action"""
    # Increment counter
    increment_micro_action_count()
    
    # Append to state.md
    raw_state = read_text(STATE_PATH)
    meta = get_metadata(raw_state)
    
    new_content = f"[{timestamp_human()}] 我选择顺便做：{req.action_title}\n\n{strip_metadata(raw_state)}"
    if meta:
        new_content = set_metadata(new_content, meta)
    write_text(STATE_PATH, new_content)
    
    # Replan
    result = run_replan()
    return {"state": result}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
