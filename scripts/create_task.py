#!/usr/bin/env python3
"""
create_task.py — 向 tasks/tasks.json 添加任务

用法:
    python scripts/create_task.py --title "任务标题" [--priority low|medium|high]

任务 ID 自动生成，格式 Task-NNN，默认状态 pending。
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
from event_log import build_event, append_event  # type: ignore


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


def generate_task_id(data):
    next_id = data.get("nextId", 1)
    return f"Task-{next_id:03d}", next_id


def main():
    parser = argparse.ArgumentParser(description="创建新任务")
    parser.add_argument("--title", required=True, help="任务标题")
    parser.add_argument(
        "--description",
        default="",
        help="任务详细描述（会原样传给执行 Agent）",
    )
    parser.add_argument(
        "--priority",
        choices=["low", "medium", "high"],
        default="medium",
        help="任务优先级 (默认: medium)",
    )
    args = parser.parse_args()

    # 整个 read-modify-write 在排他锁内，确保原子性
    try:
        with file_lock(str(TASKS_FILE), mode="exclusive"):
            data = load_tasks()
            task_id, current_next = generate_task_id(data)

            now = datetime.now(timezone.utc).isoformat()

            task = {
                "id": task_id,
                "title": args.title,
                "description": args.description,
                "status": "pending",
                "priority": args.priority,
                "assignee": None,
                "createdAt": now,
                "updatedAt": now,
                "output": None,
                "notes": "",
            }

            data.setdefault("tasks", []).append(task)
            data["nextId"] = current_next + 1

            save_tasks(data)
    except TimeoutError as e:
        print(f"[FAIL] 获取文件锁超时: {e}")
        sys.exit(1)

    # 写审计日志
    append_audit(
        event_type="task_created",
        message=f"创建任务: {args.title}",
        task_id=task_id,
        data={"priority": args.priority},
    )

    # 写事件日志
    try:
        event = build_event(
            event_type="task.created",
            source="create_task",
            correlation_id=task_id,
            payload={"taskId": task_id, "title": args.title, "priority": args.priority, "assignee": None},
        )
        append_event(event)
    except Exception as e:
        print(f"[WARN] 事件日志追加失败: {e}")

    print(f"[OK] 已创建 {task_id}: {args.title} (priority={args.priority})")


if __name__ == "__main__":
    main()
