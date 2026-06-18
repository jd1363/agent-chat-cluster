#!/usr/bin/env python3
"""
send_message.py - Master sends a message to an enabled Agent.

Usage:
    python scripts/send_message.py --to agent-ext-01 --message "check config"
    python scripts/send_message.py --to agent-ext-01 --message "task dispatched" --json

Uses only Python standard library modules.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
AGENTS_FILE = PROJECT_ROOT / "config" / "agents.json"
MESSAGES_DIR = PROJECT_ROOT / "logs" / "messages"
STATE_FILE = MESSAGES_DIR / ".state"

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from audit_log import append_audit  # type: ignore


def fail(message: str) -> None:
    print(f"[FAIL] {message}", file=sys.stderr)
    sys.exit(1)


def ensure_messages_dir() -> None:
    try:
        MESSAGES_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        fail(f"Unable to create messages directory: {e}")


def today_log_path() -> Path:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return MESSAGES_DIR / f"{today}.jsonl"


def load_agents() -> dict:
    if not AGENTS_FILE.is_file():
        fail(f"File not found: {AGENTS_FILE}")
    try:
        with open(AGENTS_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as e:
        fail(f"JSON parse error in agents.json: {e}")
    except OSError as e:
        fail(f"Unable to read agents.json: {e}")

    agents = data.get("agents", [])
    if not isinstance(agents, list):
        fail("config/agents.json: agents is not a list")
    return {agent.get("id"): agent for agent in agents if agent.get("id")}


def validate_recipient(agent_id: str) -> None:
    agents = load_agents()
    if agent_id not in agents:
        fail(f"Agent '{agent_id}' does not exist in config/agents.json")
    if not agents[agent_id].get("enabled", False):
        fail(f"Agent '{agent_id}' is disabled (enabled=false)")


def load_next_msg_number() -> int:
    ensure_messages_dir()
    if not STATE_FILE.is_file():
        return 1
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as e:
        fail(f"JSON parse error in message state: {e}")
    except OSError as e:
        fail(f"Unable to read message state: {e}")

    value = data.get("nextMsgId")
    if not isinstance(value, int) or value < 1:
        fail("Message state nextMsgId must be a positive integer")
    return value


def save_next_msg_number(next_msg_number: int) -> None:
    ensure_messages_dir()
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as fh:
            json.dump({"nextMsgId": next_msg_number}, fh, ensure_ascii=False, indent=2)
    except OSError as e:
        fail(f"Unable to write message state: {e}")


def append_message(record: dict) -> None:
    ensure_messages_dir()
    try:
        with open(today_log_path(), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as e:
        fail(f"Unable to write message log: {e}")


def send_message(to_agent: str, content: str) -> dict:
    validate_recipient(to_agent)

    next_number = load_next_msg_number()
    message_id = f"MSG-{next_number:04d}"
    save_next_msg_number(next_number + 1)

    record = {
        "id": message_id,
        "from": "master",
        "to": to_agent,
        "content": content,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "sent",
    }
    append_message(record)

    append_audit(
        event_type="message_sent",
        message=f"Message {message_id} sent to {to_agent}",
        data={"messageId": message_id, "to": to_agent},
    )
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description="Send a message from master to an enabled Agent")
    parser.add_argument("--to", required=True, help="Recipient Agent ID")
    parser.add_argument("--message", required=True, help="Message content")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Output JSON")
    args = parser.parse_args()

    record = send_message(args.to, args.message)
    if args.json_output:
        print(json.dumps({"ok": True, "message": record}, ensure_ascii=False, indent=2))
    else:
        print(f"[OK] {record['id']} sent to {record['to']}")


if __name__ == "__main__":
    main()
