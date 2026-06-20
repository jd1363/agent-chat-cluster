#!/usr/bin/env python3
"""
build_state.py — State Builder (Milestone B)

从现有文件重建统一系统状态，生成 state/system_state.json，
为后续 Scheduler Tick 提供统一事实源。

读取来源：
  - tasks/tasks.json
  - config/agents.json
  - config/policies.json
  - logs/messages/*.jsonl
  - logs/audit/*.jsonl
  - logs/events/*.jsonl（忽略 .state、.lock 等非日期 jsonl）

用法：
  python scripts/build_state.py                    # 生成 state/system_state.json + 摘要
  python scripts/build_state.py --json             # stdout 输出 JSON
  python scripts/build_state.py --output PATH      # 指定输出路径
  python scripts/build_state.py --snapshot         # 同时写入 snapshot
  python scripts/build_state.py --dry-run          # 只构建打印，不写文件

仅使用 Python 标准库。
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# 项目路径
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASKS_FILE = PROJECT_ROOT / "tasks" / "tasks.json"
AGENTS_FILE = PROJECT_ROOT / "config" / "agents.json"
POLICIES_FILE = PROJECT_ROOT / "config" / "policies.json"
MESSAGES_DIR = PROJECT_ROOT / "logs" / "messages"
AUDIT_DIR = PROJECT_ROOT / "logs" / "audit"
EVENTS_DIR = PROJECT_ROOT / "logs" / "events"
STATE_DIR = PROJECT_ROOT / "state"
SNAPSHOTS_DIR = STATE_DIR / "snapshots"
DEFAULT_OUTPUT = STATE_DIR / "system_state.json"

# 日期 JSONL 文件名模式：YYYY-MM-DD.jsonl
DATE_JSONL_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.jsonl$")

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
        fail(f"必需文件缺失: {path}")
    except OSError as e:
        fail(f"无法读取文件: {path} — {e}")
    if not isinstance(data, dict):
        fail(f"文件根元素必须是 object: {path}")
    return data


def read_jsonl_dir(dir_path: Path, dir_label: str) -> List[Dict[str, Any]]:
    """读取目录下所有日期 JSONL 文件，返回记录列表。

    忽略非日期命名的文件（如 .state、.lock）。
    某行 JSON 解析失败时 fail 并报告文件名与行号。
    目录不存在或无匹配文件时返回空列表。
    """
    records: List[Dict[str, Any]] = []
    if not dir_path.is_dir():
        return records

    jsonl_files = sorted(
        p for p in dir_path.iterdir()
        if p.is_file() and DATE_JSONL_RE.match(p.name)
    )
    if not jsonl_files:
        return records

    for path in jsonl_files:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                for line_no, line in enumerate(fh, 1):
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        record = json.loads(stripped)
                    except json.JSONDecodeError as e:
                        rel = str(path.relative_to(PROJECT_ROOT))
                        fail(f"JSONL 解析失败: {rel}:{line_no} — {e}")
                    if isinstance(record, dict):
                        records.append(record)
        except OSError as e:
            rel = str(path.relative_to(PROJECT_ROOT))
            fail(f"无法读取日志: {rel} — {e}")

    return records


# ---------------------------------------------------------------------------
# 各域构建函数
# ---------------------------------------------------------------------------

def build_tasks_state(tasks_data: Dict[str, Any]) -> Dict[str, Any]:
    """从 tasks.json 构建 tasks 状态域。"""
    items: List[Dict[str, Any]] = tasks_data.get("tasks", [])
    if not isinstance(items, list):
        fail("tasks.json 中 'tasks' 字段必须是数组")

    total = len(items)
    by_status: Dict[str, int] = {}
    by_priority: Dict[str, int] = {}
    by_assignee: Dict[str, int] = {}

    for t in items:
        if not isinstance(t, dict):
            continue
        status = t.get("status", "unknown")
        by_status[status] = by_status.get(status, 0) + 1

        priority = t.get("priority", "unknown")
        by_priority[priority] = by_priority.get(priority, 0) + 1

        assignee = t.get("assignee")
        if assignee:
            assignee_key = str(assignee)
        else:
            assignee_key = "(unassigned)"
        by_assignee[assignee_key] = by_assignee.get(assignee_key, 0) + 1

    return {
        "total": total,
        "byStatus": by_status,
        "byPriority": by_priority,
        "byAssignee": by_assignee,
        "items": items,
    }


def build_agents_state(agents_data: Dict[str, Any]) -> Dict[str, Any]:
    """从 agents.json 构建 agents 状态域。"""
    agents: List[Dict[str, Any]] = agents_data.get("agents", [])
    if not isinstance(agents, list):
        fail("agents.json 中 'agents' 字段必须是数组")

    total = len(agents)
    enabled = sum(1 for a in agents if isinstance(a, dict) and a.get("enabled", False))
    disabled = total - enabled
    by_risk: Dict[str, int] = {}

    for a in agents:
        if not isinstance(a, dict):
            continue
        risk = a.get("riskLevel", "unknown")
        by_risk[risk] = by_risk.get(risk, 0) + 1

    return {
        "total": total,
        "enabled": enabled,
        "disabled": disabled,
        "byRiskLevel": by_risk,
        "items": agents,
    }


def build_messages_state(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """从消息 JSONL 记录构建 messages 状态域。"""
    total = len(records)
    by_status: Dict[str, int] = {}
    by_recipient: Dict[str, int] = {}
    latest_timestamp: Optional[str] = None

    for r in records:
        status = r.get("status", "unknown")
        by_status[status] = by_status.get(status, 0) + 1

        recipient = r.get("to", "unknown")
        by_recipient[recipient] = by_recipient.get(recipient, 0) + 1

        ts = r.get("timestamp")
        if ts:
            if latest_timestamp is None or ts > latest_timestamp:
                latest_timestamp = ts

    return {
        "total": total,
        "byStatus": by_status,
        "byRecipient": by_recipient,
        "latestTimestamp": latest_timestamp,
    }


def build_audit_state(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """从审计 JSONL 记录构建 audit 状态域。"""
    total = len(records)
    by_event_type: Dict[str, int] = {}
    latest_timestamp: Optional[str] = None

    for r in records:
        event_type = r.get("eventType", "unknown")
        by_event_type[event_type] = by_event_type.get(event_type, 0) + 1

        ts = r.get("timestamp")
        if ts:
            if latest_timestamp is None or ts > latest_timestamp:
                latest_timestamp = ts

    return {
        "total": total,
        "byEventType": by_event_type,
        "latestTimestamp": latest_timestamp,
    }


def build_events_state(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """从事件 JSONL 记录构建 events 状态域。"""
    total = len(records)
    by_event_type: Dict[str, int] = {}
    by_status: Dict[str, int] = {}
    latest_timestamp: Optional[str] = None

    for r in records:
        event_type = r.get("eventType", "unknown")
        by_event_type[event_type] = by_event_type.get(event_type, 0) + 1

        status = r.get("status", "unknown")
        by_status[status] = by_status.get(status, 0) + 1

        ts = r.get("timestamp")
        if ts:
            if latest_timestamp is None or ts > latest_timestamp:
                latest_timestamp = ts

    return {
        "total": total,
        "byEventType": by_event_type,
        "byStatus": by_status,
        "latestTimestamp": latest_timestamp,
    }


def build_policy_state(policies_data: Dict[str, Any]) -> Dict[str, Any]:
    """从 policies.json 构建 policy 状态域（精简关键字段）。"""
    policies = policies_data.get("policies", {})
    if not isinstance(policies, dict):
        fail("policies.json 中 'policies' 字段必须是 object")

    comm = policies.get("communication", {})
    exec_cfg = policies.get("execution", {})

    global_bc = comm.get("globalBroadcast", {})
    auto_out = comm.get("autoOutbound", {})
    dangerous = exec_cfg.get("dangerousCommands", {})
    max_conc = exec_cfg.get("maxConcurrency", {})
    max_retries = exec_cfg.get("maxRetries", {})

    return {
        "maxConcurrency": max_conc.get("value", 1) if isinstance(max_conc, dict) else 1,
        "maxRetries": max_retries.get("value", 1) if isinstance(max_retries, dict) else 1,
        "globalBroadcastAllowed": global_bc.get("allowed", False) if isinstance(global_bc, dict) else False,
        "autoOutboundAllowed": auto_out.get("allowed", False) if isinstance(auto_out, dict) else False,
        "dangerousCommandsAllowed": dangerous.get("allowed", False) if isinstance(dangerous, dict) else False,
    }


def build_scheduler_state(
    tasks_state: Dict[str, Any],
    agents_state: Dict[str, Any],
    policy_state: Dict[str, Any],
) -> Dict[str, Any]:
    """从 task/agent/policy 状态推导 scheduler 状态。"""
    pending = tasks_state.get("byStatus", {}).get("pending", 0)
    in_progress = tasks_state.get("byStatus", {}).get("in_progress", 0)
    available = agents_state.get("enabled", 0)
    max_conc = policy_state.get("maxConcurrency", 1)

    reasons: List[str] = []
    backpressure = False

    if pending > 0 and available == 0:
        reasons.append("no available agents")
        backpressure = True
    if pending > 0 and max_conc <= 0:
        reasons.append("maxConcurrency is zero or negative")
        backpressure = True
    if pending > 0 and available > 0 and max_conc > 0:
        # 检查是否积压超过可用容量
        if pending > available * max_conc:
            reasons.append(
                f"pending ({pending}) exceeds capacity "
                f"({available} agents × {max_conc} concurrency = {available * max_conc})"
            )
            backpressure = True

    return {
        "pendingTasks": pending,
        "inProgressTasks": in_progress,
        "availableAgents": available,
        "backpressure": backpressure,
        "reasons": reasons,
    }


# ---------------------------------------------------------------------------
# 主构建逻辑
# ---------------------------------------------------------------------------

def build_state() -> Dict[str, Any]:
    """从所有源文件读取数据并构建统一系统状态。"""

    # 必需文件
    tasks_data = read_json(TASKS_FILE)
    agents_data = read_json(AGENTS_FILE)
    policies_data = read_json(POLICIES_FILE)

    # 可选日志
    messages_records = read_jsonl_dir(MESSAGES_DIR, "消息")
    audit_records = read_jsonl_dir(AUDIT_DIR, "审计")
    events_records = read_jsonl_dir(EVENTS_DIR, "事件")

    # 收集源文件列表
    source_files = [
        str(TASKS_FILE.relative_to(PROJECT_ROOT)),
        str(AGENTS_FILE.relative_to(PROJECT_ROOT)),
        str(POLICIES_FILE.relative_to(PROJECT_ROOT)),
    ]
    for dir_path, label in [
        (MESSAGES_DIR, "messages"),
        (AUDIT_DIR, "audit"),
        (EVENTS_DIR, "events"),
    ]:
        if dir_path.is_dir():
            for p in sorted(dir_path.iterdir()):
                if p.is_file() and DATE_JSONL_RE.match(p.name):
                    source_files.append(str(p.relative_to(PROJECT_ROOT)))

    # 构建各域
    tasks_state = build_tasks_state(tasks_data)
    agents_state = build_agents_state(agents_data)
    messages_state = build_messages_state(messages_records)
    audit_state = build_audit_state(audit_records)
    events_state = build_events_state(events_records)
    policy_state = build_policy_state(policies_data)
    scheduler_state = build_scheduler_state(tasks_state, agents_state, policy_state)

    state: Dict[str, Any] = {
        "schemaVersion": "1.0",
        "generatedAt": utc_now_iso(),
        "sourceFiles": source_files,
        "tasks": tasks_state,
        "agents": agents_state,
        "messages": messages_state,
        "audit": audit_state,
        "events": events_state,
        "policy": policy_state,
        "scheduler": scheduler_state,
    }

    return state


# ---------------------------------------------------------------------------
# 摘要输出
# ---------------------------------------------------------------------------

def print_summary(state: Dict[str, Any]) -> None:
    """打印人类可读摘要。"""
    tasks = state["tasks"]
    agents = state["agents"]
    messages = state["messages"]
    audit = state["audit"]
    events = state["events"]
    policy = state["policy"]
    scheduler = state["scheduler"]

    print(f"系统状态: schemaVersion={state['schemaVersion']}  generatedAt={state['generatedAt']}")
    print(f"源文件: {len(state['sourceFiles'])} 个")
    print("-" * 60)
    print(f"任务:   total={tasks['total']}  byStatus={tasks['byStatus']}  byPriority={tasks['byPriority']}")
    print(f"Agent:  total={agents['total']}  enabled={agents['enabled']}  disabled={agents['disabled']}")
    print(f"消息:   total={messages['total']}  byStatus={messages['byStatus']}  byRecipient={messages['byRecipient']}")
    print(f"审计:   total={audit['total']}  byEventType={audit['byEventType']}")
    print(f"事件:   total={events['total']}  byEventType={events['byEventType']}  byStatus={events['byStatus']}")
    print(f"策略:   maxConcurrency={policy['maxConcurrency']}  maxRetries={policy.get('maxRetries', 1)}  globalBroadcast={policy['globalBroadcastAllowed']}  autoOutbound={policy['autoOutboundAllowed']}  dangerous={policy['dangerousCommandsAllowed']}")
    print(f"调度器: pending={scheduler['pendingTasks']}  inProgress={scheduler['inProgressTasks']}  available={scheduler['availableAgents']}  backpressure={scheduler['backpressure']}")
    if scheduler["reasons"]:
        for reason in scheduler["reasons"]:
            print(f"        reason: {reason}")


def write_state(state: Dict[str, Any], output_path: Path) -> None:
    """将状态写入 JSON 文件。"""
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        fail(f"无法创建输出目录: {output_path.parent} — {e}")

    try:
        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False, indent=2)
    except OSError as e:
        fail(f"无法写入输出文件: {output_path} — {e}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="build_state.py — 从现有文件重建统一系统状态"
    )
    parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="向 stdout 输出 JSON 状态",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="指定输出路径（默认: state/system_state.json）",
    )
    parser.add_argument(
        "--snapshot",
        action="store_true",
        help="除主输出外，同时写入 state/snapshots/YYYY-MM-DDTHH-mm-ssZ.json",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只构建并打印摘要，不写 state/system_state.json 或 snapshot",
    )

    args = parser.parse_args()

    # 构建状态
    state = build_state()

    # 摘要仅在非 --json 模式下输出
    if not args.json_output:
        print_summary(state)

    # JSON 输出
    if args.json_output:
        # stdout 使用 ensure_ascii=True 保证跨平台 UTF-8 稳定性
        # 文件写入（write_state）仍使用 ensure_ascii=False 保持中文可读
        print(json.dumps(state, ensure_ascii=True, indent=2))

    if args.dry_run:
        if not args.json_output:
            print("\n[Dry-run] 未写入文件。")
        return

    # 写主输出（除非只用了 --json）
    if args.json_output and not args.output and not args.snapshot:
        # 只输出 JSON 到 stdout，不写文件
        return

    output_path = Path(args.output) if args.output else DEFAULT_OUTPUT
    write_state(state, output_path)
    if not args.json_output:
        print(f"\n[OK] 状态已写入: {output_path}")

    # 快照
    if args.snapshot:
        snapshot_name = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ") + ".json"
        snapshot_path = SNAPSHOTS_DIR / snapshot_name
        write_state(state, snapshot_path)
        if not args.json_output:
            print(f"[OK] 快照已写入: {snapshot_path}")


if __name__ == "__main__":
    main()
