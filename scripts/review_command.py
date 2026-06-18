#!/usr/bin/env python3
"""
review_command.py - agent command risk review CLI.

Reviews a command for an agent based on config/agents.json riskLevel and
optionally writes the review result to the audit log.

Only uses the Python standard library.
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
AGENTS_FILE = PROJECT_ROOT / "config" / "agents.json"
AUDIT_SCRIPT = PROJECT_ROOT / "scripts" / "audit_log.py"

STATUS_APPROVED = "APPROVED"
STATUS_NEEDS_REVIEW = "NEEDS_REVIEW"
STATUS_REJECTED = "REJECTED"

DESTRUCTIVE_PATTERNS = [
    r"\brm\s+-[^\n;&|]*r[^\n;&|]*f\b",
    r"\bdel\s+/f\s+/s\b",
    r"\bformat\b",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\breg\s+delete\b",
    r"\bmkfs(?:\.\w+)?\b",
    r"\bdd\s+if=",
    r">\s*/dev/sda\b",
    r"\bcurl\b.*\|.*\bbash\b",
    r"\bwget\b.*\|.*\bsh\b",
    r"\brmdir\s+/s\b",
    r"\bRemove-Item\b.*\b-Recurse\b.*\b-Force\b",
]

RISKY_PATTERNS = [
    r"\bpip\s+install\b",
    r"\bnpm\s+install\b",
    r"\bapt(?:-get)?\b",
    r"\byum\b",
    r"\bgit\s+push\b",
    r"\bgit\s+clone\b",
    r"\bscp\b",
    r"\bssh\b",
    r"\bcurl\b",
    r"\bwget\b",
    r"\bmodify\s+config\b",
    r"\bdelete\b",
    r"\bremove\b",
    r"\buninstall\b",
]

WRITE_PATTERNS = [
    r"\bnew-item\b",
    r"\bset-content\b",
    r"\badd-content\b",
    r"\bcopy-item\b",
    r"\bmove-item\b",
    r"\bremove-item\b",
    r"\btouch\b",
    r"\bmkdir\b",
    r"\bcp\b",
    r"\bmv\b",
    r"\brm\b",
    r"\bdel\b",
    r"\bcopy\b",
    r"\bmove\b",
    r"\bwrite\b",
    r"\bedit\b",
    r"\bmodify\b",
    r"\bupdate\b",
    r"\bcreate\b",
    r"\bdelete\b",
    r"\bremove\b",
    r"\binstall\b",
    r"\buninstall\b",
    r">",
    r">>",
]

READ_ONLY_PATTERNS = [
    r"^\s*ls(?:\s|$)",
    r"^\s*dir(?:\s|$)",
    r"^\s*cat(?:\s|$)",
    r"^\s*get-content(?:\s|$)",
    r"^\s*echo(?:\s|$)",
    r"^\s*print(?:\s|$)",
    r"^\s*git\s+status(?:\s|$)",
    r"^\s*git\s+log(?:\s|$)",
    r"^\s*git\s+diff(?:\s|$)",
    r"^\s*python(?:3)?\s+scripts[/\\][\w.-]+\.py(?:\s|$)",
]


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


def load_agent(agent_id: str, json_mode: bool = False) -> dict:
    data = load_json(AGENTS_FILE, json_mode=json_mode)
    agents = data.get("agents", [])
    if not isinstance(agents, list):
        fail("config/agents.json: agents 不是 list", json_mode=json_mode)

    for agent in agents:
        if agent.get("id") == agent_id:
            if not agent.get("enabled", False):
                fail(f"Agent 未启用: {agent_id}", json_mode=json_mode)
            return agent

    fail(f"Agent 不存在: {agent_id}", json_mode=json_mode)


def matches_any(command: str, patterns: list[str], flags: int = re.IGNORECASE) -> bool:
    return any(re.search(pattern, command, flags) for pattern in patterns)


def is_existing_project_script(command: str) -> bool:
    match = re.match(r"^\s*python(?:3)?\s+scripts[/\\]([\w.-]+\.py)(?:\s|$)", command, re.IGNORECASE)
    if not match:
        return False
    script_path = PROJECT_ROOT / "scripts" / match.group(1)
    return script_path.is_file()


def is_read_only(command: str) -> bool:
    if is_existing_project_script(command):
        return True
    return matches_any(command, READ_ONLY_PATTERNS)


def is_write_or_modify(command: str) -> bool:
    return matches_any(command, WRITE_PATTERNS)


def review_command(agent_id: str, command: str, risk_level: str) -> dict:
    normalized_risk = (risk_level or "unknown").lower()

    if matches_any(command, DESTRUCTIVE_PATTERNS):
        return {
            "status": STATUS_REJECTED,
            "agentId": agent_id,
            "command": command,
            "riskLevel": normalized_risk,
            "reason": "命中破坏性系统命令关键词，任何风险等级均禁止执行",
            "suggestion": "拒绝执行；需要人工重写为安全命令",
        }

    if matches_any(command, RISKY_PATTERNS):
        return {
            "status": STATUS_NEEDS_REVIEW,
            "agentId": agent_id,
            "command": command,
            "riskLevel": normalized_risk,
            "reason": "命中潜在风险关键词，需要人工审批",
            "suggestion": "提交人工审核后再执行",
        }

    read_only = is_read_only(command)
    write_or_modify = is_write_or_modify(command)

    if normalized_risk == "high" and not read_only:
        return {
            "status": STATUS_NEEDS_REVIEW,
            "agentId": agent_id,
            "command": command,
            "riskLevel": normalized_risk,
            "reason": "HIGH 风险 Agent 的非只读命令需要人工审批",
            "suggestion": "提交人工审核后再执行",
        }

    if normalized_risk == "medium" and write_or_modify:
        return {
            "status": STATUS_NEEDS_REVIEW,
            "agentId": agent_id,
            "command": command,
            "riskLevel": normalized_risk,
            "reason": "MEDIUM 风险 Agent 的写入或修改命令需要人工审批",
            "suggestion": "提交人工审核后再执行",
        }

    if read_only:
        return {
            "status": STATUS_APPROVED,
            "agentId": agent_id,
            "command": command,
            "riskLevel": normalized_risk,
            "reason": "只读操作，无危险关键词",
            "suggestion": "可直接执行",
        }

    if write_or_modify:
        return {
            "status": STATUS_NEEDS_REVIEW,
            "agentId": agent_id,
            "command": command,
            "riskLevel": normalized_risk,
            "reason": "检测到写入或修改意图，需要人工确认影响范围",
            "suggestion": "提交人工审核后再执行",
        }

    return {
        "status": STATUS_NEEDS_REVIEW,
        "agentId": agent_id,
        "command": command,
        "riskLevel": normalized_risk,
        "reason": "命令不在明确只读白名单中",
        "suggestion": "提交人工审核后再执行",
    }


def write_audit(result: dict, environment: str, json_mode: bool = False) -> None:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    task_id = f"REVIEW-{timestamp}"
    details = json.dumps(result, ensure_ascii=False)

    cmd = [
        sys.executable,
        str(AUDIT_SCRIPT),
        "--event-type",
        "review",
        "--message",
        details,
        "--task-id",
        task_id,
        "--environment",
        environment,
    ]

    try:
        completed = subprocess.run(cmd, cwd=str(PROJECT_ROOT), text=True, capture_output=True)
    except OSError as e:
        fail(f"无法写入审计日志: {e}", json_mode=json_mode)

    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or "audit_log.py 执行失败"
        fail(f"无法写入审计日志: {message}", json_mode=json_mode)


def parse_bool(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "y", "on"}:
        return True
    if lowered in {"0", "false", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError("expected true/false")


def print_human(result: dict) -> None:
    print(f"审批状态: {result['status']}")
    print(f"Agent: {result['agentId']} (riskLevel={result['riskLevel']})")
    print(f"命令: {result['command']}")
    print(f"理由: {result['reason']}")
    print(f"建议: {result['suggestion']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Review an agent command before execution")
    parser.add_argument("--agent-id", required=True, help="Target agent ID")
    parser.add_argument("--command", required=True, help="Command string to review")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--environment", default="production", help="Audit log environment")
    parser.add_argument(
        "--write-audit",
        nargs="?",
        const=True,
        default=True,
        type=parse_bool,
        help="Write result to audit log (default: true)",
    )
    parser.add_argument(
        "--no-write-audit",
        action="store_false",
        dest="write_audit",
        help="Do not write result to audit log",
    )
    args = parser.parse_args()

    agent = load_agent(args.agent_id, json_mode=args.json)
    risk_level = str(agent.get("riskLevel", "unknown"))
    result = review_command(args.agent_id, args.command, risk_level)

    if args.write_audit:
        write_audit(result, args.environment, json_mode=args.json)

    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print_human(result)


if __name__ == "__main__":
    main()
