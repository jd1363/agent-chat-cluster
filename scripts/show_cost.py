#!/usr/bin/env python3
"""
show_cost.py — 本地成本 / Token 估算台账查询与汇总

读取 logs/cost/*.jsonl，提供明细、按 Agent 汇总、按任务汇总和预算阈值提示。
不承诺精确账单；这是旧方案 `/usage` 的安全替代第一版。

示例：
    python scripts/show_cost.py --limit 10
    python scripts/show_cost.py --date 2026-06-20 --by-agent
    python scripts/show_cost.py --agent-id agent-ext-01 --budget 5
    python scripts/show_cost.py --json --by-task
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
COST_DIR = PROJECT_ROOT / "logs" / "cost"


def valid_date(value: str) -> str:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise argparse.ArgumentTypeError("date must be YYYY-MM-DD")
    return value


def read_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line_no, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError as e:
                    rel = path.relative_to(PROJECT_ROOT)
                    print(f"[FAIL] JSONL 解析错误: {rel}:{line_no}: {e}", file=sys.stderr)
                    sys.exit(1)
                if isinstance(data, dict):
                    yield data
    except OSError as e:
        rel = path.relative_to(PROJECT_ROOT) if path.exists() else path
        print(f"[FAIL] 无法读取成本日志: {rel}: {e}", file=sys.stderr)
        sys.exit(1)


def cost_files(date: Optional[str]) -> List[Path]:
    if not COST_DIR.exists():
        return []
    if date:
        path = COST_DIR / f"{date}.jsonl"
        return [path] if path.is_file() else []
    return sorted(COST_DIR.glob("*.jsonl"))


def load_records(args: argparse.Namespace) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for path in cost_files(args.date):
        for row in read_jsonl(path):
            if args.agent_id and row.get("agentId") != args.agent_id:
                continue
            if args.task_id and row.get("taskId") != args.task_id:
                continue
            rows.append(row)
    rows.sort(key=lambda r: str(r.get("timestamp", "")))
    if args.limit is not None:
        rows = rows[-args.limit :]
    return rows


def as_float(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def as_int(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def summarize(rows: List[Dict[str, Any]], key: str) -> List[Dict[str, Any]]:
    bucket: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"records": 0, "inputTokens": 0, "outputTokens": 0, "totalTokens": 0, "estimatedCost": 0.0})
    for row in rows:
        group = str(row.get(key) or "<none>")
        item = bucket[group]
        item["records"] += 1
        item["inputTokens"] += as_int(row.get("inputTokens"))
        item["outputTokens"] += as_int(row.get("outputTokens"))
        item["totalTokens"] += as_int(row.get("totalTokens"))
        item["estimatedCost"] += as_float(row.get("estimatedCost"))
    result = []
    for group, item in bucket.items():
        item[key] = group
        item["estimatedCost"] = round(float(item["estimatedCost"]), 8)
        result.append(item)
    return sorted(result, key=lambda x: str(x.get(key)))


def total_summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "records": len(rows),
        "inputTokens": sum(as_int(r.get("inputTokens")) for r in rows),
        "outputTokens": sum(as_int(r.get("outputTokens")) for r in rows),
        "totalTokens": sum(as_int(r.get("totalTokens")) for r in rows),
        "estimatedCost": round(sum(as_float(r.get("estimatedCost")) for r in rows), 8),
    }


def print_table(rows: List[Dict[str, Any]]) -> None:
    if not rows:
        print("[INFO] 没有成本记录")
        return
    for row in rows:
        print(
            f"- {row.get('timestamp', '')} | {row.get('agentId', '')} | "
            f"task={row.get('taskId', '-')} | tokens={row.get('totalTokens', 0)} | "
            f"cost={row.get('estimatedCost', 'unknown')} {row.get('currency', '')} | {row.get('notes', '')}"
        )


def print_summary(summary: Dict[str, Any], budget: Optional[float]) -> None:
    print(
        f"records={summary['records']} input={summary['inputTokens']} output={summary['outputTokens']} "
        f"total={summary['totalTokens']} estimatedCost={summary['estimatedCost']}"
    )
    if budget is not None:
        used = float(summary["estimatedCost"])
        ratio = used / budget if budget > 0 else 0.0
        if ratio >= 1.0:
            print(f"[ALERT] 预算已达到/超过: {used:.4f} / {budget:.4f}")
        elif ratio >= 0.8:
            print(f"[WARN] 预算超过 80%: {used:.4f} / {budget:.4f}")
        else:
            print(f"[OK] 预算内: {used:.4f} / {budget:.4f}")


def main() -> None:
    parser = argparse.ArgumentParser(description="查询本地成本 / Token 估算台账")
    parser.add_argument("--date", type=valid_date, default=None, help="日期 YYYY-MM-DD")
    parser.add_argument("--agent-id", default=None, help="按 Agent 过滤")
    parser.add_argument("--task-id", default=None, help="按任务过滤")
    parser.add_argument("--limit", type=int, default=None, help="仅显示最近 N 条明细")
    parser.add_argument("--by-agent", action="store_true", help="按 Agent 汇总")
    parser.add_argument("--by-task", action="store_true", help="按任务汇总")
    parser.add_argument("--budget", type=float, default=None, help="预算阈值，仅提示不自动暂停")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    rows = load_records(args)
    summary = total_summary(rows)
    grouped: Optional[List[Dict[str, Any]]] = None
    group_key: Optional[str] = None
    if args.by_agent:
        grouped = summarize(rows, "agentId")
        group_key = "agentId"
    elif args.by_task:
        grouped = summarize(rows, "taskId")
        group_key = "taskId"

    if args.json:
        print(json.dumps({"summary": summary, "groupBy": group_key, "groups": grouped, "records": rows}, ensure_ascii=False, indent=2))
        return

    print_summary(summary, args.budget)
    if grouped is not None:
        for item in grouped:
            print(f"- {item.get(group_key or '')}: records={item['records']} tokens={item['totalTokens']} cost={item['estimatedCost']}")
    else:
        print_table(rows)


if __name__ == "__main__":
    main()
