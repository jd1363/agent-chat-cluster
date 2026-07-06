#!/usr/bin/env python3
"""
migrate_to_sqlite.py - Migrate JSON/JSONL data to SQLite

Reads:
  - tasks/tasks.json        -> tasks table
  - logs/audit/*.jsonl      -> audit_log table
  - logs/cost/*.jsonl       -> cost_log table
  - logs/events/*.jsonl     -> event_log table
  - logs/messages/*.jsonl   -> messages table

Usage:
    python scripts/migrate_to_sqlite.py [--dry-run]
"""

import argparse
import glob
import json
import sys
from pathlib import Path

# Force UTF-8
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from db import get_conn, DB_PATH  # noqa: E402

TASKS_FILE = PROJECT_ROOT / "tasks" / "tasks.json"
AUDIT_DIR = PROJECT_ROOT / "logs" / "audit"
COST_DIR = PROJECT_ROOT / "logs" / "cost"
EVENTS_DIR = PROJECT_ROOT / "logs" / "events"
MESSAGES_DIR = PROJECT_ROOT / "logs" / "messages"


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def read_jsonl_dir(dirpath):
    """Read all .jsonl files in a directory, sorted by filename."""
    entries = []
    for fp in sorted(glob.glob(str(dirpath / "*.jsonl"))):
        with open(fp, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries


def migrate_tasks(conn):
    data = read_json(TASKS_FILE)
    tasks = data.get("tasks", [])
    count = 0
    for t in tasks:
        conn.execute(
            """INSERT OR IGNORE INTO tasks
               (id, title, description, status, priority, assignee, output, notes, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                t["id"],
                t.get("title", ""),
                t.get("description", ""),
                t.get("status", "pending"),
                t.get("priority", "medium"),
                t.get("assignee"),
                t.get("output"),
                t.get("notes", ""),
                t.get("createdAt", ""),
                t.get("updatedAt", ""),
            ),
        )
        # FTS
        rowid = conn.execute("SELECT rowid FROM tasks WHERE id = ?", (t["id"],)).fetchone()
        if rowid:
            conn.execute(
                "INSERT OR IGNORE INTO tasks_fts (rowid, title, description, notes) VALUES (?, ?, ?, ?)",
                (rowid["rowid"], t.get("title", ""), t.get("description", ""), t.get("notes", "") or ""),
            )
        count += 1
    return count


def migrate_audit(conn):
    entries = read_jsonl_dir(AUDIT_DIR)
    count = 0
    for e in entries:
        conn.execute(
            """INSERT INTO audit_log (timestamp, event_type, task_id, message, environment, data_json)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                e.get("timestamp", ""),
                e.get("eventType", "unknown"),
                e.get("taskId"),
                e.get("message", ""),
                e.get("environment", "production"),
                json.dumps(e.get("data"), ensure_ascii=False) if e.get("data") else None,
            ),
        )
        count += 1
    return count


def migrate_cost(conn):
    entries = read_jsonl_dir(COST_DIR)
    count = 0
    for e in entries:
        conn.execute(
            """INSERT INTO cost_log
               (timestamp, agent_id, task_id, input_tokens, output_tokens, total_tokens, estimated_cost, currency, source, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                e.get("timestamp", ""),
                e.get("agentId", "unknown"),
                e.get("taskId"),
                e.get("inputTokens", 0),
                e.get("outputTokens", 0),
                e.get("totalTokens", 0),
                e.get("estimatedCost", 0.0),
                e.get("currency", "USD"),
                e.get("source", "manual"),
                e.get("notes", ""),
            ),
        )
        count += 1
    return count


def migrate_events(conn):
    entries = read_jsonl_dir(EVENTS_DIR)
    count = 0
    for e in entries:
        conn.execute(
            """INSERT OR IGNORE INTO event_log
               (event_id, event_type, timestamp, source, correlation_id, causation_id, payload_json, policy_json, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                e.get("eventId", f"EVT-MIG-{count:06d}"),
                e.get("eventType", "unknown"),
                e.get("timestamp", ""),
                e.get("source"),
                e.get("correlationId"),
                e.get("causationId"),
                json.dumps(e.get("payload"), ensure_ascii=False) if e.get("payload") else None,
                json.dumps(e.get("policySnapshot"), ensure_ascii=False) if e.get("policySnapshot") else None,
                e.get("status", "pending"),
            ),
        )
        count += 1
    return count


def migrate_messages(conn):
    entries = read_jsonl_dir(MESSAGES_DIR)
    count = 0
    seen_ids = set()
    for e in entries:
        raw_id = e.get("id", f"MSG-MIG-{count:04d}")
        # Handle duplicate IDs (broadcast recipients share parent ID)
        msg_id = raw_id
        suffix = 1
        while msg_id in seen_ids:
            msg_id = f"{raw_id}-r{suffix}"
            suffix += 1
        seen_ids.add(msg_id)
        conn.execute(
            """INSERT OR IGNORE INTO messages
               (id, parent_id, from_user, to_user, content, timestamp, status, msg_type, recipient_count, read_at, expired_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                msg_id,
                e.get("parentId"),
                e.get("from", "master"),
                e.get("to", "all"),
                e.get("content", ""),
                e.get("timestamp", ""),
                e.get("status", "sent"),
                e.get("type"),
                e.get("recipientCount"),
                e.get("readAt"),
                e.get("expiredAt"),
            ),
        )
        count += 1
    return count


def main():
    parser = argparse.ArgumentParser(description="Migrate JSON/JSONL to SQLite")
    parser.add_argument("--dry-run", action="store_true", help="Show counts without writing")
    args = parser.parse_args()

    print(f"[INFO] DB path: {DB_PATH}")

    # Count source data
    tasks_data = read_json(TASKS_FILE)
    src_tasks = len(tasks_data.get("tasks", []))
    src_audit = len(read_jsonl_dir(AUDIT_DIR))
    src_cost = len(read_jsonl_dir(COST_DIR))
    src_events = len(read_jsonl_dir(EVENTS_DIR))
    src_messages = len(read_jsonl_dir(MESSAGES_DIR))

    print(f"[INFO] Source counts:")
    print(f"  tasks:    {src_tasks}")
    print(f"  audit:    {src_audit}")
    print(f"  cost:     {src_cost}")
    print(f"  events:   {src_events}")
    print(f"  messages: {src_messages}")

    if args.dry_run:
        print("[INFO] Dry run, not writing.")
        return

    conn = get_conn()
    try:
        # Clear existing (in case of re-run)
        for table in ("tasks_fts", "tasks", "audit_log", "cost_log", "event_log", "messages", "meta"):
            conn.execute(f"DELETE FROM {table}")

        n_tasks = migrate_tasks(conn)
        n_audit = migrate_audit(conn)
        n_cost = migrate_cost(conn)
        n_events = migrate_events(conn)
        n_messages = migrate_messages(conn)

        conn.commit()

        print(f"[OK] Migrated:")
        print(f"  tasks:    {n_tasks}")
        print(f"  audit:    {n_audit}")
        print(f"  cost:     {n_cost}")
        print(f"  events:   {n_events}")
        print(f"  messages: {n_messages}")

        # Verify
        print("[VERIFY] Row counts in SQLite:")
        for table in ("tasks", "audit_log", "cost_log", "event_log", "messages"):
            n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"  {table}: {n}")

    finally:
        conn.close()

    print("[OK] Migration complete.")


if __name__ == "__main__":
    main()
