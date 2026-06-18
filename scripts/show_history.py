#!/usr/bin/env python3
"""
show_history.py — 只读查看历史任务与汇总报告（阶段 2 前置安全闸）

从 tasks/tasks.json 读取任务，从 logs/audit/*.jsonl 读取审计日志，
支持按状态、assignee、优先级、日期范围过滤，支持 JSON 输出和汇总报告。

用法:
    python scripts/show_history.py                              # 默认列出所有任务（表格式）
    python scripts/show_history.py --history                    # 仅历史任务 (done/failed/blocked/cancelled)
    python scripts/show_history.py --status done,failed         # 按状态过滤（逗号分隔）
    python scripts/show_history.py --assignee agent-exec-01     # 按 assignee 过滤
    python scripts/show_history.py --assignee none              # 未指派的任务
    python scripts/show_history.py --since 2026-06-01           # 创建日期下限
    python scripts/show_history.py --until 2026-06-15           # 创建日期上限
    python scripts/show_history.py --priority high              # 按优先级过滤
    python scripts/show_history.py --json                       # JSON 输出
    python scripts/show_history.py --report                     # 汇总报告模式

仅使用 Python 标准库。
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASKS_FILE = PROJECT_ROOT / "tasks" / "tasks.json"
AUDIT_DIR = PROJECT_ROOT / "logs" / "audit"

VALID_STATUSES = {"pending", "in_progress", "done", "failed", "blocked", "cancelled"}
VALID_PRIORITIES = {"low", "medium", "high"}
HISTORICAL_STATUSES = {"done", "failed", "blocked", "cancelled"}


def load_tasks() -> dict:
    """加载 tasks/tasks.json。"""
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


def load_audit_logs() -> list[dict]:
    """读取所有审计日志文件，返回全部记录列表。"""
    if not AUDIT_DIR.is_dir():
        print(f"[WARN] 审计日志目录不存在: {AUDIT_DIR}", file=sys.stderr)
        return []

    records: list[dict] = []
    for logfile in sorted(AUDIT_DIR.glob("*.jsonl")):
        try:
            with open(logfile, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass  # 跳过损坏的行
        except OSError as e:
            print(f"[WARN] 无法读取审计日志 {logfile.name}: {e}", file=sys.stderr)

    return records


def parse_iso_date(s: str | None) -> date | None:
    """解析 ISO 日期字符串 (YYYY-MM-DD)，失败返回 None。"""
    if s is None:
        return None
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        print(f"[WARN] 日期格式无效: {s}，期望 YYYY-MM-DD", file=sys.stderr)
        return None


def task_created_date(task: dict) -> date | None:
    """提取任务的创建日期。"""
    raw = task.get("createdAt", "")
    if not raw:
        return None
    try:
        # 支持 ISO 8601 格式，取日期部分
        return date.fromisoformat(raw[:10])
    except (ValueError, TypeError):
        return None


def filter_tasks(
    tasks: list[dict],
    statuses: set[str] | None,
    assignee: str | None,
    priority: str | None,
    since: date | None,
    until: date | None,
) -> list[dict]:
    """多条件过滤任务列表。"""
    result: list[dict] = []
    for t in tasks:
        # 状态过滤（集合）
        if statuses is not None and t.get("status") not in statuses:
            continue

        # assignee 过滤
        if assignee is not None:
            if assignee == "none":
                actual = t.get("assignee")
                if actual is not None and actual != "":
                    continue
            else:
                if t.get("assignee") != assignee:
                    continue

        # 优先级过滤
        if priority is not None and t.get("priority") != priority:
            continue

        # 日期范围过滤
        cd = task_created_date(t)
        if since is not None and (cd is None or cd < since):
            continue
        if until is not None and (cd is None or cd > until):
            continue

        result.append(t)

    # 按 id 排序
    result.sort(key=lambda x: x.get("id", ""))
    return result


def format_table(tasks: list[dict]) -> str:
    """生成人类可读对齐表格。"""
    if not tasks:
        return "(无匹配任务)"

    id_width = min(max(max(len(t.get("id", "")) for t in tasks), 2), 14)
    title_width = min(max(max(len(t.get("title", "")) for t in tasks), 2), 50)
    status_width = min(max(max(len(t.get("status", "")) for t in tasks), 2), 14)
    assignee_width = min(max(max(len((t.get("assignee") or "-")) for t in tasks), 2), 20)
    priority_width = min(max(max(len(t.get("priority", "")) for t in tasks), 2), 10)
    created_width = 12
    updated_width = 12

    header = (
        f"{'ID':<{id_width}}  "
        f"{'标题':<{title_width}}  "
        f"{'状态':<{status_width}}  "
        f"{'assignee':<{assignee_width}}  "
        f"{'优先级':<{priority_width}}  "
        f"{'创建时间':<{created_width}}  "
        f"{'更新时间':<{updated_width}}"
    )
    sep = "-" * len(header)
    lines = [header, sep]

    for t in tasks:
        tid = t.get("id", "")[:id_width]
        ti = t.get("title", "")[:title_width]
        st = t.get("status", "")[:status_width]
        ae = (t.get("assignee") or "-")[:assignee_width]
        pr = t.get("priority", "")[:priority_width]
        ca = (t.get("createdAt") or "-")[:created_width]
        ua = (t.get("updatedAt") or "-")[:updated_width]

        lines.append(
            f"{tid:<{id_width}}  "
            f"{ti:<{title_width}}  "
            f"{st:<{status_width}}  "
            f"{ae:<{assignee_width}}  "
            f"{pr:<{priority_width}}  "
            f"{ca:<{created_width}}  "
            f"{ua:<{updated_width}}"
        )

    lines.append(f"\n共 {len(tasks)} 个任务")
    return "\n".join(lines)


def compute_duration_hours(task: dict) -> float | None:
    """计算 done/failed 任务从 createdAt 到 updatedAt 的小时数。"""
    created = task.get("createdAt", "")
    updated = task.get("updatedAt", "")
    if not created or not updated:
        return None
    try:
        # 尝试完整 ISO 8601 解析
        ct = datetime.fromisoformat(created)
        ut = datetime.fromisoformat(updated)
        return (ut - ct).total_seconds() / 3600.0
    except (ValueError, TypeError):
        return None


def generate_report(tasks: list[dict], audit_records: list[dict]) -> str:
    """生成汇总报告。"""
    total = len(tasks)
    if total == 0:
        return "台账为空，无报告数据。"

    lines: list[str] = []
    lines.append("=" * 64)
    lines.append("  任务台账汇总报告")
    lines.append("=" * 64)
    lines.append(f"  报告时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"  任务总数: {total}")
    lines.append("")

    # ---- 状态分布 ----
    lines.append("-" * 40)
    lines.append("  状态分布")
    lines.append("-" * 40)
    status_counts: dict[str, int] = defaultdict(int)
    for t in tasks:
        st = t.get("status", "unknown")
        status_counts[st] += 1
    for st in sorted(status_counts.keys()):
        cnt = status_counts[st]
        pct = cnt / total * 100
        bar = "█" * int(pct / 2)
        lines.append(f"  {st:<14} {cnt:>4}  ({pct:5.1f}%)  {bar}")
    lines.append("")

    # ---- 优先级分布 ----
    lines.append("-" * 40)
    lines.append("  优先级分布")
    lines.append("-" * 40)
    priority_counts: dict[str, int] = defaultdict(int)
    for t in tasks:
        pr = t.get("priority", "unknown")
        priority_counts[pr] += 1
    for pr in sorted(priority_counts.keys()):
        cnt = priority_counts[pr]
        pct = cnt / total * 100
        bar = "█" * int(pct / 2)
        lines.append(f"  {pr:<10} {cnt:>4}  ({pct:5.1f}%)  {bar}")
    lines.append("")

    # ---- assignee 分布 ----
    lines.append("-" * 40)
    lines.append("  assignee 分布")
    lines.append("-" * 40)
    assignee_counts: dict[str, int] = defaultdict(int)
    for t in tasks:
        ae = t.get("assignee") or "(未指派)"
        assignee_counts[ae] += 1
    for ae in sorted(assignee_counts.keys(), key=lambda a: assignee_counts[a], reverse=True):
        cnt = assignee_counts[ae]
        pct = cnt / total * 100
        lines.append(f"  {ae:<20} {cnt:>4}  ({pct:5.1f}%)")
    lines.append("")

    # ---- done/failed 平均耗时 ----
    lines.append("-" * 40)
    lines.append("  平均耗时 (done / failed)")
    lines.append("-" * 40)
    for target_status in ("done", "failed"):
        matching = [t for t in tasks if t.get("status") == target_status]
        durations = [d for t in matching if (d := compute_duration_hours(t)) is not None]
        if durations:
            avg = sum(durations) / len(durations)
            if avg >= 24:
                lines.append(f"  {target_status:<10} {len(matching):>3} 个, 平均 {avg/24:.1f} 天 ({avg:.1f} 小时)")
            else:
                lines.append(f"  {target_status:<10} {len(matching):>3} 个, 平均 {avg:.1f} 小时")
        else:
            lines.append(f"  {target_status:<10} {len(matching):>3} 个, 无耗时数据")
    lines.append("")

    # ---- 每日创建直方图 ----
    lines.append("-" * 40)
    lines.append("  每日创建分布")
    lines.append("-" * 40)
    daily: dict[str, int] = defaultdict(int)
    for t in tasks:
        cd = task_created_date(t)
        if cd is not None:
            daily[cd.isoformat()] += 1
    if daily:
        max_cnt = max(daily.values())
        bar_max = 40
        for day_str in sorted(daily.keys()):
            cnt = daily[day_str]
            bar_len = max(1, int(cnt / max_cnt * bar_max))
            bar = "█" * bar_len
            lines.append(f"  {day_str}  {cnt:>3}  {bar}")
    else:
        lines.append("  (无日期数据)")
    lines.append("")

    # ---- 审计日志统计 ----
    if audit_records:
        lines.append("-" * 40)
        lines.append("  审计日志统计")
        lines.append("-" * 40)
        audit_total = len(audit_records)
        event_counts: dict[str, int] = defaultdict(int)
        for r in audit_records:
            event_counts[r.get("eventType", "unknown")] += 1
        lines.append(f"  审计记录总数: {audit_total}")
        for et in sorted(event_counts.keys()):
            lines.append(f"    {et}: {event_counts[et]}")
    else:
        lines.append("-" * 40)
        lines.append("  审计日志: (无数据)")
        lines.append("-" * 40)
    lines.append("")

    lines.append("=" * 64)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="只读查看历史任务与汇总报告")
    parser.add_argument(
        "--status",
        default=None,
        help="按状态过滤，逗号分隔 (如 done,failed)",
    )
    parser.add_argument(
        "--assignee",
        default=None,
        help="按 assignee 过滤；使用 'none' 匹配未指派的任务",
    )
    parser.add_argument(
        "--since",
        default=None,
        help="创建日期下限，格式 YYYY-MM-DD",
    )
    parser.add_argument(
        "--until",
        default=None,
        help="创建日期上限，格式 YYYY-MM-DD",
    )
    parser.add_argument(
        "--priority",
        choices=sorted(VALID_PRIORITIES),
        default=None,
        help="按优先级过滤",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="输出 JSON 格式",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="生成汇总报告",
    )
    parser.add_argument(
        "--history",
        action="store_true",
        help="仅显示历史任务 (done/failed/blocked/cancelled)",
    )
    args = parser.parse_args()

    # 解析状态过滤
    status_filter: set[str] | None = None
    if args.status is not None:
        desired = {s.strip() for s in args.status.split(",") if s.strip()}
        invalid = desired - VALID_STATUSES
        if invalid:
            print(f"[FAIL] 非法状态值: {sorted(invalid)}，允许: {sorted(VALID_STATUSES)}", file=sys.stderr)
            sys.exit(1)
        status_filter = desired
    elif args.history:
        status_filter = HISTORICAL_STATUSES

    # 解析日期
    since = parse_iso_date(args.since)
    until = parse_iso_date(args.until)

    # 加载数据
    data = load_tasks()
    all_tasks: list[dict] = data.get("tasks", [])

    # 过滤
    filtered = filter_tasks(all_tasks, status_filter, args.assignee, args.priority, since, until)

    # 加载审计日志（始终加载，用于 report）
    audit_records = load_audit_logs()

    if args.report:
        # 汇总报告基于过滤后的任务
        print(generate_report(filtered, audit_records))
    elif args.json_output:
        output = {
            "schemaVersion": data.get("schemaVersion"),
            "nextId": data.get("nextId"),
            "count": len(filtered),
            "auditRecords": len(audit_records),
            "tasks": filtered,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        # 默认表格式
        if args.history:
            print("(仅显示历史任务: done, failed, blocked, cancelled)")
        if args.status:
            print(f"状态过滤: {args.status}")
        if args.assignee:
            print(f"assignee: {args.assignee}")
        if args.since:
            print(f"创建日期 >= {args.since}")
        if args.until:
            print(f"创建日期 <= {args.until}")
        if args.priority:
            print(f"优先级: {args.priority}")
        if any([args.history, args.status, args.assignee, args.since, args.until, args.priority]):
            print()
        print(format_table(filtered))


if __name__ == "__main__":
    main()
