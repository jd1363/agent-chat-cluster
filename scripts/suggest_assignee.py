#!/usr/bin/env python3
"""
suggest_assignee.py — 任务分配策略引擎

根据任务标题和策略，从已启用的 agent 中推荐最合适的 assignee。
支持三种策略：round-robin（轮询）、load（负载均衡）、specialist（关键词匹配）。

用法:
    python scripts/suggest_assignee.py --title "测试 policies 读取"
    python scripts/suggest_assignee.py --task-id Task-001
    python scripts/suggest_assignee.py --title "Code Review" --strategy load
    python scripts/suggest_assignee.py --title "fix bug" --strategy specialist --json

仅使用 Python 标准库。
"""

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
AGENTS_FILE = PROJECT_ROOT / "config" / "agents.json"
TASKS_FILE = PROJECT_ROOT / "tasks" / "tasks.json"
RR_STATE_FILE = PROJECT_ROOT / "config" / ".round_robin_state"

RISK_ORDER = {"low": 0, "medium": 1, "high": 2}


def load_enabled_agents() -> list[dict]:
    """加载并返回所有 enabled=true 的 agent，按 id 排序。"""
    if not AGENTS_FILE.is_file():
        print(f"[FAIL] 找不到文件: {AGENTS_FILE}", file=sys.stderr)
        sys.exit(1)
    try:
        with open(AGENTS_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError) as e:
        print(f"[FAIL] 无法读取 agents.json: {e}", file=sys.stderr)
        sys.exit(1)

    agents = [a for a in data.get("agents", []) if a.get("enabled", False)]
    if not agents:
        print("[FAIL] 没有启用的 agent", file=sys.stderr)
        sys.exit(1)
    agents.sort(key=lambda a: a.get("id", ""))
    return agents


def load_tasks() -> list[dict]:
    """加载 tasks.json 中的任务列表。"""
    if not TASKS_FILE.is_file():
        print(f"[FAIL] 找不到文件: {TASKS_FILE}", file=sys.stderr)
        sys.exit(1)
    try:
        with open(TASKS_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError) as e:
        print(f"[FAIL] 无法读取 tasks.json: {e}", file=sys.stderr)
        sys.exit(1)
    return data.get("tasks", [])


def load_task_by_id(task_id: str) -> dict | None:
    """按 task id 查找任务，找不到返回 None。"""
    tasks = load_tasks()
    for t in tasks:
        if t.get("id") == task_id:
            return t
    return None


def count_in_progress(agents: list[dict], tasks: list[dict]) -> dict[str, int]:
    """统计每个 agent 的 in_progress 任务数。返回 {agent_id: count}。"""
    counts: dict[str, int] = {a["id"]: 0 for a in agents}
    for t in tasks:
        if t.get("status") == "in_progress":
            assignee = t.get("assignee")
            if assignee and assignee in counts:
                counts[assignee] += 1
    return counts


# ---- Strategy implementations ----


def suggest_round_robin(agents: list[dict], _tasks: list[dict], _title: str) -> dict:
    """轮询策略：每次调用推进到下一个启用的 agent。

    在 config/.round_robin_state 中维护轮询指针，
    每次调用将指针推进到下一个 agent 并持久化。
    """
    state = {"currentIndex": -1}
    if RR_STATE_FILE.is_file():
        try:
            with open(RR_STATE_FILE, "r", encoding="utf-8") as fh:
                state = json.load(fh)
        except (json.JSONDecodeError, OSError):
            pass

    current_idx = state.get("currentIndex", -1)
    n = len(agents)
    next_idx = (current_idx + 1) % n

    state["currentIndex"] = next_idx
    RR_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(RR_STATE_FILE, "w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False)

    suggested = agents[next_idx]
    alt_idx = (next_idx + 1) % n
    alternatives = [
        {"agent": agents[alt_idx]["id"], "reason": "轮询序列中的下一个 agent"}
    ]

    return {
        "suggestedAssignee": suggested["id"],
        "strategy": "round-robin",
        "reason": f"轮询序列中第 {next_idx + 1}/{n} 个 agent",
        "alternatives": alternatives,
    }


def suggest_load(agents: list[dict], tasks: list[dict], _title: str) -> dict:
    """负载均衡策略：选 in_progress 任务最少的 agent。

    平局时按 riskLevel 排序（low < medium < high）。
    """
    counts = count_in_progress(agents, tasks)

    sorted_agents = sorted(
        agents,
        key=lambda a: (
            counts.get(a["id"], 0),
            RISK_ORDER.get(a.get("riskLevel", "medium"), 1),
        ),
    )

    suggested = sorted_agents[0]
    suggested_count = counts.get(suggested["id"], 0)

    alternatives = []
    for alt in sorted_agents[1:]:
        alt_count = counts.get(alt["id"], 0)
        alternatives.append(
            {"agent": alt["id"], "reason": f"{alt_count} 个 in_progress"}
        )

    return {
        "suggestedAssignee": suggested["id"],
        "strategy": "load",
        "reason": (
            f"当前 in_progress 任务最少 ({suggested_count} 个), "
            f"riskLevel={suggested.get('riskLevel')}"
        ),
        "alternatives": alternatives,
    }


def _lowest_risk_agent(agents: list[dict]) -> dict:
    """返回 riskLevel 最低的启用 agent。"""
    return min(
        agents, key=lambda a: RISK_ORDER.get(a.get("riskLevel", "medium"), 1)
    )


def _build_specialist_alternatives(
    agents: list[dict], exclude_id: str
) -> list[dict]:
    """构建备选 agent 列表（排除 suggested agent）。"""
    alts = []
    for a in agents:
        if a["id"] != exclude_id:
            alts.append(
                {"agent": a["id"], "reason": f"riskLevel={a.get('riskLevel')}"}
            )
    return alts


def suggest_specialist(agents: list[dict], tasks: list[dict], title: str) -> dict:
    """关键词匹配策略。

    匹配规则：
    - test|debug|bug|fix → agent-exec-01（executor）
    - doc|docs|write|readme|manual → riskLevel 最低的 agent
    - config|script|setup|env → riskLevel 最低的 agent
    - code|dev|build|impl → riskLevel 最低的 agent
    - 无匹配 → fallback 到 round-robin
    """
    title_lower = title.lower()

    # test|debug|bug|fix → executor agent
    if re.search(r"test|debug|bug|fix", title_lower):
        exec_agent = next(
            (a for a in agents if a["id"] == "agent-exec-01"), None
        )
        if exec_agent:
            return {
                "suggestedAssignee": "agent-exec-01",
                "strategy": "specialist",
                "reason": "标题匹配关键词 (test/debug/bug/fix)，指派 executor agent",
                "alternatives": _build_specialist_alternatives(
                    agents, "agent-exec-01"
                ),
            }
        # agent-exec-01 不在启用列表中，fallback 到 round-robin
        result = suggest_round_robin(agents, tasks, title)
        result["strategy"] = "specialist"
        result["reason"] = (
            "匹配 test/debug/bug/fix 但 agent-exec-01 未启用，"
            "fallback 到 round-robin"
        )
        return result

    # 文档类 → 最低 riskLevel
    if re.search(r"doc|docs|write|readme|manual", title_lower):
        best = _lowest_risk_agent(agents)
        return {
            "suggestedAssignee": best["id"],
            "strategy": "specialist",
            "reason": (
                "标题匹配关键词 (doc/write/readme/manual)，"
                f"选 riskLevel 最低的 agent ({best.get('riskLevel')})"
            ),
            "alternatives": _build_specialist_alternatives(agents, best["id"]),
        }

    # 配置/脚本类 → 最低 riskLevel
    if re.search(r"config|script|setup|env", title_lower):
        best = _lowest_risk_agent(agents)
        return {
            "suggestedAssignee": best["id"],
            "strategy": "specialist",
            "reason": (
                "标题匹配关键词 (config/script/setup/env)，"
                f"选 riskLevel 最低的 agent ({best.get('riskLevel')})"
            ),
            "alternatives": _build_specialist_alternatives(agents, best["id"]),
        }

    # 代码/构建类 → 最低 riskLevel
    if re.search(r"code|dev|build|impl", title_lower):
        best = _lowest_risk_agent(agents)
        return {
            "suggestedAssignee": best["id"],
            "strategy": "specialist",
            "reason": (
                "标题匹配关键词 (code/dev/build/impl)，"
                f"选 riskLevel 最低的 agent ({best.get('riskLevel')})"
            ),
            "alternatives": _build_specialist_alternatives(agents, best["id"]),
        }

    # 无关键词匹配 → fallback 到 round-robin
    result = suggest_round_robin(agents, tasks, title)
    result["strategy"] = "specialist"
    result["reason"] = "无关键词匹配，fallback 到 round-robin"
    return result


# ---- Strategy registry ----

STRATEGIES = {
    "round-robin": suggest_round_robin,
    "load": suggest_load,
    "specialist": suggest_specialist,
}


# ---- Output formatting ----


def format_human(result: dict) -> str:
    """生成人类可读输出。"""
    lines = [
        f"建议 assignee: {result['suggestedAssignee']}",
        f"策略: {result['strategy']}",
        f"理由: {result['reason']}",
    ]
    for alt in result.get("alternatives", []):
        lines.append(f"备选: {alt['agent']} ({alt['reason']})")
    return "\n".join(lines)


def format_json(result: dict) -> str:
    """生成 JSON 输出。"""
    return json.dumps(result, ensure_ascii=False, indent=2)


# ---- Main ----


def main():
    parser = argparse.ArgumentParser(description="任务分配策略引擎")
    parser.add_argument(
        "--title",
        default=None,
        help="任务标题，用于关键词匹配",
    )
    parser.add_argument(
        "--task-id",
        default=None,
        help="使用已有任务的 ID 读取其标题",
    )
    parser.add_argument(
        "--strategy",
        choices=list(STRATEGIES.keys()),
        default="round-robin",
        help="分配策略 (默认: round-robin)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="输出 JSON 格式",
    )
    args = parser.parse_args()

    # 确定标题
    title = args.title
    if title is None and args.task_id is not None:
        task = load_task_by_id(args.task_id)
        if task is None:
            print(f"[FAIL] 任务不存在: {args.task_id}", file=sys.stderr)
            sys.exit(1)
        title = task.get("title", "")
        if not title:
            print(
                f"[FAIL] 任务 {args.task_id} 缺少 title 字段", file=sys.stderr
            )
            sys.exit(1)
    elif title is None:
        print("[FAIL] 需要 --title 或 --task-id 参数", file=sys.stderr)
        sys.exit(1)

    agents = load_enabled_agents()
    tasks = load_tasks()

    strategy_fn = STRATEGIES[args.strategy]
    result = strategy_fn(agents, tasks, title)

    if args.json_output:
        print(format_json(result))
    else:
        print(format_human(result))


if __name__ == "__main__":
    main()
