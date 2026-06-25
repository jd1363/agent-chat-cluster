#!/usr/bin/env python3
"""
validate_task.py — 任务台账与 Agent 注册表校验（阶段 2 前置安全闸）

校验 tasks/tasks.json 与 config/agents.json：
  - schemaVersion 存在。
  - tasks 是 list。
  - 每个任务必须有 id/title/status/priority。
  - status 只能是 pending,in_progress,done,failed,blocked,cancelled。
  - priority 只能是 low,medium,high。
  - id 格式必须是 Task-三位数字，如 Task-001。
  - 如果任务有 assignee 且不为 null/空字符串，必须存在于
    config/agents.json 且 enabled=true。

用法:
    python scripts/validate_task.py

仅使用 Python 标准库。
"""

import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASKS_FILE = PROJECT_ROOT / "tasks" / "tasks.json"
AGENTS_FILE = PROJECT_ROOT / "config" / "agents.json"

VALID_STATUSES = {"pending", "in_progress", "done", "failed", "blocked", "cancelled"}
VALID_PRIORITIES = {"low", "medium", "high"}
TASK_ID_PATTERN = re.compile(r"^Task-\d{3}$")

exit_code = 0


def fail(msg: str):
    """输出 [FAIL] 并设置退出码为 1。"""
    global exit_code
    print(f"[FAIL] {msg}")
    exit_code = 1


def ok(msg: str):
    """输出 [OK]。"""
    print(f"[OK] {msg}")


def load_json(filepath: Path) -> dict | None:
    """加载 JSON 文件，失败返回 None。"""
    if not filepath.is_file():
        fail(f"找不到文件: {filepath}")
        return None
    try:
        with open(filepath, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as e:
        fail(f"JSON 解析错误 ({filepath.name}): {e}")
        return None
    except OSError as e:
        fail(f"无法读取文件 ({filepath.name}): {e}")
        return None


def load_agents() -> dict[str, dict]:
    """返回 {agent_id: agent_obj} 映射。"""
    data = load_json(AGENTS_FILE)
    if data is None:
        return {}
    agents_list = data.get("agents", [])
    if not isinstance(agents_list, list):
        fail("config/agents.json: agents 不是 list")
        return {}
    enabled_map: dict[str, dict] = {}
    for agent in agents_list:
        aid = agent.get("id", "")
        if aid:
            enabled_map[aid] = agent
    return enabled_map


def validate_tasks():
    data = load_json(TASKS_FILE)
    if data is None:
        return

    # 1. schemaVersion
    if "schemaVersion" not in data:
        fail("tasks.json: 缺少 schemaVersion")
    else:
        ok(f"schemaVersion: {data['schemaVersion']}")

    # 2. tasks 是 list
    tasks = data.get("tasks")
    if not isinstance(tasks, list):
        fail("tasks.json: tasks 不是 list")
        return

    ok(f"tasks 是 list，共 {len(tasks)} 个任务")

    if len(tasks) == 0:
        ok("台账为空，跳过逐条校验")
        return

    # 加载 agents 用于 assignee 校验
    agents_map = load_agents()

    # 3-7. 逐条校验
    seen_ids: set[str] = set()
    for i, task in enumerate(tasks):
        prefix = f"tasks[{i}]"
        tid = task.get("id")

        # 必须有 id
        if "id" not in task:
            fail(f"{prefix}: 缺少 id 字段")
            continue
        if not isinstance(tid, str) or tid.strip() == "":
            fail(f"{prefix}: id 为空或非字符串")
            continue

        # id 格式必须是 Task-三位数字
        if not TASK_ID_PATTERN.match(tid):
            fail(f"{prefix}: id 格式不合法 (期望 Task-三位数字, 实际: {tid})")
        else:
            ok(f"{prefix} ({tid}): id 格式合法")

        # 检查重复 id
        if tid in seen_ids:
            fail(f"{prefix} ({tid}): id 重复")
        seen_ids.add(tid)

        # 必须有 title
        if "title" not in task:
            fail(f"{prefix} ({tid}): 缺少 title 字段")
        elif not isinstance(task["title"], str) or task["title"].strip() == "":
            fail(f"{prefix} ({tid}): title 为空或非字符串")

        # 必须有 status
        if "status" not in task:
            fail(f"{prefix} ({tid}): 缺少 status 字段")
        else:
            st = task["status"]
            if st not in VALID_STATUSES:
                fail(f"{prefix} ({tid}): 非法 status 值 ({st})，允许: {sorted(VALID_STATUSES)}")
            else:
                ok(f"{prefix} ({tid}): status={st}")

        # 必须有 priority
        if "priority" not in task:
            fail(f"{prefix} ({tid}): 缺少 priority 字段")
        else:
            pr = task["priority"]
            if pr not in VALID_PRIORITIES:
                fail(f"{prefix} ({tid}): 非法 priority 值 ({pr})，允许: {sorted(VALID_PRIORITIES)}")
            else:
                ok(f"{prefix} ({tid}): priority={pr}")

        # assignee 校验
        assignee = task.get("assignee")
        if assignee is not None and assignee != "":
            if assignee not in agents_map:
                fail(f"{prefix} ({tid}): assignee '{assignee}' 不在 config/agents.json 中")
            else:
                agent_obj = agents_map[assignee]
                if not agent_obj.get("enabled", False):
                    # 只对活跃状态（pending/in_progress）的任务报错，历史任务只警告
                    if st in ("pending", "in_progress"):
                        fail(f"{prefix} ({tid}): assignee '{assignee}' 未启用 (enabled=false)")
                    else:
                        ok(f"{prefix} ({tid}): assignee '{assignee}' (历史任务，Agent 已禁用)")
                else:
                    ok(f"{prefix} ({tid}): assignee '{assignee}' 存在且已启用")


def main():
    ok("开始校验 agent-chat-cluster 台账与 Agent 注册表")
    validate_tasks()

    if exit_code != 0:
        print(f"\n[FAIL] 校验未通过，发现 {exit_code} 处错误")
    else:
        print(f"\n[OK] 所有校验通过")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
