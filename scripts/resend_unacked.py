#!/usr/bin/env python3
"""
resend_unacked.py - Retry or fail sent messages that were not marked read.

Usage:
    python scripts/resend_unacked.py
    python scripts/resend_unacked.py --timeout-minutes 5
    python scripts/resend_unacked.py --timeout-minutes 0 --json
    python scripts/resend_unacked.py --dry-run
    python scripts/resend_unacked.py --timeout-minutes 10 --dry-run --json

Uses only Python standard library modules.
"""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MESSAGES_DIR = PROJECT_ROOT / "logs" / "messages"
MAX_RETRIES = 3

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


def parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


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


def append_message(record: dict) -> None:
    ensure_messages_dir()
    try:
        with open(today_log_path(), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as e:
        fail(f"Unable to write message log: {e}")


def is_retry_candidate(record: dict) -> bool:
    if record.get("status") != "sent":
        return False
    if record.get("from") != "master":
        return False
    if record.get("to") == "all":
        return False
    if record.get("type") == "system":
        return False
    return isinstance(record.get("id"), str)


def acked_message_ids(records: list[dict]) -> set[str]:
    acked: set[str] = set()
    for record in records:
        if record.get("from") != "system" or record.get("to") != "master":
            continue
        ack_for = record.get("ackFor")
        if isinstance(ack_for, str) and ack_for:
            acked.add(ack_for)
    return acked


def retry_or_fail(record: dict, now: datetime, dry_run: bool = False) -> dict | None:
    """Process one candidate record: retry (append a new sent) or mark failed.

    When dry_run=True, only compute the planned action and return a planning dict;
    no filesystem writes or audit entries are performed.
    """
    message_id = str(record["id"])
    retry_count = record.get("retryCount", 0)
    if not isinstance(retry_count, int) or retry_count < 0:
        retry_count = 0

    updated = dict(record)
    updated["timestamp"] = now.isoformat()

    if retry_count >= MAX_RETRIES:
        updated["status"] = "failed"
        updated["failedAt"] = now.isoformat()
        updated["failureReason"] = "ACK timeout retry limit exceeded"
        action = "fail"
        if not dry_run:
            append_message(updated)
            append_audit(
                event_type="message_failed",
                message=f"Message {message_id} failed after {MAX_RETRIES} retries",
                data={"messageId": message_id, "to": record.get("to"), "retryCount": retry_count},
            )
    else:
        updated["status"] = "sent"
        updated["retryCount"] = retry_count + 1
        updated["resentAt"] = now.isoformat()
        action = "resent"
        if not dry_run:
            append_message(updated)
            append_audit(
                event_type="message_resent",
                message=f"Message {message_id} resent to {record.get('to')}",
                data={"messageId": message_id, "to": record.get("to"), "retryCount": retry_count + 1},
            )

    if dry_run:
        return {
            "messageId": message_id,
            "to": record.get("to"),
            "action": action,
            "retryCount": retry_count,
            "plannedRecord": updated,
        }
    return updated


def resend_unacked(timeout_minutes: int, dry_run: bool = False) -> list[dict]:
    if timeout_minutes < 0:
        fail("--timeout-minutes must be zero or greater")

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=timeout_minutes)
    updated_records: list[dict] = []
    records = load_message_records()
    acked_ids = acked_message_ids(records)
    for record in current_messages(records):
        if not is_retry_candidate(record):
            continue
        if record.get("id") in acked_ids:
            continue
        timestamp = parse_timestamp(record.get("timestamp"))
        if timestamp is None or timestamp > cutoff:
            continue
        result = retry_or_fail(record, now, dry_run=dry_run)
        if result is not None:
            updated_records.append(result)
    return updated_records


def main() -> None:
    parser = argparse.ArgumentParser(description="Retry or fail unacknowledged sent messages")
    parser.add_argument("--timeout-minutes", type=int, default=5, help="Sent-message age before retry (default: 5)")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Output JSON")
    parser.add_argument("--dry-run", action="store_true", dest="dry_run", help="Report planned actions without executing them")
    args = parser.parse_args()

    updated = resend_unacked(args.timeout_minutes, dry_run=args.dry_run)

    if args.dry_run:
        if args.json_output:
            print(json.dumps({"ok": True, "dry_run": True, "count": len(updated), "messages": updated}, ensure_ascii=False, indent=2))
        else:
            for item in updated:
                mid = item.get("messageId", item.get("id"))
                to = item.get("to", "?")
                action = item.get("action", "?")
                retry = item.get("retryCount", 0)
                if action == "fail":
                    print(f"[DRY-RUN] Would mark {mid} to {to} as failed (retries exhausted: {retry}/{MAX_RETRIES})")
                else:
                    print(f"[DRY-RUN] Would resend {mid} to {to} (retry {retry + 1}/{MAX_RETRIES})")
            if not updated:
                print("[DRY-RUN] No unacked messages to process")
            else:
                print(f"[DRY-RUN] {len(updated)} message(s) would be processed")
    else:
        if args.json_output:
            print(json.dumps({"ok": True, "count": len(updated), "messages": updated}, ensure_ascii=False, indent=2))
        else:
            print(f"[OK] Processed {len(updated)} unacked messages")


if __name__ == "__main__":
    main()
