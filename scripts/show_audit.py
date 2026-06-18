#!/usr/bin/env python3
"""
show_audit.py — 只读查看审计日志（阶段 2 前置安全闸）

从 logs/audit/*.jsonl 读取审计记录，支持按日期、任务 ID、事件类型过滤，
支持 --limit 限制条数，支持 JSON 输出。不修改任何文件。

用法:
    python scripts/show_audit.py                           # 默认今天，最近20条
    python scripts/show_audit.py --date 2026-06-14          # 指定日期
    python scripts/show_audit.py --task-id Task-001         # 按任务过滤
    python scripts/show_audit.py --event-type task_created  # 按事件类型过滤
    python scripts/show_audit.py --limit 5                  # 限制条数
    python scripts/show_audit.py --json                     # JSON 输出

仅使用 Python 标准库。
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
AUDIT_DIR = PROJECT_ROOT / "logs" / "audit"


def _resolve_date(date_arg: str | None) -> str:
    """解析日期参数，返回 YYYY-MM-DD 字符串。默认今天 UTC。"""
    if date_arg is not None:
        # 简单校验格式 YYYY-MM-DD
        parts = date_arg.split("-")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            print(f"[FAIL] 日期格式无效: {date_arg}，期望 YYYY-MM-DD", file=sys.stderr)
            sys.exit(1)
        return date_arg
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def read_audit_log(date_str: str) -> list[dict]:
    """读取指定日期的审计日志，返回记录列表（最近的在最前）。"""
    log_path = AUDIT_DIR / f"{date_str}.jsonl"
    if not log_path.is_file():
        print(f"[WARN] 审计日志不存在: {log_path}", file=sys.stderr)
        return []

    records = []
    try:
        with open(log_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    # 跳过损坏的行
                    print(f"[WARN] 跳过损坏的审计记录行", file=sys.stderr)
    except OSError as e:
        print(f"[FAIL] 无法读取审计日志: {e}", file=sys.stderr)
        sys.exit(1)

    # 按时间戳降序（最近的在最前）
    records.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
    return records


def filter_records(
    records: list[dict],
    task_id: str | None,
    event_type: str | None,
) -> list[dict]:
    """过滤记录。"""
    result = []
    for r in records:
        if task_id is not None and r.get("taskId") != task_id:
            continue
        if event_type is not None and r.get("eventType") != event_type:
            continue
        result.append(r)
    return result


def format_table(records: list[dict]) -> str:
    """生成人类可读简表。"""
    if not records:
        return "(无匹配审计记录)"

    ts_width = 26
    event_width = max(max(len(r.get("eventType", "")) for r in records), 10)
    task_width = max(max(len(r.get("taskId") or "-") for r in records), 7)
    msg_width = min(max(max(len(r.get("message", "")) for r in records), 20), 80)

    header = (
        f"{'时间':<{ts_width}}  "
        f"{'事件类型':<{event_width}}  "
        f"{'任务ID':<{task_width}}  "
        f"{'描述':<{msg_width}}"
    )
    sep = "-" * len(header)
    lines = [header, sep]

    for r in records:
        ts = r.get("timestamp", "")[:ts_width]
        et = r.get("eventType", "")[:event_width]
        ti = (r.get("taskId") or "-")[:task_width]
        msg = r.get("message", "")[:msg_width]

        lines.append(
            f"{ts:<{ts_width}}  "
            f"{et:<{event_width}}  "
            f"{ti:<{task_width}}  "
            f"{msg:<{msg_width}}"
        )

    lines.append(f"\n共 {len(records)} 条记录")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="只读查看审计日志")
    parser.add_argument(
        "--date",
        default=None,
        help="指定日期，格式 YYYY-MM-DD（默认: 今天 UTC）",
    )
    parser.add_argument(
        "--task-id",
        default=None,
        help="按任务 ID 过滤",
    )
    parser.add_argument(
        "--event-type",
        default=None,
        help="按事件类型过滤（如 task_created, task_dispatched）",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="最多显示条数（默认: 20）",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="输出 JSON 格式",
    )
    args = parser.parse_args()

    date_str = _resolve_date(args.date)
    records = read_audit_log(date_str)

    filtered = filter_records(records, args.task_id, args.event_type)
    limited = filtered[: args.limit]

    if args.json_output:
        output = {
            "date": date_str,
            "total": len(filtered),
            "shown": len(limited),
            "records": limited,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(f"审计日志日期: {date_str}")
        if args.task_id:
            print(f"过滤: taskId={args.task_id}")
        if args.event_type:
            print(f"过滤: eventType={args.event_type}")
        print()
        print(format_table(limited))


if __name__ == "__main__":
    main()
