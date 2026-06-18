#!/usr/bin/env python3
"""
show_history.py — 历史任务查询与统计报表

从 tasks/tasks.json 读取任务，支持按状态、assignee、日期范围、优先级过滤，
支持 JSON 输出与报表模式。可读取 logs/audit/*.jsonl 做事件补充统计。

用法:
    python scripts/show_history.py
    python scripts/show_history.py --status done,failed
    python scripts/show_history.py --assignee agent-exec-01 --since 2026-06-01
    python scripts/show_history.py --report
    python scripts/show_history.py --report --status done
    python scripts/show_history.py --json --since 2026-06-01 --until 2026-06-30

仅使用 Python 标准库。
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASKS_FILE = PROJECT_ROOT / "tasks" / "tasks.json"
AUDIT_DIR = PROJECT_ROOT / "logs" / "audit"

VALID_STATUSES = {"pending", "in_progress", "done", "failed", "blocked", "cancelled"}
VALID_PRIORITIES = {"low", "medium", "high"}


def load_tasks() -> dict:
    if not TASKS_FILE.is_file():
        print(f"[FAIL] 找不到文件: {TASKS_FILE}", file=sys.stderr)
        sys.exit(1)
    try:
        with open(TASKS_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as e:
        print(f"[FAIL] JSON 解析错误: {e}", file=sys.stderr)
        sys.exit(1)
    except OSError as e:
        print(f"[FAIL] 无法读取文件: {e}", file=sys.stderr)
        sys.exit(1)


def parse_iso_date(s: str) -> datetime:
    """解析 ISO 8601 日期字符串，失败时退出。"""
    try:
        # 处理带或不带时区的情况
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except ValueError as e:
        print(f"[FAIL] 日期解析错误 ({s}): {e}", file=sys.stderr)
        sys.exit(1)


def filter_tasks(
    tasks: list,
    statuses: set[str] | None,
    assignee: str | None,
    since: str | None,
    until: str | None,
    priority: str | None,
) -> list:
    result = []
    for t in tasks:
        if statuses is not None and t.get("status") not in statuses:
            continue

        if assignee is not None:
            if assignee == "none":
                actual = t.get("assignee")
                if actual is not None and actual != "":
                    continue
            else:
                if t.get("assignee") != assignee:
                    continue

        created_at = t.get("createdAt", "")
        if since is not None:
            if created_at < since:
                continue
        if until is not None:
            if created_at > until:
                continue

        if priority is not None and t.get("priority") != priority:
            continue

        result.append(t)

    result.sort(key=lambda x: x.get("id", ""))
    return result


def format_table(tasks: list) -> str:
    if not tasks:
        return "(无匹配任务)"

    id_width = max(max(len(t.get("id", "")) for t in tasks), 6)
    status_width = max(max(len(t.get("status", "")) for t in tasks), 6)
    title_width = max(max(len(t.get("title", "")) for t in tasks), 5)
    priority_width = max(max(len(t.get("priority", "")) for t in tasks), 8)
    assignee_width = max(max(len(t.get("assignee") or "-") for t in tasks), 8)

    id_width = min(id_width, 12)
    status_width = min(status_width, 14)
    title_width = min(title_width, 50)
    priority_width = min(priority_width, 10)
    assignee_width = min(assignee_width, 20)

    header = (
        f"{'ID':<{id_width}}  {'状态':<{status_width}}  "
        f"{'标题':<{title_width}}  {'优先级':<{priority_width}}  "
        f"{'assignee':<{assignee_width}}  {'创建时间':<20}  {'更新时间':<20}"
    )
    sep = "-" * len(header)
    lines = [header, sep]

    for t in tasks:
        tid = t.get("id", "")[:id_width]
        st = t.get("status", "")[:status_width]
        ti = t.get("title", "")[:title_width]
        pr = t.get("priority", "")[:priority_width]
        ae = (t.get("assignee") or "-")[:assignee_width]
        ct = (t.get("createdAt", "")[:19])[:20]  # 截取 YYYY-MM-DDTHH:MM:SS
        ut = (t.get("updatedAt", "")[:19])[:20]

        lines.append(
            f"{tid:<{id_width}}  {st:<{status_width}}  "
            f"{ti:<{title_width}}  {pr:<{priority_width}}  "
            f"{ae:<{assignee_width}}  {ct:<20}  {ut:<20}"
        )

    lines.append(f"\n共 {len(tasks)} 个任务")
    return "\n".join(lines)


def load_all_audit_records() -> list[dict]:
    """读取 logs/audit 下所有 .jsonl 文件。"""
    records = []
    if not AUDIT_DIR.is_dir():
        return records

    for log_path in sorted(AUDIT_DIR.glob("*.jsonl")):
        try:
            with open(log_path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        print(f"[WARN] 跳过损坏的审计记录行: {log_path.name}", file=sys.stderr)
        except OSError as e:
            print(f"[WARN] 无法读取审计日志 {log_path.name}: {e}", file=sys.stderr)

    records.sort(key=lambda r: r.get("timestamp", ""))
    return records


def compute_duration(created: str, updated: str) -> float | None:
    """返回两个 ISO 时间之间的秒数，失败返回 None。"""
    try:
        c = parse_iso_date(created)
        u = parse_iso_date(updated)
        return (u - c).total_seconds()
    except Exception:
        return None


def format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds / 60)}m"
    if seconds < 86400:
        return f"{seconds / 3600:.1f}h"
    return f"{seconds / 86400:.1f}d"


def generate_report(tasks: list, audit_records: list[dict]) -> str:
    lines = []
    lines.append("=" * 60)
    lines.append("            历史任务统计报表")
    lines.append("=" * 60)
    lines.append("")

    # 1. 总数
    lines.append(f"总任务数: {len(tasks)}")
    lines.append("")

    # 2. 按状态分布
    status_counts = Counter(t.get("status", "unknown") for t in tasks)
    lines.append("【按状态分布】")
    for st in sorted(VALID_STATUSES):
        cnt = status_counts.get(st, 0)
        pct = (cnt / len(tasks) * 100) if tasks else 0
        lines.append(f"  {st:<14} : {cnt:>3}  ({pct:>5.1f}%)")
    lines.append("")

    # 3. 按 assignee 分布
    assignee_counts = Counter(
        (t.get("assignee") or "未指派") for t in tasks
    )
    lines.append("【按 assignee 分布】")
    for ae, cnt in assignee_counts.most_common():
        lines.append(f"  {ae:<20} : {cnt:>3}")
    lines.append("")

    # 4. 按优先级分布
    priority_counts = Counter(t.get("priority", "unknown") for t in tasks)
    lines.append("【按优先级分布】")
    for pr in ["high", "medium", "low"]:
        cnt = priority_counts.get(pr, 0)
        lines.append(f"  {pr:<10} : {cnt:>3}")
    lines.append("")

    # 5. 平均耗时（仅 done/failed）
    terminal_tasks = [t for t in tasks if t.get("status") in ("done", "failed")]
    durations = []
    for t in terminal_tasks:
        d = compute_duration(t.get("createdAt", ""), t.get("updatedAt", ""))
        if d is not None and d >= 0:
            durations.append(d)

    if durations:
        avg_sec = sum(durations) / len(durations)
        lines.append("【平均执行耗时 (done/failed)】")
        lines.append(f"  样本数: {len(durations)}")
        lines.append(f"  平均:   {format_duration(avg_sec)}")
        lines.append(f"  最短:   {format_duration(min(durations))}")
        lines.append(f"  最长:   {format_duration(max(durations))}")
    else:
        lines.append("【平均执行耗时】无 done/failed 任务或时间数据缺失")
    lines.append("")

    # 6. 每日创建直方图
    day_counts = defaultdict(int)
    for t in tasks:
        created = t.get("createdAt", "")
        if created:
            day = created[:10]  # YYYY-MM-DD
            day_counts[day] += 1

    if day_counts:
        lines.append("【每日创建任务数】")
        for day in sorted(day_counts):
            cnt = day_counts[day]
            bar = "█" * min(cnt, 40)
            lines.append(f"  {day}  {cnt:>3}  {bar}")
    lines.append("")

    # 7. 审计事件统计（可选补充）
    if audit_records:
        event_counts = Counter(r.get("eventType", "unknown") for r in audit_records)
        lines.append("【审计事件统计 (全量)】")
        for ev, cnt in event_counts.most_common():
            lines.append(f"  {ev:<20} : {cnt:>3}")
        lines.append("")

    lines.append("=" * 60)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="历史任务查询与统计报表")
    parser.add_argument(
        "--status",
        default=None,
        help="按状态过滤，逗号分隔 (如 done,failed,blocked)",
    )
    parser.add_argument(
        "--assignee",
        default=None,
        help="按 assignee 过滤；使用 'none' 匹配未指派的任务",
    )
    parser.add_argument(
        "--since",
        default=None,
        help="创建时间不早于，格式 YYYY-MM-DD 或完整 ISO",
    )
    parser.add_argument(
        "--until",
        default=None,
        help="创建时间不晚于，格式 YYYY-MM-DD 或完整 ISO",
    )
    parser.add_argument(
        "--priority",
        choices=sorted(VALID_PRIORITIES),
        default=None,
        help="按优先级过滤",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="生成统计报表（替代默认表格输出）",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="输出 JSON 格式（与 --report 互斥，优先 report）",
    )
    parser.add_argument(
        "--history",
        action="store_true",
        help="默认只显示历史任务 (done/failed/blocked/cancelled)",
    )
    args = parser.parse_args()

    # 解析 status 参数
    statuses = None
    if args.status:
        parts = [s.strip() for s in args.status.split(",")]
        invalid = [p for p in parts if p not in VALID_STATUSES]
        if invalid:
            print(
                f"[FAIL] 非法状态值: {invalid}，允许: {sorted(VALID_STATUSES)}",
                file=sys.stderr,
            )
            sys.exit(1)
        statuses = set(parts)

    # 如果 --history 且未指定 --status，默认过滤历史状态
    if args.history and statuses is None:
        statuses = {"done", "failed", "blocked", "cancelled"}

    data = load_tasks()
    all_tasks = data.get("tasks", [])

    filtered = filter_tasks(
        all_tasks,
        statuses,
        args.assignee,
        args.since,
        args.until,
        args.priority,
    )

    if args.report:
        audit_records = load_all_audit_records()
        print(generate_report(filtered, audit_records))
    elif args.json_output:
        output = {
            "schemaVersion": data.get("schemaVersion"),
            "nextId": data.get("nextId"),
            "count": len(filtered),
            "tasks": filtered,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        # 打印过滤条件摘要
        filters_desc = []
        if statuses:
            filters_desc.append(f"status={','.join(sorted(statuses))}")
        if args.assignee:
            filters_desc.append(f"assignee={args.assignee}")
        if args.since:
            filters_desc.append(f"since={args.since}")
        if args.until:
            filters_desc.append(f"until={args.until}")
        if args.priority:
            filters_desc.append(f"priority={args.priority}")
        if filters_desc:
            print(f"过滤条件: {' | '.join(filters_desc)}")
            print()
        print(format_table(filtered))


if __name__ == "__main__":
    main()
