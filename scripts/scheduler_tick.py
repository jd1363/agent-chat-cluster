#!/usr/bin/env python3
"""
scheduler_tick.py — Scheduler Tick dry-run (Milestone C)

从统一系统状态读取任务/Agent/策略，执行保守调度判断，
输出推荐或阻塞原因。当前版本只做 dry-run，不真实派工。

用法:
    python scripts/scheduler_tick.py --dry-run
    python scripts/scheduler_tick.py --dry-run --json
    python scripts/scheduler_tick.py --state state/system_state.json --dry-run
    python scripts/scheduler_tick.py --write-event --dry-run

仅使用 Python 标准库。
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# 项目路径
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATE = PROJECT_ROOT / "state" / "system_state.json"

# 优先级顺序：high > medium > low > 其他
PRIORITY_ORDER: Dict[str, int] = {"high": 0, "medium": 1, "low": 2}


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def fail(message: str) -> None:
    """输出错误信息并以 exit 1 终止。"""
    print(f"[FAIL] {message}", file=sys.stderr)
    sys.exit(1)


def utc_now_iso() -> str:
    """返回 UTC ISO 8601 时间戳。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_json(path: Path) -> Dict[str, Any]:
    """读取 JSON 文件，解析失败则 fail。"""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as e:
        fail(f"JSON 解析失败: {path} — {e}")
    except FileNotFoundError:
        fail(
            f"状态文件不存在: {path}\n"
            f"请先运行: python scripts/build_state.py --output state/system_state.json"
        )
    except OSError as e:
        fail(f"无法读取文件: {path} — {e}")
    if not isinstance(data, dict):
        fail(f"文件根元素必须是 object: {path}")
    return data


def priority_sort_key(task: Dict[str, Any]) -> tuple:
    """按 priority（high > medium > low > 其他），同优先级按 createdAt 升序。"""
    priority = task.get("priority", "unknown")
    order = PRIORITY_ORDER.get(priority, 99)
    created_at = task.get("createdAt", "")
    return (order, created_at)


# ---------------------------------------------------------------------------
# 调度逻辑
# ---------------------------------------------------------------------------

def get_pending_tasks(
    tasks_state: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """从 tasks 状态域中提取 status == 'pending' 的任务，按优先级排序。"""
    items: List[Dict[str, Any]] = tasks_state.get("items", [])
    if not isinstance(items, list):
        return []

    pending = [t for t in items if isinstance(t, dict) and t.get("status") == "pending"]
    pending.sort(key=priority_sort_key)
    return pending


def get_enabled_agents(
    agents_state: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """从 agents 状态域中提取 enabled == true 的 Agent。"""
    items: List[Dict[str, Any]] = agents_state.get("items", [])
    if not isinstance(items, list):
        return []

    enabled = [
        a for a in items
        if isinstance(a, dict) and a.get("enabled") is True
    ]
    return enabled


def get_retry_count(task: Dict[str, Any]) -> int:
    """读取任务重试次数，兼容未来可能出现的字段名。

    当前 tasks.json 尚未正式引入 retry 字段，因此缺省为 0。
    """
    for key in ("retryCount", "retries", "attempts"):
        value = task.get(key)
        if isinstance(value, int):
            return value
    return 0


def count_in_progress_by_agent(tasks_state: Dict[str, Any]) -> Dict[str, int]:
    """只统计 in_progress 任务负载，避免 done/failed 历史任务污染调度。"""
    counts: Dict[str, int] = {}
    items: List[Dict[str, Any]] = tasks_state.get("items", [])
    if not isinstance(items, list):
        return counts
    for task in items:
        if not isinstance(task, dict):
            continue
        if task.get("status") != "in_progress":
            continue
        assignee = task.get("assignee")
        if assignee:
            agent_id = str(assignee)
            counts[agent_id] = counts.get(agent_id, 0) + 1
    return counts


def select_agent(
    enabled_agents: List[Dict[str, Any]],
    by_assignee: Dict[str, int],
) -> Optional[Dict[str, Any]]:
    """从已启用 Agent 中选择负载最低的。
    
    优先选择当前任务数较少的 Agent（使用 byAssignee 估算负载），
    同负载按 agent id 排序。
    """
    if not enabled_agents:
        return None

    def agent_load(agent: Dict[str, Any]) -> tuple:
        agent_id = agent.get("id", "")
        load = by_assignee.get(agent_id, 0)
        return (load, agent_id)

    sorted_agents = sorted(enabled_agents, key=agent_load)
    return sorted_agents[0]


def run_tick(state: Dict[str, Any]) -> Dict[str, Any]:
    """执行单次调度判断，返回决策结果字典。

    不修改任何文件，不发送消息，不派工。
    """
    tasks_state: Dict[str, Any] = state.get("tasks", {})
    agents_state: Dict[str, Any] = state.get("agents", {})
    policy_state: Dict[str, Any] = state.get("policy", {})
    scheduler_state: Dict[str, Any] = state.get("scheduler", {})

    if not isinstance(tasks_state, dict):
        fail("state['tasks'] 必须是 object")
    if not isinstance(agents_state, dict):
        fail("state['agents'] 必须是 object")
    if not isinstance(policy_state, dict):
        fail("state['policy'] 必须是 object")
    if not isinstance(scheduler_state, dict):
        fail("state['scheduler'] 必须是 object")

    # 提取关键数据
    pending_tasks = get_pending_tasks(tasks_state)
    enabled_agents = get_enabled_agents(agents_state)
    by_assignee: Dict[str, int] = count_in_progress_by_agent(tasks_state)

    max_concurrency: int = policy_state.get("maxConcurrency", 1)
    max_retries: int = policy_state.get("maxRetries", 1)
    in_progress: int = scheduler_state.get("inProgressTasks", 0)
    pending_count: int = len(pending_tasks)
    available_count: int = len(enabled_agents)
    capacity: int = max_concurrency

    retry_exhausted_tasks: List[Dict[str, Any]] = [
        t for t in pending_tasks if get_retry_count(t) > max_retries
    ]
    schedulable_tasks: List[Dict[str, Any]] = [
        t for t in pending_tasks if get_retry_count(t) <= max_retries
    ]

    reasons: List[str] = []
    warnings: List[str] = []
    decision: str
    selected_task: Optional[Dict[str, Any]] = None
    selected_agent: Optional[Dict[str, Any]] = None

    if pending_count > available_count * max_concurrency and pending_count > 0:
        warnings.append(
            "backpressure: pending tasks exceed available scheduling capacity "
            f"({pending_count} > {available_count} agents × {max_concurrency})"
        )
    if retry_exhausted_tasks:
        warnings.append(
            f"{len(retry_exhausted_tasks)} pending task(s) exceed maxRetries={max_retries}; "
            "candidate for dead-letter handling"
        )

    # 步骤 1: 检查是否有 pending task
    if pending_count == 0:
        decision = "idle"
        reasons.append("no pending tasks")
    # 步骤 2: 检查 maxConcurrency
    elif in_progress >= max_concurrency:
        decision = "blocked"
        reasons.append(
            f"maxConcurrency reached (inProgress={in_progress}, max={max_concurrency})"
        )
    # 步骤 3: 检查是否有可用 Agent
    elif available_count == 0:
        decision = "blocked"
        reasons.append("no enabled agents available")
    # 步骤 4: retry 策略过滤
    elif not schedulable_tasks:
        decision = "blocked"
        reasons.append("all pending tasks exceed retry policy; dead-letter handling required")
    # 步骤 5: 可以调度
    else:
        decision = "suggest_dispatch"
        selected_task = schedulable_tasks[0]
        selected_agent = select_agent(enabled_agents, by_assignee)
        if selected_agent is None:
            decision = "blocked"
            reasons.append("no agent could be selected (internal error)")
        else:
            reasons.append(
                f"task '{selected_task.get('id', '?')}' "
                f"(priority={selected_task.get('priority', '?')}) "
                f"→ agent '{selected_agent.get('id', '?')}'"
            )

    constraints = {
        "maxConcurrency": max_concurrency,
        "maxRetries": max_retries,
        "inProgressTasks": in_progress,
        "pendingTasks": pending_count,
        "availableAgents": available_count,
        "capacity": capacity,
        "backpressure": bool(warnings),
    }

    result: Dict[str, Any] = {
        "schemaVersion": "1.0",
        "generatedAt": utc_now_iso(),
        "mode": "dry-run",
        "decision": decision,
        "selectedTask": selected_task["id"] if selected_task else None,
        "selectedAgent": selected_agent["id"] if selected_agent else None,
        "reasons": reasons,
        "warnings": warnings,
        "deadLetterCandidates": [t.get("id") for t in retry_exhausted_tasks],
        "constraints": constraints,
        "wouldWriteEvent": False,
        "eventId": None,
    }

    return result


# ---------------------------------------------------------------------------
# 事件写入（通过 event_log.py 子进程）
# ---------------------------------------------------------------------------

def write_scheduler_event(decision_result: Dict[str, Any]) -> str:
    """通过 event_log.py 子进程写入 scheduler.tick.evaluated 事件。
    
    返回 eventId。
    """
    payload = {
        "decision": decision_result["decision"],
        "selectedTask": decision_result["selectedTask"],
        "selectedAgent": decision_result["selectedAgent"],
        "reasons": decision_result["reasons"],
        "constraints": decision_result["constraints"],
        "warnings": decision_result.get("warnings", []),
        "deadLetterCandidates": decision_result.get("deadLetterCandidates", []),
    }

    script = str(PROJECT_ROOT / "scripts" / "event_log.py")
    cmd = [
        sys.executable,
        script,
        "append",
        "--event-type", "scheduler.tick.evaluated",
        "--source", "scheduler",
        "--payload", json.dumps(payload, ensure_ascii=False),
        "--json",
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        fail("写入事件超时（30s）")
    except OSError as e:
        fail(f"无法启动 event_log.py: {e}")

    if proc.returncode != 0:
        fail(f"写入事件失败: {proc.stderr.strip()}")

    stdout = proc.stdout.strip()
    if not stdout:
        fail("写入事件后无输出")

    try:
        event_data = json.loads(stdout)
    except json.JSONDecodeError as e:
        fail(f"解析事件输出失败: {e} — 输出: {stdout[:200]}")

    return event_data.get("eventId", "unknown")


# ---------------------------------------------------------------------------
# 人类可读摘要
# ---------------------------------------------------------------------------

def print_summary(result: Dict[str, Any]) -> None:
    """打印人类可读摘要。"""
    constraints = result["constraints"]
    decision = result["decision"]

    print(f"Scheduler Tick — {result['generatedAt']} — mode={result['mode']}")
    print("-" * 60)
    print(
        f"约束: maxConcurrency={constraints['maxConcurrency']}  "
        f"inProgress={constraints['inProgressTasks']}  "
        f"pending={constraints['pendingTasks']}  "
        f"availableAgents={constraints['availableAgents']}"
    )
    print(f"决策: {decision}")
    if result["reasons"]:
        for r in result["reasons"]:
            print(f"  → {r}")
    if result.get("warnings"):
        print("警告:")
        for w in result["warnings"]:
            print(f"  ! {w}")
    if result.get("deadLetterCandidates"):
        print(f"Dead-letter 候选: {', '.join(result['deadLetterCandidates'])}")
    if result["selectedTask"]:
        print(f"推荐任务: {result['selectedTask']}")
    if result["selectedAgent"]:
        print(f"推荐 Agent: {result['selectedAgent']}")
    if result["eventId"]:
        print(f"事件 ID: {result['eventId']}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scheduler Tick — dry-run 调度决策（Milestone C）",
    )
    parser.add_argument(
        "--state",
        type=str,
        default=str(DEFAULT_STATE),
        help=f"状态文件路径（默认: {DEFAULT_STATE}）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="dry-run 模式（当前必须）",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="输出纯 JSON",
    )
    parser.add_argument(
        "--write-event",
        action="store_true",
        dest="write_event",
        help="写入调度决策事件到 Event Layer（仍需 --dry-run）",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # 安全检查：当前版本必须要求 --dry-run
    if not args.dry_run:
        print(
            "[FAIL] 当前版本仅支持 --dry-run 模式。不会真实派工。",
            file=sys.stderr,
        )
        sys.exit(1)

    # 读取状态文件
    state_path = Path(args.state)
    if not state_path.is_absolute():
        state_path = PROJECT_ROOT / state_path

    state = read_json(state_path)

    # 执行调度判断
    result = run_tick(state)

    # 写入事件（如需要）
    if args.write_event:
        result["wouldWriteEvent"] = True
        event_id = write_scheduler_event(result)
        result["eventId"] = event_id

    # 输出
    if args.json_output:
        # ensure_ascii=True 避免 Windows 编码问题
        print(json.dumps(result, ensure_ascii=True))
    else:
        print_summary(result)


if __name__ == "__main__":
    main()
