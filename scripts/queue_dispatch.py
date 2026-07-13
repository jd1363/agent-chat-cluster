#!/usr/bin/env python3
"""
queue_dispatch.py — 多任务队列调度器（阶段 4）

扫描 tasks/tasks.json 中所有 status==pending 的任务，按优先级
(high > medium > low) 再按 createdAt 升序排序，然后串行（MVP 先不做
真并发）依次调用现有的 scripts/dispatch_task.py 完成派发。

设计原则：
    - 复用现有单任务派发脚本，不重写派发逻辑（通过 subprocess 调用）。
    - 单个任务派发失败不中断整个队列，记录后继续下一个。
    - 调度开始/结束各写一条审计日志（queue_dispatch_start / queue_dispatch_done）。

用法:
    python scripts/queue_dispatch.py                          # 派发全部 pending 任务
    python scripts/queue_dispatch.py --assignee agent-ext-01  # 指定统一 assignee
    python scripts/queue_dispatch.py --max 2                  # 本轮最多派发 2 个
    python scripts/queue_dispatch.py --dry-run                # 只列出派发顺序，不改状态
    python scripts/queue_dispatch.py --execute-real           # 透传给 dispatch_task.py（真实执行 CLI）

仅使用 Python 标准库。
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path as _Path

# 强制 UTF-8 输出，避免 GBK 乱码（与其他脚本一致）
sys.path.insert(0, str(_Path(__file__).resolve().parent))
from fix_encoding import setup_utf8_stdout  # type: ignore

setup_utf8_stdout()

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASKS_FILE = PROJECT_ROOT / "tasks" / "tasks.json"
DISPATCH_SCRIPT = PROJECT_ROOT / "scripts" / "dispatch_task.py"

# 导入审计日志模块
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from audit_log import append_audit  # type: ignore

# 优先级排序权重（数值越小越靠前）
PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def load_tasks() -> dict:
    """只读读取任务台账。"""
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


def collect_pending(tasks: list) -> list:
    """筛选 pending 任务并排序：先优先级 (high>medium>low)，再 createdAt 升序。"""
    pending = [t for t in tasks if t.get("status") == "pending"]
    pending.sort(
        key=lambda t: (
            PRIORITY_ORDER.get(t.get("priority", "low"), 99),
            t.get("createdAt", ""),
        )
    )
    return pending


def dispatch_one(task_id: str, assignee: str, execute_real: bool) -> tuple[bool, str]:
    """
    调用现有 scripts/dispatch_task.py 派发单个任务。

    返回 (成功?, 输出摘要)。派发失败不抛异常，交由上层继续队列。
    """
    cmd = [
        sys.executable,
        str(DISPATCH_SCRIPT),
        "--id",
        task_id,
        "--assignee",
        assignee,
    ]
    if execute_real:
        cmd.append("--execute-real")

    try:
        result = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except Exception as e:  # noqa: BLE001 - 派发失败不中断队列
        return False, f"调用 dispatch_task.py 异常: {e}"

    output = (result.stdout or "") + (result.stderr or "")
    return result.returncode == 0, output.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="多任务队列调度器：串行派发全部 pending 任务")
    parser.add_argument(
        "--assignee",
        default="agent-exec-01",
        help="指定统一 assignee（默认: agent-exec-01）",
    )
    parser.add_argument(
        "--max",
        type=int,
        default=None,
        dest="max_count",
        help="本轮最多派发 n 个任务（默认: 全部）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只列出将要派发的任务顺序，不真正派发、不改状态",
    )
    parser.add_argument(
        "--execute-real",
        action="store_true",
        help="透传给 dispatch_task.py（真实执行 CLI，谨慎使用）",
    )
    args = parser.parse_args()

    data = load_tasks()
    all_tasks = data.get("tasks", [])
    pending = collect_pending(all_tasks)

    # 应用 --max 上限
    if args.max_count is not None:
        if args.max_count < 0:
            print("[FAIL] --max 不能为负数", file=sys.stderr)
            sys.exit(1)
        selected = pending[: args.max_count]
    else:
        selected = pending

    total = len(selected)

    if total == 0:
        print("[INFO] 当前没有 pending 任务可派发")
        return

    # 派发顺序预览
    print(f"[QUEUE] 共 {len(pending)} 个 pending 任务，本轮计划派发 {total} 个")
    print(f"[QUEUE] assignee={args.assignee}  dry-run={args.dry_run}  execute-real={args.execute_real}")
    print("[QUEUE] 派发顺序（优先级 high>medium>low，同级按 createdAt 升序）:")
    for idx, task in enumerate(selected, start=1):
        print(
            f"    [{idx}/{total}] {task.get('id')}  "
            f"priority={task.get('priority')}  "
            f"createdAt={task.get('createdAt')}  "
            f"title={task.get('title', '')[:40]}"
        )

    if args.dry_run:
        print("[DRY-RUN] 未派发任何任务，未修改任何状态")
        return

    # 审计：调度开始
    append_audit(
        event_type="queue_dispatch_start",
        message=f"队列调度开始：计划派发 {total} 个 pending 任务至 {args.assignee}",
        data={
            "assignee": args.assignee,
            "plannedCount": total,
            "executeReal": args.execute_real,
            "taskIds": [t.get("id") for t in selected],
        },
    )

    success_count = 0
    fail_count = 0
    results: list[dict] = []

    for idx, task in enumerate(selected, start=1):
        task_id = task.get("id")
        print(f"\n[{idx}/{total}] Task {task_id} → {args.assignee}")
        ok, output = dispatch_one(task_id, args.assignee, args.execute_real)
        if ok:
            success_count += 1
            print(f"    [OK] {task_id} 派发成功")
        else:
            fail_count += 1
            print(f"    [FAIL] {task_id} 派发失败，继续下一个")
        # 打印子进程输出的最后几行，便于排查
        if output:
            for line in output.splitlines()[-6:]:
                print(f"      | {line}")
        results.append({"taskId": task_id, "success": ok})

    # 汇总
    print(f"\n[SUMMARY] 成功 {success_count} / 失败 {fail_count} （共 {total}）")

    # 审计：调度结束
    append_audit(
        event_type="queue_dispatch_done",
        message=f"队列调度结束：成功 {success_count}，失败 {fail_count}，共 {total}",
        data={
            "assignee": args.assignee,
            "total": total,
            "success": success_count,
            "failed": fail_count,
            "results": results,
        },
    )


if __name__ == "__main__":
    main()
