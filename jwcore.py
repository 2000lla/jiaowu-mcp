"""通用工具: 学期推算、节次解析、课表渲染与落盘。

这里只放纯函数, 不含任何学校地址、账号、令牌等环境相关信息。
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "outputs"
SESSION = HERE / ".session.json"

WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


# ---------------------------------------------------------------- 学期
def current_term() -> tuple[str, str]:
    """按自然月推断当前学年/学期。xqm: 3=第1学期, 12=第2学期。"""
    today = dt.date.today()
    year = today.year if today.month >= 8 else today.year - 1
    return str(year), "3" if (today.month >= 8 or today.month == 1) else "12"


def parse_term_arg(term: str) -> tuple[str, str]:
    m = re.fullmatch(r"(\d{4})-(\d{1,2})", term.strip())
    if not m:
        raise SystemExit(f"term 格式应为 2026-1 或 2026-2, 收到: {term}")
    return m.group(1), "3" if m.group(2) == "1" else "12"


def term_label(xnm: str, xqm: str) -> tuple[str, str]:
    """返回 (可读学期名, 文件名 slug)。"""
    no = 1 if xqm == "3" else 2
    return f"{xnm}-{int(xnm) + 1} 学年第{no}学期", f"{xnm}-{no}"


# ---------------------------------------------------------------- 节次
def parse_jc(jc: str) -> tuple[int, int]:
    """'1-5节' / '3' / 4位编码 '0102' -> (起节, 止节)。"""
    jc = (jc or "").strip()
    nums = re.findall(r"\d+", jc)
    if not nums:
        return (0, 0)
    if len(nums) >= 2 and "-" in jc:
        return int(nums[0]), int(nums[1])
    if len(nums) == 1:
        n = int(nums[0])
        if n >= 1000 and len(jc) == 4:
            a, b = int(jc[:2]), int(jc[2:])
            return a, b or a
        return n, n
    return int(nums[0]), int(nums[-1])


def normalize(item: dict) -> dict:
    start, end = parse_jc(item.get("jc") or item.get("jcs") or "")
    return {
        "课程": (item.get("kcmc") or "").strip(),
        "教师": (item.get("xm") or "").strip(),
        "地点": (item.get("cdmc") or "").strip(),
        "星期": str(item.get("xqj") or "").strip(),
        "节次": f"{start}-{end}" if start else (item.get("jc") or ""),
        "起始节": start,
        "结束节": end,
        "周次": (item.get("zcd") or "").strip(),
        "教学班": (item.get("jxbmc") or "").strip(),
    }


# ---------------------------------------------------------------- 渲染
def build_grid(courses: list[dict]) -> str:
    slots: dict[int, dict[int, list[str]]] = {}
    for c in courses:
        day = int(c["星期"]) if c["星期"].isdigit() else 0
        if not day:
            continue
        for p in range(c["起始节"], c["结束节"] + 1):
            slots.setdefault(p, {}).setdefault(day, []).append(
                f"{c['课程']} {c['地点']}".strip())
    if not slots:
        return ""
    lines = ["| 节次 | " + " | ".join(WEEKDAYS) + " |", "|" + "---|" * 8]
    for p in range(1, max(slots) + 1):
        cols = []
        for day in range(1, 8):
            e = slots.get(p, {}).get(day, [])
            cols.append("<br>".join(e) if e else " ")
        lines.append(f"| {p} | " + " | ".join(cols) + " |")
    return "\n".join(lines)


def print_console(courses: list[dict], label: str) -> None:
    print(f"\n===== 课表 · {label} ({len(courses)} 条) =====")
    cur = None
    for c in sorted(courses, key=lambda x: (x["星期"], x["起始节"], x["课程"])):
        day = c["星期"]
        if day != cur:
            name = WEEKDAYS[int(day) - 1] if day.isdigit() and 1 <= int(day) <= 7 else day
            print(f"\n【{name}】")
            cur = day
        print(f"  {c['节次']:>5}节  {c['课程']}  @{c['地点']}  "
              f"{c['教师']}  [{c['周次']}]")


def write_outputs(courses: list[dict], label: str, xnm: str, xqm: str,
                  student: dict, slug: str) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    by_day = sorted(courses, key=lambda c: (c["星期"], c["起始节"], c["课程"]))
    payload = {
        "学年": xnm, "学期": 1 if xqm == "3" else 2, "学期名称": label,
        "学生": student, "课程数": len(courses), "课程": by_day,
        "抓取时间": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    (OUT / f"schedule_{slug}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    md = [f"# 课表 · {label}", ""]
    if student.get("姓名"):
        md.append(f"**{student.get('姓名')}** · {student.get('班级', '')}")
        md.append("")
    md.append(f"共 **{len(courses)}** 节次")
    md.append("")
    grid = build_grid(courses)
    if grid:
        md += ["## 周课表", "", grid, ""]
    md += ["## 课程清单", "",
           "| 星期 | 节次 | 课程 | 教师 | 地点 | 周次 |",
           "|---|---|---|---|---|---|"]
    for c in by_day:
        day = (WEEKDAYS[int(c["星期"]) - 1]
               if c["星期"].isdigit() and 1 <= int(c["星期"]) <= 7 else c["星期"])
        md.append(f"| {day} | {c['节次']} | {c['课程']} | {c['教师']} | "
                  f"{c['地点']} | {c['周次']} |")
    (OUT / f"schedule_{slug}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return payload
