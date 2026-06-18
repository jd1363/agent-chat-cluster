#!/usr/bin/env python3
"""
benchmark_pipeline.py - agent-chat-cluster pipeline benchmark report.

Reads tasks/tasks.json and config/agents.json, then reports read-only baseline
metrics for task status, lifecycle timing, and agent workload.

Only uses the Python standard library.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASKS_FILE = PROJECT_ROOT / "tasks" / "tasks.json"
AGENTS_FILE = PROJECT_ROOT / "config" / "agents.json"

STATUSES = ["pending", "in_progress", "done", "failed", "blocked", "cancelled"]
STAGE_ESTIMATES_MS = {
    "create": 50,
    "validate": 30,
    "suggest_assignee": 40,
    "review_command": 35,
    "dispatch": 60,
    "complete": 50,
}
STATUS_AVG_LABELS = {
    "pending": "平均等待",
    "in_progress": "平均进行",
    "done": "平均完成后",
    "failed": "平均失败后",
    "blocked": "平均阻塞",
    "cancelled": "平均取消后",
}


def fail(message: str, json_mode: bool = False) -> None:
    if json_mode:
        print(json.dumps({"error": message}, ensure_ascii=False))
    else:
        print(f"[FAIL] {message}", file=sys.stderr)
    sys.exit(1)


def load_json(filepath: Path, json_mode: bool = False) -> dict:
    if not filepath.is_file():
        fail(f"找不到文件: {filepath}", json_mode=json_mode)
    try:
        with open(filepath, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as e:
        fail(f"JSON 解析错误 ({filepath.name}): {e}", json_mode=json_mode)
    except OSError as e:
        fail(f"无法读取文件 ({filepath.name}): {e}", json_mode=json_mode)


def load_tasks(json_mode: bool = False) -> list[dict]:
    data = load_json(TASKS_FILE, json_mode=json_mode)
    tasks = data.get("tasks", [])
    if not isinstance(tasks, list):
        fail("tasks.json: tasks 不是 list", json_mode=json_mode)
    return tasks


def load_agents(json_mode: bool = False) -> list[dict]:
    data = load_json(AGENTS_FILE, json_mode=json_mode)
    agents = data.get("agents", [])
    if not isinstance(agents, list):
        fail("agents.json: agents 不是 list", json_mode=json_mode)
    return agents


def parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def format_duration_hours(hours: float | None) -> str:
    if hours is None:
        return "n/a"
    if hours < 0:
        hours = 0.0
    return f"{hours:.1f}h"


def analyze_status(tasks: list[dict], now: datetime) -> dict:
    total = len(tasks)
    buckets = {
        status: {
            "count": 0,
            "percentage": 0.0,
            "averageHoursInStatus": None,
        }
        for status in STATUSES
    }
    elapsed_by_status: dict[str, list[float]] = {status: [] for status in STATUSES}

    for task in tasks:
        status = task.get("status")
        if status not in buckets:
            continue

        buckets[status]["count"] += 1
        status_started_at = parse_timestamp(task.get("updatedAt")) or parse_timestamp(
            task.get("createdAt")
        )
        if status_started_at is not None:
            elapsed = (now - status_started_at).total_seconds() / 3600
            elapsed_by_status[status].append(max(elapsed, 0.0))

    for status, bucket in buckets.items():
        if total:
            bucket["percentage"] = (bucket["count"] / total) * 100
        elapsed_values = elapsed_by_status[status]
        if elapsed_values:
            bucket["averageHoursInStatus"] = sum(elapsed_values) / len(elapsed_values)

    return {"totalTasks": total, "statuses": buckets}


def analyze_lifecycle(tasks: list[dict]) -> dict:
    pending_tasks = [task for task in tasks if task.get("status") == "pending"]
    per_task_total_ms = sum(STAGE_ESTIMATES_MS.values())
    pending_count = len(pending_tasks)
    stage_totals = {
        stage: estimate_ms * pending_count
        for stage, estimate_ms in STAGE_ESTIMATES_MS.items()
    }
    bottleneck_stage = max(STAGE_ESTIMATES_MS, key=STAGE_ESTIMATES_MS.get)

    return {
        "pendingTasks": pending_count,
        "perTaskTotalMs": per_task_total_ms,
        "totalPendingMs": per_task_total_ms * pending_count,
        "stages": dict(STAGE_ESTIMATES_MS),
        "stageTotalsMs": stage_totals,
        "bottleneck": {
            "stage": bottleneck_stage,
            "msPerTask": STAGE_ESTIMATES_MS[bottleneck_stage],
            "cumulativeMs": stage_totals[bottleneck_stage],
        },
    }


def analyze_agents(tasks: list[dict], agents: list[dict], lifecycle: dict) -> dict:
    enabled_agents = [
        agent for agent in agents if agent.get("enabled", False) and agent.get("id")
    ]
    enabled_agents.sort(key=lambda agent: str(agent.get("id", "")))

    counts = {str(agent["id"]): 0 for agent in enabled_agents}
    for task in tasks:
        if task.get("status") != "in_progress":
            continue
        assignee = task.get("assignee")
        if assignee in counts:
            counts[assignee] += 1

    per_task_total_ms = lifecycle["perTaskTotalMs"]
    throughput = 0.0
    if per_task_total_ms > 0:
        throughput = 3600 / per_task_total_ms

    workloads = []
    for agent in enabled_agents:
        agent_id = str(agent["id"])
        in_progress = counts.get(agent_id, 0)
        workloads.append(
            {
                "id": agent_id,
                "riskLevel": agent.get("riskLevel"),
                "inProgress": in_progress,
                "throughputTasksPerHour": throughput,
                "overloaded": in_progress > 1,
                "idle": in_progress == 0,
            }
        )

    return {
        "enabledAgents": len(enabled_agents),
        "capacityPerAgentInProgress": 1,
        "workloads": workloads,
        "overloadedAgents": [
            item["id"] for item in workloads if item["overloaded"]
        ],
        "idleAgents": [item["id"] for item in workloads if item["idle"]],
    }


def build_report(tasks: list[dict], agents: list[dict]) -> dict:
    now = datetime.now(timezone.utc)
    lifecycle = analyze_lifecycle(tasks)
    return {
        "analysisTime": now.isoformat(),
        "projectRoot": str(PROJECT_ROOT),
        "totalTasks": len(tasks),
        "enabledAgents": len(
            [agent for agent in agents if agent.get("enabled", False)]
        ),
        "status": analyze_status(tasks, now),
        "lifecycle": lifecycle,
        "agent": analyze_agents(tasks, agents, lifecycle),
    }


def format_status_section(status_report: dict) -> list[str]:
    lines = ["", "[状态分布]"]
    for status in STATUSES:
        item = status_report["statuses"][status]
        avg_hours = item["averageHoursInStatus"]
        line = f"{status + ':':<13}{item['count']:>3} ({item['percentage']:>5.1f}%)"
        if item["count"] > 0:
            label = STATUS_AVG_LABELS.get(status, "平均停留")
            line += f"  {label}: {format_duration_hours(avg_hours)}"
        lines.append(line)
    return lines


def format_lifecycle_section(lifecycle: dict) -> list[str]:
    bottleneck = lifecycle["bottleneck"]
    lines = [
        "",
        "[流水线瓶颈分析]",
        f"待处理任务: {lifecycle['pendingTasks']}",
        f"预估单任务总耗时: {lifecycle['perTaskTotalMs']}ms",
        f"预估全部pending处理耗时: {lifecycle['totalPendingMs']}ms",
        f"瓶颈阶段: {bottleneck['stage']} ({bottleneck['msPerTask']}ms/任务)",
        "",
        "[阶段耗时]",
    ]
    for stage, estimate_ms in lifecycle["stages"].items():
        total_ms = lifecycle["stageTotalsMs"][stage]
        lines.append(f"{stage + ':':<17}{estimate_ms:>4}ms/任务, 累计 {total_ms}ms")
    return lines


def format_agent_section(agent: dict) -> list[str]:
    lines = ["", "[Agent负载]"]
    if not agent["workloads"]:
        lines.append("无已启用 Agent")
        return lines

    for item in agent["workloads"]:
        lines.append(
            f"{item['id'] + ':':<16} {item['inProgress']} in_progress, "
            f"吞吐量 {item['throughputTasksPerHour']:.1f} 任务/小时"
        )

    overloaded = ", ".join(agent["overloadedAgents"]) or "无"
    idle = ", ".join(agent["idleAgents"]) or "无"
    lines.append(f"过载 Agent: {overloaded}")
    lines.append(f"空闲 Agent: {idle}")
    return lines


def format_human(report: dict, mode: str) -> str:
    analysis_time = parse_timestamp(report["analysisTime"])
    if analysis_time is None:
        analysis_time_text = report["analysisTime"]
    else:
        analysis_time_text = analysis_time.strftime("%Y-%m-%d %H:%M:%S UTC")

    lines = [
        "=== Agent Chat Cluster 性能基线报告 ===",
        f"分析时间: {analysis_time_text}",
        f"总任务数: {report['totalTasks']}",
        f"已启用 Agent: {report['enabledAgents']}",
    ]

    if mode == "status":
        lines.extend(format_status_section(report["status"]))
        lines.extend(format_lifecycle_section(report["lifecycle"]))
        lines.extend(format_agent_section(report["agent"]))
    elif mode == "lifecycle":
        lines.extend(format_lifecycle_section(report["lifecycle"]))
    elif mode == "agent":
        lines.extend(format_agent_section(report["agent"]))

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read-only benchmark report for agent-chat-cluster pipeline"
    )
    parser.add_argument(
        "--mode",
        choices=["status", "lifecycle", "agent"],
        default="status",
        help="分析模式 (默认: status)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="输出 JSON 格式",
    )
    args = parser.parse_args()

    tasks = load_tasks(json_mode=args.json_output)
    agents = load_agents(json_mode=args.json_output)
    report = build_report(tasks, agents)
    report["mode"] = args.mode

    if args.json_output:
        payload = {
            "mode": args.mode,
            "analysisTime": report["analysisTime"],
            "projectRoot": report["projectRoot"],
            "totalTasks": report["totalTasks"],
            "enabledAgents": report["enabledAgents"],
            args.mode: report[args.mode],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(format_human(report, args.mode))


if __name__ == "__main__":
    main()
