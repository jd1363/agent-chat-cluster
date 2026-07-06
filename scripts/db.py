#!/usr/bin/env python3
"""
db.py - SQLite data access layer for Agent Chat Cluster

Replaces tasks.json + JSONL logs with a single SQLite database.
Provides CRUD helpers + FTS5 full-text search.
Only dependency: Python standard library (sqlite3 bundled).
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "data" / "cluster.db"


# ---------------------------------------------------------------------------
# Connection helper
# ---------------------------------------------------------------------------

def get_conn() -> sqlite3.Connection:
    """Return a connection with row factory + WAL mode."""
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# TASKS
# ---------------------------------------------------------------------------

def create_task(title: str, priority: str = "medium", description: str = "") -> dict:
    """Insert a new task, return the task dict."""
    conn = get_conn()
    try:
        row = conn.execute("SELECT COUNT(*) + 1 AS n FROM tasks").fetchone()
        task_id = f"Task-{row['n']:03d}"
        now = utc_now()
        conn.execute(
            """INSERT INTO tasks (id, title, description, status, priority, assignee, output, notes, created_at, updated_at)
               VALUES (?, ?, ?, 'pending', ?, NULL, NULL, '', ?, ?)""",
            (task_id, title, description, priority, now, now),
        )
        # FTS index
        rowid = conn.execute("SELECT rowid FROM tasks WHERE id = ?", (task_id,)).fetchone()["rowid"]
        conn.execute(
            "INSERT INTO tasks_fts (rowid, title, description, notes) VALUES (?, ?, ?, '')",
            (rowid, title, description),
        )
        conn.commit()
        return get_task(task_id)
    finally:
        conn.close()


def get_task(task_id: str) -> dict | None:
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_tasks(status: str | None = None, assignee: str | None = None, limit: int = 200) -> list[dict]:
    conn = get_conn()
    try:
        sql = "SELECT * FROM tasks"
        params: list = []
        clauses: list[str] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if assignee:
            if assignee == "none":
                clauses.append("assignee IS NULL")
            else:
                clauses.append("assignee = ?")
                params.append(assignee)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_task(task_id: str, **fields) -> dict | None:
    """Update task fields. Allowed: status, priority, assignee, output, notes."""
    allowed = {"status", "priority", "assignee", "output", "notes"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return get_task(task_id)
    sets = ", ".join(f"{k} = ?" for k in updates)
    vals = list(updates.values()) + [utc_now(), task_id]
    conn = get_conn()
    try:
        conn.execute(f"UPDATE tasks SET {sets}, updated_at = ? WHERE id = ?", vals)
        # Refresh FTS if notes changed
        if "notes" in updates:
            t = get_task(task_id)
            if t:
                conn.execute(
                    "UPDATE tasks_fts SET title=?, description=?, notes=? WHERE rowid=(SELECT rowid FROM tasks WHERE id=?)",
                    (t["title"], t["description"], t["notes"] or "", task_id),
                )
        conn.commit()
        return get_task(task_id)
    finally:
        conn.close()


def get_task_stats() -> dict:
    conn = get_conn()
    try:
        rows = conn.execute("SELECT status, COUNT(*) AS n FROM tasks GROUP BY status").fetchall()
        return {r["status"]: r["n"] for r in rows}
    finally:
        conn.close()


def search_tasks(query: str, limit: int = 20) -> list[dict]:
    """FTS5 full-text search across title, description, notes."""
    conn = get_conn()
    try:
        sql = """SELECT t.* FROM tasks t
                 JOIN tasks_fts f ON t.rowid = f.rowid
                 WHERE tasks_fts MATCH ?
                 ORDER BY rank LIMIT ?"""
        rows = conn.execute(sql, (query, limit)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# AUDIT LOG
# ---------------------------------------------------------------------------

def append_audit(event_type: str, message: str, task_id: str | None = None,
                 data: dict | None = None, environment: str | None = None) -> None:
    env = environment or os.environ.get("AGENT_CHAT_ENV", "production")
    data_json = json.dumps(data, ensure_ascii=False) if data else None
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO audit_log (timestamp, event_type, task_id, message, environment, data_json)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (utc_now(), event_type, task_id, message, env, data_json),
        )
        conn.commit()
    finally:
        conn.close()


def list_audit(limit: int = 50, task_id: str | None = None, event_type: str | None = None) -> list[dict]:
    conn = get_conn()
    try:
        sql = "SELECT * FROM audit_log"
        params: list = []
        clauses: list[str] = []
        if task_id:
            clauses.append("task_id = ?")
            params.append(task_id)
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            if d.get("data_json"):
                d["data"] = json.loads(d.pop("data_json"))
            else:
                d.pop("data_json", None)
            result.append(d)
        return result
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# COST LOG
# ---------------------------------------------------------------------------

def record_cost(agent_id: str, task_id: str | None = None,
                input_tokens: int = 0, output_tokens: int = 0,
                estimated_cost: float = 0.0, currency: str = "USD",
                source: str = "manual", notes: str = "") -> None:
    total = input_tokens + output_tokens
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO cost_log (timestamp, agent_id, task_id, input_tokens, output_tokens, total_tokens, estimated_cost, currency, source, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (utc_now(), agent_id, task_id, input_tokens, output_tokens, total, estimated_cost, currency, source, notes),
        )
        conn.commit()
    finally:
        conn.close()


def get_cost_summary() -> dict:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS entries, COALESCE(SUM(estimated_cost),0) AS total_cost, COALESCE(SUM(total_tokens),0) AS total_tokens FROM cost_log"
        ).fetchone()
        by_agent_rows = conn.execute(
            "SELECT agent_id, COALESCE(SUM(estimated_cost),0) AS cost, COALESCE(SUM(total_tokens),0) AS tokens FROM cost_log GROUP BY agent_id"
        ).fetchall()
        recent = conn.execute("SELECT * FROM cost_log ORDER BY id DESC LIMIT 20").fetchall()
        return {
            "totalCost": round(row["total_cost"], 4),
            "totalTokens": row["total_tokens"],
            "entries": row["entries"],
            "byAgent": {r["agent_id"]: {"cost": r["cost"], "tokens": r["tokens"]} for r in by_agent_rows},
            "recent": [dict(r) for r in recent],
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# EVENT LOG
# ---------------------------------------------------------------------------

def append_event(event_type: str, source: str, correlation_id: str | None = None,
                 causation_id: str | None = None, payload: dict | None = None,
                 policy_snapshot: dict | None = None, status: str = "pending") -> str:
    conn = get_conn()
    try:
        row = conn.execute("SELECT COUNT(*) + 1 AS n FROM event_log").fetchone()
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        event_id = f"EVT-{date_str}-{row['n']:06d}"
        conn.execute(
            """INSERT INTO event_log (event_id, event_type, timestamp, source, correlation_id, causation_id, payload_json, policy_json, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (event_id, event_type, utc_now(), source, correlation_id, causation_id,
             json.dumps(payload, ensure_ascii=False) if payload else None,
             json.dumps(policy_snapshot, ensure_ascii=False) if policy_snapshot else None,
             status),
        )
        conn.commit()
        return event_id
    finally:
        conn.close()


def list_events(limit: int = 50) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM event_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            if d.get("payload_json"):
                d["payload"] = json.loads(d.pop("payload_json"))
            else:
                d.pop("payload_json", None)
            if d.get("policy_json"):
                d["policySnapshot"] = json.loads(d.pop("policy_json"))
            else:
                d.pop("policy_json", None)
            result.append(d)
        return result
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# MESSAGES
# ---------------------------------------------------------------------------

def send_message(from_user: str, to_user: str, content: str,
                 msg_type: str = "direct", recipient_count: int | None = None) -> dict:
    conn = get_conn()
    try:
        row = conn.execute("SELECT COUNT(*) + 1 AS n FROM messages").fetchone()
        msg_id = f"MSG-{row['n']:04d}"
        conn.execute(
            """INSERT INTO messages (id, from_user, to_user, content, timestamp, status, msg_type, recipient_count)
               VALUES (?, ?, ?, ?, ?, 'sent', ?, ?)""",
            (msg_id, from_user, to_user, content, utc_now(), msg_type, recipient_count),
        )
        conn.commit()
        return get_message(msg_id)
    finally:
        conn.close()


def get_message(msg_id: str) -> dict | None:
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM messages WHERE id = ?", (msg_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_messages(limit: int = 30, to_user: str | None = None) -> list[dict]:
    conn = get_conn()
    try:
        sql = "SELECT * FROM messages"
        params: list = []
        if to_user:
            sql += " WHERE to_user = ?"
            params.append(to_user)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def ack_message(msg_id: str) -> dict | None:
    conn = get_conn()
    try:
        conn.execute("UPDATE messages SET status = ?, read_at = ? WHERE id = ?",
                     ("acked", utc_now(), msg_id))
        conn.commit()
        return get_message(msg_id)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# META (key-value store for misc state)
# ---------------------------------------------------------------------------

def get_meta(key: str, default: str | None = None) -> str | None:
    conn = get_conn()
    try:
        row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default
    finally:
        conn.close()


def set_meta(key: str, value: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = ?",
            (key, value, value),
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CLI self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("[TEST] db.py self-test")
    print(f"  DB path: {DB_PATH}")
    print(f"  DB exists: {DB_PATH.exists()}")

    conn = get_conn()
    for table in ("tasks", "audit_log", "cost_log", "event_log", "messages"):
        n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {n} rows")
    conn.close()
    print("[OK] db.py self-test passed")
