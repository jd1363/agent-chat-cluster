#!/usr/bin/env python3
"""
record_cost.py — 本地成本 / Token 估算台账写入

替代旧方案中不可确认的 `/usage ...` 命令第一版：
- 仅标准库
- 写入 logs/cost/YYYY-MM-DD.jsonl
- 支持 dry-run，不自动暂停 Agent
- 成本可手动填写，也可按输入/输出 token 单价粗略估算
- 写入审计日志

示例：
    python scripts/record_cost.py --agent-id agent-ext-01 --task-id Task-010 --input-tokens 1200 --output-tokens 800 --estimated-cost 0.03 --notes "manual estimate"
    python scripts/record_cost.py --agent-id agent-ext-01 --input-tokens 1000 --output-tokens 500 --rate-input-per-1k 0.002 --rate-output-per-1k 0.006 --dry-run
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
COST_DIR = PROJECT_ROOT / "logs" / "cost"

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from audit_log import append_audit  # type: ignore
from event_log import build_event, append_event  # type: ignore


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def today_path() -> Path:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return COST_DIR / f"{day}.jsonl"


def non_negative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("must be an integer")
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be >= 0")
    return parsed


def non_negative_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("must be a number")
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be >= 0")
    return parsed


def estimate_cost(input_tokens: int, output_tokens: int, rate_input: Optional[float], rate_output: Optional[float]) -> Optional[float]:
    if rate_input is None and rate_output is None:
        return None
    in_rate = rate_input or 0.0
    out_rate = rate_output or 0.0
    return round((input_tokens / 1000.0) * in_rate + (output_tokens / 1000.0) * out_rate, 8)


def build_record(args: argparse.Namespace) -> Dict[str, Any]:
    estimated = args.estimated_cost
    if estimated is None:
        estimated = estimate_cost(args.input_tokens, args.output_tokens, args.rate_input_per_1k, args.rate_output_per_1k)

    record: Dict[str, Any] = {
        "timestamp": utc_now(),
        "agentId": args.agent_id,
        "taskId": args.task_id,
        "model": args.model,
        "inputTokens": args.input_tokens,
        "outputTokens": args.output_tokens,
        "totalTokens": args.input_tokens + args.output_tokens,
        "estimatedCost": estimated,
        "currency": args.currency,
        "source": args.source,
        "notes": args.notes,
    }
    return {k: v for k, v in record.items() if v is not None}


def append_record(record: Dict[str, Any]) -> Path:
    COST_DIR.mkdir(parents=True, exist_ok=True)
    path = today_path()
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="记录本地成本 / Token 估算")
    parser.add_argument("--agent-id", required=True, help="Agent ID，例如 agent-ext-01")
    parser.add_argument("--task-id", default=None, help="关联任务 ID，例如 Task-010")
    parser.add_argument("--model", default=None, help="模型/工具名称")
    parser.add_argument("--input-tokens", type=non_negative_int, default=0, help="输入 token 数")
    parser.add_argument("--output-tokens", type=non_negative_int, default=0, help="输出 token 数")
    parser.add_argument("--estimated-cost", type=non_negative_float, default=None, help="手动估算成本")
    parser.add_argument("--rate-input-per-1k", type=non_negative_float, default=None, help="输入每 1k token 单价，用于估算")
    parser.add_argument("--rate-output-per-1k", type=non_negative_float, default=None, help="输出每 1k token 单价，用于估算")
    parser.add_argument("--currency", default="USD", help="币种，默认 USD")
    parser.add_argument("--source", choices=["manual", "session", "estimated"], default="manual", help="记录来源")
    parser.add_argument("--notes", default="", help="备注")
    parser.add_argument("--dry-run", action="store_true", help="仅打印记录，不写文件")
    args = parser.parse_args()

    record = build_record(args)
    if args.dry_run:
        print(json.dumps(record, ensure_ascii=False, indent=2))
        return

    try:
        path = append_record(record)
    except OSError as e:
        print(f"[FAIL] 无法写入成本台账: {e}", file=sys.stderr)
        sys.exit(1)

    append_audit(
        event_type="cost_recorded",
        message=f"记录成本估算: {args.agent_id}",
        task_id=args.task_id,
        data={
            "agentId": args.agent_id,
            "inputTokens": args.input_tokens,
            "outputTokens": args.output_tokens,
            "estimatedCost": record.get("estimatedCost"),
            "source": args.source,
        },
    )
    try:
        _corr = args.task_id or args.agent_id
        _evt = build_event(
            event_type="cost.recorded",
            source="record_cost",
            correlation_id=_corr,
            payload={
                "entryId": args.agent_id,
                "agent": args.agent_id,
                "task": args.task_id,
                "tokensIn": args.input_tokens,
                "tokensOut": args.output_tokens,
                "cost": record.get("estimatedCost"),
            },
        )
        append_event(_evt)
    except Exception as e:
        print(f"[WARN] 事件日志追加失败: {e}")
    print(f"[OK] 成本记录已写入: {path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
