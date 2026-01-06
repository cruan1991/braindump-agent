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
        "Well, you actually moved.",
        "Wow, you finished. A miracle.",
        "Fine. Don't get cocky.",
        "Done. Don't push it.",
        "Alright, barely acceptable.",
        "Finally did something useful.",
        "See? That wasn't so hard.",
        "Good. Now stop.",
    ],
    "neutral": [
        "Done.",
        "Completed.",
        "One down.",
        "Checked off.",
        "Done. Next.",
        "Finished.",
        "OK.",
        "Complete.",
    ],
    "warm": [
        "Great job! Take a breather.",
        "Done! You're doing great.",
        "Nice progress!",
        "You did it! Rest a bit.",
        "Good work. You can relax now.",
        "Completed! Give yourself a pat.",
        "One more done. Keep it up!",
        "Nice! You're making progress.",
    ],
}

SAFETY_NOTES = {
    "snarky": "Stop here. Don't be greedy.",
    "neutral": "That's enough for now.",
    "warm": "Take it easy. Don't overdo it.",
}

SHUTDOWN_NOTES = {
    "snarky": "Enough for today. Stop grinding.",
    "neutral": "Daily recommendations used up. Wrap it up.",
    "warm": "You've worked hard today. Time to rest.",
}

# Parking task hints
PARKING_HINTS = {
    "snarky": {
        "main_first": "Main tasks aren't done yet. Maybe do those first?",
        "all_done": "All done?! You're a god today.",
        "bonus": "Main tasks cleared. This is a bonus.",
    },
    "neutral": {
        "main_first": "Main tasks not complete. Consider doing those first.",
        "all_done": "Congrats! All tasks completed today.",
        "bonus": "Main tasks done. This is extra credit.",
    },
    "warm": {
        "main_first": "Your main tasks are waiting! Want to check on them?",
        "all_done": "Amazing! You went above and beyond today!",
        "bonus": "Main tasks done! This is a bonus achievement!",
    },
}

# --- Micro Actions Library ---

MICRO_ACTIONS = [
    {
        "id": "log_result",
        "title": "Log the result",
        "steps": "Write down the outcome (confirmation number, key info) in state",
        "eta_seconds": 60,
        "type": "closing",
    },
    {
        "id": "open_doc",
        "title": "Open tomorrow's doc",
        "steps": "Open the document you'll need tomorrow. Just open it, don't edit.",
        "eta_seconds": 45,
        "type": "prep",
    },
    {
        "id": "copy_phone",
        "title": "Copy phone number",
        "steps": "Copy the phone number you need to call to the top of state",
        "eta_seconds": 30,
        "type": "prep",
    },
    {
        "id": "write_first_step",
        "title": "Write the first step",
        "steps": "Break one task into its first step. Write just one sentence.",
        "eta_seconds": 60,
        "type": "prep",
    },
    {
        "id": "drink_water",
        "title": "Drink water",
        "steps": "Stand up, pour a glass of water, drink it",
        "eta_seconds": 60,
        "type": "reset",
    },
    {
        "id": "stretch",
        "title": "Stretch for 60 sec",
        "steps": "Stand up, stretch your neck and shoulders",
        "eta_seconds": 60,
        "type": "reset",
    },
    {
        "id": "walk",
        "title": "Take a short walk",
        "steps": "Leave your seat, walk around, come back in 60 seconds",
        "eta_seconds": 60,
        "type": "reset",
    },
    {
        "id": "close_tabs",
        "title": "Close extra tabs",
        "steps": "Close browser tabs related to the finished task",
        "eta_seconds": 45,
        "type": "closing",
    },
    {
        "id": "note_blocker",
        "title": "Note the blocker",
        "steps": "If something is stuck, write one line about it at top of state",
        "eta_seconds": 45,
        "type": "closing",
    },
    {
        "id": "set_reminder",
        "title": "Set a reminder",
        "steps": "If there's a deadline tomorrow, set an alarm on your phone",
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
    """Parse state.md into structured data"""
    text = strip_metadata(text)
    main_content, archive_lines = split_done_archive(text)
    
    today_tasks = []
    parking_tasks = []
    extra_tasks = []
    
    current_section = None
    
    for line in main_content.splitlines():
        line_stripped = line.strip()
        line_lower = line_stripped.lower()
        
        if "today" in line_lower or "do these" in line_lower:
            current_section = "today"
            continue
        elif "parking" in line_lower or "can skip" in line_lower or "not today" in line_lower:
            current_section = "parking"
            continue
        elif "extra" in line_lower or "if you have energy" in line_lower:
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
    
    lines = [f"# Done Summary — {y}-W{w:02d}", "", f"- Total completed: **{total}**"]
    if days:
        lines.append(f"- Date range: {days[0].isoformat()} ~ {days[-1].isoformat()}")
    lines += ["", "## By Day", ""]
    for d in days:
        lines.append(f"### {d.isoformat()} ({len(by_day[d])})")
        lines.extend(f"- {item}" for item in by_day[d])
        lines.append("")
    
    SUMMARIES_DIR.mkdir(exist_ok=True)
    out_path = SUMMARIES_DIR / f"weekly_{y}-W{w:02d}.md"
    write_text(out_path, "\n".join(lines).strip())


# --- Micro Action Selection ---

def select_micro_action(completed_task: str, remaining_tasks: List[dict]) -> Optional[dict]:
    """Select a micro action based on context"""
    candidates = []
    
    closing_actions = [a for a in MICRO_ACTIONS if a["type"] == "closing"]
    candidates.extend(closing_actions)
    
    if remaining_tasks:
        prep_actions = [a for a in MICRO_ACTIONS if a["type"] == "prep"]
        candidates.extend(prep_actions)
    
    reset_actions = [a for a in MICRO_ACTIONS if a["type"] == "reset"]
    candidates.extend(reset_actions)
    
    if not candidates:
        return None
    
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
        done_context = "(Already archived, don't list again)\n" + "\n".join(completed_today) + "\n\n"

    user_message = f"""{done_context}[User's brain dump / current state]

{brain_dump if brain_dump else "(empty)"}

---

Based on the above:

1. **Identify what the user said they completed** (e.g. "finished", "done", "completed")
   - If user mentioned completing something, output a `## Just Completed` section at the end

2. **Generate a new task list** in this format:

## Today's Tasks

1. **Task name**  
   → How to start (can begin within 15 min)

(Max 3-5, pick the easiest to start)

---

## Can Skip Today

- Task — Reason why it can wait

(**Important: All tasks mentioned but not in "Today" must go here. Don't lose any tasks.**)

---

## If You Have Extra Energy

- Optional task

## Just Completed
- [x] {today_str} — xxx (if user said they completed something)

**Key rules (must follow):**
1. Don't lose any tasks the user mentioned
2. "Today" max 3-5 items, prioritize easiest to start
3. Remaining tasks must all go to "Can Skip Today" with reasons
4. If user said they completed something, put it in "Just Completed"
5. Only output the format above, no explanations"""

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
    """Execute replan flow, return parsed result"""
    prompt = read_text(PROMPT_PATH)
    raw_state = read_text(STATE_PATH)

    if not raw_state:
        return {"today": [], "parking": [], "extra": [], "done": []}

    meta = get_metadata(raw_state)
    
    original_main, archive_lines = split_done_archive(raw_state)
    
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
    if "## Just Completed" in clean_tasks:
        clean_tasks = clean_tasks.split("## Just Completed", 1)[0].strip()
    clean_tasks = remove_done_lines(clean_tasks)

    combined_archive = dedupe_preserve_order(archive_lines + newly_done_from_user + model_done_normalized)

    has_today_tasks = "Today" in clean_tasks or "today" in clean_tasks.lower()
    
    if not clean_tasks.strip() or not has_today_tasks:
        clean_tasks = """## Today's Tasks

1. **Take a break**  
   → You've done a lot today, time to relax

---

## Can Skip Today

- Other tasks — Tomorrow

---

## If You Have Extra Energy

- Think about what to do tomorrow"""

    final_state = clean_tasks
    if combined_archive:
        final_state += f"\n\n{DONE_ARCHIVE_HEADER}\n" + "\n".join(combined_archive)
    
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
    """Detect if user said everything is done
    Returns (today_all_done, include_parking)
    """
    include_parking_patterns = [
        r"all\s*all",
        r"everything.*everything",
        r"including.*parking",
        r"parking.*too",
        r"completely.*clear",
        r"nothing.*left",
        r"totally.*done",
    ]
    
    include_parking = False
    for pattern in include_parking_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            include_parking = True
            break
    
    if include_parking:
        return (True, True)
    
    all_done_patterns = [
        r"all.*done",
        r"everything.*done",
        r"finished.*all",
        r"completed.*all",
        r"cleared",
        r"all\s*clear",
    ]
    
    today_done = False
    for pattern in all_done_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            today_done = True
            break
    
    return (today_done, False)


def detect_completed_items(text: str) -> List[str]:
    """Detect completed items from user input"""
    completed = []
    patterns = [
        r"(?:finished|done|completed|submitted|sent|called|replied)[:：]?\s*(.+?)(?:[,，。\n]|$)",
        r"(.+?)(?:is done|is finished|is completed)",
    ]
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for m in matches:
            item = m.strip()
            if item and len(item) < 50:
                completed.append(item)
    return list(set(completed))[:3]


@app.post("/api/capture")
async def capture(req: CaptureRequest):
    """Append text to state.md and replan"""
    raw_state = read_text(STATE_PATH)
    meta = get_metadata(raw_state)
    style = get_praise_style()
    
    current_state = parse_state_sections(strip_metadata(raw_state))
    today_tasks = current_state.get("today", [])
    parking_tasks = current_state.get("parking", [])
    
    today_done, include_parking = detect_all_done(req.text)
    
    if today_done and (today_tasks or parking_tasks):
        all_task_names = [t["name"] for t in today_tasks]
        parking_task_names = [p["name"] for p in parking_tasks] if include_parking else []
        
        return {
            "state": current_state,
            "praise": None,
            "pending_confirm": all_task_names,
            "pending_parking": parking_task_names if include_parking else None,
            "confirm_all": True,
            "include_parking": include_parking,
        }
    
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
    
    if detected_completed:
        return {
            "state": result, 
            "praise": None,
            "pending_confirm": detected_completed,
        }
    
    if new_done_count > old_done_count:
        praise = random.choice(PRAISE_POOLS.get(style, PRAISE_POOLS["neutral"]))
    
    return {"state": result, "praise": praise, "pending_confirm": None}


@app.post("/api/complete")
async def complete(req: CompleteRequest):
    """Complete a task, return Aftercare"""
    raw_state = read_text(STATE_PATH)
    meta = get_metadata(raw_state)
    today_str = date.today().isoformat()
    style = get_praise_style()
    
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
        new_lines.insert(0, f"[{timestamp_human()}] Note: {req.note}\n")
    
    new_content = "\n".join(new_lines)
    if meta:
        new_content = set_metadata(new_content, meta)
    write_text(STATE_PATH, new_content)
    
    result = run_replan()
    
    completed_task_lower = req.task_text.lower()
    result["today"] = [t for t in result.get("today", []) if completed_task_lower not in t.get("name", "").lower()]
    
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
    
    micro_action = select_micro_action(req.task_text, result.get("today", []))
    
    return {
        "state": result,
        "praise": praise,
        "praise_style": style,
        "ask": "Want to do a quick micro-action?" if micro_action else None,
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
    """Complete all tasks at once (optionally including parking) - no AI call"""
    raw_state = read_text(STATE_PATH)
    meta = get_metadata(raw_state)
    style = get_praise_style()
    today_str = date.today().isoformat()
    
    all_tasks = req.tasks + (req.parking_tasks or [])
    
    _, existing_archive = split_done_archive(raw_state)
    
    new_done_lines = [f"- [x] {today_str} — {task}" for task in all_tasks]
    
    combined_archive = dedupe_preserve_order(new_done_lines + existing_archive)
    
    new_state = f"""## Today's Tasks

(All done! 🎉)

---

## Can Skip Today

(Also all done!)

---

## If You Have Extra Energy

- Rest well

{DONE_ARCHIVE_HEADER}
{chr(10).join(combined_archive)}"""
    
    if meta:
        new_state = set_metadata(new_state, meta)
    
    write_text(STATE_PATH, new_state)
    
    RUNS_DIR.mkdir(exist_ok=True)
    write_text(RUNS_DIR / f"state_{timestamp()}.md", new_state)
    
    update_weekly_summary(combined_archive)
    
    result = {
        "today": [],
        "parking": [],
        "extra": ["Rest well"],
        "done": [{"date": today_str, "text": t} for t in all_tasks] + 
                [{"date": d.get("date", ""), "text": d.get("text", "")} 
                 for d in parse_state_sections(raw_state).get("done", [])],
    }
    
    hints = PARKING_HINTS.get(style, PARKING_HINTS["neutral"])
    
    if req.parking_tasks:
        super_praise = {
            "snarky": "All clear?! What did you eat today? Beast mode.",
            "neutral": "Congrats! All tasks (including optional) completed.",
            "warm": "Amazing!! You finished absolutely everything! You're incredible today! 🎉",
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
    """Complete a parking task with conditional feedback"""
    raw_state = read_text(STATE_PATH)
    meta = get_metadata(raw_state)
    style = get_praise_style()
    
    current_state = parse_state_sections(strip_metadata(raw_state))
    today_tasks = current_state.get("today", [])
    parking_tasks = current_state.get("parking", [])
    done_count = len(current_state.get("done", []))
    
    lines = strip_metadata(raw_state).splitlines()
    new_lines = []
    found = False
    
    for line in lines:
        if req.task_name in line and "—" in line and not found:
            new_lines.append(f"- [x] {req.task_name}")
            found = True
            continue
        new_lines.append(line)
    
    if req.note:
        new_lines.insert(0, f"[{timestamp_human()}] Note: {req.note}\n")
    
    new_content = "\n".join(new_lines)
    if meta:
        new_content = set_metadata(new_content, meta)
    write_text(STATE_PATH, new_content)
    
    result = run_replan()
    
    task_lower = req.task_name.lower()
    result["parking"] = [p for p in result.get("parking", []) if task_lower not in p.get("name", "").lower()]
    
    hints = PARKING_HINTS.get(style, PARKING_HINTS["neutral"])
    remaining_today = result.get("today", [])
    remaining_parking = result.get("parking", [])
    new_done_count = len(result.get("done", []))
    
    main_done_today = new_done_count - done_count - 1
    
    if len(remaining_today) > 0 and main_done_today <= 0:
        return {
            "state": result,
            "praise": random.choice(PRAISE_POOLS.get(style, PRAISE_POOLS["neutral"])),
            "praise_style": style,
            "hint": hints["main_first"],
            "hint_type": "main_first",
            "all_done": False,
            "safety_note": SAFETY_NOTES.get(style, SAFETY_NOTES["neutral"]),
        }
    
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
    
    if len(remaining_today) == 0:
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
    """User confirms completing something, archive and return praise"""
    raw_state = read_text(STATE_PATH)
    meta = get_metadata(raw_state)
    today_str = date.today().isoformat()
    style = get_praise_style()
    
    done_line = f"- [x] {req.item}"
    new_content = f"{done_line}\n\n{strip_metadata(raw_state)}"
    if meta:
        new_content = set_metadata(new_content, meta)
    write_text(STATE_PATH, new_content)
    
    result = run_replan()
    
    completed_item_lower = req.item.lower()
    result["today"] = [t for t in result.get("today", []) if completed_item_lower not in t.get("name", "").lower()]
    
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
        "ask": "Want to do a quick micro-action?" if micro_action else None,
        "micro_action": micro_action,
        "safety_note": SAFETY_NOTES.get(style, SAFETY_NOTES["neutral"]),
    }


@app.post("/api/accept_micro")
async def accept_micro(req: MicroActionRequest):
    """User accepted micro action"""
    increment_micro_action_count()
    
    raw_state = read_text(STATE_PATH)
    meta = get_metadata(raw_state)
    
    new_content = f"[{timestamp_human()}] Chose to do: {req.action_title}\n\n{strip_metadata(raw_state)}"
    if meta:
        new_content = set_metadata(new_content, meta)
    write_text(STATE_PATH, new_content)
    
    result = run_replan()
    return {"state": result}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
