#!/usr/bin/env python3
"""
send_message.py - Master sends a message to an enabled Agent.

Usage:
    python scripts/send_message.py --to agent-ext-01 --message "check config"
    python scripts/send_message.py --to all --message "maintenance notice"
    python scripts/send_message.py --to agent-ext-01 --message "task dispatched" --json

Uses only Python standard library modules.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
AGENTS_FILE = PROJECT_ROOT / "config" / "agents.json"
POLICIES_FILE = PROJECT_ROOT / "config" / "policies.json"
MESSAGES_DIR = PROJECT_ROOT / "logs" / "messages"
STATE_FILE = MESSAGES_DIR / ".state"
STATE_LOCK_FILE = MESSAGES_DIR / ".state.lock"
LOCK_RETRY_SECONDS = 0.05
LOCK_TIMEOUT_SECONDS = 5

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


def load_json_file(path: Path, label: str) -> dict:
    if not path.is_file():
        fail(f"File not found: {label}")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as e:
        fail(f"JSON parse error in {label}: {e}")
    except OSError as e:
        fail(f"Unable to read {label}: {e}")
    if not isinstance(data, dict):
        fail(f"{label}: root must be an object")
    return data


def load_agents() -> dict:
    data = load_json_file(AGENTS_FILE, "config/agents.json")
    agents = data.get("agents", [])
    if not isinstance(agents, list):
        fail("config/agents.json: agents is not a list")
    return {agent.get("id"): agent for agent in agents if agent.get("id")}


def load_policies() -> dict:
    return load_json_file(POLICIES_FILE, "config/policies.json")


def broadcast_allowed_by_policy() -> bool:
    policies = load_policies().get("policies", {})
    communication = policies.get("communication", {}) if isinstance(policies, dict) else {}
    global_broadcast = communication.get("globalBroadcast", {}) if isinstance(communication, dict) else {}
    if not isinstance(global_broadcast, dict):
        return False
    return bool(global_broadcast.get("allowed", False))


def validate_broadcast_approval(manual_approval: bool) -> None:
    if broadcast_allowed_by_policy():
        return
    if not manual_approval:
        fail("Broadcast is disabled by config/policies.json; rerun with --manual-approval after human approval")


def validate_recipient(agent_id: str) -> None:
    agents = load_agents()
    if agent_id not in agents:
        fail(f"Agent '{agent_id}' does not exist in config/agents.json")
    if not agents[agent_id].get("enabled", False):
        fail(f"Agent '{agent_id}' is disabled (enabled=false)")


def enabled_agent_ids() -> list[str]:
    agents = load_agents()
    return sorted(
        agent_id
        for agent_id, agent in agents.items()
        if agent.get("enabled", False)
    )


def acquire_state_lock() -> int:
    ensure_messages_dir()
    deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
    while True:
        try:
            return os.open(str(STATE_LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if time.monotonic() >= deadline:
                fail("Timed out waiting for message state lock")
            time.sleep(LOCK_RETRY_SECONDS)
        except OSError as e:
            fail(f"Unable to create message state lock: {e}")


def release_state_lock(fd: int) -> None:
    try:
        os.close(fd)
    finally:
        try:
            STATE_LOCK_FILE.unlink()
        except FileNotFoundError:
            pass
        except OSError as e:
            fail(f"Unable to remove message state lock: {e}")


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


def allocate_message_id() -> str:
    lock_fd = acquire_state_lock()
    try:
        next_number = load_next_msg_number()
        message_id = f"MSG-{next_number:04d}"
        save_next_msg_number(next_number + 1)
        return message_id
    finally:
        release_state_lock(lock_fd)


def send_message(to_agent: str, content: str) -> dict:
    validate_recipient(to_agent)

    message_id = allocate_message_id()

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


def send_broadcast(content: str, manual_approval: bool = False) -> dict:
    validate_broadcast_approval(manual_approval)
    recipients = enabled_agent_ids()
    if not recipients:
        fail("No enabled agents found in config/agents.json")

    parent_id = allocate_message_id()
    timestamp = datetime.now(timezone.utc).isoformat()
    parent_record = {
        "id": parent_id,
        "from": "master",
        "to": "all",
        "content": content,
        "timestamp": timestamp,
        "status": "sent",
        "type": "broadcast",
        "recipientCount": len(recipients),
    }
    append_message(parent_record)

    child_records = []
    for index, agent_id in enumerate(recipients, start=1):
        child = {
            "id": f"{parent_id}-{index:02d}",
            "parentId": parent_id,
            "from": "master",
            "to": agent_id,
            "content": content,
            "timestamp": timestamp,
            "status": "sent",
            "type": "broadcast_recipient",
        }
        append_message(child)
        child_records.append(child)

    append_audit(
        event_type="broadcast_sent",
        message=f"Broadcast {parent_id} sent to {len(recipients)} agents",
        data={"messageId": parent_id, "to": recipients, "recipientCount": len(recipients), "manualApproval": manual_approval},
    )
    return {"parent": parent_record, "children": child_records}


def main() -> None:
    parser = argparse.ArgumentParser(description="Send a message from master to an enabled Agent")
    parser.add_argument("--to", required=True, help="Recipient Agent ID, or 'all' for enabled agents")
    parser.add_argument("--message", required=True, help="Message content")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Output JSON")
    parser.add_argument(
        "--manual-approval",
        action="store_true",
        help="Confirm human approval for --to all when globalBroadcast is disabled by policy",
    )
    args = parser.parse_args()

    if args.to == "all":
        result = send_broadcast(args.message, manual_approval=args.manual_approval)
        if args.json_output:
            print(json.dumps({"ok": True, "broadcast": result}, ensure_ascii=False, indent=2))
        else:
            print(f"[OK] {result['parent']['id']} broadcast to {len(result['children'])} agents")
        return

    record = send_message(args.to, args.message)
    if args.json_output:
        print(json.dumps({"ok": True, "message": record}, ensure_ascii=False, indent=2))
    else:
        print(f"[OK] {record['id']} sent to {record['to']}")


if __name__ == "__main__":
    main()
