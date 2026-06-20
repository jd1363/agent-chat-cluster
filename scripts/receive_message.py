#!/usr/bin/env python3
"""
receive_message.py - Agent receives its latest unread message.

Usage:
    python scripts/receive_message.py --agent-id agent-ext-01
    python scripts/receive_message.py --agent-id agent-ext-01 --mark-read
    python scripts/receive_message.py --agent-id agent-ext-01 --ack
    python scripts/receive_message.py --agent-id agent-ext-01 --json

Uses only Python standard library modules.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MESSAGES_DIR = PROJECT_ROOT / "logs" / "messages"
MAX_MESSAGE_LOG_BYTES = 5 * 1024 * 1024


def fail(message: str) -> None:
    print(f"[FAIL] {message}", file=sys.stderr)
    sys.exit(1)


def safe_os_error(error: OSError) -> str:
    return error.strerror or error.__class__.__name__


def ensure_messages_dir() -> None:
    try:
        MESSAGES_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        fail(f"Unable to create messages directory: {safe_os_error(e)}")


def load_message_records() -> List[Dict]:
    ensure_messages_dir()
    records: List[Dict] = []
    for path in sorted(MESSAGES_DIR.glob("*.jsonl")):
        try:
            if path.stat().st_size > MAX_MESSAGE_LOG_BYTES:
                fail(f"Message log {path.name} exceeds {MAX_MESSAGE_LOG_BYTES // 1024} KB limit")
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
            fail(f"Unable to read message log {path.name}: {safe_os_error(e)}")
    return records


def current_messages(records: List[Dict]) -> List[Dict]:
    by_id: Dict[str, Dict] = {}
    for record in records:
        message_id = record.get("id")
        if isinstance(message_id, str):
            by_id[message_id] = record
    return list(by_id.values())


def timestamp_key(record: Dict) -> str:
    value = record.get("timestamp")
    return value if isinstance(value, str) else ""


def append_message(record: Dict) -> None:
    ensure_messages_dir()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = MESSAGES_DIR / f"{today}.jsonl"
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as e:
        fail(f"Unable to write message log: {safe_os_error(e)}")


def append_ack(record: Dict, agent_id: str) -> Dict:
    message_id = record.get("id")
    if not isinstance(message_id, str) or not message_id:
        fail("Cannot ACK a message without a valid id")

    ack = {
        "id": f"{message_id}-ACK-{agent_id}",
        "from": "system",
        "to": "master",
        "content": f"ACK: {message_id} received by {agent_id}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "sent",
        "type": "system",
        "ackFor": message_id,
    }
    append_message(ack)
    return ack


def latest_unread_for(agent_id: str) -> Optional[Dict]:
    messages = [
        record
        for record in current_messages(load_message_records())
        if record.get("to") == agent_id and record.get("status") != "read"
    ]
    messages.sort(key=timestamp_key, reverse=True)
    return messages[0] if messages else None


def mark_read(record: Dict) -> Dict:
    updated = dict(record)
    updated["status"] = "read"
    updated["readAt"] = datetime.now(timezone.utc).isoformat()
    append_message(updated)
    return updated


def format_message(record: Dict) -> str:
    return (
        f"ID: {record.get('id', '')}\n"
        f"From: {record.get('from', '')}\n"
        f"To: {record.get('to', '')}\n"
        f"Timestamp: {record.get('timestamp', '')}\n"
        f"Status: {record.get('status', '')}\n"
        f"Content: {record.get('content', '')}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Receive the latest unread message for an Agent")
    parser.add_argument("--agent-id", required=True, help="Receiving Agent ID")
    parser.add_argument("--mark-read", action="store_true", help="Append an updated read-status record")
    parser.add_argument("--ack", action="store_true", help="Append a system ACK message to master")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Output JSON")
    args = parser.parse_args()

    record = latest_unread_for(args.agent_id)
    if record is None:
        if args.json_output:
            print(json.dumps({"ok": True, "message": None}, ensure_ascii=False, indent=2))
        else:
            print("[INFO] No new messages")
        return

    output_record = mark_read(record) if args.mark_read else record
    ack_record = append_ack(record, args.agent_id) if args.ack else None
    if args.json_output:
        print(json.dumps({"ok": True, "message": output_record, "ack": ack_record}, ensure_ascii=False, indent=2))
    else:
        print(format_message(output_record))
        if ack_record is not None:
            print(f"\n[OK] ACK sent to master for {record.get('id', '')}")


if __name__ == "__main__":
    main()

