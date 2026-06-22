#!/usr/bin/env python3
"""
update_task.py — 更新任务字段

用法:
    python scripts/update_task.py --id Task-001 [--status pending|in_progress|done|failed|blocked|cancelled] [--assignee agent-exec-01] [--notes "备注"]

仅更新提供的字段，其余保持不变。
仅使用 Python 标准库。
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASKS_FILE = PROJECT_ROOT / "tasks" / "tasks.json"
VALID_STATUSES = {"pending", "in_progress", "done", "failed", "blocked", "cancelled"}

# 导入审计日志模块
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from audit_log import append_audit  # type: ignore
from file_lock import file_lock  # type: ignore


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
    parser = argparse.ArgumentParser(description="更新任务字段")
    parser.add_argument("--id", required=True, help="任务 ID，如 Task-001")
    parser.add_argument("--status", choices=list(VALID_STATUSES), help="新状态")
    parser.add_argument("--assignee", help="分配给哪个 Agent")
    parser.add_argument("--notes", help="追加备注（会覆盖原有备注）")
    args = parser.parse_args()

    # read-modify-write 原子操作，加排他锁
    try:
        with file_lock(str(TASKS_FILE), mode='exclusive'):
            data = load_tasks()
            tasks = data.get("tasks", [])

            found = None
            for t in tasks:
                if t.get("id") == args.id:
                    found = t
                    break

            if found is None:
                print(f"[FAIL] 找不到任务: {args.id}")
                sys.exit(1)

            updated = False
            changes = {}

            if args.status is not None:
                found["status"] = args.status
                updated = True
                changes["status"] = args.status
                print(f"[OK] 状态更新为: {args.status}")

            if args.assignee is not None:
                found["assignee"] = args.assignee
                updated = True
                changes["assignee"] = args.assignee
                print(f"[OK] 负责人更新为: {args.assignee}")

            if args.notes is not None:
                found["notes"] = args.notes
                updated = True
                changes["notes"] = args.notes
                print(f"[OK] 备注已更新")

            if updated:
                found["updatedAt"] = datetime.now(timezone.utc).isoformat()
                save_tasks(data)
                print(f"[OK] {args.id} 更新完成")
    except TimeoutError as e:
        print(f"[FAIL] 获取文件锁超时: {e}")
        sys.exit(1)

    # 写审计日志（锁外执行，不影响文件操作）
    if updated:
        append_audit(
            event_type="task_updated",
            message=f"更新任务字段: {', '.join(changes.keys())}",
            task_id=args.id,
            data=changes,
        )
    else:
        print(f"[INFO] 未提供任何更新字段，{args.id} 保持不变")


if __name__ == "__main__":
    main()
