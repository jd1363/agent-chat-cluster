#!/usr/bin/env python3
"""
list_tasks.py — 只读查看任务台账（阶段 2 前置安全闸）

从 tasks/tasks.json 读取任务列表，支持按状态、assignee 过滤，
支持 JSON 输出。不修改任何文件。

用法:
    python scripts/list_tasks.py                          # 默认列出所有任务
    python scripts/list_tasks.py --status pending         # 按状态过滤
    python scripts/list_tasks.py --assignee agent-exec-01 # 按 assignee 过滤
    python scripts/list_tasks.py --assignee none          # 未指派的
    python scripts/list_tasks.py --json                   # JSON 输出

仅使用 Python 标准库。
"""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASKS_FILE = PROJECT_ROOT / "tasks" / "tasks.json"

VALID_STATUSES = {"pending", "in_progress", "done", "failed", "blocked", "cancelled"}


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


def filter_tasks(tasks: list, status: str | None, assignee: str | None) -> list:
    """过滤任务列表。"""
    result = []
    for t in tasks:
        # 状态过滤
        if status is not None:
            if t.get("status") != status:
                continue

        # assignee 过滤
        if assignee is not None:
            if assignee == "none":
                # 匹配 assignee 为 null、None、空字符串或不存在
                actual = t.get("assignee")
                if actual is not None and actual != "":
                    continue
            else:
                if t.get("assignee") != assignee:
                    continue

        result.append(t)

    # 按 id 排序
    result.sort(key=lambda x: x.get("id", ""))
    return result


def format_table(tasks: list) -> str:
    """生成人类可读简表。"""
    if not tasks:
        return "(无匹配任务)"

    # 计算列宽
    id_width = max(max(len(t.get("id", "")) for t in tasks), 6)
    status_width = max(max(len(t.get("status", "")) for t in tasks), 6)
    title_width = max(max(len(t.get("title", "")) for t in tasks), 5)
    priority_width = max(max(len(t.get("priority", "")) for t in tasks), 8)
    assignee_width = max(max(len(t.get("assignee") or "-") for t in tasks), 8)

    # 总宽度不超过合理范围
    id_width = min(id_width, 12)
    status_width = min(status_width, 14)
    title_width = min(title_width, 50)
    priority_width = min(priority_width, 10)
    assignee_width = min(assignee_width, 20)

    header = (
        f"{'ID':<{id_width}}  {'状态':<{status_width}}  "
        f"{'标题':<{title_width}}  {'优先级':<{priority_width}}  "
        f"{'assignee':<{assignee_width}}"
    )
    sep = "-" * len(header)
    lines = [header, sep]

    for t in tasks:
        tid = t.get("id", "")[:id_width]
        st = t.get("status", "")[:status_width]
        ti = t.get("title", "")[:title_width]
        pr = t.get("priority", "")[:priority_width]
        ae = (t.get("assignee") or "-")[:assignee_width]

        lines.append(
            f"{tid:<{id_width}}  {st:<{status_width}}  "
            f"{ti:<{title_width}}  {pr:<{priority_width}}  "
            f"{ae:<{assignee_width}}"
        )

    lines.append(f"\n共 {len(tasks)} 个任务")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="只读查看任务台账")
    parser.add_argument(
        "--status",
        choices=sorted(VALID_STATUSES),
        default=None,
        help="按状态过滤",
    )
    parser.add_argument(
        "--assignee",
        default=None,
        help="按 assignee 过滤；使用 'none' 匹配未指派的任务",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="输出 JSON 格式",
    )
    args = parser.parse_args()

    data = load_tasks()
    all_tasks = data.get("tasks", [])

    filtered = filter_tasks(all_tasks, args.status, args.assignee)

    if args.json_output:
        output = {
            "schemaVersion": data.get("schemaVersion"),
            "nextId": data.get("nextId"),
            "count": len(filtered),
            "tasks": filtered,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(format_table(filtered))


if __name__ == "__main__":
    main()
