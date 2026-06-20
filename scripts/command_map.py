#!/usr/bin/env python3
"""
command_map.py — 旧方案命令 → 当前真实替代方式映射器

用途：防止把方案文档里的伪 slash 命令直接复制执行。
只读工具，不执行任何映射命令。

示例：
    python scripts/command_map.py --old "/task list"
    python scripts/command_map.py --old "/usage set-budget agent codex 25" --json
    python scripts/command_map.py --list
"""

import argparse
import json
from typing import Dict, List

MAPPINGS: List[Dict[str, object]] = [
    {
        "prefixes": ["/task list", "/task status"],
        "status": "replaced",
        "risk": "low",
        "replacement": "python scripts/list_tasks.py 或 python scripts/show_history.py",
        "notes": "当前使用 tasks/tasks.json + Python 脚本替代旧方案 /task 查询命令。",
    },
    {
        "prefixes": ["/task create"],
        "status": "replaced",
        "risk": "low",
        "replacement": "python scripts/create_task.py --title \"...\" --priority high|medium|low",
        "notes": "优先级需使用英文 high/medium/low；创建会写审计日志。",
    },
    {
        "prefixes": ["/task transfer"],
        "status": "replaced",
        "risk": "medium",
        "replacement": "python scripts/update_task.py --id Task-XXX --assignee agent-ext-01 后再 validate_task.py",
        "notes": "转交前必须确认 assignee 已在 config/agents.json 注册且 enabled=true。",
    },
    {
        "prefixes": ["/task stop"],
        "status": "replaced",
        "risk": "medium",
        "replacement": "python scripts/update_task.py --id Task-XXX --status cancelled 或 complete_task.py --status blocked/failed",
        "notes": "终止任务属于状态变更，应保留 notes/summary。",
    },
    {
        "prefixes": ["/audit enable", "/audit export"],
        "status": "replaced",
        "risk": "low",
        "replacement": "scripts/audit_log.py 已默认按需写入；查询用 python scripts/show_audit.py",
        "notes": "当前审计是本地 JSONL append-only，不需要先执行 /audit enable。",
    },
    {
        "prefixes": ["/snapshot save"],
        "status": "replaced",
        "risk": "low",
        "replacement": "python scripts/snapshot_config.py save --name NAME --reason \"...\"",
        "notes": "快照写入 snapshots/；会记录审计。",
    },
    {
        "prefixes": ["/snapshot list"],
        "status": "replaced",
        "risk": "low",
        "replacement": "python scripts/snapshot_config.py list",
        "notes": "支持 --json。",
    },
    {
        "prefixes": ["/snapshot restore"],
        "status": "replaced",
        "risk": "medium",
        "replacement": "python scripts/snapshot_config.py restore --name NAME --yes",
        "notes": "会覆盖 config/tasks；恢复前自动创建 pre-restore 快照。",
    },
    {
        "prefixes": ["/usage set-budget", "/usage set-alert", "/usage set-protection"],
        "status": "pending",
        "risk": "medium",
        "replacement": "第一版仅支持 python scripts/record_cost.py 与 python scripts/show_cost.py --budget 做记录/提示",
        "notes": "不承诺精确账单，不自动暂停 Agent；旧 /usage 命令不可直接执行。",
    },
    {
        "prefixes": ["/usage export", "/usage report", "/usage show"],
        "status": "partially_replaced",
        "risk": "low",
        "replacement": "python scripts/show_cost.py --json --by-agent / --by-task",
        "notes": "当前是本地估算台账汇总，还不是 CSV/日报/周报完整报表。",
    },
    {
        "prefixes": ["/acp spawn"],
        "status": "forbidden_until_verified",
        "risk": "high",
        "replacement": "暂缓。需先确认 OpenClaw 当前真实 ACP/session 创建方式；不要照旧方案参数执行。",
        "notes": "旧方案里的 --name/--cmd/--track-usage/--workdir 参数未验证。",
    },
    {
        "prefixes": ["/acp broadcast", "/acp group broadcast"],
        "status": "replaced_guarded",
        "risk": "high",
        "replacement": "python scripts/send_message.py --to all --message \"...\" --manual-approval 或 python scripts/broadcast.py --message \"...\" --manual-approval",
        "notes": "全局广播默认禁止；只允许主控受控多播，不开放自由群聊。",
    },
    {
        "prefixes": ["/acp group start", "/acp group stop", "/acp group kill"],
        "status": "pending",
        "risk": "high",
        "replacement": "暂缓。当前仅通过 config/agents.json 管理启用状态，并需人工审批。",
        "notes": "不直接启动/杀死真实 Agent 进程。",
    },
    {
        "prefixes": ["/self-heal"],
        "status": "forbidden",
        "risk": "high",
        "replacement": "无。当前 policies.json 明确禁用自动自愈。",
        "notes": "避免无限重启、无限重试、无限烧钱。",
    },
    {
        "prefixes": ["/permission set"],
        "status": "partially_replaced",
        "risk": "high",
        "replacement": "python scripts/test_isolation.py + config/policies.json allowedPaths；真实 OS/sandbox 权限另行确认",
        "notes": "目录规则不是强安全边界；不要把它当系统级权限隔离。",
    },
    {
        "prefixes": ["/tag"],
        "status": "pending",
        "risk": "low",
        "replacement": "未实现。后续可在 config/agents.json 增加 tags 字段与查询脚本。",
        "notes": "标签化管理是低风险增强项。",
    },
    {
        "prefixes": ["/alias"],
        "status": "pending",
        "risk": "low",
        "replacement": "未实现。后续可用 docs/REAL_COMMANDS.md 或命令映射器替代。",
        "notes": "别名只做便利性，不影响核心安全。",
    },
    {
        "prefixes": ["/cron add"],
        "status": "replaced_by_openclaw_tool",
        "risk": "medium",
        "replacement": "使用 OpenClaw cron 工具；重要定时任务需先人工确认策略与输出目标。",
        "notes": "不要在 shell 里用 sleep/poll 模拟定时。",
    },
    {
        "prefixes": ["openclaw --web"],
        "status": "forbidden_until_verified",
        "risk": "high",
        "replacement": "openclaw gateway status/start/restart；不要随意改端口或启动方式。",
        "notes": "旧方案里的 --enable-usage-tracking/--enable-group-mode 未确认。",
    },
]

DEFAULT_RESULT = {
    "status": "unknown",
    "risk": "unknown",
    "replacement": "无已知替代。先查 docs/REAL_COMMANDS.md、PROJECT_PLAN.md 或人工评估。",
    "notes": "未知旧方案命令不得直接执行。",
}


def normalize(command: str) -> str:
    return " ".join(command.strip().split())


def match_command(command: str) -> Dict[str, object]:
    normalized = normalize(command)
    for item in MAPPINGS:
        prefixes = item.get("prefixes", [])
        for prefix in prefixes:  # type: ignore[assignment]
            if normalized.startswith(str(prefix)):
                result = dict(item)
                result["matchedPrefix"] = prefix
                result["input"] = command
                return result
    result = dict(DEFAULT_RESULT)
    result["input"] = command
    return result


def list_mappings(json_output: bool) -> None:
    if json_output:
        print(json.dumps({"mappings": MAPPINGS}, ensure_ascii=True, indent=2))
        return
    for item in MAPPINGS:
        prefixes = ", ".join(str(p) for p in item["prefixes"])  # type: ignore[index]
        print(f"- {prefixes} => {item['status']} | risk={item['risk']} | {item['replacement']}")


def show_result(result: Dict[str, object], json_output: bool) -> None:
    if json_output:
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return
    print(f"input: {result.get('input')}")
    if result.get("matchedPrefix"):
        print(f"matched: {result.get('matchedPrefix')}")
    print(f"status: {result.get('status')}")
    print(f"risk: {result.get('risk')}")
    print(f"replacement: {result.get('replacement')}")
    print(f"notes: {result.get('notes')}")


def main() -> None:
    parser = argparse.ArgumentParser(description="旧方案命令到当前真实替代方式的只读映射器")
    parser.add_argument("--old", help="旧方案命令，例如 /usage set-budget agent codex 25")
    parser.add_argument("--list", action="store_true", help="列出全部已知映射")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    if args.list:
        list_mappings(args.json)
        return
    if args.old:
        show_result(match_command(args.old), args.json)
        return
    parser.error("需要 --old 或 --list")


if __name__ == "__main__":
    main()
