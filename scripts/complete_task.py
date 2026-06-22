#!/usr/bin/env python3
"""
complete_task.py — 任务完成/结束脚本（阶段 1）

更新 tasks/tasks.json 中指定任务的状态、输出、摘要与更新时间，
并记录审计日志。

**重要**：本脚本仅做台账更新，不做任何外部动作（不启动 Agent，不执行命令）。

用法:
    python scripts/complete_task.py --id Task-001 --status done --summary "任务完成" [--output path/to/output.md]

仅使用 Python 标准库。
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASKS_FILE = PROJECT_ROOT / "tasks" / "tasks.json"

# 导入审计日志模块
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from audit_log import append_audit  # type: ignore
from file_lock import file_lock  # type: ignore

VALID_FINAL_STATUSES = {"done", "failed", "blocked"}


def load_tasks():
    if not TASKS_FILE.is_file():
        print(f"[FAIL] 找不到文件: {TASKS_FILE}")
        sys.exit(1)
    try:
        with open(TASKS_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as e:
        print(f"[FAIL] JSON 解析错误: {e}")
        sys.exit(1)
    except OSError as e:
        print(f"[FAIL] 无法读取文件: {e}")
        sys.exit(1)


def save_tasks(data):
    try:
        with open(TASKS_FILE, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"[FAIL] 无法写入文件: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="完成任务或标记失败/阻塞")
    parser.add_argument("--id", required=True, help="任务 ID，如 Task-001")
    parser.add_argument("--status", required=True, choices=list(VALID_FINAL_STATUSES), help="终态")
    parser.add_argument("--summary", required=True, help="执行摘要")
    parser.add_argument("--output", default=None, help="输出文件路径（相对路径）")
    parser.add_argument(
        "--force",
        action="store_true",
        help="管理员人工覆盖状态机限制；会写入审计日志",
    )
    args = parser.parse_args()

    # read-modify-write 原子操作，加排他锁
    try:
        with file_lock(str(TASKS_FILE), mode='exclusive'):
            data = load_tasks()
            tasks = data.get("tasks", [])

            target = None
            for t in tasks:
                if t.get("id") == args.id:
                    target = t
                    break

            if target is None:
                print(f"[FAIL] 找不到任务: {args.id}")
                sys.exit(1)

            previous_status = target.get("status")
            if previous_status != "in_progress" and not args.force:
                print(
                    f"[FAIL] 任务 {args.id} 当前状态不是 in_progress（当前: {previous_status}），"
                    "如需管理员覆盖请加 --force"
                )
                sys.exit(1)

            if previous_status != "in_progress" and args.force:
                print(f"[WARN] 管理员 force 覆盖状态流转: {previous_status} -> {args.status}")

            # 更新任务字段
            target["status"] = args.status
            target["updatedAt"] = datetime.now(timezone.utc).isoformat()
            target["notes"] = args.summary
            if args.output is not None:
                target["output"] = args.output

            save_tasks(data)
    except TimeoutError as e:
        print(f"[FAIL] 获取文件锁超时: {e}")
        sys.exit(1)

    # 审计日志事件类型映射
    event_type_map = {
        "done": "task_completed",
        "failed": "task_failed",
        "blocked": "task_blocked",
    }
    event_type = event_type_map[args.status]

    append_audit(
        event_type=event_type,
        message=f"任务标记为 {args.status}。摘要: {args.summary}",
        task_id=args.id,
        data={
            "previousStatus": previous_status,
            "newStatus": args.status,
            "summary": args.summary,
            "output": args.output,
            "force": args.force,
        },
    )

    print(f"[OK] {args.id} 已更新为 {args.status}")


if __name__ == "__main__":
    main()
