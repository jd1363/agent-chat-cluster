#!/usr/bin/env python3
"""
list_messages.py - Query message history.

Usage:
    python scripts/list_messages.py
    python scripts/list_messages.py --to agent-ext-01
    python scripts/list_messages.py --from master
    python scripts/list_messages.py --status sent
    python scripts/list_messages.py --since 2026-06-18 --json

Uses only Python standard library modules.
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MESSAGES_DIR = PROJECT_ROOT / "logs" / "messages"


def fail(message: str) -> None:
    print(f"[FAIL] {message}", file=sys.stderr)
    sys.exit(1)


def ensure_messages_dir() -> None:
    try:
        MESSAGES_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        fail(f"Unable to create messages directory: {e}")


def load_message_records() -> list[dict]:
    ensure_messages_dir()
    records: list[dict] = []
    for path in sorted(MESSAGES_DIR.glob("*.jsonl")):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError as e:
                        fail(f"JSON parse error in {path.name}: {e}")
                    if isinstance(record, dict):
                        records.append(record)
        except OSError as e:
            fail(f"Unable to read message log {path.name}: {e}")
    return records


def current_messages(records: list[dict]) -> list[dict]:
    by_id: dict[str, dict] = {}
    for record in records:
        message_id = record.get("id")
        if isinstance(message_id, str):
            by_id[message_id] = record
    return list(by_id.values())


def parse_since(value: str | None) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        fail(f"Invalid --since date '{value}', expected YYYY-MM-DD")


def message_date(record: dict) -> date | None:
    timestamp = record.get("timestamp")
    if not isinstance(timestamp, str) or len(timestamp) < 10:
        return None
    try:
        return date.fromisoformat(timestamp[:10])
    except ValueError:
        return None


def timestamp_key(record: dict) -> str:
    value = record.get("timestamp")
    return value if isinstance(value, str) else ""


def filter_messages(
    messages: list[dict],
    to_agent: str | None,
    from_sender: str | None,
    status: str | None,
    since: date | None,
) -> list[dict]:
    result: list[dict] = []
    for record in messages:
        if to_agent is not None and record.get("to") != to_agent:
            continue
        if from_sender is not None and record.get("from") != from_sender:
            continue
        if status is not None and record.get("status") != status:
            continue
        if since is not None:
            record_date = message_date(record)
            if record_date is None or record_date < since:
                continue
        result.append(record)
    result.sort(key=timestamp_key, reverse=True)
    return result


def format_table(messages: list[dict]) -> str:
    if not messages:
        return "[INFO] No messages"

    id_width = max(8, min(12, max(len(str(m.get("id", ""))) for m in messages)))
    from_width = max(4, min(16, max(len(str(m.get("from", ""))) for m in messages)))
    to_width = max(2, min(18, max(len(str(m.get("to", ""))) for m in messages)))
    status_width = max(6, min(10, max(len(str(m.get("status", ""))) for m in messages)))
    timestamp_width = 25
    content_width = 60

    header = (
        f"{'ID':<{id_width}}  {'FROM':<{from_width}}  {'TO':<{to_width}}  "
        f"{'STATUS':<{status_width}}  {'TIMESTAMP':<{timestamp_width}}  CONTENT"
    )
    lines = [header, "-" * len(header)]
    for record in messages:
        content = str(record.get("content", "")).replace("\n", " ")
        if len(content) > content_width:
            content = content[: content_width - 3] + "..."
        lines.append(
            f"{str(record.get('id', ''))[:id_width]:<{id_width}}  "
            f"{str(record.get('from', ''))[:from_width]:<{from_width}}  "
            f"{str(record.get('to', ''))[:to_width]:<{to_width}}  "
            f"{str(record.get('status', ''))[:status_width]:<{status_width}}  "
            f"{str(record.get('timestamp', ''))[:timestamp_width]:<{timestamp_width}}  "
            f"{content}"
        )
    lines.append(f"\nTotal: {len(messages)}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="List message history")
    parser.add_argument("--to", dest="to_agent", default=None, help="Filter by recipient Agent ID")
    parser.add_argument("--from", dest="from_sender", default=None, help="Filter by sender")
    parser.add_argument("--status", default=None, help="Filter by message status")
    parser.add_argument("--since", default=None, help="Filter by date lower bound (YYYY-MM-DD)")
    parser.add_argument("--limit", type=int, default=20, help="Maximum messages to return")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Output JSON")
    args = parser.parse_args()

    if args.limit < 1:
        fail("--limit must be a positive integer")

    since = parse_since(args.since)
    messages = current_messages(load_message_records())
    filtered = filter_messages(messages, args.to_agent, args.from_sender, args.status, since)
    limited = filtered[: args.limit]

    if args.json_output:
        output = {"ok": True, "count": len(limited), "totalMatched": len(filtered), "messages": limited}
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(format_table(limited))


if __name__ == "__main__":
    main()
