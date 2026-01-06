#!/usr/bin/env python3
"""
BrainDump Agent — state.md 是唯一输入和输出

用户只需：
1. 打开 state.md 随便写
2. 用 - [x] 标记完成的
3. 运行 ./run
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import List, Tuple, Dict

from groq import Groq

ROOT = Path(__file__).parent
PROMPT_PATH = ROOT / "prompts" / "brain_dump.md"
STATE_PATH = ROOT / "state.md"
RUNS_DIR = ROOT / "runs"
SUMMARIES_DIR = ROOT / "summaries"

DEFAULT_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

DONE_ARCHIVE_HEADER = "## Done Archive"
DONE_LINE_RE = re.compile(r"^\s*-\s*\[x\]\s*(.+?)\s*$", re.IGNORECASE)
DATED_DONE_RE = re.compile(r"^\s*-\s*\[x\]\s*(\d{4}-\d{2}-\d{2})\s*—\s*(.+?)\s*$")


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


# --- Parsing ---

def split_done_archive(text: str) -> Tuple[str, List[str]]:
    """分离主体和 Done Archive"""
    if DONE_ARCHIVE_HEADER not in text:
        return text.strip(), []
    main, tail = text.split(DONE_ARCHIVE_HEADER, 1)
    archive_lines = []
    for line in tail.splitlines():
        line = line.strip()
        if line.lower().startswith("- [x]"):
            archive_lines.append(line)
    return main.strip(), archive_lines


def extract_done_lines(text: str) -> List[str]:
    """提取所有 - [x] 行"""
    return [line.strip() for line in text.splitlines() if DONE_LINE_RE.match(line)]


def remove_done_lines(text: str) -> str:
    """移除 - [x] 行"""
    return "\n".join(line for line in text.splitlines() if not DONE_LINE_RE.match(line)).strip()


def normalize_done_item(raw_line: str, done_date: date) -> str:
    """标准化为 - [x] YYYY-MM-DD — 内容"""
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


# --- Weekly Summary ---

@dataclass(frozen=True)
class DoneEntry:
    when: date
    text: str


def parse_done_entries(lines: List[str]) -> List[DoneEntry]:
    entries = []
    for line in lines:
        m = DATED_DONE_RE.match(line.strip())
        if m:
            entries.append(DoneEntry(when=date.fromisoformat(m.group(1)), text=m.group(2).strip()))
    return entries


def iso_week_key(d: date) -> Tuple[int, int]:
    y, w, _ = d.isocalendar()
    return y, w


def weekly_summary_path(year: int, week: int) -> Path:
    return SUMMARIES_DIR / f"weekly_{year}-W{week:02d}.md"


def render_weekly_summary(year: int, week: int, entries: List[DoneEntry]) -> str:
    by_day: Dict[date, List[str]] = {}
    for e in entries:
        by_day.setdefault(e.when, []).append(e.text)
    days = sorted(by_day.keys())
    total = sum(len(v) for v in by_day.values())

    lines = [f"# Done 摘要 — {year}-W{week:02d}", "", f"- 总完成条目：**{total}**"]
    if days:
        lines.append(f"- 覆盖日期：{days[0].isoformat()} ~ {days[-1].isoformat()}")
    lines += ["", "## 按天", ""]
    for d in days:
        lines.append(f"### {d.isoformat()}（{len(by_day[d])}）")
        lines.extend(f"- {item}" for item in by_day[d])
        lines.append("")
    return "\n".join(lines).strip()


def update_weekly_summary(archive_lines: List[str]) -> Path | None:
    entries = parse_done_entries(archive_lines)
    if not entries:
        return None
    today = date.today()
    y, w = iso_week_key(today)
    this_week = [e for e in entries if iso_week_key(e.when) == (y, w)]
    if not this_week:
        return None
    out_path = weekly_summary_path(y, w)
    write_text(out_path, render_weekly_summary(y, w, this_week))
    return out_path


# --- Groq ---

def generate_new_state(prompt: str, brain_dump: str, completed_today: List[str]) -> str:
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    today_str = date.today().isoformat()

    done_context = ""
    if completed_today:
        done_context = "（刚完成的，不要再列出）\n" + "\n".join(completed_today) + "\n\n"

    user_message = f"""{done_context}【用户的 brain dump / 当前状态】

{brain_dump if brain_dump else "（空）"}

---

根据以上内容，生成新的任务清单。格式：

## 今天做这几件就够了

1. **任务名**  
   → 怎么开始（15分钟内能动手）

---

## 今天可以不做

- 任务 — 原因

---

## 如果还有余力

- 可选任务

注意：
- 最多 3-5 个任务
- 不要输出 Done Archive
- 不要输出 - [x] 行
- 只输出上面的格式，不要解释"""

    response = client.chat.completions.create(
        model=DEFAULT_MODEL,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=0.3,
    )
    return response.choices[0].message.content.strip()


# --- Main ---

def main():
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY not set.")

    prompt = read_text(PROMPT_PATH)
    raw_state = read_text(STATE_PATH)

    if not raw_state:
        print("❌ state.md 是空的，随便写点东西再跑")
        return

    # 1. 分离 Done Archive
    main_content, archive_lines = split_done_archive(raw_state)

    # 2. 提取主体中的 [x] 完成项
    done_in_main = extract_done_lines(main_content)
    brain_dump = remove_done_lines(main_content)

    # 3. 标准化完成项（加日期）
    today = date.today()
    newly_done = [normalize_done_item(x, today) for x in done_in_main]

    # 4. 调用模型生成新任务
    new_tasks = generate_new_state(prompt, brain_dump, newly_done)

    # 5. 清理模型输出（防止它输出 Done Archive）
    if DONE_ARCHIVE_HEADER in new_tasks:
        new_tasks = new_tasks.split(DONE_ARCHIVE_HEADER, 1)[0].strip()
    new_tasks = remove_done_lines(new_tasks)

    # 6. 合并 Done Archive
    combined_archive = dedupe_preserve_order(archive_lines + newly_done)

    # 7. 组装最终 state.md
    final_state = new_tasks
    if combined_archive:
        final_state += f"\n\n{DONE_ARCHIVE_HEADER}\n" + "\n".join(combined_archive)

    # 8. 保存
    write_text(STATE_PATH, final_state)

    RUNS_DIR.mkdir(exist_ok=True)
    snap_path = RUNS_DIR / f"state_{timestamp()}.md"
    write_text(snap_path, final_state)

    # 9. 更新周报
    summary_path = update_weekly_summary(combined_archive)

    # 10. 输出
    print("\n===== state.md =====\n")
    print(final_state)
    print(f"\n[Saved] {snap_path}")
    if summary_path:
        print(f"[Weekly] {summary_path}")
    print()


if __name__ == "__main__":
    main()
