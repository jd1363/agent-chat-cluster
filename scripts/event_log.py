#!/usr/bin/env python3
"""
event_log.py — 本地事件日志模块（标准库 only）

为 Agent Chat Cluster 提供事件层骨架：
- 按天切分 JSONL 事件日志：logs/events/YYYY-MM-DD.jsonl
- 死信队列预留：logs/dead_letter/YYYY-MM-DD.jsonl
- 跨进程并发安全（基于文件锁的状态文件）
- CLI 子命令：append / list / replay

Usage:
    python scripts/event_log.py append --event-type task.created --source test --correlation-id Task-001 --payload '{"title":"demo"}'
    python scripts/event_log.py append --event-type task.created --json
    python scripts/event_log.py list
    python scripts/event_log.py list --date 2026-06-20 --limit 10 --json
    python scripts/event_log.py replay --dry-run

Uses only Python standard library modules.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# 项目路径
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVENTS_DIR = PROJECT_ROOT / "logs" / "events"
DEAD_LETTER_DIR = PROJECT_ROOT / "logs" / "dead_letter"
STATE_FILE = EVENTS_DIR / ".state"
STATE_LOCK_FILE = EVENTS_DIR / ".state.lock"
LOCK_RETRY_SECONDS = 0.05
LOCK_TIMEOUT_SECONDS = 5

# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def fail(message: str) -> None:
    """输出错误信息并以非零退出码终止。"""
    print(f"[FAIL] {message}", file=sys.stderr)
    sys.exit(1)


def ensure_events_dir() -> None:
    """确保事件日志目录存在。"""
    try:
        EVENTS_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        fail(f"无法创建事件日志目录: {e}")


def today_str() -> str:
    """返回当天 UTC 日期字符串，格式 YYYY-MM-DD。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def today_log_path(date_str: str | None = None) -> Path:
    """返回指定日期的事件日志文件路径。默认当天。"""
    if date_str is None:
        date_str = today_str()
    return EVENTS_DIR / f"{date_str}.jsonl"


def utc_now_iso() -> str:
    """返回 UTC ISO 8601 时间戳，以 Z 结尾。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# ---------------------------------------------------------------------------
# 跨进程锁（参考 send_message.py 的 .state.lock 模式）
# ---------------------------------------------------------------------------

def acquire_state_lock() -> int:
    """使用 O_CREAT|O_EXCL 获取排他文件锁，返回 fd。"""
    ensure_events_dir()
    deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
    while True:
        try:
            return os.open(str(STATE_LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if time.monotonic() >= deadline:
                fail("等待事件状态锁超时")
            time.sleep(LOCK_RETRY_SECONDS)
        except OSError as e:
            fail(f"无法创建事件状态锁: {e}")


def release_state_lock(fd: int) -> None:
    """释放排他文件锁并删除锁文件。"""
    try:
        os.close(fd)
    finally:
        try:
            STATE_LOCK_FILE.unlink()
        except FileNotFoundError:
            pass
        except OSError as e:
            fail(f"无法删除事件状态锁文件: {e}")

# ---------------------------------------------------------------------------
# 状态文件（跟踪当天递增序号）
# ---------------------------------------------------------------------------

def load_state() -> dict:
    """读取状态文件，返回完整状态字典。文件不存在时返回初始状态。"""
    ensure_events_dir()
    if not STATE_FILE.is_file():
        return {"nextEventNumber": 1}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as e:
        fail(f"事件状态 JSON 解析错误: {e}")
    except OSError as e:
        fail(f"无法读取事件状态文件: {e}")

    if not isinstance(data, dict):
        fail("事件状态文件根元素必须是 object")
    return data


def save_state(state: dict) -> None:
    """写入状态文件。"""
    ensure_events_dir()
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False, indent=2)
    except OSError as e:
        fail(f"无法写入事件状态文件: {e}")


def allocate_event_id() -> str:
    """线程安全地分配当天唯一 eventId（跨天自动重置计数）。"""
    lock_fd = acquire_state_lock()
    try:
        state = load_state()
        current_date = datetime.now(timezone.utc).strftime("%Y%m%d")
        stored_date = state.get("date")

        # 跨天重置：state date 与当前 UTC 日期不一致时，计数归 1
        # 兼容旧 state：date 缺失时保留 nextEventNumber 并补上当前日期
        if stored_date is None:
            next_number = state.get("nextEventNumber", 1)
            state["date"] = current_date
        elif stored_date != current_date:
            next_number = 1
            state["date"] = current_date
        else:
            next_number = state.get("nextEventNumber", 1)
            if not isinstance(next_number, int) or next_number < 1:
                fail("事件状态 nextEventNumber 必须是正整数")

        event_id = f"EVT-{current_date}-{next_number:06d}"
        state["nextEventNumber"] = next_number + 1
        save_state(state)
        return event_id
    finally:
        release_state_lock(lock_fd)

# ---------------------------------------------------------------------------
# 事件构建与写入
# ---------------------------------------------------------------------------

def build_event(
    event_type: str,
    source: str = "control-plane",
    correlation_id: str | None = None,
    causation_id: str | None = None,
    payload: dict | None = None,
    policy_snapshot: dict | None = None,
    status: str = "pending",
) -> dict:
    """构建一条符合规范的事件记录。"""
    event = {
        "eventId": allocate_event_id(),
        "eventType": event_type,
        "timestamp": utc_now_iso(),
        "source": source,
        "correlationId": correlation_id,
        "causationId": causation_id,
        "payload": payload if payload is not None else {},
        "policySnapshot": policy_snapshot if policy_snapshot is not None else {},
        "status": status,
    }
    return event


def append_event(event: dict) -> None:
    """向当天事件日志追加一条事件（JSONL 一行）。"""
    ensure_events_dir()
    try:
        with open(today_log_path(), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")
    except OSError as e:
        fail(f"无法写入事件日志: {e}")

# ---------------------------------------------------------------------------
# 事件读取
# ---------------------------------------------------------------------------

def read_events(
    date_str: str | None = None,
    event_type: str | None = None,
    correlation_id: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    """读取并过滤事件，返回列表（按文件内顺序）。"""
    log_path = today_log_path(date_str)
    if not log_path.is_file():
        return []

    events: list[dict] = []
    try:
        with open(log_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    evt = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if event_type and evt.get("eventType") != event_type:
                    continue
                if correlation_id and evt.get("correlationId") != correlation_id:
                    continue

                events.append(evt)
                if limit is not None and len(events) >= limit:
                    break
    except OSError as e:
        fail(f"无法读取事件日志: {e}")

    return events

# ---------------------------------------------------------------------------
# CLI: append
# ---------------------------------------------------------------------------

def cmd_append(args: argparse.Namespace) -> None:
    """处理 append 子命令。"""
    payload = {}
    if args.payload:
        try:
            payload = json.loads(args.payload)
        except json.JSONDecodeError as e:
            fail(f"--payload JSON 解析失败: {e}")
        if not isinstance(payload, dict):
            fail("--payload 必须是 JSON object")

    policy_snapshot = {}
    if args.policy_snapshot:
        try:
            policy_snapshot = json.loads(args.policy_snapshot)
        except json.JSONDecodeError as e:
            fail(f"--policy-snapshot JSON 解析失败: {e}")
        if not isinstance(policy_snapshot, dict):
            fail("--policy-snapshot 必须是 JSON object")

    event = build_event(
        event_type=args.event_type,
        source=args.source,
        correlation_id=args.correlation_id,
        causation_id=args.causation_id,
        payload=payload,
        policy_snapshot=policy_snapshot,
        status=args.status,
    )
    append_event(event)

    log_path = today_log_path()
    if args.json_output:
        print(json.dumps(event, ensure_ascii=False, indent=2))
    else:
        print(f"[OK] {event['eventId']} -> {log_path}")

# ---------------------------------------------------------------------------
# CLI: list
# ---------------------------------------------------------------------------

def cmd_list(args: argparse.Namespace) -> None:
    """处理 list 子命令。"""
    date_str = args.date if args.date else today_str()
    log_path = today_log_path(date_str)
    events = read_events(
        date_str=date_str,
        event_type=args.event_type,
        correlation_id=args.correlation_id,
        limit=args.limit,
    )

    if args.json_output:
        print(json.dumps(events, ensure_ascii=False, indent=2))
    else:
        if not events:
            print(f"（无匹配事件）日志文件: {log_path}")
            return
        print(f"事件日志: {log_path}（共 {len(events)} 条）")
        print("-" * 60)
        for evt in events:
            eid = evt.get("eventId", "?")
            etype = evt.get("eventType", "?")
            ts = evt.get("timestamp", "?")
            cid = evt.get("correlationId") or "-"
            print(f"  {eid}  {etype:30s}  {ts}  cid={cid}")

# ---------------------------------------------------------------------------
# CLI: replay
# ---------------------------------------------------------------------------

def cmd_replay(args: argparse.Namespace) -> None:
    """处理 replay 子命令。当前只支持 --dry-run。"""
    if not args.dry_run:
        fail("当前只支持 --dry-run 模式。请添加 --dry-run 参数后重试。")

    date_str = args.date if args.date else today_str()
    log_path = today_log_path(date_str)
    events = read_events(date_str=date_str)

    if args.json_output:
        print(json.dumps({
            "mode": "dry-run",
            "date": date_str,
            "eventCount": len(events),
            "events": events,
        }, ensure_ascii=False, indent=2))
    else:
        print(f"REPLAY DRY-RUN — 日志文件: {log_path}")
        print(f"将按顺序 replay {len(events)} 条事件:")
        print("-" * 60)
        for i, evt in enumerate(events, start=1):
            eid = evt.get("eventId", "?")
            etype = evt.get("eventType", "?")
            ts = evt.get("timestamp", "?")
            print(f"  [{i:03d}] {eid}  {etype}  {ts}")
        print("-" * 60)
        print(f"合计: {len(events)} 条事件（仅 dry-run，未执行实际 replay）")

# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Agent Chat Cluster 事件日志模块（Event Layer 骨架）"
    )
    sub = parser.add_subparsers(dest="command", help="子命令")

    # ---- append ----
    ap = sub.add_parser("append", help="追加一条事件")
    ap.add_argument("--event-type", required=True, help="事件类型（必填），如 task.created")
    ap.add_argument("--source", default="control-plane", help="事件源（默认: control-plane）")
    ap.add_argument("--correlation-id", default=None, help="关联 ID（可选）")
    ap.add_argument("--causation-id", default=None, help="因果 ID（可选）")
    ap.add_argument("--payload", default=None, help="JSON object 事件载荷（默认: {}）")
    ap.add_argument("--policy-snapshot", default=None, help="JSON object 策略快照（默认: {}）")
    ap.add_argument("--status", default="pending", help="事件状态（默认: pending）")
    ap.add_argument("--json", action="store_true", dest="json_output", help="以 JSON 格式输出")

    # ---- list ----
    lp = sub.add_parser("list", help="列出事件")
    lp.add_argument("--date", default=None, help="日期过滤，格式 YYYY-MM-DD（默认: 当天）")
    lp.add_argument("--event-type", default=None, help="按事件类型过滤")
    lp.add_argument("--correlation-id", default=None, help="按关联 ID 过滤")
    lp.add_argument("--limit", type=int, default=None, help="最大返回条数")
    lp.add_argument("--json", action="store_true", dest="json_output", help="以 JSON array 格式输出")

    # ---- replay ----
    rp = sub.add_parser("replay", help="事件回放（当前仅支持 dry-run）")
    rp.add_argument("--date", default=None, help="日期过滤，格式 YYYY-MM-DD（默认: 当天）")
    rp.add_argument("--dry-run", action="store_true", help="试运行模式（不实际执行 replay）")
    rp.add_argument("--json", action="store_true", dest="json_output", help="以 JSON 格式输出")

    args = parser.parse_args()

    if args.command == "append":
        cmd_append(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "replay":
        cmd_replay(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
