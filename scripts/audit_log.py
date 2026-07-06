#!/usr/bin/env python3
"""
audit_log.py — 审计日志模块与 CLI

提供标准库实现的审计日志记录功能：
    append_audit(event_type, message, task_id=None, data=None)

日志按天切分，写入 logs/audit/YYYY-MM-DD.jsonl，每行一个 JSON 对象。

CLI 用法:
    python scripts/audit_log.py --event-type test --message "hello" [--task-id Task-001]

仅使用 Python 标准库。
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
AUDIT_DIR = PROJECT_ROOT / "logs" / "audit"


def _ensure_audit_dir():
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)


def _today_log_path() -> Path:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return AUDIT_DIR / f"{today}.jsonl"


def append_audit(event_type: str, message: str, task_id: str | None = None, data: dict | None = None, environment: str | None = None) -> None:
    """
    追加一条审计日志。

    参数:
        event_type: 事件类型，如 task_created, task_dispatched, task_completed 等。
        message: 人类可读的事件描述。
        task_id: 关联的任务 ID（可选）。
        data: 任意附加结构化数据（可选）。
        environment: 运行环境，如 production / test（可选，默认从环境变量 AGENT_CHAT_ENV 读取）。
    """
    _ensure_audit_dir()
    log_path = _today_log_path()

    env = environment or os.environ.get("AGENT_CHAT_ENV", "production")

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "eventType": event_type,
        "taskId": task_id,
        "message": message,
        "environment": env,
        "data": data,
    }

    # 移除值为 None 的键，保持日志紧凑
    record = {k: v for k, v in record.items() if v is not None}

    # 写 JSONL (向后兼容)
    try:
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as e:
        print(f"[FAIL] 无法写入审计日志: {e}", file=sys.stderr)
        sys.exit(1)

    # 写 SQLite
    try:
        sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
        from db import append_audit as db_append_audit
        db_append_audit(event_type, message, task_id=task_id, data=data, environment=env)
    except Exception as e:
        print(f"[WARN] SQLite 审计日志写入失败: {e}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="审计日志 CLI")
    parser.add_argument("--event-type", required=True, help="事件类型")
    parser.add_argument("--message", required=True, help="事件描述")
    parser.add_argument("--task-id", default=None, help="关联任务 ID")
    parser.add_argument("--environment", default=None, help="运行环境 (production/test)")
    args = parser.parse_args()

    append_audit(args.event_type, args.message, task_id=args.task_id, environment=args.environment)
    print(f"[OK] 审计日志已记录: {args.event_type}")


if __name__ == "__main__":
    main()
